from datetime import datetime
import json
import math
import os
import streamlit as st

from src.embeddings import get_embedding
from src.rag.load_index import load_chroma_collection, search_vector_store
from src.newsletter.news_searcher import search_all_newslist, search_all_text
from src.newsletter.policy_search import search_press_release
from src.newsletter.newsletter_renderer import NewsletterRenderer
from src.utils.storage import save_html
from openai import OpenAI


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# KK = NewsletterAgent()
# KK.run()
# KK.state['articles']

class NewsletterAgent:
    PHASE_ASK_NEWS_TOPIC = "ask_news_topic"
    PHASE_SET_NEWS_TOPIC = "set_news_topic"
    PHASE_NEWS_SEARCH = "news_search" # User input triggers search, returns options
    PHASE_AWAITING_NEWS_PICK = "awaiting_news_pick"
    PHASE_AWAITING_CONSULT_PICK = "awaiting_consult_pick"
    PHASE_AWAITING_POLICY_PICK = "awaiting_policy_pick"
    PHASE_ASK_CONSULT_TOPIC = "ask_consult_topic"
    PHASE_SET_CONSULT_TOPIC = "set_consult_topic"
    PHASE_CONSULT_SEARCH = "consult_search" # User input triggers search, returns options
    PHASE_POLICY_SELECT = "policy_select" # This phase returns policy options
    PHASE_READY_TO_GENERATE = "ready_to_generate"

    def __init__(self):
        self.renderer = NewsletterRenderer()

        # 템플릿 구성 슬롯
        self.state = {
            "main_title": None,
            "news_topic": None,
            "consult_topic": None,
            "date": datetime.today().strftime('%Y.%m.%d'),
            "articles": [],
            "consult": [],
            "policy": []
        }

        self._raw_articles = None
        self._raw_consult = None
        self._selected_news_source = None
        self._selected_policy_items = None
        self._news_options = None
        self._consult_options = None

         # 멀티턴 진행 상태
        self._phase = self.PHASE_ASK_NEWS_TOPIC
        # ask_news_topic → news_search → ask_consult_topic → consult_search → policy_select → ready_to_generate
    
    def reset_state(self):
        """Resets all transient state variables for a new document generation session."""
        self.state = {
            "main_title": None,
            "news_topic": None,
            "consult_topic": None,
            "date": datetime.today().strftime('%Y.%m.%d'),
            "articles": [],
            "consult": [],
            "policy": []
        }
        self._raw_articles = None
        self._raw_consult = None
        self._selected_news_source = None
        self._selected_policy_items = None
        self._news_options = None
        self._consult_options = None
        self._phase = self.PHASE_ASK_NEWS_TOPIC

    def run_steps(self, user_input: str):
        # Check for the INITIAL state first, regardless of user input content.
        print('### 뉴스레터 작성 에이전트 시작 ###')
        if self._phase == self.PHASE_ASK_NEWS_TOPIC:
            # 1st Turn: User initiated the process. Transition to phase 2 (awaiting subject).
            self._phase = self.PHASE_SET_NEWS_TOPIC
            print('setting news topic...')
            return {"type": "message", "content": "뉴스레터의 [**주목할 만한 뉴스**] 섹션을 위한 검색 **주제**를 입력해 주시기 바랍니다."}
        # --- PHASE 2: RECEIVING THE SUBJECT (This is where the search should run) ---
        elif self._phase == self.PHASE_SET_NEWS_TOPIC:
            if not user_input or user_input.lower() in ["뉴스레터를 작성해줘", "시작", ""]:
                # If the user somehow repeats the trigger, or provides empty input, ask again.
                return {"type": "message", "content": "주제를 명확히 입력해 주셔야 검색을 진행할 수 있습니다."}
            
            # Case: User has provided a subject (e.g., "산재"). Execute search immediately.
            self.state["news_topic"] = user_input

            # Execute search
            print('searching news...')
            results = self.search_news_sources(user_input)
            self._news_options = results
            
            # Transition to waiting for the user to pick one of the options
            self._phase = self.PHASE_AWAITING_NEWS_PICK
            return {"type": "options_news", "content": results, "message": f"'{user_input}'(으)로 검색된 뉴스 기사 목록입니다. **하나를 선택**해 주세요."}
        
        # --- PHASE 3/4: CONSULT TOPIC START/INPUT ---
        # This handles receiving the subject for the consulting section
        elif self._phase == self.PHASE_ASK_CONSULT_TOPIC:
            self._phase = self.PHASE_SET_CONSULT_TOPIC
            print('setting consulting topic...')
            return {"type": "message", "content": "이제 뉴스레터의 [**자문사례**] 섹션을 위한 검색 **주제**를 입력해 주시기 바랍니다."}

        elif self._phase == self.PHASE_SET_CONSULT_TOPIC:
            # Case: User provides consult subject. Execute search immediately.
            self.state["consult_topic"] = user_input
            
            results = self.search_consult_sources(user_input)
            self._consult_options = results
            
            self._phase = self.PHASE_AWAITING_CONSULT_PICK
            return {"type": "options_consult", "content": results, "message": f"'{user_input}'(으)로 검색된 노무 상담 사례 목록입니다. **하나를 선택**해 주세요."}
        
        elif self._phase == self.PHASE_POLICY_SELECT:    
                # Execute search
            print('searching policy sources...')
            results = self.search_policy_sources() # <--- EXECUTES THE SEARCH
            self._selected_policy_items = results # <--- STORES THE RESULTS
            
            # Transition to the waiting phase for user selection
            self._phase = self.PHASE_AWAITING_POLICY_PICK
            return {
                "type": "options_policy", 
                "content": results, 
                "message": "마지막으로 뉴스레터에 포함할 [**정책 자료**]를 선택해주세요. (여러 개 선택 가능)"
            }
                    
        # 5. FINAL GENERATION
        elif self._phase == self.PHASE_READY_TO_GENERATE:
            # Check if user input is the trigger to run final generation
            if "생성" in user_input.lower() or "generate" in user_input.lower():
                html = self.run() 
                # Reset phase after successful generation
                self.reset_state()
                return {"type": "newsletter", "content": html}
            else:
                return {"type": "message", "content": "뉴스레터 생성을 원하시면 '생성'을 입력해주세요."}

        # --- PHASE 6: Awaiting pick (Handled by app.py UI, Agent just waits) ---
        elif self._phase in [self.PHASE_AWAITING_NEWS_PICK, self.PHASE_AWAITING_CONSULT_PICK, self.PHASE_AWAITING_POLICY_PICK]:
            print('awating user pick...')
            return {"type": "message", "content": f"시스템 대기 중입니다. 사용자에게 선택지 제시 중입니다. (현재: {self._phase})"}
        
        else:
            return {"type": "message", "content": "알 수 없는 단계입니다."}

    # ===========================
    # 1) 뉴스 검색 및 선택
    # ===========================
    def search_news_sources(self, topic: str):
        self.state["news_topic"] = topic
        return search_all_newslist(topic)

    def choose_news_source(self, selected_title):

        if not self._news_options:
            raise Exception("뉴스 옵션이 없습니다. 먼저 검색을 실행해야 합니다.")

        chosen = next(item for item in self._news_options if item["title"] == selected_title)
        self._selected_news_source = chosen
        self._raw_articles = search_all_text(chosen)

        self._phase = self.PHASE_ASK_CONSULT_TOPIC
        return chosen

    # ===========================
    # 2) 자문사례 검색 및 선택
    # ===========================
    def search_consult_sources(self, topic: str):
        moel_iqrs = load_chroma_collection(
            load_dir="db/chroma_index",
            collection_name="moel_iqrs"
        )[0]

        results = search_vector_store(
            collection=moel_iqrs,
            query=topic,
            get_embedding_fn=get_embedding,
            top_k=5
        )   
        return results

    def choose_consult_source(self, selected_title):
        if not self._consult_options:
            raise Exception("상담 사례 옵션이 없습니다. 먼저 검색을 실행해야 합니다.")
        
        chosen = next(item for item in self._consult_options if item.startswith(f"Title: {selected_title}"))
        self._raw_consult = chosen

        self._phase = self.PHASE_POLICY_SELECT
        return chosen
    
    # ===========================
    # 3) 정책자료 검색 및 선택
    # ===========================
    def search_policy_sources(self, max_page=3):
        results = search_press_release(max_page)
        self._selected_policy_items = results 
        return results

    def choose_policy(self, selected_items):
        self._selected_policy_items = selected_items        
        self._phase = self.PHASE_READY_TO_GENERATE

    # ===========================
    # 4) 메인 타이틀 생성
    # ===========================
    def create_main_title(self):
        today = datetime.today()
        year, month, day = today.year, today.month, today.day
        first_day = datetime(year, month, 1)
        # Calculate week number (Assuming you want the nth week of the month)
        week_number = math.ceil((day + first_day.weekday()) / 7) 

        self.state["main_title"] = f"[화안HR] {year}년 {month}월 {week_number}주차 뉴스레터"
        return self.state["main_title"]
    
    # ===========================
    # 5) 기사 생성 섹션
    # ===========================
    def create_article_section(self): 
        print("\n[기사 섹션 구성]")
        if self._raw_articles is None:
            raise ValueError("기사 전문이 없습니다. choose_news_source() 먼저 실행하세요.")

        session = []
        directive = """
        당신은 인사/노무 관련 뉴스기사를 기반으로 뉴스레터를 작성하기 위해 기사를 요약 정리하는 에이전트입니다.
        다음 규칙에 따라 사용자가 요청한 작업을 수행합니다.

        1. 공통 규칙
          - 항상 한글로만 대답합니다.
          - 욕설과 비속어는 사용하지 않습니다.
          - 당신의 답변은 주어진 뉴스기사에만 근거해야 합니다.
            단, 답변과 관련한 근거를 국가법령정보센터(www.law.go.kr)로부터 검색하여 사용할 수는 있습니다.
          - '~입니다.', '~습니다'와 같은 격식을 갖춘 어미로 구성된 존대말를 사용합니다.
            절대로 “~다”, “~요”, “합니다”, “해요”, “합니다요”, "~임", "~음" 등의 어미를 사용하지 않습니다.
          - 문단 사이에 적절히 줄바꿈을 하고 줄바꿈 시 줄바꿈 문자를 적용합니다.(\n\n)
        
        2. 주어진 기사의 전문을 바탕으로 기사의 요약과 시사점을 출력합니다.
            항상 아래 JSON형식으로만 출력하세요:
            {
                "summary": "...",
                "implication": "...",
            } 

        3. 먼저 기사의 요약은 전문을 1000자 내외 분량으로 요약하여 답변을 구성합니다.
           답변 예시는 다음과 같습니다.
           "드라마 보조 작가의 웹소설 연재나 번역 업무 종사자의 외주 번역처럼, 근로시간 외의 겸직 활동을 기업이 어디까지 제한할 수 있는지에 대한 기준은 여전히 불명확한 상황입니다. 기업들은 주로 회사의 이익 침해 위험 차단, 특히 지식·창작 기반 업종에서는 정보 누출 우려 때문에 겸직금지 조항을 설정합니다.
           
           그러나 겸직금지는 법률에 명시된 제도가 아니며, 그 근거는 근로자의 성실 의무를 해석하는 데 있을 뿐입니다. 이 조항은 근로자의 직업 선택의 자유를 제한하기 때문에, 법원은 근로시간 외의 활동에 대해 매우 엄격하게 심사하며 제한적으로만 제재를 인정합니다.
           
           전문가들은 겸직금지 조항의 제한 폭이 넓지 않다고 설명합니다. 법적으로 제재가 가능한 핵심 기준은 겸직 활동이 회사의 '영업비밀'과 연관이 있는지, 그리고 그 유출 가능성을 높이는지입니다. 예를 들어, 드라마 보조 작가가 퇴근 후 웹소설을 쓰는 것은 시장을 직접 잠식하거나 영업상 불이익을 주는 구조가 아니므로 현실적으로 문제 삼기 어렵습니다.
           
           겸직금지 위반을 이유로 해고가 이뤄지는 경우, 법원은 해고의 정당성을 인정하지 않는 경우가 많습니다. 겸직 자체가 징계 사유는 될 수 있으나, 대부분 경고나 감봉 등 가벼운 징계에 그치며, 해고까지 인정되려면 영업비밀 유출, 불법행위, 또는 기업 신뢰의 중대한 침해가 수반되어야 한다는 것이 법원의 일관된 입장입니다. 회사가 보호할 가치가 있는 영업비밀과 무관한 추상적인 조항으로 과도하게 제한하려는 시도는 법원에서 인정되지 않을 가능성이 높습니다."
        
        4. 다음으로 기사로부터 인사/노무 업무 상의 시사점을 도출하여 500자 내외로 답변합니다.
           답변 예시는 다음과 같습니다. 시사점 앞에는 항상 '※' 기호를 넣습니다. 
           "※ 법원은 근로자의 직업 선택의 자유를 강하게 보호하므로, 기업은 영업비밀 보호라는 명확한 목적 하에 겸직금지 조항을 운영해야 합니다. 따라서 추상적인 전면 금지 규정을 지양하고, 회사의 핵심 이익을 훼손하는 행위를 구체적으로 특정하여 제한하는 방향으로 규정을 정비해야 합니다. 또한, 겸직 위반 시 징계 양정의 과도함이 문제되지 않도록 해고는 중대한 사안에만 적용하고 경미한 위반은 경고 등 낮은 수위에 그치도록 징계 기준의 균형을 맞추는 것이 핵심입니다."
 
        """
        session = [
            {"role": "system", "content": directive},
            {"role": "user", "content": f"뉴스 기사 전문:\n{self._raw_articles}"}
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session,
            response_format={"type": "json_object"},
            )
        
        parsed = json.loads(response.choices[0].message.content)

        result = {
            "title": self._selected_news_source["title"],
            "date": self._selected_news_source["date"],
            "content": parsed["summary"],
            "implication": parsed["implication"],
            "link": self._selected_news_source["link"],
        }

        self.state["articles"] = [result]
        return result
    
    # ===========================
    # 6) 컨설팅 섹션
    # ===========================
    def create_consult_section(self):
        print("\n[컨설팅 영역 구성]")
        if self._raw_consult is None:
            raise ValueError("상담사례 원문이 없습니다. choose_consult_source() 먼저 실행하세요.")

        session = []
        directive = """
        당신은 인사/노무 관련 뉴스기사를 기반으로 뉴스레터를 작성하기 위해 질의응답을 정리하는 에이전트입니다.
        다음 규칙에 따라 사용자가 요청한 작업을 수행합니다.

        1. 공통 규칙
          - 항상 한글로만 대답합니다.
          - 욕설과 비속어는 사용하지 않습니다.
          - 당신의 답변은 주어진 질의응답 원문에만 근거해야 합니다.
            단, 답변과 관련한 근거를 국가법령정보센터(www.law.go.kr)로부터 검색하여 사용할 수는 있습니다.
          - '~입니다.', '~습니다'와 같은 격식을 갖춘 어미로 구성된 존대말를 사용합니다.
            절대로 “~다”, “~요”, “합니다”, “해요”, “합니다요”, "~임", "~음" 등의 어미를 사용하지 않습니다.
            다만, 질문 작성 부분에 한해 "~요?"와 같은 친근한 어투로 작성합니다.
          - 원문에 나온 내용을 그대로 쓰지 않고, 적절히 수정합니다. 일반적인 사례로 읽히도록 해야하므로
            '귀하', '귀 질의'와 같은 표현은 쓰지 않습니다.
          - 문단 사이에 적절히 줄바꿈을 하고 줄바꿈 시 html 줄바꿈 문자를 적용합니다.(<br>)
        
        2. 주어진 질의응답 전문을 바탕으로 질문과 그에 대한 응답을 매끄럽게 정리하여 json 형식으로 출력합니다.
            항상 아래 JSON형식으로만 출력하세요:
            {
                "question": "...",
                "answer": "...",
            } 

        3. 주어진 질의응답 원문에 나타난 질문을 한 문장의 의문문으로 정리합니다.
           답변 예시는 다음과 같습니다.
           "question": "Q. 회사가 징계절차를 개시하면서 징계혐의자의 징계회부사실을 회사 게시판에 공지해도 되나요?",

        4. 주어진 질의응답 원문에 나타난 답변을 다듬어 1500자 내외로 답변합니다. 답변의 마지막에는 관련 참조문서 번호와 회시 일자를 괄호 안에 표기합니다.
           답변 예시는 다음과 같습니다.

           "answer": "형법은 명예훼손죄에 관하여 “공연히 사실을 적시하여 사람의 명예를 훼손”하는 행위가 “진실한 사실로서 오로지 공공의 이익에 관한 때에는 처벌하지 아니한다”고 규정하고 있습니다(형법 제307조, 제310조). 회사 담당자가 특정 직원에 대한 징계절차를 개시하면서 그의 징계혐의와 징계회부사실을 사내 게시판에 게재하여 구성원에게 공지하는 경우, 그러한 공지의 목적이 조직 내 향후 유사사례 재발 방지 등이라는 이유로 ‘공공의 이익에 관한 때’에 해당하여 명예훼손죄의 위법성이 조각되는 경우로 볼 수 있는지 살펴보겠습니다. 
           
           대법원은 “공연히 사실을 적시하여 사람의 명예를 훼손하는 행위가 진실한 사실로서 오로지 공공의 이익에 관한 때에는 형법 제310조에 따라 처벌할 수 없다”고 하면서, “공공의 이익에 관한 것에는 널리 국가·사회 기타 일반 다수인의 이익에 관한 것뿐만 아니라 특정한 사회집단이나 그 구성원 전체의 관심과 이익에 관한 것도 포함”된다는 입장입니다(대법원 2021.8.26. 선고 2021도6416 판결). 해당 판결에서 대법원은 징계회부를 한 후 곧바로 징계혐의사실과 징계회부사실을 회사 게시판에 게시한 행위가 ‘회사 내부의 원활하고 능률적인 운영의 도모’라는 공공의 이익에 관한 것이라고 판단한 원심이 명예훼손죄에서의 ‘공공의 이익’에 관한 법리를 오해하였다고 하면서, “회사 징계절차가 공적인 측면이 있다고 해도 징계절차에 회부된 단계부터 그 과정 전체가 낱낱이 공개되어야 하는 것은 아니고, 징계혐의 사실은 징계절차를 거친 다음 일응 확정되는 것이므로 징계절차에 회부되었을 뿐인 단계에서 그 사실을 공개함으로써 피해자의 명예를 훼손하는 경우, 이를 사회적으로 상당한 행위라고 보기는 어렵고, 그 단계에서의 공개로 원심이 밝힌 공익이 달성될 수 있을지도 의문”이라고 판단하여 원심을 파기하였습니다. 
           
           따라서, 질의의 경우와 같이 징계절차를 개시하면서 징계혐의자의 징계회부사실을 회사 게시판에 공지하는 행위는 형법상 명예훼손죄의 위법성이 조각되는 경우에 해당하지 않아 형사처벌 대상이 될 수 있으므로 유의하실 필요가 있겠습니다. (근로기준정책과-2211, 2023.07.04)"
 
        """
        session = [
            {"role": "system", "content": directive},
            {"role": "user", "content": f"질의회시 전문:\n{self._raw_consult}"}
            ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=session,
            response_format={"type": "json_object"},
            )
        parsed = json.loads(response.choices[0].message.content)

        result = {
            "question": parsed["question"],
            "answer": parsed["answer"],
        }

        self.state["consult"] = result
        return result
    
    # ===========================
    # 7) 정책자료 섹션
    # ===========================
    def create_policy_section(self):
        html_text = "<br>".join(
            f"■ {item['title']} (<a href='{item['link']}'>고용노동부</a>)"
            for item in self._selected_policy_items
        )
        self.state["policy"] = html_text
        return html_text
    
    # ===========================
    # 8) HTML 렌더링 & 저장
    # ===========================
    def render_html(self):
        html = self.renderer.render(self.state)
        save_html("newsletter.html", html)
        print("HTML 파일이 newsletter.html 로 저장되었습니다.")
        return html
    
    # ===========================
    # 9) 전체 실행 run()
    # ===========================
    def run(self):
        print("\n=== 뉴스레터 생성 프로세스 시작 ===")
        if self._phase != self.PHASE_READY_TO_GENERATE:
            raise ValueError("아직 모든 선택이 완료되지 않았습니다.")

        self.create_main_title()
        self.create_article_section()
        self.create_consult_section()
        self.create_policy_section()

        # 1. Capture the final HTML content
        final_html_content = self.render_html()

        print("\n### 뉴스레터 생성이 완료되었습니다! ###")
        
        # 2. Return the HTML content inside the 'newsletter' key
        return final_html_content
