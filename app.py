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

# API KEY 설정
os.environ['OPENAI_API_KEY']="sk-p"

from main import get_response 
from src.consult.legal_report_builder import LegalAgent 
from src.newsletter.newsletter_builder import NewsletterAgent

# -------------------------
# 🔧 Crawler import
# -------------------------
from src.moel_iqrs_crawler import main as iqrs_update
from src.moel_fastcounsel_crawler import main as fastcounsel_update

# -------------------------
# 🔧 Handler (로직 처리 함수들)
# -------------------------

def handle_news_selection_click(selected_title):
    agent = st.session_state["newsletter_agent"]
    agent.choose_news_source(selected_title) 
    st.session_state.chat_history.append({"role": "user", "content": f"뉴스 기사: **{selected_title}** 선택 완료"})
    
    next_response = agent.run_steps("") 
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["content"]})
    st.rerun()

def handle_consult_selection_click(selected_title):
    agent = st.session_state["newsletter_agent"]
    agent.choose_consult_source(selected_title) 
    st.session_state.chat_history.append({"role": "user", "content": f"노무 상담 사례: **{selected_title}** 선택 완료"})
    
    next_response = agent.run_steps("") 
    prompt_content = next_response.get("message", next_response.get("content"))
    if prompt_content is not None:
         st.session_state.chat_history.append({"role": "assistant", "content": prompt_content})
    st.rerun()

def handle_policy_selection_click(policy_options, selected_indices):
    agent = st.session_state["newsletter_agent"]
    selected_items = [policy_options[i] for i in selected_indices]
    agent.choose_policy(selected_items) 
    st.session_state.chat_history.append({"role": "user", "content": f"정책 자료 {len(selected_items)}개 선택 완료"})
    
    next_response = agent.run_steps("") 
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["content"]})
    st.rerun()

def handle_final_generation():
    agent = st.session_state["newsletter_agent"]
    st.session_state.chat_history.append({"role": "user", "content": "뉴스레터 최종 생성 시작"})
    
    with st.spinner("💭 뉴스레터 최종 문서 생성 및 HTML 렌더링 중..."):
        final_response = agent.run_steps("생성")
        
    if final_response.get("type") == "newsletter":
        content = final_response.get("content")
        newsletter_html = content.get("newsletter") if isinstance(content, dict) else content
        st.session_state["newsletter_html"] = newsletter_html
        st.session_state.chat_history.append({"role": "assistant", "content": newsletter_html})
    
    st.session_state["newsletter_agent"] = NewsletterAgent()
    st.rerun()

# -------------------------
# Streamlit 페이지 설정
# -------------------------
st.set_page_config(page_title="노무 RAG/보고서 AI", layout="wide")
st.title("노무사를 위한 개인비서")
st.write("인사/노무에 대한 질의를 입력하면 AI가 적절한 작업을 판단하여 결과를 제공합니다.")

# -------------------------
# Agent/State 초기화
# -------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "legal_agent" not in st.session_state:
    st.session_state["legal_agent"] = LegalAgent()
if "newsletter_agent" not in st.session_state:
    st.session_state["newsletter_agent"] = NewsletterAgent()

# -------------------------
# Sidebar (데이터 업데이트 등)
# -------------------------
with st.sidebar:
    st.title("🧩 Control Panel")
    if st.button("🧹 New Session"):
        st.session_state.clear()
        st.rerun()
    st.write("---")
    st.markdown("### 🔄 데이터 업데이트")
    
    st.markdown("#### 📌 질의회시DB Update 옵션")
    iqrs_max_page = st.number_input("Max Page (질의회시)", min_value=1, max_value=10, value=2)
    if st.button("질의회시DB Update"):
        with st.spinner("업데이트 중..."):
            iqrs_update(max_pages=iqrs_max_page)
            st.success("완료!")

    st.write("---")
    st.markdown("#### 📌 인터넷상담DB Update 옵션")
    fast_max_page = st.number_input("Max Page (인터넷상담)", min_value=1, max_value=10, value=2)
    if st.button("인터넷상담DB Update"):
        with st.spinner("업데이트 중..."):
            fastcounsel_update(max_pages=fast_max_page)
            st.success("완료!")

# -------------------------
# PDF 변환 함수
# -------------------------
def md_to_pdf_bytes(md_content: str) -> bytes:
    output_file = f"/tmp/report_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    pypandoc.convert_text(md_content, to="pdf", format="md", outputfile=output_file, extra_args=["--pdf-engine=wkhtmltopdf"])
    with open(output_file, "rb") as f:
        pdf_bytes = f.read()
    return pdf_bytes

# -------------------------
# 메인 로직: 대화 표시 + 인라인 UI (수정 핵심)
# -------------------------
current_newsletter_agent = st.session_state["newsletter_agent"]
agent_phase = current_newsletter_agent._phase

