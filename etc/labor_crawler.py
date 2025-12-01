from playwright.sync_api import sync_playwright
import json
import time

BASE_URL = "https://labor.moel.go.kr"
LIST_PAGE = f"{BASE_URL}/cmmt/iqrs_list.do"

def fetch_list_rows(page):
    """
    페이지 로딩 후 리스트 테이블의 row들을 반환
    """
    page.goto(LIST_PAGE)
    # 네트워크가 안정될 때까지 대기
    page.wait_for_load_state("networkidle")
    # JS 렌더링이 끝날 때까지 잠시 대기
    time.sleep(1.5)

    # 테이블 row 선택
    rows = page.query_selector_all("table.board_list tbody tr")
    return rows

def parse_row(row):
    """
    row에서 데이터 추출
    """
    cells = row.query_selector_all("td")
    if len(cells) < 4:
        return None
    a_tag = cells[1].query_selector("a")
    if not a_tag:
        return None
    title = a_tag.inner_text().strip()
    href = a_tag.get_attribute("href")
    full_link = BASE_URL + href
    date = cells[-1].inner_text().strip()
    return {"title": title, "link": full_link, "date": date}

def fetch_detail(page, url):
    """
    상세 페이지에서 질문/답변 추출
    """
    page.goto(url)
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)  # JS 렌더링 대기

    question_el = page.query_selector(".question_section")
    answer_el = page.query_selector(".answer_section")

    question = question_el.inner_text().strip() if question_el else ""
    answer = answer_el.inner_text().strip() if answer_el else ""
    return {"question": question, "answer": answer}

def main(total_pages=2, delay=0.5):
    all_data = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 실제 브라우저 확인 가능
        page = browser.new_page()

        for pg in range(1, total_pages + 1):
            print(f"[PAGE] {pg}")
            rows = fetch_list_rows(page)

            for row in rows:
                item = parse_row(row)
                if not item:
                    continue
                print(f"  Fetching detail: {item['title']}")
                try:
                    detail = fetch_detail(page, item["link"])
                except Exception as e:
                    print(f"    Failed to fetch detail for {item['link']}: {e}")
                    continue
                record = {
                    "title": item["title"],
                    "date": item["date"],
                    "link": item["link"],
                    "question": detail["question"],
                    "answer": detail["answer"]
                }
                all_data.append(record)
                time.sleep(delay)

            # 다음 페이지 버튼 클릭
            try:
                next_btn = page.query_selector(f"a[onclick*='fn_goPage({pg+1})']")
                if next_btn:
                    next_btn.click()
                    time.sleep(1)
                else:
                    print(f"Page button {pg+1} not found, skipping")
                    break
            except Exception as e:
                print(f"Failed to go to next page: {e}")
                break

        browser.close()

    # JSON 저장
    with open("moel_iqrs_browser.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_data)} records.")

if __name__ == "__main__":
    main(total_pages=5, delay=0.5)
