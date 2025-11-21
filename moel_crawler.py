# moel_fastcounsel_detail_scrape_final_v5.py

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import json
import time
import re

# 크롤링할 기본 URL
BASE_LIST_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"

# 요청 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
}

def parse_detail(page):
    """
    상세 페이지에서 제목과 내용을 파싱합니다.
    """
    title = ""
    try:
        # 제목 파싱
        title_selectors = ["h3", ".board_view_title", ".title", ".tit", ".view_tit"] 
        for selector in title_selectors:
            title_el = page.query_selector(selector)
            if title_el:
                title = title_el.inner_text().strip()
                break
                
        # 내용 파싱
        content_selectors = [".board_view_content", ".content_view", "article", ".view_content", "div.article"]
        content = ""
        for selector in content_selectors:
            content_el = page.query_selector(selector)
            if content_el:
                content = content_el.inner_text().strip()
                break
                
        # 내용 확인 및 에러 메시지 처리
        if not content:
            body_text = page.inner_text("body") 
            if "죄송합니다" in body_text or "요청 하셨습니다" in body_text:
                content = "[ERROR] 접근 불가 페이지로 확인됨"
            else:
                 content = "[WARN] 상세 내용 파싱 실패 (셀렉터 미일치)"
                 
        return {"title": title, "content": content}
        
    except Exception as e:
        return {"title": title, "content": f"[ERROR] 상세 파싱 중 예외 발생: {e}"}


def crawl(max_pages=3, delay=1.5, output_json="fastcounsel_with_detail.json"):
    collected = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="ko-KR")
        list_page = context.new_page()

        print(f"🚀 {BASE_LIST_URL} 접속 시도...")
        list_page.goto(BASE_LIST_URL, timeout=45000) 
        time.sleep(delay)

        for page_index in range(1, max_pages + 1):
            print(f"\n[info] 📋 처리중 목록 페이지 {page_index}")
            
            list_page.goto(f"{BASE_LIST_URL}?pageIndex={page_index}", timeout=45000)
            time.sleep(delay)

            try:
                list_page.wait_for_selector("table tbody tr", timeout=15000)
            except PWTimeout:
                print("[warn] 목록이 로드되지 않아 해당 페이지 건너뛰기.")
                continue
            
            # 1. 항목 정보 미리 추출
            rows = list_page.query_selector_all("table tbody tr")
            items_to_process = []
            for tr in rows:
                a = tr.query_selector("td:nth-child(2) a")
                date_td = tr.query_selector("td:nth-child(4)")
                
                if a:
                    items_to_process.append({
                        "title": a.inner_text().strip(),
                        "date": date_td.inner_text().strip() if date_td else "미확인",
                    })
            
            # 2. 추출된 정보를 순회하며 상세 크롤링
            for item in items_to_process:
                title = item['title']
                date = item['date']
                href = "인페이지 클릭 실패"
                
                print(f"  + 상세 수집 시도 (클릭): {title}")

                try:
                    # 1. 목록 페이지 재접속 (DOM 컨텍스트 복원)
                    list_page.goto(f"{BASE_LIST_URL}?pageIndex={page_index}", timeout=30000)
                    time.sleep(1.0) 

                    # 2. 해당 A 태그를 제목 텍스트로 다시 찾습니다.
                    a_locator = list_page.locator("td:nth-child(2) a", has_text=title).first
                    
                    if not a_locator.is_visible():
                        print(f"    [warn] 링크 요소를 다시 찾는 데 실패: {title}")
                        continue
                        
                    # ⭐⭐⭐ 3. 클릭 및 강제 대기 (타임아웃 우회) ⭐⭐⭐
                    a_locator.click(timeout=10000)
                    
                    print("    [debug] 5초간 강제 대기 시작...")
                    time.sleep(5.0) # Playwright의 대기 기능 대신 무조건 5초 대기
                    print("    [debug] 강제 대기 종료. 파싱 시도.")

                    # 4. 파싱 수행
                    detail = parse_detail(list_page)
                    href = list_page.url 

                except Exception as e:
                    error_msg = str(e).split('\n')[0]
                    print(f"[warn] 항목 처리 중 예외 발생 (클릭/파싱 문제): {error_msg}")
                    detail = {"title": title, "content": f"[ERROR] 클릭 또는 파싱 중 예외: {error_msg}"}
                    href = "클릭 실패"
                
                # 수집된 정보 저장
                collected.append({
                    "list": {"title": title, "date": date, "link": href},
                    "detail": {"title": detail["title"], "content": detail["content"]}
                })

                time.sleep(delay) 
                
        browser.close()

    # JSON 저장
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(collected, f, ensure_ascii=False, indent=2)

    print(f"\n[done] ✨ 수집 완료: {len(collected)}개 항목 → **{output_json}**")

if __name__ == "__main__":
    # 딜레이를 1.5초로 유지하여 서버 부하를 줄입니다.
    crawl(max_pages=2, delay=1.5)