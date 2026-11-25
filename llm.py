"""llm.py — 13주차 공통 LLM 래퍼 (openai | ollama | mock)

같은 코드가 환경에 따라 provider를 자동으로 고릅니다.
  - 로컬 노트북 : secrets.toml 또는 환경변수 PROVIDER=ollama  → 로컬 Ollama
  - 클라우드    : Cloud Secrets 에 PROVIDER=openai + OPENAI_API_KEY → OpenAI
  - 아무 설정 없음: mock (규칙 기반 고정 응답) → 키가 없어도 배포는 반드시 성공

결정 순서: st.secrets["PROVIDER"] → os.getenv("PROVIDER") → "mock"
ollama가 지정됐는데 연결이 안 되면: 경고 후 openai(키가 있을 때) → mock 순서로 자동 대체
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Iterator

import requests

try:  # streamlit 없이(pytest 등)도 import 가능하게
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None

VALID_PROVIDERS = ("openai", "ollama", "mock")
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
# localhost 대신 127.0.0.1: Windows 에서는 localhost 가 IPv6(::1)를 먼저 시도해 요청마다 약 2초가 더 걸린다
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:1.5b"
# 사이드바 배지용 이름: (표시 이름, 배지 색)
PROVIDER_LABELS = {"ollama": ("로컬 Ollama", "green"), "openai": ("OpenAI", "blue"),
                   "mock": ("데모 mock", "orange")}
MOCK_DELAY = 0.03          # mock 스트리밍 조각(단어) 간격(초)
_OLLAMA_CACHE: dict = {}    # {url: (확인시각, 연결여부)} — 30초 동안 재사용
_NOTICE = {"text": "", "used": ""}  # 마지막 자동 대체 경고(화면 표시용), 실제로 답한 provider
OLLAMA_NUM_PREDICT = 400    # 답변 토큰 상한: 작은 모델이 같은 말을 끝없이 반복해도 멈추게(openai 도 같은 상한)


# ── 설정 읽기 ────────────────────────────────────────────────
def get_setting(name: str, default: str | None = None) -> str | None:
    """st.secrets → 환경변수 → default 순서로 설정값을 읽는다(값은 화면에 출력하지 말 것)."""
    if st is not None:
        try:
            if name in st.secrets:
                return str(st.secrets[name])
        except Exception:
            pass  # secrets.toml 이 아예 없으면 예외 → 환경변수로 넘어감
    value = os.getenv(name)
    return value if value not in (None, "") else default


def get_requested_provider() -> str:
    """사용자가 '요청한' provider. 잘못된 값이면 mock."""
    value = (get_setting("PROVIDER", "mock") or "mock").strip().lower()
    return value if value in VALID_PROVIDERS else "mock"


def ollama_base_url() -> str:
    """Ollama 서버 주소(끝의 /, /api/chat 은 떼어 냄).

    OLLAMA_URL → OLLAMA_HOST(12주차 방식, http 로 시작할 때만) → 기본값 순서.
    10주차처럼 'http://…/api/chat' 까지 적어 넣어도 동작하게 한다.
    """
    host = get_setting("OLLAMA_HOST", "") or ""
    url = get_setting("OLLAMA_URL") or (host if host.startswith("http") else DEFAULT_OLLAMA_URL)
    url = url.strip().rstrip("/")
    return url[: -len("/api/chat")] if url.endswith("/api/chat") else url


def ollama_available(timeout: float = 1.5) -> bool:
    """로컬 Ollama 서버가 응답하는지 확인(결과 30초 캐시)."""
    url = ollama_base_url()
    cached = _OLLAMA_CACHE.get(url)
    if cached and time.time() - cached[0] < 30:
        return cached[1]
    try:
        ok = requests.get(f"{url}/api/tags", timeout=timeout).status_code == 200
    except requests.RequestException:
        ok = False
    _OLLAMA_CACHE[url] = (time.time(), ok)
    return ok


def get_provider() -> str:
    """실제로 사용할 provider를 돌려준다(자동 대체 포함)."""
    requested = get_requested_provider()
    has_key = bool(get_setting("OPENAI_API_KEY"))
    _NOTICE["text"] = ""
    if requested == "ollama" and not ollama_available():
        fallback = "openai" if has_key else "mock"
        _NOTICE["text"] = f"Ollama 연결 실패 → {fallback}(으)로 자동 전환"
        return fallback
    if requested == "openai" and not has_key:
        _NOTICE["text"] = "OPENAI_API_KEY 없음 → mock(데모) 모드"
        return "mock"
    return requested


def get_provider_notice() -> str:
    """가장 최근 get_provider()/chat()에서 생긴 자동 대체 경고(없으면 빈 문자열)."""
    return _NOTICE["text"]


def get_last_used_provider() -> str:
    """가장 최근 chat() 에서 '실제로' 답한 provider(호출 실패로 mock 대체됐으면 mock)."""
    return _NOTICE["used"]


# ── mock: 규칙 기반 고정 응답 ─────────────────────────────────
_MOCK_RULES = [  # 위에서부터 먼저 걸린 규칙 하나만 사용
    (("넘어", "부딪", "빠졌", "부러", "깨졌"), "다쳐서 이가 빠지거나 부러졌다면 시간이 중요합니다. "
                                         "가능한 한 빨리 치과(야간·휴일에는 응급실)로 가세요."),
    (("사랑니",), "사랑니 주변 잇몸이 붓고 아픈 것은 사랑니 주위 염증에서 흔합니다. 입안을 깨끗이 헹구고 "
                 "치과 진료를 받아 보세요. 얼굴이 붓고 열이 나면 빨리 진료를 받으세요."),
    (("시린", "시려", "찬물", "찬 것"), "찬 것에 이가 시린 것은 잇몸이 내려가거나 치아 표면이 닳았을 때 흔합니다. "
                                    "너무 세게 닦지 말고, 계속되면 치과에서 원인을 확인하세요."),
    (("구내염", "입병", "헐었", "헐어"), "입안이 헐어 생기는 구내염은 보통 1~2주 안에 저절로 낫는 경우가 많습니다. "
                                    "자극적인 음식을 피하고, 2주 넘게 낫지 않으면 진료를 받아 보세요."),
    (("잇몸", "피가", "출혈"), "양치할 때 잇몸에서 피가 나는 것은 치태(플라크)로 생긴 잇몸 염증에서 흔합니다. "
                            "부드러운 칫솔로 꼼꼼히 닦고, 계속되면 치과 진료를 받아 보세요."),
    (("치통", "이가 아", "욱신", "충치"), "치통의 흔한 원인 중 하나는 깊어진 충치입니다. 진통제로 잠시 가라앉아도 "
                                      "원인은 남으므로 치과 진료를 받아 보세요."),
]
_RED_FLAGS = ("숨쉬기", "숨이 차", "호흡", "삼키기", "삼킴", "가슴", "흉통", "의식", "마비")


def _last_user_text(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def mock_answer(messages: list[dict]) -> str:
    """마지막 사용자 메시지의 키워드로 정해진 문장을 고른다."""
    text = _last_user_text(messages)
    if any(w in text for w in _RED_FLAGS):
        body = "숨쉬기·삼키기 곤란, 가슴 통증, 의식 변화는 응급 신호일 수 있습니다. 즉시 119 또는 응급실에 연락하세요."
    else:
        body = next((ans for keys, ans in _MOCK_RULES if any(k in text for k in keys)),
                    "증상을 조금 더 구체적으로(어느 이·잇몸인지, 언제부터, 찬 것이나 씹을 때 아픈지) 적어 주시면 "
                    "쉬운 말로 설명해 드릴게요.")
    return f"[데모 mock 응답] {body} 이 내용은 일반 정보이며 진단이 아닙니다."


def _mock(messages, stream, temperature, json_mode):
    text = mock_answer(messages)
    if json_mode:
        text = json.dumps({"answer": text}, ensure_ascii=False)
    if not stream:
        return text

    def gen() -> Iterator[str]:
        # 단어(공백 포함) 단위로 → 스트리밍 흉내. 한 글자씩 보내면 화면 갱신이 많아 수 초 걸린다
        for piece in re.findall(r"\S+\s*", text):
            time.sleep(MOCK_DELAY)
            yield piece
    return gen()


# ── openai ──────────────────────────────────────────────────
def _openai(messages, stream, temperature, json_mode):
    from openai import OpenAI  # 필요할 때만 import(메모리 절약)

    # OPENAI_BASE_URL(선택): 학교 프록시나 Ollama(http://127.0.0.1:11434/v1) 같은 OpenAI 호환 서버
    base_url = get_setting("OPENAI_BASE_URL")
    # 재시도 1번: 서버가 멈춰도 약 1분 안에 mock 으로 넘어감(SDK 기본은 재시도 2번 → 1분 30초)
    client = OpenAI(api_key=get_setting("OPENAI_API_KEY"), base_url=base_url, timeout=30, max_retries=1)
    kwargs = {"model": get_setting("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
              "messages": messages, "temperature": temperature, "stream": stream,
              # 출력 토큰 상한 = 공개 URL 비용 관리. OpenAI 최신 모델은 max_completion_tokens, 호환 서버는 max_tokens
              ("max_tokens" if base_url else "max_completion_tokens"): OLLAMA_NUM_PREDICT}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    if not stream:
        return resp.choices[0].message.content or ""

    def gen() -> Iterator[str]:
        for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    return gen()


# ── ollama (requests 로 직접 호출) ───────────────────────────
def _ollama(messages, stream, temperature, json_mode):
    url = ollama_base_url() + "/api/chat"
    payload = {"model": get_setting("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL), "messages": messages,
               "stream": stream, "options": {"temperature": temperature, "num_ctx": 2048,
                           "num_predict": OLLAMA_NUM_PREDICT}}
    if json_mode:
        payload["format"] = "json"
    resp = requests.post(url, json=payload, stream=stream, timeout=120)
    resp.raise_for_status()
    if not stream:
        return resp.json().get("message", {}).get("content", "")

    def gen() -> Iterator[str]:
        for line in resp.iter_lines():
            if line:
                data = json.loads(line)
                yield data.get("message", {}).get("content", "")
                if data.get("done"):
                    break
    return gen()


_BACKENDS = {"openai": _openai, "ollama": _ollama, "mock": _mock}


def _safe_stream(gen: Iterator[str], messages: list[dict]) -> Iterator[str]:
    """스트리밍 도중 오류가 나면 mock 문장으로 이어 붙인다(앱이 죽지 않게)."""
    try:
        yield from gen
    except Exception as e:  # 네트워크 끊김 등
        _NOTICE["text"] = f"응답 도중 오류({type(e).__name__}) → mock 응답으로 대체했습니다."
        _NOTICE["used"] = "mock"
        yield "\n\n" + mock_answer(messages)


def chat(messages: list[dict], stream: bool = True, temperature: float = 0.2,
         json_mode: bool = False) -> str | Iterator[str]:
    """공통 인터페이스. stream=True 면 글자 조각을 yield 하는 iterator, 아니면 str."""
    provider = get_provider()
    _NOTICE["used"] = provider
    try:
        out = _BACKENDS[provider](messages, stream, temperature, json_mode)
    except Exception as e:  # 키 오류·네트워크 오류 → 앱은 계속 동작
        # 오류 메시지 원문에는 민감정보가 섞일 수 있어 예외 '종류'만 남긴다
        _NOTICE["text"] = f"{provider} 호출 실패({type(e).__name__}) → mock 응답으로 대체했습니다."
        _NOTICE["used"] = "mock"
        return _mock(messages, stream, temperature, json_mode)
    if stream and provider != "mock":
        return _safe_stream(out, messages)
    return out
