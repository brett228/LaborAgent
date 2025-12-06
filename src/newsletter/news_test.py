from nicegui import ui, events
import asyncio
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# -----------------------------
# 1. CONFIG
# -----------------------------
API_KEY = "YOUR_GOOGLE_API_KEY"
CX = "YOUR_CSE_ID"
OPENAI_API_KEY = "YOUR_OPENAI_KEY"

client = OpenAI(api_key=OPENAI_API_KEY)


# -----------------------------
# 2. GOOGLE SEARCH
# -----------------------------
async def google_search(query: str):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": API_KEY,
        "cx": CX,
        "q": query,
        "num": 10,
    }

    res = requests.get(url, params=params).json()
    results = []

    for item in res.get("items", []):
        results.append({
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "link": item.get("link"),
        })
    return results


# -----------------------------
# 3. ARTICLE CRAWLER
# -----------------------------
async def fetch_article_text(url: str) -> str:
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        paras = soup.find_all("p")
        text = "\n".join(p.get_text(strip=True) for p in paras)
        return text
    except Exception as e:
        return f"(크롤링 실패) {e}"


# -----------------------------
# 4. SUMMARY GENERATOR
# -----------------------------
async def generate_newsletter(article_text: str) -> str:
    prompt = f"""
당신은 뉴스레터 작성 전문가입니다.
아래 기사 전체 내용을 읽고 다음 형식으로 요약하세요:

- 핵심 요약 (3줄)
- 주요 배경
- 현재 논점
- 이해관계자 영향
- 앞으로의 전망
- 한 문장 요약

기사 내용:
{article_text}
"""

    rsp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return rsp.choices[0].message["content"]


# -----------------------------
# 5. NICEGUI UI
# -----------------------------
ui.markdown("## 🔍 뉴스 검색 에이전트 (NiceGUI + async)")
ui.markdown("검색 → 기사 선택 → 뉴스레터 생성 과정을 순차적으로 진행합니다.")

query_input = ui.input(label="검색어 입력", placeholder="예: 노동 정책, 임금 협상 ...")
search_button = ui.button("검색")

results_container = ui.column()
newsletter_output = ui.markdown("")


# 검색 버튼 클릭 이벤트 (수정됨)
async def on_search(e: events.ClickEventArguments):
    keyword = query_input.value.strip()
    if not keyword:
        ui.notify("검색어를 입력하세요.")
        return

    results_container.clear()
    newsletter_output.set_content("")

    ui.notify("검색중...")

    results = await google_search(keyword)

    if not results:
        ui.notify("검색결과 없음")
        return

    ui.markdown("### 📄 검색 결과", parent=results_container)

    for idx, r in enumerate(results):
        with results_container:
            with ui.row().classes("items-start"):
                ui.markdown(f"**{r['title']}**\n\n{r['snippet']}")
                ui.button(
                    "선택",
                    on_click=lambda e, url=r["link"]: asyncio.create_task(on_select(url))
                )


search_button.on('click', on_search)


# 기사 선택 시 실행되는 로직
async def on_select(url: str):
    ui.notify("기사 크롤링 중…")

    article_text = await fetch_article_text(url)

    ui.notify("요약 생성 중…")

    summary = await generate_newsletter(article_text)

    newsletter_output.set_content(f"### 📰 생성된 뉴스레터\n\n{summary}")


ui.run(reload=False)
