from datetime import datetime
import json
import math
import os
from pathlib import Path
from jinja2 import Template
import streamlit as st

# RAG 구성
from chromadb import PersistentClient
from src.embeddings import get_embedding
from src.rag.load_index import load_chroma_collection, search_vector_store, search_multiple_collections
from src.newsletter.news_searcher import search_all_newslist, search_all_text
from src.newsletter.policy_search import search_press_release
from src.newsletter.newsletter_renderer import NewsletterRenderer
from src.utils.selectors import prompt_user_choice, prompt_user_choice_multiple
from src.utils.storage import save_html
from openai import OpenAI
import pypandoc
# pypandoc.download_pandoc()


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# KK = LegalAgent()
# KK.run("임금항목별 통상임금 해당여부 문의- 해외주재원(세금보전금액), 복지포인트, 인센티브- 국외근로수당, 겸직(겸무)수당, 근무지이동수당, 변동상여")
# KK.state

common_directive = """
    [공통 규칙]
        - 항상 한글로만 대답합니다.
        - 욕설과 비속어는 사용하지 않습니다.
        - 당신의 답변은 주어진 질의응답 원문에만 근거해야 합니다.
          단, 답변과 관련한 근거를 국가법령정보센터(www.law.go.kr)로부터 검색하여 사용할 수는 있습니다.
          본 답변은 실제 법률적 조언이 아님을 전제로 합니다.
        - markdown 문법에 적합하도록 문단 사이에 적절히 줄바꿈을 하고 줄바꿈 시 줄바꿈 문자를 적용합니다.(\n\n)
    """


