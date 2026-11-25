"""2_헬스체크.py — llm.chat 이 실제로 응답하는지 '핑' 테스트하고 응답 시간을 잰다."""
import time

import streamlit as st

import guard
import llm

st.set_page_config(page_title="헬스체크", page_icon="🩺")
guard.require_password()
max_calls = guard.get_max_calls()
allowed = guard.rate_limit(max_calls)  # 핑도 API 를 쓰므로 같은 한도에 포함


def ping() -> dict:
    """짧은 질문 1개를 보내 응답 시간과 앞부분만 돌려준다."""
    started = time.time()
    text = llm.chat([{"role": "user", "content": "연결 테스트입니다. '정상'이라고만 답하세요."}],
                    stream=False, temperature=0.0)
    elapsed = time.time() - started
    # get_provider() 를 다시 부르면 경고가 지워지므로, chat() 이 '실제로' 쓴 provider 를 읽는다
    return {"provider": llm.get_last_used_provider(), "seconds": elapsed, "preview": str(text)[:120],
            "notice": llm.get_provider_notice()}


st.title("헬스체크")
st.write("배포 직후 이 페이지에서 **LLM 연결**과 **응답 시간**을 확인하세요.")

col1, col2 = st.columns(2)
col1.metric("현재 provider", llm.PROVIDER_LABELS[llm.get_provider()][0])
remaining_slot = col2.empty()  # 핑을 누른 뒤의 값으로 아래에서 채운다
if llm.get_requested_provider() == "ollama":
    st.write("Ollama 서버 연결:", "정상" if llm.ollama_available() else "연결 안 됨")

if st.button("핑 테스트 실행", type="primary", disabled=not allowed):
    guard.count_call()
    result = ping()
    guard.safe_log("ping", provider=result["provider"], latency_ms=int(result["seconds"] * 1000))
    show = st.warning if result["notice"] else st.success  # 대체(fallback)됐으면 노란색
    show(f"응답 시간 {result['seconds']:.2f}초 · provider = {result['provider']}")
    st.code(result["preview"], language=None)
    if result["notice"]:
        st.warning(result["notice"])
remaining_slot.metric("남은 호출 수", f"{guard.remaining_calls()} / {max_calls}")
if not allowed:
    st.error("이 세션의 호출 한도를 모두 사용했습니다.")

st.caption("참고: 클라우드 앱이 잠들어(sleep) 있었다면 첫 응답이 느릴 수 있습니다.")
guard.show_disclaimer()
