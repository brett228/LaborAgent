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


os.environ['OPENAI_API_KEY']="sk"

from main import get_response 
from src.consult.legal_report_builder import LegalAgent 
from src.newsletter.newsletter_builder import NewsletterAgent

# Explicitly load .env from project root (parent of src)
# env_path = Path(__file__).parent.parent / ".env"
# load_dotenv(dotenv_path=env_path)

# -------------------------
# 🔧 Crawler import
# -------------------------
from src.moel_iqrs_crawler import main as iqrs_update
from src.moel_fastcounsel_crawler import main as fastcounsel_update

# -------------------------
# 🔧 Handler
# -------------------------
# 1. Handler for News Selection (The failing step in your conversation)
def handle_news_selection_click(selected_title):
    agent = st.session_state["newsletter_agent"]
    
    # 1. Agent processes the selection, updates its internal state to PHASE_ASK_CONSULT_TOPIC
    agent.choose_news_source(selected_title) 
    
    # 2. Add user action and transition message to chat history
    st.session_state.chat_history.append({"role": "user", "content": f"뉴스 기사: **{selected_title}** 선택 완료"})
    
    # 3. IMMEDIATELY call run_steps() to trigger the new phase's prompt ("이제 노무 상담사례...")
    # NOTE: The user_input is empty because the UI button click provides the selection, not new text input.
    next_response = agent.run_steps("") 
    
    # 4. Add the new phase's prompt to history
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["content"]})
    
    # 5. Rerun the app to show the new message and move to the next step
    st.rerun() 

# 2. Handler for Consult Selection
def handle_consult_selection_click(selected_title):
    agent = st.session_state["newsletter_agent"]
    
    # We need the options saved internally in the agent to find the raw text, 
    # but we can pass the title for clean history.
    agent.choose_consult_source(selected_title) 
    
    st.session_state.chat_history.append({"role": "user", "content": f"노무 상담 사례: **{selected_title}** 선택 완료"})
    
    # Immediately trigger the next search (Policy Search)
    next_response = agent.run_steps("") 
    
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["message"]})
    
    # NOTE: You might need to store `next_response["content"]` (policy options) 
    # if you want to access them easily in the UI. We'll rely on the agent's internal state for now.
    st.rerun()

# -------------------------
# Streamlit 페이지 설정
# -------------------------
st.set_page_config(page_title="노무 RAG/보고서 AI", layout="wide")
st.title("Chat App")
# st.title("노무사를 위한 개인비서")
# st.write(
#     """
#     인사/노무에 대한 질의를 입력하면 AI가 적절한 작업을 판단하여 결과를 제공합니다.
#     """
# )

# -------------------------
# Agent/State Initialization
# -------------------------
# Initialize all persistent state objects
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    
if "legal_agent" not in st.session_state:
    st.session_state["legal_agent"] = LegalAgent()

if "newsletter_agent" not in st.session_state:
    st.session_state["newsletter_agent"] = NewsletterAgent()
    # If starting a new session, run the first step of newsletter agent (optional but helpful)
    # st.session_state.chat_history.append({"role": "assistant", "content": "안녕하세요. 노무 보고서, 뉴스레터 작성 등 무엇을 도와드릴까요?"})

directive = st.session_state.get("directive", "")
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
# Interactive UI Display 
# -------------------------
current_newsletter_agent = st.session_state["newsletter_agent"]
agent_phase = current_newsletter_agent._phase

# Check if the agent is in an AWAITING_PICK phase and display the UI components
if agent_phase == NewsletterAgent.PHASE_ASK_CONSULT_TOPIC:

    prompt_key = f"prompt_for_{agent_phase}"
    
    if st.session_state.get(prompt_key) is None:
        try:
            # Run the agent's next step to get the prompt message
            next_response = current_newsletter_agent.run_steps("")
            
            if next_response.get("type") == "message":
                prompt_content = next_response["content"]
                
                # Append the new prompt to history
                st.session_state.chat_history.append({"role": "assistant", "content": prompt_content})
                
                # Set the flag so we don't prompt again on the next rerun
                st.session_state[prompt_key] = True 
                
                # Force a display refresh to show the prompt immediately
                st.rerun()

        except Exception as e:
            # Catch errors during the forced prompt generation
            st.error(f"Error during prompt generation: {e}")

if agent_phase == NewsletterAgent.PHASE_AWAITING_NEWS_PICK:
    with st.container(border=True):
        st.markdown("**1️⃣ 뉴스 기사 선택**")
        
        # Get options from the agent's internal state
        news_options = current_newsletter_agent._news_options
        if news_options:
            titles = [item["title"] for item in news_options]
            
            # Use a unique key for the selectbox
            selected_title = st.selectbox("뉴스 기사 목록", titles, key="news_pick_select")
            
            # Button to trigger the transition
            if st.button("뉴스 선택 완료", key="news_pick_button"):
                handle_news_selection_click(selected_title)
        else:
            st.warning("뉴스 검색 결과가 없습니다. 주제를 다시 입력해 주세요.")
            
elif agent_phase == NewsletterAgent.PHASE_AWAITING_CONSULT_PICK:
    with st.container(border=True):
        st.markdown("**2️⃣ 노무 상담 사례 선택**")
        
        consult_options = current_newsletter_agent._consult_options
        if consult_options:
            # Extract title from "Title: ..." format
            titles = [item.split("Title: ")[-1] for item in consult_options]
            
            selected_title = st.selectbox("상담 사례 목록", titles, key="consult_pick_select")
            
            if st.button("상담 사례 선택 완료", key="consult_pick_button"):
                handle_consult_selection_click(selected_title)
        else:
            st.warning("상담 사례 검색 결과가 없습니다. 주제를 다시 입력해 주세요.")

# -------------------------
# 사용자 입력 + 처리
# -------------------------
input_disabled = agent_phase.startswith("awaiting") or agent_phase.startswith("ready")

if query := st.chat_input("질의를 입력하세요"):
    # 1. Add user query to history
    st.session_state.chat_history.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)
        logger.info("🚀 질문이 입력되었습니다.")

    # 2. Get current agent instances from session state
    current_legal_agent = st.session_state["legal_agent"]
    current_newsletter_agent = st.session_state["newsletter_agent"]

    with st.chat_message("assistant"):
        with st.spinner("💭 Thinking... (Tool Routing)"):
            # 3. Call get_response, passing the agent instances
            reply, tool_results, updated_legal_agent, updated_newsletter_agent = get_response(
                query=query, 
                legal_agent_instance=current_legal_agent,
                newsletter_agent_instance=current_newsletter_agent,
                directive="",
                continuous=True
            )
            
            # 4. Save the updated agent instances back to session state
            st.session_state["legal_agent"] = updated_legal_agent
            st.session_state["newsletter_agent"] = updated_newsletter_agent
            
            # 5. Display the final LLM response
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
