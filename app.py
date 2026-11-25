"""app.py — 13주차 배포 템플릿 (완성본, 멀티페이지 진입점)

"구강 증상 설명 → 쉬운 말 구강 건강 정보" 챗봇(치통, 잇몸 출혈, 시린 이, 구내염, 사랑니 통증 등).
실행:  streamlit run app.py
Streamlit Community Cloud 의 Main file path 에도 app.py 를 지정합니다.
pages/ 폴더의 파일은 사이드바에 자동으로 페이지로 나타납니다.
"""
import time

import streamlit as st

import guard
import llm

st.set_page_config(page_title="쉬운 말 구강 증상 정보 챗봇", page_icon="🦷")

SYSTEM_PROMPT = (
    "너는 치의학대학원 수업용 구강 증상 일반 정보 도우미다. 사용자가 설명한 치아·잇몸·입안 증상에 대해 "
    "일반적인 구강 건강 정보를 중학생도 이해할 쉬운 한국어로 5문장 이내로 설명한다. "
    "진단이나 약 처방을 하지 않는다. 얼굴·목이 붓고 열이 나거나 숨쉬기·삼키기가 힘들면 즉시 119/응급실, "
    "외상으로 이가 빠지거나 부러졌으면 빨리 치과 방문을 권한다. "
    "마지막에 '정확한 판단은 치과의사와 상담하세요'를 덧붙인다."
)

# 1) 시작 시 순서: 비밀번호 → 호출 수 제한
guard.require_password()
max_calls = guard.get_max_calls()
allowed = guard.rate_limit(max_calls)


def render_sidebar() -> str:
    """provider 배지와 남은 호출 수를 사이드바에 표시하고 provider 를 돌려준다."""
    provider = llm.get_provider()
    label, color = llm.PROVIDER_LABELS[provider]
    with st.sidebar:
        st.markdown(f"**LLM 제공자** :{color}-background[{label}]")
        # 자동 전환 경고 + 직전 대화에서 생긴 '호출 실패 → mock 대체' 경고(같은 문장은 한 번만)
        notices = [llm.get_provider_notice(), st.session_state.pop("_chat_notice", "")]
        for notice in dict.fromkeys(n for n in notices if n):
            st.warning(notice)
        st.metric("남은 호출 수", f"{guard.remaining_calls()} / {max_calls}")
        st.caption("호출 수는 브라우저 세션마다 따로 셉니다.")
    return provider


def answer(prompt: str, provider: str) -> None:
    """사용자 입력을 기록하고 스트리밍으로 답한다(입력 원문은 로그에 남기지 않음)."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    guard.count_call()
    started = time.time()
    notice = guard.emergency_notice(prompt)  # 응급·위험 신호는 LLM 답과 상관없이 먼저 보여 준다
    with st.chat_message("assistant"):
        if notice:
            st.error(notice)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages[-6:]
        text = st.write_stream(llm.chat(msgs, stream=True))
    head = f"**[응급 신호 안내]** {notice}\n\n" if notice else ""
    st.session_state.messages.append({"role": "assistant", "content": head + str(text)})
    st.session_state["_chat_notice"] = llm.get_provider_notice()
    used = llm.get_last_used_provider() or provider  # 호출 실패로 mock 대체됐으면 mock
    guard.safe_log("chat", provider=used, n_chars=len(prompt), red_flag=bool(notice),
                   latency_ms=int((time.time() - started) * 1000), remaining=guard.remaining_calls())


st.title("쉬운 말 구강 증상 정보 챗봇")
st.caption("치아·잇몸·입안 증상을 적으면 일반적인 구강 건강 정보를 쉬운 말로 알려 줍니다. (13주차 배포 실습)")
provider = render_sidebar()

st.session_state.setdefault("messages", [])
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# 2) 입력창 위 경고(공개 웹)
st.warning(guard.PUBLIC_WARNING)
if not allowed:
    st.error(f"이 세션의 호출 한도({max_calls}회)를 모두 사용했습니다. 새 탭에서 다시 접속하세요.")
prompt = st.chat_input("예: 찬물을 마시면 어금니가 시려요", disabled=not allowed)
if prompt and allowed:
    answer(prompt, provider)
    st.rerun()  # 사이드바의 남은 호출 수를 바로 갱신

# 3) 하단 고지
guard.show_disclaimer()
