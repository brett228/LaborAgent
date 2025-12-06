"""
고용노동부 보도자료 모듈
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

BASE_LIST_URL = "https://www.moel.go.kr/news/enews/report/enewsList.do"
BASE_DETAIL_URL = "https://www.moel.go.kr/news/enews/report/"
BASE_URL = "https://labor.moel.go.kr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; YourBot/1.0; +youremail@example.com)"
}

# -------------------------
# 1) 리스트 페이지 XHR 요청 (HTML 예시)
# -------------------------
def fetch_press_list(page_index):
    params = {"pageIndex": page_index}
    resp = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=30, verify=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html5lib")
    soup.find_all("td")
    td_list = soup.find_all("td")

    results = []

    for td in td_list:
        a_tag = td.find("a")
        if a_tag:
            title = a_tag.get_text(strip=True)
            link = a_tag.get("href")
            results.append({"title": title, "link": BASE_DETAIL_URL + link})
    
    return results

# -------------------------
# 2) 메인
# -------------------------
def search_press_release(max_pages=None):
    
    page_index = 1
    stop_flag = False

    rslt = []

    while True:
        # Stop if we've reached max_pages (if max_pages is not None)
        if max_pages is not None and page_index > max_pages:
            break

        html = fetch_press_list(page_index)
        
        rslt.extend(html)
        print(f"[INFO] Page {page_index} crawled, {len(html)} items")
        page_index += 1
        time.sleep(0.2)

    return rslt
