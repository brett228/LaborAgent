"""
고용노동부 빠른인터넷 상담 크롤링 모듈
"""

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import json
import time
import re
import urllib.parse
import os

# 크롤링할 기본 URL
BASE_URL = "https://www.moel.go.kr"
BASE_LIST_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"

# 요청 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
}



def load_previous_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        old = json.load(f)
        # qnum 기준으로 dict 매핑
        return { item["list"]["qnum"]: item for item in old }


def merge_incremental(previous_dict, new_items):
    """
    previous_dict: 기존 JSON을 qnum 기준 dict 형태로 만든 것
    new_items: 이번에 수집한 collected 리스트
    """
    updated_items = previous_dict.copy()

    for item in new_items:
        qnum = item["list"]["qnum"]
        new_state = item["list"]["state"]

        if qnum not in previous_dict:
            # 신규 항목
            updated_items[qnum] = item
            print(f"[NEW] 신규 질문 추가: {qnum} {item['list']['title']}")
            continue
        
        # 기존 항목
        old_state = previous_dict[qnum]["list"]["state"]

        # 미완료 → 답변완료 변경 확인
        if old_state != "답변완료" and new_state == "답변완료":
            updated_items[qnum] = item
            print(f"[UPDATE] 답변완료로 갱신: {qnum} {item['list']['title']}")
            continue

        # 그 외는 변경 없음 (skip)
    
    # dict → list로 변환
    return list(updated_items.values())


def parse_detail(page):
    """
    상세 페이지에서 질의(dt)와 답변(dd)을 파싱합니다.
    """
    try:
        # dl 태그 찾기
        dl_element = page.query_selector_all("dl")
        
        if not dl_element:
            body_text = page.inner_text("body")
            if "죄송합니다" in body_text or "요청 하셨습니다" in body_text:
                return {"question": "[ERROR] 접근 불가 페이지", "answer": ""}
            return {"question": "[WARN] dl 태그를 찾을 수 없음", "answer": ""}
        
        # dt (질의) 파싱
        dt_element = dl_element[0].query_selector("dd")
        question = dt_element.inner_text().strip() if dt_element else "[WARN] 질의 없음"
        
        # dd (답변) 파싱
        dd_element = dl_element[1].query_selector("dd")
        answer = dd_element.inner_text().strip() if dd_element else "[WARN] 답변 없음"
        
        print('question: ', question)
        print('answer: ', answer)
        return {"question": question, "answer": answer}
        
    except Exception as e:
        return {"question": "[ERROR] 파싱 중 예외 발생", "answer": str(e)}


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
                qnum = tr.query_selector("td:nth-child(1)")
                a = tr.query_selector("td:nth-child(2) a")
                date_td = tr.query_selector("td:nth-child(3)")
                state_td = tr.query_selector("td:nth-child(4)")
                if a:
                    items_to_process.append({
                        "qnum": qnum.inner_text().strip(),
                        "title": a.inner_text().strip(),
                        "date": date_td.inner_text().strip(),
                        "state": state_td.inner_text().strip() if state_td else "미완료",
                    })
            
            # 2. 추출된 정보를 순회하며 상세 크롤링
            for item in items_to_process:
                qnum = item['qnum']
                title = item['title']
                date = item['date']
                state = item['state']
                href = "인페이지 클릭 실패"
                
                print(f"  + 상세 수집 시도 (클릭): {title}")

                try:
                    # 1. 목록 페이지 재접속 (DOM 컨텍스트 복원)
                    list_page.goto(f"{BASE_LIST_URL}?pageIndex={page_index}", timeout=30000)
                    time.sleep(1.0) 

                    # 2. 해당 A 태그를 제목 텍스트로 다시 찾습니다.
                    a_locator = list_page.locator("td:nth-child(2) a", has_text=title).first
                    href = BASE_URL + a_locator.get_attribute('href')
                    
                    if not a_locator.is_visible():
                        print(f"    [warn] 링크 요소를 다시 찾는 데 실패: {title}")
                        continue
                        
                    # 3. 클릭 및 강제 대기
                    a_locator.click(timeout=10000)
                    
                    print("    [debug] 5초간 강제 대기 시작...")
                    time.sleep(5.0)
                    print("    [debug] 강제 대기 종료. 파싱 시도.")

                    # 4. 파싱 수행
                    detail = parse_detail(list_page)

                except Exception as e:
                    error_msg = str(e).split('\n')[0]
                    print(f"[warn] 항목 처리 중 예외 발생 (클릭/파싱 문제): {error_msg}")
                    detail = {"question": title, "answer": f"[ERROR] 클릭 또는 파싱 중 예외: {error_msg}"}
                    href = "클릭 실패"
                
                # 수집된 정보 저장
                collected.append({
                    "list": {"qnum": qnum, "title": title, "date": date, "state": state, "link": href},
                    "detail": {"question": detail["question"], "answer": detail["answer"]}
                })

                time.sleep(delay) 
                
        browser.close()

    # JSON 저장
    # 1) 기존 JSON 로드
    previous = load_previous_json(output_json)

    # 2) 신규 + 변경 항목만 반영하여 merge
    merged = merge_incremental(previous, collected)

    # 3) 최종 저장
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n[done] ✨ 수집 완료 (증분 반영): 기존 {len(previous)} → 현재 {len(merged)} 개")



if __name__ == "__main__":
    crawl(max_pages=1, delay=1.5)