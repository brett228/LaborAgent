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

OUTPUT_JSON = "moel_iqrs.jsonl"
OUTPUT_DB = "moel_iqrs.db"
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
        CREATE TABLE IF NOT EXISTS moel_iqrs (
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
    
    data_to_insert = [
        (
            item["qnum"],
            item["title"],
            item["question"],
            item["answer"],
            item["link"],
            item["ref_no"],
            item["date"],
        )
        for item in items
        ]

    cur.executemany("""
        INSERT OR IGNORE INTO moel_iqrs (qnum, title, question, answer, link, ref_no, date)
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
        text = (
            f"Title: {item['title']}\n"
            f"Q: {item['question']}\n"
            f"A: {item['answer']}\n"
            f"Link: {item['link']}\n"
            f"Ref_no: {item['ref_no']}"
        )
        
        chunks.append(text)
    
    if chunks:
        print(f"[Embedding] Processing {len(chunks)} chunks...")
        add_documents(chunks, get_embedding, collection_name="moel_iqrs")
        print("[Embedding] Done.")

# -------------------------
# 1) 기존 보유 qnum 불러오기
# -------------------------
def get_existing_qnums():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT qnum FROM moel_iqrs")
    rows = cur.fetchall()
    conn.close()
    return set(row[0] for row in rows)

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
def append_jsonl(record):
    with open(JSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# -------------------------
# 6) 메인
# -------------------------
def main(max_pages=None):
    init_db() # DB 초기화
    
    existing_qnums = get_existing_qnums()
    print(f"[INFO] Existing records in DB: {len(existing_qnums)}")
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

            detail = fetch_detail(item["link"])
            record = {
                "qnum": item["qnum"],
                "title": item["title"],
                "question": detail.get("question", ""),
                "answer": detail.get("answer", ""),
                "link": item["link"],
                "ref_no": item["ref_no"],
                "date": item["date"]
            }

            # 신규만 추가
            append_jsonl(record)
            all_new.append(record)

        if stop_flag:
            break

        print(f"[INFO] Page {page_index} crawled, {len(page_items)} items")
        page_index += 1
        time.sleep(0.2)

    # DB 및 임베딩 저장 (신규 데이터만)
    if all_new:
        save_to_db(all_new)
        process_embeddings(all_new)

    print(f"[DONE] 신규 {len(all_new)}개 저장 완료.")


if __name__ == "__main__":
    main(max_pages=2)
