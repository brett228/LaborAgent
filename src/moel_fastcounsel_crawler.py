"""
고용노동부 빠른인터넷 상담 크롤링 모듈
"""

from bs4 import BeautifulSoup
import hashlib
import json
import requests
import sqlite3
import time
from pathlib import Path

from src.embeddings import get_embedding
from src.rag.build_index import add_documents


# -------------------------
# 0) URL / 환경 설정
# -------------------------
try:
    BASE_DIR = Path(__file__).resolve().parent.parent
except NameError:
    BASE_DIR = Path.cwd()

OUTPUT_JSON = "moel_fastcounsel.jsonl"
OUTPUT_DB = "moel_fastcounsel.db"
JSON_PATH = BASE_DIR / "data" / OUTPUT_JSON
DB_PATH = BASE_DIR / "db"/ OUTPUT_DB

BASE_LIST_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"
BASE_URL = "https://www.moel.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


# -------------------------
# 0-1) DB 초기화
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS moel_fastcounsel (
            qnum TEXT PRIMARY KEY,
            title TEXT,
            question TEXT,
            answer TEXT,
            link TEXT,
            state TEXT,
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
            item["state"],
            item["date"],
        )
        for item in items if item["state"] == "답변완료"
        ]
        
    cur.executemany("""
        INSERT OR IGNORE INTO moel_fastcounsel (qnum, title, question, answer, link, state, date)
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
        q = item["question"]
        a = item["answer"]
        title = item["title"]
        link = item["link"]
        
        # 문서 포맷팅
        text = f"Title: {title}\nQ: {q}\nA: {a}\nLink: {link}"
        chunks.append(text)
    
    if chunks:
        print(f"[Embedding] Processing {len(chunks)} chunks...")
        add_documents(chunks, get_embedding, collection_name="moel_fastcounsel")
        print("[Embedding] Done.")


# -------------------------
# 1) 기존 보유 qnum 불러오기
# -------------------------
def get_existing_qnums():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT qnum FROM moel_fastcounsel")
    rows = cur.fetchall()
    conn.close()
    return set(row[0] for row in rows)

# -------------------------
# 2) 리스트 페이지 XHR 요청 (HTML 예시)
# -------------------------
def fetch_list_page(page_index):
    params = {"pageIndex": page_index}
    resp = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=30)
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
        dd_q = dls[0].select("dd") if len(dls) > 0 else []
        dd_a = dls[1].select("dd") if len(dls) > 1 else []
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
        # print('q:', question)
        # print('a:', answer)

        return {"question": question, "answer": answer}
    except Exception as e:
        return {"question": "[ERROR]", "answer": str(e)}

# -------------------------
# 6) 증분 merge
# -------------------------
def append_jsonl(record):
    with open(JSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# -------------------------
# 7) 메인
# -------------------------
def main(max_pages=None, min_consecutive_complete=50):
    init_db() # DB 초기화
    
    existing_qnums = get_existing_qnums()
    print(f"[INFO] Existing records in DB: {len(existing_qnums)}")
    all_new = []

    page_index = 1
    stop_flag = False
    consecutive_complete_state = 0

    while True:
        if max_pages is not None and page_index > max_pages:
            break

        html = fetch_list_page(page_index)
        page_items = parse_list_page(html)

        # Stop if no more items on the page
        if not page_items:
            break

        for item in page_items:
            qnum = item["qnum"]
            state = item["state"]

            if state == "답변완료":
                consecutive_complete_state += 1
            else:
                consecutive_complete_state = 0
            # print(consecutive_complete_state, qnum in existing_qnums)
            # 기존 데이터에 item이 존재하고, 크롤링 대상이 연속으로 설정한 숫자 이상 답변완료인 경우 크롤링 중단
            if (qnum in existing_qnums) & (consecutive_complete_state >= min_consecutive_complete):
                # ★ 증분 크롤링 종료 지점
                print(f"[STOP] Reached existing qnum {qnum}.\n       Reached {consecutive_complete_state} consecutive [답변완료] state.\n       Stopping incremental crawl.")
                stop_flag = True
                break

            detail = fetch_detail(item["link"])

            record = {
                "qnum": item["qnum"],
                "title": item["title"],
                "question": detail.get("question", ""),
                "answer": detail.get("answer", ""),
                "link": item["link"],
                "state": item["state"],
                "date": item["date"]
            }

            if (record["state"] == "답변완료") and (qnum not in existing_qnums):
                append_jsonl(record)
                all_new.append(record)
        
        if stop_flag:
            break

        print(f"[INFO] Page {page_index} crawled, new & complete: {len(all_new)} items")
        page_index += 1
        time.sleep(0.2)
    
    # DB 및 임베딩 저장 (신규 데이터만)
    if all_new:
        save_to_db(all_new)
        process_embeddings(all_new)

    print(f"[DONE] 신규 {len(all_new)}개 저장 완료.")

if __name__ == "__main__":
    main(max_pages=3)
