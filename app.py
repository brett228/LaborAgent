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
    
    # 1. Agent processes selection, sets phase to PHASE_ASK_CONSULT_TOPIC
    agent.choose_news_source(selected_title) 
    
    st.session_state.chat_history.append({"role": "user", "content": f"뉴스 기사: **{selected_title}** 선택 완료"})
    
    # 2. Call run_steps to get the NEXT prompt/phase's message.
    next_response = agent.run_steps("") 
    
    # 3. Add the next prompt to history
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["content"]})
    
    # 4. ONE RERUN: The entire app re-executes and the new prompt is displayed.
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

    prompt_content = next_response.get("message", next_response.get("content"))
    
    if prompt_content is not None:
         st.session_state.chat_history.append({"role": "assistant", "content": prompt_content})
    
    # NOTE: You might need to store `next_response["content"]` (policy options) 
    # if you want to access them easily in the UI. We'll rely on the agent's internal state for now.
    st.rerun()

# 3. Handler for Policy Selection and Final Generation Setup
def handle_policy_selection_click(policy_options, selected_indices):
    agent = st.session_state["newsletter_agent"]
    
    # 1. Extract the selected items from the full options list
    selected_items = [policy_options[i] for i in selected_indices]
    
    # 2. Agent processes the selection, sets phase to PHASE_READY_TO_GENERATE
    agent.choose_policy(selected_items) 
    
    # 3. Add user action to chat history
    st.session_state.chat_history.append({"role": "user", "content": f"정책 자료 {len(selected_items)}개 선택 완료"})
    
    # 4. IMMEDIATELY call run_steps() to trigger the final readiness message
    # run_steps should now return the PHASE_READY_TO_GENERATE message.
    next_response = agent.run_steps("") 
    
    # 5. Add the final prompt to history
    st.session_state.chat_history.append({"role": "assistant", "content": next_response["content"]})
    
    # 6. Rerun the app to enable the final generation button
    st.rerun()

# app.app (Add this function to the handler section)

def handle_final_generation():
    agent = st.session_state["newsletter_agent"]
    
    # 1. Add user action to history (simulating the '생성' command)
    st.session_state.chat_history.append({"role": "user", "content": "뉴스레터 최종 생성 시작"})
    
    with st.spinner("💭 뉴스레터 최종 문서 생성 및 HTML 렌더링 중..."):
        # 2. Call run_steps with the trigger word. 
        # Since the phase is PHASE_READY_TO_GENERATE, this executes the agent.run() logic.
        final_response = agent.run_steps("생성")
        
    # 3. Add success message and final document to history
    if final_response.get("type") == "newsletter":
        content = final_response.get("content")
        # Extract the HTML string
        newsletter_html = content.get("newsletter") if isinstance(content, dict) else content
        st.session_state["newsletter_html"] = newsletter_html
        st.session_state.chat_history.append({"role": "assistant", "content": newsletter_html})
        
    # 4. Reset the Agent for a new session
    st.session_state["newsletter_agent"] = NewsletterAgent()
    
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

    with st.chat_message(role):

        if role == "user":
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
                        html_bytes = None

                        if not md_news:
                            st.error("Error: Newsletter content was generated but is empty.")   
                        else:
                            st.markdown("**✅ 뉴스레터 파일 생성이 완료되었습니다.**")
                            # st.markdown(md_news, unsafe_allow_html=True)
                            html_bytes = md_news.encode('utf-8')

                            st.download_button(
                                label="⬇️ Download HTML Newsletter",
                                data=html_bytes, 
                                file_name=f"newsletter_{datetime.now().strftime('%Y%m%d_%H%M')}.html", # Use dynamic filename
                                mime="text/html"
                                )

                    else:
                        pass

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
    pass

if agent_phase == NewsletterAgent.PHASE_AWAITING_NEWS_PICK:
    with st.container(border=True):
        st.markdown("**1️⃣ 뉴스 기사 선택**")
        
        # Get options from the agent's internal state
        news_options = current_newsletter_agent._news_options
        if news_options:
            # ... (Selection box logic remains the same) ...
            titles = [item["title"] for item in news_options]
            selected_title = st.selectbox("뉴스 기사 목록", titles, key="news_pick_select")
            
            # Button to trigger the transition
            if st.button("뉴스 선택 완료", key="news_pick_button"):
                handle_news_selection_click(selected_title)
        else:
            st.warning("뉴스 검색 결과가 없습니다. 주제를 다시 입력해 주세요.")  
    pass

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
    pass

elif agent_phase == NewsletterAgent.PHASE_AWAITING_POLICY_PICK:
    with st.container(border=True):
        st.markdown("**3️⃣ 정책 자료 선택**")
        
        # FIX: Policy options are stored in _selected_policy_items
        policy_options = current_newsletter_agent._selected_policy_items 
        
        if policy_options:
            titles = [item["title"] for item in policy_options]
            
            # Use multiselect for policy items
            selected_indices = st.multiselect(
                "정책 자료 목록 (다중 선택 가능)", 
                options=list(range(len(titles))), 
                format_func=lambda i: titles[i], 
                key="policy_pick_select"
            )
            
            # You will need a handler for the final policy selection
            if st.button("정책 선택 완료 및 최종 생성 준비", key="policy_pick_button"):
                # You'll need to define this handler function!
                handle_policy_selection_click(policy_options, selected_indices)
        else:
            st.warning("정책 자료 검색 결과가 없습니다.")
    pass

elif agent_phase == NewsletterAgent.PHASE_READY_TO_GENERATE:
    if "newsletter_html" not in st.session_state:
        # Generate newsletter once
        handle_final_generation()
    
    with st.chat_message("assistant"):
        st.markdown("모든 자료 선택이 완료되었습니다. **뉴스레터가 생성되었습니다.**")

    if "newsletter_html" in st.session_state:
        html_bytes = st.session_state["newsletter_html"].encode("utf-8")
        st.download_button(
            label="⬇️ Download HTML Newsletter",
            data=html_bytes,
            file_name=f"newsletter_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
            mime="text/html"
        )

    # We use a session state flag to ensure automatic generation runs only once
    # when the app hits this phase, not on every subsequent rerun.
    # if st.session_state.get("generating_finished") is None:
        
    #     # Display an interim message before the spinner takes over
    #     with st.chat_message("assistant"):
    #         st.markdown("모든 자료 선택이 완료되었습니다. **자동으로 최종 뉴스레터 생성을 시작합니다.**")
            
    #     st.session_state["generating_finished"] = True # Set flag to prevent loop
    #     handle_final_generation() # Automatically call the function
    
    # else:
    #     # If the flag is set, just wait for the rerun to complete the generation/reset
    #     pass

# -------------------------
# 사용자 입력 + 처리
# -------------------------
input_disabled = agent_phase.startswith("awaiting")

if query := st.chat_input("질의를 입력하세요", disabled=input_disabled):
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
