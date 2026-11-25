"""guard.py — 공개 URL에서 API 키 남용을 막는 최소 안전장치

  require_password()      : secrets 에 APP_PASSWORD 가 있으면 비밀번호 입력을 요구
  rate_limit(max_calls)   : 세션당 호출 수 제한(초과하면 False)
  count_call()            : LLM 을 1회 호출할 때마다 카운트 증가
  safe_log(event, **meta) : 입력 원문 없이 '사건 종류 + 숫자 정보'만 로그에 남김
  emergency_notice(text)  : 구강 증상 입력에 응급·위험 신호 표현이 있으면 안내 문장을 돌려줌
"""
from __future__ import annotations

import hmac
import json
import logging
import time

import streamlit as st

from llm import get_setting

DEFAULT_MAX_CALLS = 20
_AUTH_KEY = "_guard_auth_ok"
_COUNT_KEY = "_guard_calls"
_MAX_KEY = "_guard_max_calls"
# 로그에 남겨도 되는 키(화이트리스트). 여기에 없는 키는 버린다.
_LOG_ALLOWED = {"provider", "latency_ms", "n_chars", "ok", "page", "remaining", "error_type", "red_flag"}

logger = logging.getLogger("dentai.week13")
if not logger.handlers:  # Cloud 에서는 표준출력 로그가 'Manage app' 로그 창에 보인다
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


def _state(state):
    """테스트에서는 dict 를, 앱에서는 st.session_state 를 쓴다."""
    return st.session_state if state is None else state


def require_password(state=None) -> None:
    """APP_PASSWORD 가 설정돼 있을 때만 비밀번호 화면을 띄우고, 통과 전에는 st.stop()."""
    password = get_setting("APP_PASSWORD")
    s = _state(state)
    if not password or s.get(_AUTH_KEY):
        return  # 비밀번호 미설정(로컬 실습) 또는 이미 통과
    st.markdown("### 접속 비밀번호")
    st.caption("수업용 공개 앱입니다. 강사/조원에게 받은 비밀번호를 입력하세요.")
    typed = st.text_input("비밀번호", type="password")
    if typed:
        # 길이에 따라 비교 시간이 달라지지 않도록 hmac.compare_digest 사용
        if hmac.compare_digest(typed.encode(), password.encode()):
            s[_AUTH_KEY] = True
            safe_log("login", ok=True)
            st.rerun()
        st.error("비밀번호가 맞지 않습니다.")
        safe_log("login", ok=False)
    st.stop()


def get_max_calls() -> int:
    """secrets 의 MAX_CALLS_PER_SESSION(없으면 20)."""
    try:
        return max(0, int(get_setting("MAX_CALLS_PER_SESSION", DEFAULT_MAX_CALLS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_CALLS


def rate_limit(max_calls: int = 20, state=None) -> bool:
    """세션당 호출 수 제한. 아직 호출 가능하면 True, 한도를 넘었으면 False."""
    s = _state(state)
    s.setdefault(_COUNT_KEY, 0)
    s[_MAX_KEY] = max_calls
    return s[_COUNT_KEY] < max_calls


def count_call(state=None) -> int:
    """LLM 호출 1회를 기록하고 누적 횟수를 돌려준다."""
    s = _state(state)
    s[_COUNT_KEY] = s.get(_COUNT_KEY, 0) + 1
    return s[_COUNT_KEY]


def remaining_calls(state=None) -> int:
    """남은 호출 수(사이드바 표시용)."""
    s = _state(state)
    return max(0, s.get(_MAX_KEY, DEFAULT_MAX_CALLS) - s.get(_COUNT_KEY, 0))


DISCLAIMER = ("교육용 — 진료 판단에 사용 금지. 합성 예시로 만든 수업용 앱이며, "
              "실제 환자 진료·진단·처방에 쓰지 마세요. 입력 내용은 저장하지 않습니다.")
PUBLIC_WARNING = "실제 개인정보·환자정보를 입력하지 마세요(공개 웹)"


# ── 응급·위험 신호 규칙(키워드 기반, 교육용) ──────────────────
# 각 규칙: (이름, 단어 묶음 목록, 안내 문장). 묶음마다 단어가 '하나 이상' 들어 있으면 해당.
# 키워드 규칙은 놓치는 표현도, 과하게 걸리는 표현도 있다 → '안내'만 하고 판단은 하지 않는다.
_ER = "즉시 119에 연락하거나 응급실로 가세요."
EMERGENCY_RULES = [
    ("호흡·삼킴 곤란", [("숨쉬기", "숨이 차", "숨을 못", "호흡", "삼키기", "삼키지", "삼킴", "침을 못")],
     "숨쉬기나 삼키기가 힘든 것은 응급 신호일 수 있습니다. " + _ER),
    ("얼굴·목 부기와 열", [("붓", "부었", "부어", "부기"), ("열", "목", "눈 밑", "턱 밑", "턱 아래")],
     "얼굴·목이 붓고 열이 나면 감염이 퍼지는 신호일 수 있습니다. 숨쉬기·삼키기가 힘들면 "
     + _ER + " 그렇지 않아도 오늘 바로 치과나 응급실 진료를 받으세요."),
    ("가슴 통증·의식 변화", [("가슴", "흉통", "의식", "마비", "쓰러")],
     "가슴 통증(턱으로 퍼지는 통증 포함)·의식 변화·마비는 치과 문제가 아닐 수 있는 응급 신호입니다. " + _ER),
    ("치아 외상", [("넘어", "부딪", "맞아서", "맞았", "사고", "다쳐", "다쳤", "외상")],
     "외상으로 이가 빠지거나 부러졌다면 가능한 한 빨리 치과(야간·휴일에는 응급실)로 가세요. "
     "빠진 이는 뿌리를 만지지 말고 우유나 생리식염수에 담가 가져가세요."),
    ("이가 빠지거나 부러짐", [("이가", "치아가", "앞니가", "이빨이"), ("빠졌", "부러", "깨졌")],
     "외상으로 이가 빠지거나 부러졌다면 가능한 한 빨리 치과(야간·휴일에는 응급실)로 가세요. "
     "빠진 이는 뿌리를 만지지 말고 우유나 생리식염수에 담가 가져가세요."),
    ("멈추지 않는 출혈", [("피가", "피를", "피는", "출혈"), ("안 멈", "멈추지", "멈추질", "안 그쳐", "지혈이 안", "지혈 안")],
     "깨끗한 거즈를 꽉 물어 눌러도 피가 멈추지 않으면 바로 치과나 응급실에 연락하세요."),
]


def emergency_notice(text: str) -> str:
    """입력에 응급·위험 신호 표현이 있으면 첫 번째로 걸린 규칙의 안내 문장, 없으면 ""."""
    for _name, groups, message in EMERGENCY_RULES:
        if all(any(w in text for w in group) for group in groups):
            return message
    return ""


def show_disclaimer() -> None:
    """페이지 하단 고지 문구."""
    st.divider()
    st.caption(DISCLAIMER)


def safe_log(event: str, **meta) -> dict:
    """입력 원문은 절대 남기지 않는다. 허용된 키 + 숫자/불리언/짧은 단어만 기록."""
    record = {"ts": int(time.time()), "event": str(event)[:40]}
    for key, value in meta.items():
        if key not in _LOG_ALLOWED:
            continue  # 예: prompt=..., answer=... 는 버림
        if isinstance(value, (bool, int, float)):
            record[key] = value
        elif isinstance(value, str) and len(value) <= 20:
            record[key] = value
    logger.info(json.dumps(record, ensure_ascii=False))
    return record
