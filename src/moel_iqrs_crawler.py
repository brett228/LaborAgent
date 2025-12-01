"""
고용노동부 질의회시 크롤링 모듈
"""

from bs4 import BeautifulSoup
import json
import re
import requests
import time
import sqlite3
import datetime
from pathlib import Path
import sys
import urllib3
from src.embeddings import get_embedding
from src.rag.build_index import add_documents


# -------------------------
# 0) URL / 환경 설정
# -------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path.cwd()

OUTPUT_JSON = "iqrs_incremental.json"
OUTPUT_DB = "iqrs.db"
JSON_PATH = BASE_DIR / "data" / OUTPUT_JSON
DB_PATH = BASE_DIR / "db"/ OUTPUT_DB
BASE_LIST_URL = "https://labor.moel.go.kr/cmmt/iqrs_list.do"
BASE_DETAIL_URL = "https://labor.moel.go.kr/cmmt/iqrs_detail.do?id="
BASE_URL = "https://labor.moel.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YourBot/1.0; +youremail@example.com)"
}



# -------------------------
# 0-1) DB 초기화
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iqrs_data (
            qnum TEXT PRIMARY KEY,
            title TEXT,
            question TEXT,
            answer TEXT,
            link TEXT,
            ref_no TEXT,
            date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# -------------------------
# 0-2) DB 저장
# -------------------------
def save_to_db(items):
    if not items:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    data_to_insert = []
    for item in items:
        # detail이 없는 경우 대비
        detail = item.get("detail", {})
        question = detail.get("question", "")
        answer = detail.get("answer", "")
        
        # list 정보
        if "list" in item:
            qnum = item["list"]["qnum"]
            title = item["list"]["title"]
            link = item["list"]["link"]
            ref_no = item["list"]["ref_no"]
            date = item["list"]["date"]
        else:
            continue

        data_to_insert.append((qnum, title, question, answer, link, ref_no, date))

    cur.executemany("""
        INSERT OR IGNORE INTO iqrs_data (qnum, title, question, answer, link, ref_no, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, data_to_insert)
    
    conn.commit()
    conn.close()
    print(f"[DB] Saved {len(data_to_insert)} items to {DB_PATH}")

# -------------------------
# 0-3) 임베딩 처리
# -------------------------
def process_embeddings(items):
    if not items:
        return

    # 텍스트 청크 생성
    chunks = []
    for item in items:
        if "list" not in item or "detail" not in item:
            continue
            
        q = item["detail"].get("question", "")
        a = item["detail"].get("answer", "")
        title = item["list"].get("title", "")
        link = item["list"].get("link", "")
        ref_no = item["list"].get("ref_no", "")
        
        # 문서 포맷팅
        text = f"Title: {title}\nQ: {q}\nA: {a}\nLink: {link}\nRef_no: {ref_no}"
        chunks.append(text)
    
    if chunks:
        print(f"[Embedding] Processing {len(chunks)} chunks...")
        add_documents(chunks, get_embedding, collection_name="iqrs")
        print("[Embedding] Done.")

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
# 2) 리스트 페이지 XHR 요청 (HTML 예시)
# -------------------------
def fetch_list_page(page_index):
    params = {"pageNum": page_index}
    resp = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.text

# -------------------------
# 3) 리스트 파싱 (HTML)
# -------------------------
def parse_list_page(html):
    soup = BeautifulSoup(html, "html5lib")
    rows = soup.select("table tbody tr")
    items = []
    
    for tr in rows:
        if tr.find("th"):  # th 있는 행 제거
            continue
        tds = tr.select("td")
        if len(tds) < 4:
            continue
        else:
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
# 4) 상세 페이지 크롤링
# -------------------------
def fetch_detail(link):
    try:
        resp = requests.get(link, headers=HEADERS, timeout=20, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html5lib")

        qbox = soup.find_all("dd", class_="qBox")
        abox = soup.find_all("dd", class_="aBox")

        dd_q = qbox[0].select("span") if qbox else []
        dd_a = abox[0].select("p") if abox else []
        
        question = " ".join([dd_q[i].get_text(strip=True) for i in range(len(dd_q))]) if len(dd_q) > 0 else ""
        answer = " ".join([dd_a[i].get_text(strip=True) for i in range(len(dd_a))]) if len(dd_a) > 0 else ""
        # print('q:', question)
        # print('a:', answer)

        return {"question": question, "answer": answer}
    except Exception as e:
        return {"question": "[ERROR]", "answer": str(e)}

# -------------------------
# 5) 증분 merge
# -------------------------
def merge_incremental(previous, new_items):
    updated = previous.copy()
    new_records = []

    for item in new_items:
        qnum = item["qnum"]
        if qnum not in previous:
            detail = fetch_detail(item["link"])
            record = {
                "list": item,
                "detail": detail,
            }
            new_records.append(record)
            updated[qnum] = record

    # 신규를 앞에 붙이고, 기존은 뒤로
    existing_records = [v for k, v in previous.items()]
    return new_records, new_records + existing_records

# -------------------------
# 6) 메인
# -------------------------
def main(max_pages=None):
    init_db() # DB 초기화
    
    previous = load_previous(JSON_PATH)
    existing_qnums = set(previous.keys())
    all_new = []

    page_index = 1
    stop_flag = False

    while True:
        # Stop if we've reached max_pages (if max_pages is not None)
        if max_pages is not None and page_index > max_pages:
            break

        html = fetch_list_page(page_index)
        page_items = parse_list_page(html)

        # Stop if no more items on the page
        if not page_items:
            break

        for item in page_items:
            qnum = item["qnum"]

            if qnum in existing_qnums:
                # ★ 증분 크롤링 종료 지점
                print(f"[STOP] Reached existing qnum {qnum}. Stopping incremental crawl.")
                stop_flag = True
                break

            # 신규만 추가
            all_new.append(item)

        if stop_flag:
            break

        print(f"[INFO] Page {page_index} crawled, {len(page_items)} items")
        page_index += 1
        time.sleep(0.2)

    new_records_with_detail, merged = merge_incremental(previous, all_new)

    # 저장
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # DB 및 임베딩 저장 (신규 데이터만)
    if new_records_with_detail:
        save_to_db(new_records_with_detail)
        process_embeddings(new_records_with_detail)

    print(f"[DONE] 총 {len(merged)}개 항목 저장 완료. (신규: {len(new_records_with_detail)})")


if __name__ == "__main__":
    main(max_pages=5)