class LegalAgent:
    """
    query에 맞는 법령, 판례, 의견 등을 반환
    """

    def __init__(self):

        # 템플릿 구성 슬롯
        self.state = {
            "query_summary": None,
            "related_laws": None,
            "related_cases": None,
            "related_query": None,
            "answer": None,
            "date": datetime.today().strftime('%Y.%m.%d'),
        }

    def run(self, query):
        print("### 의견서 생성 에이전트 시작 ###\n")
        if not query:
            raise ValueError("Query cannot be empty for Legal Report generation.")

        self.query = query

        # 1. 각 템플릿 영역별 생성
        self.process_sections()

        # 2. 렌더링 후 md / pdf 생성
        self.render_final_md()
        self.convert_md_to_pdf()

        # 3. download 설정
        st.session_state.legal_report_md = "legal_opinion.md"
        st.session_state.legal_report_pdf = "legal_opinion.pdf"
        st.chat_message("assistant").write("의견서 생성이 완료되었습니다.")

        if "legal_report_md" in st.session_state:
            with open("legal_opinion.md", "rb") as f:
                st.download_button("Download md file", f, file_name="legal_opinion.md")
        if "legal_report_pdf" in st.session_state:
            with open("legal_opinion.pdf", "rb") as f:
                st.download_button("Download pdf file", f, file_name="legal_opinion.pdf")

        print("\n### 의견서 생성이 완료되었습니다! ###")
        return {
            "message": "의견서가 작성되었습니다. 추가로 필요하신 사항이 있으면 말씀해 주세요."
        }

    
    # --------------------------------------------------------------------
    def create_ground(self):

        print("\n[질의 요약 및 법령 근거 생성]")

        session = []
        directive = """
        당신은 인사/노무 관련 질의사항을 간략히 정리하고, 그로부터 법령 근거자료를 생성하는 에이전트입니다.
        - 질의 요약은 사용자가 입력한 질의 의미의 변경 없이 출력하되, "~임", "~음", "~인가"와 같이 문어체로 축약된 어조를 사용합니다.
        - 법령 근거 및 관련 질의의 경우, '~입니다.', '~습니다'와 같은 격식을 갖춘 어미로 구성된 존대말를 사용합니다.
          절대로 “~다”, “~요”, “해요”, “합니다요”, "~임", "~음" 등의 어미를 사용하지 않습니다.
        - 문장마다 markdown 적용가능하도록 줄바꿈을 사용하고, 복수의 질의/결과가 있을 경우 불릿기호('-')를 이용해 구분합니다.
        - 질의로부터 관련 법령과 판례를 시사점을 출력합니다.
            항상 아래 JSON형식으로만 출력하세요:
            {
                "query_summary": "...",
                "related_laws": "...",
                "related_cases": "...",
            } 
        - 관련 법령은 가급적 국가법령정보선터에서 찾아서 인용하며, 
          법령 상의 용어 정의, 개념 등을 정리한 후. 관련 조문을 직접인용하고 링크를 제시합니다.
          또한, 이에 대한 간략한 해석 및 일반적인 적용방안을 추가합니다.
          전체 5000자 내외로 작성합니다.
        - 관련 판례는 공신력있는 웹사이트로부터 찾아서 문장을 다듬어 출력합니다.
          판례번호 및 링크를 함께 제시합니다. 전체 5000자 내외로 작성합니다.

        - 답변 예시는 다음과 같습니다.
            {   
                "query_summary":
                    "임금항목별 통상임금 해당여부 문의
                    - 해외주재원(세금보전금액), 복지포인트, 인센티브
                    - 국외근로수당, 겸직(겸무)수당, 근무지이동수당", 변동상여 "question": "Q. 회사가 징계절차를 개시하면서 징계혐의자의 징계회부사실을 회사 게시판에 공지해도 되나요?" 

                "related_laws": 
                    "질의에 대한 판단 근거로, 근로기준법 제76조의2에서는 “직장 내 괴롭힘 금지”를 규정하고 있습니다.
                    사용자 또는 근로자는 직장에서의 지위 또는 관계 등의 우위를 이용하여 업무상 적정범위를 넘어 
                    다른 근로자에게 신체적ㆍ정신적 고통을 주거나 근무환경을 악화시키는 행위를 직장내 괴롭힘으로 정의하고 있습니다.(https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1012828841)
                    법 조항은 구체적 행위를 일일이 열거하고 있진 않지만, 실제 실무나 매뉴얼에서는 다양한 유형이 괴롭힘으로 인정될 수 있다고 보고됩니다. 
                    예:
                    - 정당한 이유 없이 능력을 무시하거나 업무나 보상에서 차별 — 예: 승진·보상 거부, 부당한 업무 할당
                    - 과도한 업무 강요, 집단 따돌림, 회식·음주 강요
                    - 지나친 감시, 고립, 업무와 관련 없는 사적 지시
                    - 폭언·모욕, 조롱, 정신적 압박 등",
                "related_cases": 
                    "관련 판례: 
                    수원지방법원 안산지원 2021. 1. 29. 선고 (사건번호 2020가단68472) (https://www.kbei.org/new/05info/s_4.php?action=view&bid=column_kim&idx=472)
                    - 하급자인 근로자에 대해 약 2년 동안 반복적인 폭언과 욕설이 있었던 사안.
                    - 법원은 이를 “직장 내 괴롭힘”으로 인정하고, 피고에게 원고에게 1,200만 원의 손해배상(위자료) 책임을 인정함. 
                    
                    수원지방법원 2022. 12. 9. 선고 (사건번호 2021나93038) (https://www.kbei.org/new/05info/s_4.php?action=view&bid=column_kim&idx=472)
                    - 현장소장 지위의 가해자가 안전팀장을 업무에서 배제하고, 욕설·모욕, 근무 위치를 화장실 통로 옆으로 이동, 휴가 명령, 근무 계획표에서만 삭제하는 등의 조치를 한 경우.
                    - 법원은 위 행위를 직장 내 괴롭힘으로 인정하고, 위자료 300만 원 지급을 판결함."
            } 
        """
        session = [
            {"role": "system", "content": common_directive},
            {"role": "system", "content": directive},
            {"role": "user", "content": f"질의사항 전문:\n{self.query}"}
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session,
            response_format={"type": "json_object"},
            )
        
        content = response.choices[0].message.content.strip()
        if not content:
            raise ValueError("LLM 응답이 비어있습니다.")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            print("JSON 파싱 오류 발생:", e)
            print("원본 응답:", content)
            parsed = {}
        self.state["query_summary"] = parsed.get("query_summary", "")
        self.state["related_laws"] = parsed.get("related_laws", "")
        self.state["related_cases"] = parsed.get("related_cases", "")
        # self.state["query_summary"] = json.loads(response.choices[0].message.content)['query_summary']
        # self.state["related_laws"] = json.loads(response.choices[0].message.content)['related_laws']
        # self.state["related_cases"] = json.loads(response.choices[0].message.content)['related_cases']


    def select_consult_sources_and_crawl(self):
        try:
            chroma_client
        except NameError:
            load_dir = Path("db/chroma_index")
            chroma_client = PersistentClient(path=str(load_dir))
        
        existing_collections = [col.name for col in chroma_client.list_collections()]
        if not existing_collections:
            result = {"error": "검색 가능한 컬렉션이 없습니다."}
        else:
            result = search_multiple_collections(
                client=chroma_client,
                collection_names=existing_collections,
                query=self.query,
                get_embedding_fn=get_embedding,
                top_k=5
                )

        self.raw_consult = result

        print(f"관련 질의를 로드했습니다.\n")

    def create_related_query(self):
        print("\n[관련 질의 생성]")

        session = []
        directive = """
        당신은 인사/노무 관련 질의사항으로부터 유사한 질의 사례를 찾아 정리하는 에이전트입니다.
        - 사용자의 질의사항과 찾아낸 유사사례를 바탕으로 가장 유사한 사례를 최대 3건 찾아 작성합니다..
        - '~입니다.', '~습니다'와 같은 격식을 갖춘 어미로 구성된 존대말를 사용합니다.
          절대로 “~다”, “~요”, “합니다”, “해요”, “합니다요”, "~임", "~음" 등의 어미를 사용하지 않습니다.
        - 반드시 관련 질의 검색결과(raw_consult)에 있는 응답 중에서만 작성할 내용을 텍스트로 출력하며, 여기에 없는 내용을 추가하지 않습니다.
        - 전체 5000자 내외로 작성하며, 근거자료 링크를 추가합니다.
          결과는 반드시 질의:... 응답:... 형식으로 구분하여 출력하며, 질의와 응답간 줄바꿈을 합니다.
          서로 다른 사례에는 한 줄의 공백을 둡니다.

        - 답변 예시는 다음과 같습니다.
            "질의:  업무수행 평가결과에 따른 인센티브, 기준물량 초과 시 분기마다 지급하는 격려금(시간외근무수당 등은 별도 지급)의 임금성
             응답:「근로기준법」상 임금이란 사용자가 근로의 대가로 근로자에게 지급하는 금품으로서, 근로자에게 계속적, 정기적으로 지급되고 단체협약, 취업규칙,급여규정, 근로계약, 노동관행 등에 의하여 사용자에게 그 지급의무가 지워져 있는 것을 말함(대법원 2018.10.12. 선고 2015두36157 판결 등 참고). 질의의 내용만으로는 구체적인 사실관계를 알 수 없어 명확한 답변을드리기는 어려우나, 질의상 인센티브와 격려금은 카드발급 업무에 따른 결과(발급량) 등 근로의 대가로 지급되는 것으로 보이는바, 정해진 지급기준과 지급시기에 따라 정기적·계속적으로 지급되고, 지급기준 등의 요건에 맞는 실적을 달성할 경우 회사로서는 인센티브, 격려금의 지급을 거절할 수 없는 것이라면 「근로기준법」상 임금으로 볼 수 있을 것으로 사료됨. 
             link: https://labor.moel.go.kr/cmmt/iqrs_detail.do?id=20773"
            
        """
        session = [
            {"role": "system", "content": common_directive},
            {"role": "system", "content": directive},
            {"role": "user", "content": f"질의사항 전문:\n{self.query}"},
            {"role": "user", "content": f"관련질의 검색 결과:\n{self.raw_consult}"}
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session,
            )
        
        self.state["related_query"] = response.choices[0].message.content


    def create_answer(self):
        print("\n[검토 의견 생성]")

        session = []
        directive = """
        당신은 인사/노무 관련 질의사항으로부터 법령근거 및 유사한 질의 사례를 찾아 검토 의견을 생성하는 에이전트입니다.
        - '~입니다.', '~습니다'와 같은 격식을 갖춘 어미로 구성된 존대말를 사용합니다.
          의견이나 판단이 결부되는 문장은 "~사료됩니다."나 "~판단됩니다."와 같은 어미를 사용합니다.
          절대로 “~다”, “~요”, “해요”, “합니다요”, "~임", "~음" 등의 어미를 사용하지 않습니다.
        - 다음의 순서에 따라 작성합니다.
          - 질의 사항 및 문제 상황에 대한 추측 (1000자 내외)
          - 법령 근거자료 및 관련 질의에 대한 요약 및 취지 기술 (3000자 내외)
          - 질의에 대한 최종 판단 (2000자 내외) 

        - 답변 예시는 다음과 같습니다.
            "귀사의 변동상여는 직책자를 대상으로 전년도 성과평가 결과에 따라 당해연도에 차등하여 정액으로 지급하는 금품으로, 급여규정에 근거를 두고 있는 것으로 보입니다. 
            
            대법원은 전년도 인사평가 결과에 따라 당해연도 지급액이 달라질 수 있는 임금에 대해 “일단 전년도 인사평가 결과를 바탕으로 한 인상분이 정해질 경우 월 기본급의 700%에 그 인상분을 더한 금액이 해당 연도의 근무실적과는 관계없이 해당 연도 근로의 대가로 액수 변동 없이 지급되는 것으로서, 근로자가 소정근로를 제공하기만 하면 그 지급이 확정된 것이라고 볼 수 있어, 모두 정기적·일률적으로 지급되는 고정적인 임금인 통상임금에 해당”한다고 본 바 있습니다(대법원 2015.11.27. 선고 2012다10980 판결 참고). 
            
            위 판례를 참고할 때, 귀사의 변동상여 또한 비록 전년도 성과평가 결과에 따라 그 지급액이 달라지기는 하나 당해연도 소정근로의 대가로서 정기적·일률적으로 지급하기로 정한 임금이라 볼 수 있으므로, 통상임금에 해당하는 것으로 사료됩니다."
            
        """
        session = [
            {"role": "system", "content": common_directive},
            {"role": "system", "content": directive},
            {"role": "user", "content": f"질의사항 전문:\n{self.query}"},
            {"role": "user", "content": f"법령근거:\n{self.state["related_laws"] }"},
            {"role": "user", "content": f"관련판례:\n{self.state["related_cases"] }"},
            {"role": "user", "content": f"관련질의:\n{self.state["related_query"]}"}
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session,
            )
        
        self.state["answer"] = response.choices[0].message.content

    # --------------------------------------------------------------------
    def process_sections(self):
        print("섹션별 콘텐츠 구성 단계 실행\n")

        # 질의 요약 및 관련 법령 구성
        self.create_ground()

        self.select_consult_sources_and_crawl()

        # 관련 질의 구성
        self.create_related_query()

        # 정책 영역 구성
        self.create_answer()

    # --------------------------------------------------------------------
    def render_final_md(self):
        with open("templates/consult_template.md", "r", encoding="utf-8") as f:
            template_content = f.read()

        template = Template(template_content)
        rendered_md = template.render(**self.state)
        
        # 파일로 저장
        with open("legal_opinion.md", "w", encoding="utf-8") as f:
            f.write(rendered_md)
    
    def convert_md_to_pdf(self, md_path='legal_opinion.md', pdf_path='legal_opinion.pdf'):
        print(md_path)
        os.path.exists(md_path)
        """Convert markdown to PDF using pypandoc."""
        pypandoc.convert_file(
            md_path,
            to="pdf",
            format="md",
            outputfile=pdf_path,
            extra_args=["--standalone", "--pdf-engine=wkhtmltopdf"]
        )
        return pdf_path

