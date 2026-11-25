"""1_환경_정보.py — 지금 앱이 '어디서, 무엇으로' 돌고 있는지 확인하는 페이지

주의: secrets 는 '키가 있는지'만 보여 주고, 값은 절대 화면에 출력하지 않는다.
"""
import os
import platform
import sys
from pathlib import Path

import streamlit as st

import guard
import llm

st.set_page_config(page_title="환경 정보", page_icon="🧭")
guard.require_password()  # 페이지마다 호출해야 비밀번호를 우회할 수 없다

SECRET_KEYS = ["PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "APP_PASSWORD", "MAX_CALLS_PER_SESSION"]


def guess_location() -> str:
    """실행 위치 추정(확실하지 않음). Community Cloud 는 /mount/src/<repo> 에서 실행되는 경우가 많다."""
    cwd = Path.cwd().as_posix()
    if cwd.startswith("/mount/src") or os.getenv("HOME") == "/home/appuser":
        return "클라우드(Streamlit Community Cloud 추정)"
    if platform.system() in ("Windows", "Darwin"):
        return "로컬 노트북(추정)"
    return "알 수 없음(리눅스 서버 또는 로컬 리눅스)"


def memory_mb() -> str:
    """현재 프로세스 메모리(RSS). psutil 이 없으면 리눅스 /proc 로 대신 읽는다."""
    try:
        import psutil  # requirements-local.txt 에만 있음
        return f"{psutil.Process().memory_info().rss / 1024**2:.0f} MB"
    except ImportError:
        pass
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return f"{int(line.split()[1]) / 1024:.0f} MB"
    except OSError:
        pass
    return "측정 불가(psutil 미설치)"


def secret_presence_rows() -> list[dict]:
    """키 이름과 '있음/없음'만. 값(value)은 절대 넣지 않는다."""
    return [{"키": k, "설정 여부": "있음" if llm.get_setting(k) else "없음"} for k in SECRET_KEYS]


st.title("환경 정보")
requested, effective = llm.get_requested_provider(), llm.get_provider()
c1, c2 = st.columns(2)
c1.metric("요청한 provider", requested)
c2.metric("실제 사용 provider", llm.PROVIDER_LABELS[effective][0])
if llm.get_provider_notice():
    st.warning(llm.get_provider_notice())

st.subheader("실행 환경")
st.table([
    {"항목": "Python 버전", "값": sys.version.split()[0]},
    {"항목": "Streamlit 버전", "값": st.__version__},
    {"항목": "운영체제", "값": f"{platform.system()} {platform.release()}"},
    {"항목": "실행 위치", "값": guess_location()},
    {"항목": "메모리(RSS)", "값": memory_mb()},
])
if not sys.version.startswith("3.11"):
    st.info("수업 표준은 Python 3.11 입니다. Cloud 에서는 배포 시 Advanced settings 에서 고릅니다.")

st.subheader("Secrets 설정 여부 (값은 표시하지 않음)")
st.table(secret_presence_rows())
st.caption("값을 확인하고 싶어도 화면·로그에 출력하지 마세요. 공개 URL 에서는 누구나 볼 수 있습니다.")

guard.show_disclaimer()