# -------------------------
# 메인 로직: 대화 표시 + 인라인 UI 통합 수정본
# -------------------------
for i, chat in enumerate(st.session_state.chat_history):
    role = chat["role"]
    content = chat["content"]

    with st.chat_message(role):
        # 1. 메시지 본문 출력 영역
        if role == "user":
            st.markdown(content)
            rendered = True
        else:
            rendered = False
            # JSON 데이터(보고서/뉴스레터 결과) 파싱 시도
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "report" in parsed:
                    st.markdown("**📝 Legal Report (Markdown)**")
                    st.markdown(parsed["report"], unsafe_allow_html=True)
                    pdf_bytes = md_to_pdf_bytes(parsed["report"])
                    st.download_button(label="📄 Download PDF", data=pdf_bytes, file_name=f"report_{i}.pdf", mime="application/pdf", key=f"json_pdf_{i}")
                    rendered = True
                elif isinstance(parsed, dict) and "newsletter" in parsed:
                    st.markdown("**✅ 뉴스레터 파일 생성이 완료되었습니다.**")
                    html_bytes = parsed["newsletter"].encode('utf-8')
                    st.download_button(label="⬇️ Download HTML", data=html_bytes, file_name=f"newsletter_{i}.html", mime="text/html", key=f"json_html_{i}")
                    rendered = True
            except:
                pass

            # 일반 텍스트 및 HTML 직출력
            if not rendered:
                if "<html" in content.lower() or content.strip().endswith("</html>"):
                    st.markdown("**📨 뉴스레터 HTML이 생성되었습니다.**")
                    st.download_button(label="⬇️ Download HTML", data=content.encode("utf-8"), file_name=f"newsletter_{i}.html", mime="text/html", key=f"direct_html_{i}")
                else:
                    st.markdown(content)
                rendered = True

        # 2. [추가 로직] 작성 완료된 법률 의견서 다운로드 버튼 (본문 바로 아래 배치)
        is_last = (i == len(st.session_state.chat_history) - 1)
        if role == "assistant" and is_last:
            # PDF 의견서 버튼
            if "legal_report_pdf" in st.session_state and os.path.exists("legal_opinion.pdf"):
                with open("legal_opinion.pdf", "rb") as f:
                    st.download_button(
                        label="📄 의견서 PDF 다운로드",
                        data=f.read(),
                        file_name="legal_opinion.pdf",
                        mime="application/pdf",
                        key=f"dl_pdf_fixed_{i}"
                    )
            # MD 의견서 버튼
            if "legal_report_md" in st.session_state and os.path.exists("legal_opinion.md"):
                with open("legal_opinion.md", "rb") as f:
                    st.download_button(
                        label="📝 MD 파일 다운로드",
                        data=f.read(),
                        file_name="legal_opinion.md",
                        key=f"dl_md_fixed_{i}"
                    )

            # 3. 뉴스레터 단계별 선택 UI (가장 하단 배치)
            # 뉴스 선택
            if agent_phase == NewsletterAgent.PHASE_AWAITING_NEWS_PICK:
                with st.container(border=True):
                    st.info("💡 뉴스레터에 분석할 기사를 하나 선택해주세요.")
                    news_options = current_newsletter_agent._news_options
                    if news_options:
                        titles = [item["title"] for item in news_options]
                        selected_title = st.selectbox("기사 목록", titles, key=f"news_sel_{i}")
                        if st.button("기사 선택 완료", key=f"btn_news_{i}"):
                            handle_news_selection_click(selected_title)
            
            # 상담 사례 선택
            elif agent_phase == NewsletterAgent.PHASE_AWAITING_CONSULT_PICK:
                with st.container(border=True):
                    st.info("💡 포함할 상담 사례를 선택해주세요.")
                    consult_options = current_newsletter_agent._consult_options
                    if consult_options:
                        titles = [item.split("Title: ")[-1] for item in consult_options]
                        selected_title = st.selectbox("상담 사례 목록", titles, key=f"cons_sel_{i}")
                        if st.button("사례 선택 완료", key=f"btn_cons_{i}"):
                            handle_consult_selection_click(selected_title)

            # 정책 자료 다중 선택
            elif agent_phase == NewsletterAgent.PHASE_AWAITING_POLICY_PICK:
                with st.container(border=True):
                    st.info("💡 포함할 정책 자료들을 모두 선택해주세요.")
                    policy_options = current_newsletter_agent._selected_policy_items
                    if policy_options:
                        titles = [item["title"] for item in policy_options]
                        selected_indices = st.multiselect("정책 목록 (다중선택)", range(len(titles)), format_func=lambda x: titles[x], key=f"poly_sel_{i}")
                        if st.button("정책 선택 및 생성 시작", key=f"btn_poly_{i}"):
                            handle_policy_selection_click(policy_options, selected_indices)

            # 최종 생성 안내
            elif agent_phase == NewsletterAgent.PHASE_READY_TO_GENERATE:
                if "newsletter_html" not in st.session_state:
                    handle_final_generation()
                else:
                    st.success("모든 자료 선택이 완료되어 뉴스레터가 생성되었습니다.")

# -------------------------
# 사용자 입력 처리
# -------------------------
input_disabled = agent_phase.startswith("awaiting")

if query := st.chat_input("질의를 입력하세요", disabled=input_disabled):
    st.session_state.pop("legal_report_pdf", None)
    st.session_state.pop("legal_report_md", None)

    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    current_legal_agent = st.session_state["legal_agent"]
    current_newsletter_agent = st.session_state["newsletter_agent"]

    with st.chat_message("assistant"):
        with st.spinner("💭 AI 분석 중..."):
            reply, tool_results, updated_legal_agent, updated_newsletter_agent = get_response(
                query=query, 
                legal_agent_instance=current_legal_agent,
                newsletter_agent_instance=current_newsletter_agent,
                directive="",
                continuous=True
            )
            st.session_state["legal_agent"] = updated_legal_agent
            st.session_state["newsletter_agent"] = updated_newsletter_agent
            
            st.markdown(reply)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})

    if tool_results:
        with st.expander("🔧 실행된 도구 로그 확인", expanded=False):
            st.json(tool_results)
    
    # 입력 후 에이전트 상태 변화를 반영하기 위해 리런
    st.rerun()