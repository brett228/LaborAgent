# app.py
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st
import pypandoc
import logging
logger = logging.getLogger(__name__)


os.environ['OPENAI_API_KEY']="sk-"

from main import get_response 

# Explicitly load .env from project root (parent of src)
# env_path = Path(__file__).parent.parent / ".env"
# load_dotenv(dotenv_path=env_path)

# -------------------------
# 🔧 Crawler import
# -------------------------
from src.moel_iqrs_crawler import main as iqrs_update
from src.moel_fastcounsel_crawler import main as fastcounsel_update


# -------------------------
# Streamlit 페이지 설정
# -------------------------
st.set_page_config(page_title="노무 RAG/보고서 AI", layout="wide")
st.title("노무사를 위한 개인비서")
st.write(
    """
    인사/노무에 대한 질의를 입력하면 AI가 적절한 작업을 판단하여 결과를 제공합니다.
    """
)


# -------------------------
# Sidebar
# -------------------------
with st.sidebar:
    st.title("🧩 Control Panel")

    # ================================
    # 새 세션 시작
    # ================================
    if st.button("🧹 New Session"):
        st.session_state.clear()
        st.rerun()

    st.write("---")

    st.markdown("### 🔄 데이터 업데이트")

    # ================================
    # 질의회시 DB 업데이트
    # ================================
    st.markdown("#### 📌 질의회시DB Update 옵션")

    iqrs_max_page = st.number_input(
        "Max Page (질의회시)",
        min_value=1,
        max_value=10,
        value=2
    )

    if st.button("질의회시DB Update"):
        with st.spinner(f"질의회시 DB 업데이트 중... (1 ~ {iqrs_max_page})"):
            try:
                iqrs_update(max_pages=iqrs_max_page)
                st.success("질의회시 DB 업데이트 완료!")
            except Exception as e:
                st.error(f"오류 발생: {e}")


    st.write("---")

    # ================================
    # 인터넷상담 DB 업데이트
    # ================================
    st.markdown("#### 📌 인터넷상담DB Update 옵션")

    fast_max_page = st.number_input(
        "Max Page (인터넷상담)",
        min_value=1,
        max_value=10,
        value=2
    )

    if st.button("인터넷상담DB Update"):
        with st.spinner(f"인터넷상담 DB 업데이트 중... (1 ~ {fast_max_page})"):
            try:
                fastcounsel_update(max_pages=fast_max_page)
                st.success("인터넷상담 DB 업데이트 완료!")
            except Exception as e:
                st.error(f"오류 발생: {e}")

# -------------------------
# 대화 기록 초기화
# -------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

directive = st.session_state.get("directive", "")


# -------------------------
# PDF 변환 함수
# -------------------------
def md_to_pdf_bytes(md_content: str) -> bytes:
    """
    Markdown 문자열을 PDF로 변환하여 bytes 반환
    """
    output_file = f"/tmp/report_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    pypandoc.convert_text(
        md_content,
        to="pdf",
        format="md",
        outputfile=output_file,
        extra_args=["--pdf-engine=wkhtmltopdf"]
    )
    with open(output_file, "rb") as f:
        pdf_bytes = f.read()
    return pdf_bytes


# -------------------------
# 대화 표시
# -------------------------
for chat in st.session_state.chat_history:
    role = chat["role"]
    content = chat["content"]

    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    else:
        try:
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                if "report" in parsed:  # 📄 Legal Report
                    md_report = parsed["report"]
                    st.markdown("**📝 Legal Report (Markdown)**")
                    st.markdown(md_report, unsafe_allow_html=True)

                    # PDF Download
                    pdf_bytes = md_to_pdf_bytes(md_report)
                    st.download_button(
                        label="📄 Download PDF",
                        data=pdf_bytes,
                        file_name=f"legal_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf"
                    )

                elif "newsletter" in parsed:  # 📰 Newsletter
                    md_news = parsed["newsletter"]
                    st.markdown("**📰 Newsletter (Markdown)**")
                    st.markdown(md_news, unsafe_allow_html=True)

                else:
                    st.json(parsed)

            else:
                st.markdown(content)

        except Exception:
            st.markdown(content)


# -------------------------
# 사용자 입력 + 처리
# -------------------------
from src.newsletter.newsletter_builder import NewsletterAgent

if "newsletter_agent" not in st.session_state:
    st.session_state["newsletter_agent"] = NewsletterAgent()

agent = st.session_state["newsletter_agent"]

if query := st.chat_input("질의를 입력하세요"):
    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
        logger.info("🚀 질문이 입력되었습니다.")

    with st.chat_message("assistant"):
        with st.spinner("💭 Thinking..."):
            reply, tool_results = get_response(
                query,query, 
                directive="",
                continuous=True
            )
    st.markdown(reply)
    st.session_state.chat_history.append({"role": "assistant", "content": reply})

    # 🛠 Tool 호출 로그 및 결과 표시
    if tool_results:
        st.markdown("**🔧 Tool 호출 결과**")
        for tool_msg in tool_results:
            try:
                content = json.loads(tool_msg["content"])
            except Exception:
                content = tool_msg["content"]
            st.markdown(f"- **Tool:** `{tool_msg['name']}`")
            st.json(content)
    
    if agent._phase != "ready_to_generate":
        result = agent.run_steps(query)
        reply = result.get("message", "")
    else:
        # 최종 뉴스레터 생성
        result = agent.run_steps(query)
        reply = result.get("newsletter", "")