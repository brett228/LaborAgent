import requests
from bs4 import BeautifulSoup
import time

BASE_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YourBot/1.0; +youremail@example.com)"
}

def fetch_list(page_index=1, rows_per_page=20, search_text=None, status=None):
    params = {
        "pageIndex": page_index,
        "pageUnit": rows_per_page,  # 혹은 "pageSize" 또는 비슷한 이름
    }
    if search_text:
        params["searchText"] = search_text
    if status:
        params["status"] = status  # 예: "답변완료", "미완료"
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_list(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    # 게시판 테이블의 rows 선택자 조정
    table = soup.select_one("table.board_list")  # 예시; 실제 클래스명 확인 필요
    if not table:
        # 다른 구조일 경우 리스트 형태 li 등
        items = soup.select(".fastcounselList li")
    else:
        items = table.select("tr")[1:]  # 헤더 제외

    for item in items:
        # 번호
        num_td = item.select_one("td.num")
        number = num_td.get_text(strip=True) if num_td else None

        # 제목 + 링크
        title_a = item.select_one("td.title a")
        title = title_a.get_text(strip=True) if title_a else None
        link = title_a["href"] if title_a and "href" in title_a.attrs else None

        # 등록일
        date_td = item.select_one("td.date")
        date = date_td.get_text(strip=True) if date_td else None

        # 답변 여부
        status_td = item.select_one("td.status")
        status = status_td.get_text(strip=True) if status_td else None

        rows.append({
            "number": number,
            "title": title,
            "link": link,
            "date": date,
            "status": status
        })
    return rows

def crawl_all(max_pages=100):
    all_items = []
    for page in range(1, max_pages + 1):
        html = fetch_list(page_index=page, rows_per_page=20)
        items = parse_list(html)
        if not items:
            break
        all_items.extend(items)
        print(f"Page {page} fetched, {len(items)} items.")
        time.sleep(1.0)
    return all_items

if __name__ == "__main__":
    data = crawl_all(max_pages=50)
    # 저장 예
    import csv
    with open("fastcounsel_list.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["number","title","link","date","status"])
        writer.writeheader()
        writer.writerows(data)
