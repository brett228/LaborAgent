"""
고용노동부 빠른인터넷 상담 크롤링 모듈
"""

from bs4 import BeautifulSoup
import hashlib
import json
import requests
import time


# -------------------------
# 0) URL / 환경 설정
# -------------------------

BASE_LIST_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"
BASE_URL = "https://www.moel.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}
OUTPUT_JSON = "fastcounsel_incremental.json"

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
# 2) 변경 감지용 hash 계산
# -------------------------
def compute_hash(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()

# -------------------------
# 3) 리스트 페이지 XHR 요청 (HTML 예시)
# -------------------------
def fetch_list_page(page_index):
    params = {"pageIndex": page_index}
    resp = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=30)
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
        tds = tr.select("td")
        qnum = tds[0].get_text(strip=True)
        title = tds[1].get_text(strip=True)
        link_tag = tds[1].find("a")
        link = BASE_URL + link_tag["href"] if link_tag else ""
        date = tds[2].get_text(strip=True)
        state = tds[3].get_text(strip=True) if len(tds) > 3 else "미완료"

        items.append({
            "qnum": qnum,
            "title": title,
            "link": link,
            "date": date,
            "state": state
        })
    return items

# -------------------------
# 5) 상세 페이지 크롤링
# -------------------------
def fetch_detail(link):
    try:
        resp = requests.get(link, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html5lib")
        dls = soup.select("dl")

        dls = soup.select("dl")
        if not dls:
            return {"question": "", "answer": ""}

        # 모든 dl에서 dd만 추출
        dd_q = dls[0].select("dd")  # 첫 번째 dl 기준
        dd_a = dls[1].select("dd")  # 첫 번째 dl 기준
        # print("dls: ", len(dls))
        # print("dls0: ", dls[0], "\n", "dls1: ", dls[1])
        # print("dls0: ",(dls[0].select("dd")[0]))
        # print("dls1: ",(dls[1].select("dd")[0]))
        # print("dd_elements: ", len(dd_elements))
        # for dd in dls[0].select("dd"):
        #     print(dd)
        # for dd in dls[1].select("dd"):
        #     print(dd)
        
        question = dd_q[0].get_text(strip=True) if len(dd_q) > 0 else ""
        answer = dd_a[0].get_text(strip=True) if len(dd_a) > 0 else ""
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
        text_hash = compute_hash(item["title"] + item["state"])
        prev_hash = previous[qnum]["hash"] if qnum in previous else None

        # 신규 또는 상태 변경
        if qnum not in previous or text_hash != prev_hash:
            # 상세 페이지 가져오기
            detail = fetch_detail(item["link"])
            updated[qnum] = {
                "list": item,
                "detail": detail,
                "hash": text_hash
            }
            print(f"[UPDATE] {qnum} {item['title']}")
    return list(updated.values())

# -------------------------
# 7) 메인
# -------------------------
def main(max_pages=80):
    previous = load_previous(OUTPUT_JSON)
    all_new = []

    for page_index in range(1, max_pages + 1):
        html = fetch_list_page(page_index)
        page_items = parse_list_page(html)
        all_new.extend(page_items)
        time.sleep(0.2)  # 부하 최소화

    merged = merge_incremental(previous, all_new)

    # 저장
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"[DONE] 총 {len(merged)}개 항목 저장 완료.")

if __name__ == "__main__":
    main(max_pages=2)
