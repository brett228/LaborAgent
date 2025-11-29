"""
고용노동부 질의회시 크롤링 모듈
"""

from bs4 import BeautifulSoup
import hashlib
import json
import re
import requests
import time



# -------------------------
# 0) URL / 환경 설정
# -------------------------

BASE_LIST_URL = "https://labor.moel.go.kr/cmmt/iqrs_list.do"
BASE_DETAIL_URL = "https://labor.moel.go.kr/cmmt/iqrs_detail.do?id="
BASE_URL = "https://labor.moel.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YourBot/1.0; +youremail@example.com)"
}

OUTPUT_JSON = "iqrs_incremental.json"

# -------------------------
# 1) 이전 JSON 불러오기
# -------------------------
def load_previous(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # qnum 기준 dict
            return {item["list"]["qnum"]: item for item in data}
    except FileNotFoundError:
        return {}

# -------------------------
# 3) 리스트 페이지 XHR 요청 (HTML 예시)
# -------------------------
def fetch_list_page(page_index):
    params = {"pageIndex": page_index}
    resp = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.text

# -------------------------
# 4) 리스트 파싱 (HTML)
# -------------------------
def parse_list_page(html):
    soup = BeautifulSoup(html, "html5lib")
    rows = soup.select("table tbody tr")
    items = []

    for tr in rows:
        if tr.find("th"):  # th 있는 행 제거
            continue
        tds = tr.select("td")
        
        qnum = tds[0].get_text(strip=True)
        title = tds[1].get_text(strip=True)
        link_tag = tds[1].find("a")["onclick"]
        link_id = re.search(r'fn_detail\((\d+)\)', link_tag).group(1)
        link = BASE_DETAIL_URL + link_id if link_tag else ""
        ref_no = tds[2].get_text(strip=True)
        date = tds[3].get_text(strip=True)

        items.append({
            "qnum": qnum,
            "title": title,
            "link": link,
            "ref_no": ref_no,
            "date": date,
        })
    return items

# -------------------------
# 5) 상세 페이지 크롤링
# -------------------------
def fetch_detail(link):
    try:
        resp = requests.get(link, headers=HEADERS, timeout=20, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html5lib")

        qbox = soup.find_all("dd", class_="qBox")
        abox = soup.find_all("dd", class_="aBox")

        dd_q = qbox[0].select("span") 
        dd_a = abox[0].select("p") 
        
        question = " ".join([dd_q[i].get_text(strip=True) for i in range(len(dd_q))]) if len(dd_q) > 0 else ""
        answer = " ".join([dd_a[i].get_text(strip=True) for i in range(len(dd_a))]) if len(dd_a) > 0 else ""
        print('q:', question)
        print('a:', answer)

        return {"question": question, "answer": answer}
    except Exception as e:
        return {"question": "[ERROR]", "answer": str(e)}

# -------------------------
# 6) 증분 merge
# -------------------------
def merge_incremental(previous, new_items):
    updated = previous.copy()
    for item in new_items:
        qnum = item["qnum"]
        # 신규 또는 상태 변경
        if qnum not in previous:
            # 상세 페이지 가져오기
            detail = fetch_detail(item["link"])
            updated[qnum] = {
                "list": item,
                "detail": detail,
            }
            print(f"[UPDATE] {qnum} {item['title']}")
    return list(updated.values())

# -------------------------
# 7) 메인
# -------------------------
def main(max_pages=None):
    previous = load_previous(OUTPUT_JSON)
    all_new = []

    page_index = 1
    while True:
        # Stop if we've reached max_pages (if max_pages is not None)
        if max_pages is not None and page_index > max_pages:
            break

        html = fetch_list_page(page_index)
        page_items = parse_list_page(html)

        # Stop if no more items on the page
        if not page_items:
            break

        all_new.extend(page_items)
        print(f"[INFO] Page {page_index} crawled, {len(page_items)} items")
        page_index += 1
        time.sleep(0.2)  # 부하 최소화

    merged = merge_incremental(previous, all_new)

    # 저장
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 총 {len(merged)}개 항목 저장 완료.")


if __name__ == "__main__":
    main()
