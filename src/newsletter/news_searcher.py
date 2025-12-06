"""
월간노동법률, 매일노동뉴스 및 네이버 뉴스검색을 통한 뉴스 확인
"""


import json
import os
import sys
import urllib.request
import requests
import time
from bs4 import BeautifulSoup
import numpy as np
from urllib.parse import urlencode
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path


# Explicitly load .env from project root (parent of src)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ------------------------------------------------------------
# 0. 환경변수 / 설정
# ------------------------------------------------------------
NAVER_CLIENT_ID = "rBFQAitfHHLKrDlFtbI9"
NAVER_CLIENT_SECRET = "XyLphyWbaa"
GOOGLE_CSE_API_KEY = "AIzaSyDPGKHWCgCR6BURDhWJGpBU3yGL8njkyOw"
GOOGLE_CSE_CX = "031c6c55ff389400f"  # custom search engine identifier



# ------------------------------------------------------------
# 1. 네이버 뉴스 검색 API
# ------------------------------------------------------------
def search_naver_news(query, display=20, sort="date"):
    base_url = "https://openapi.naver.com/v1/search/news.json"
    params = {
        "query": query,
        "display": display,
        "sort": sort  # date(최신순)
    }
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    url = f"{base_url}?{urlencode(params)}"
    res = requests.get(url, headers=headers)
    res.raise_for_status()

    articles = []

    items = res.json().get("items", [])
    for k, item in enumerate(items):
        title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '')  # HTML 태그 제거
        link = item['link']
        description = item['description'].replace('<b>', '').replace('</b>', '').replace('&quot;', '')
        pubDate = item['pubDate']

        articles.append({
            "key": "N"+str(k + 1).zfill(4),
            "title": title,
            "link": link,
            "content": description
            })
        
    return articles 

# ------------------------------------------------------------
# 2. 월간노동법률
# ------------------------------------------------------------
def search_worklaw_news(query, n_news=5, max_pages=10):
    articles = []
    url = "https://www.googleapis.com/customsearch/v1"

    for page in range(1, max_pages + 1):
        start = (page - 1) * 10 + 1
        params = {
            "key": GOOGLE_CSE_API_KEY,
            "cx": GOOGLE_CSE_CX,
            "q": query,
            "start": start,
            "sort": "date",
            "siteSearch": "www.worklaw.co.kr",
            "siteSearchFilter": "i"  # include only
        }
    
        res = requests.get(url, params=params).json()

        if "items" not in res:
            break

        for k, item in enumerate(res.get("items", [])):
            articles.append({
                "key": "W"+str(k + 1).zfill(4),
                "title": item["title"],
                "link": item["link"],
                "content": item["snippet"],
                "source": "월간노동법률"
                })
        
            if len(articles) >= n_news:
                break
    
    return articles[:min(len(articles), n_news)]

# ------------------------------------------------------------
# 3. 매일노동법률
# ------------------------------------------------------------
def search_labortoday_news(query, n_news=5, max_pages=10):
    base = "https://www.labortoday.co.kr/news/articleList.html"
    link_base = "https://www.labortoday.co.kr"
    
    articles = []

    for page in range(1, max_pages + 1):
        params = {
            "sc_area": "A",
            "view_type": "sm",
            "sc_section_code": "S1N27",
            "sc_word": query,
            "page": page
        }

        res = requests.get(base, params=params, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")

        h4_list = soup.select("h4.titles")
        p_list = soup.select("p")

        # 페이지만 존재하고 결과가 없는 경우 종료
        if not h4_list:
            break

        for k, (h4, p) in enumerate(zip(h4_list, p_list)):
            a_tag = h4.find("a")
            title = a_tag.get_text(strip=True) if a_tag else None
            link = a_tag["href"] if a_tag and a_tag.has_attr("href") else None
            content = p.get_text(" ", strip=True)
            
            if title == '':
                continue

            articles.append({
                "key": "L"+str(k + 1).zfill(4),
                "title": title,
                "link": link_base + link,
                "content": content,
                "source": "매일노동법률"
            })

            if len(articles) >= n_news:
                break
    
    return articles[:min(len(articles), n_news)]

# ------------------------------------------------------------
# 4. 기사 본문 크롤링
# ------------------------------------------------------------

def get_worklaw_full_text(url):
    res = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")

    paragraphs = soup.find_all("br")
    text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    return text

def get_labortoday_full_text(url):
    res = requests.get(url, headers={"User-Agent":"Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")

    paragraphs = soup.find_all("p")
    text = "\n".join(p.get_text(strip=True) for p in paragraphs)
    return text


# ------------------------------------------------------------
# 5. 월간노동법률 + 매일노동법률
# ------------------------------------------------------------
def search_all_newslist(query, n_news_each=5):
    l_news = search_labortoday_news(query, n_news=n_news_each, max_pages=10)
    w_news = search_worklaw_news(query, n_news=n_news_each, max_pages=10)

    return l_news + w_news

def search_all_text(list_dict):
    if list_dict['source'] == "매일노동법률":
        text = get_labortoday_full_text(list_dict['link'])
    elif list_dict['source'] == "월간노동법률":
        text = get_worklaw_full_text(list_dict['link'])
    else:
        raise ValueError("가져올 수 없는 기사입니다.")
    
    return text


# url = "https://www.worklaw.co.kr/main2022/view/view.asp?in_cate=122&gopage=1&bi_pidx=37067&sPrm=in_cate$$122@@in_cate2$$0@@noidx$$37068"
# url = "https://www.labortoday.co.kr/news/articleView.html?idxno=231561"

# rslt_list= search_all_newslist(query="부당해고", n_news_each=5)
# rslt_list[0]
# rslt_list[5]

# text0 = search_all_text(rslt_list[0])
# text5 = search_all_text(rslt_list[5])