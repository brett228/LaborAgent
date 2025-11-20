# moel_fastcounsel_crawl.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
import csv
import time
import urllib.parse

BASE_URL = "https://www.moel.go.kr/minwon/fastcounsel/fastcounselList.do"
USER_AGENT = "Mozilla/5.0 (compatible; bot/1.0; +youremail@example.com)"

def parse_list_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # 1) 우선 table 행 기반 파싱 시도
    table_rows = soup.select("table tbody tr")
    if table_rows:
        for tr in table_rows:
            # 헤더 또는 비어있는 행은 건너뜀
            tds = tr.find_all("td")
            if not tds or len(tds) < 2:
                continue
            # 사이트 구조에 따라 조정 필요
            # 예: [번호, 제목(링크), 첨부, 등록일, 답변여부]
            title_a = tr.select_one("a")
            title = title_a.get_text(strip=True) if title_a else tr.get_text(strip=True)
            href = title_a["href"] if title_a and title_a.has_attr("href") else None
            # 절대URL로 변환
            if href:
                href = urllib.parse.urljoin(BASE_URL, href)
            # 등록일 찾기 (마지막 td에 날짜가 있는 경우가 많음)
            date = tds[-2].get_text(strip=True) if len(tds) >= 2 else None
            items.append({"title": title, "link": href, "date": date})
        return items

    # 2) table이 없으면 리스트(ul/li) 형태 시도
    lis = soup.select("ul li")
    if lis:
        for li in lis:
            a = li.select_one("a")
            title = a.get_text(strip=True) if a else li.get_text(strip=True)
            href = a["href"] if a and a.has_attr("href") else None
            if href:
                href = urllib.parse.urljoin(BASE_URL, href)
            items.append({"title": title, "link": href, "date": None})
        return items

    # 3) 그 외: 페이지 내 키워드로 블록 추출 시도 (최후 수단)
    # (사용자 환경에 맞춰 확장 가능)
    return items

def parse_detail_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    # 제목
    h = soup.select_one("h3") or soup.select_one(".board_view_title") or soup.select_one(".bbs_view .title")
    title = h.get_text(strip=True) if h else None
    # 본문: 흔한 클래스들 적용, fallback to article/body
    body = soup.select_one(".board_view_content") or soup.select_one(".content_view") or soup.select_one(".bbs_view .content") or soup.select_one("article")
    content = body.get_text("\n", strip=True) if body else None
    return {"title": title, "content": content}

def crawl(headless=True, max_pages=500, delay_between_pages=1.0, output_csv="fastcounsel.csv"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=USER_AGENT, locale="ko-KR")
        page = context.new_page()
        collected = []

        page.goto(BASE_URL, timeout=30000)
        time.sleep(0.5)

        current_page = 1
        while current_page <= max_pages:
            print(f"[info] 처리중: 페이지 {current_page}")
            # 페이지가 바뀔 때까지 대기
            try:
                page.wait_for_selector("table, ul, .list", timeout=5000)
            except PWTimeout:
                # 그래도 content를 가져와서 시도
                pass

            html = page.content()
            items = parse_list_from_html(html)
            if not items:
                print("[warn] 해당 페이지에서 목록을 찾지 못했음 — 수동 확인 필요")
                # 페이징 누르기 시도 후 계속
            else:
                # 각 항목의 상세페이지 방문 및 수집
                for it in items:
                    # 상세 링크 없으면 스킵
                    if not it.get("link"):
                        continue
                    # 간단한 중복 체크
                    if any(d.get("link") == it["link"] for d in collected):
                        continue
                    try:
                        page_detail = context.new_page()
                        page_detail.goto(it["link"], timeout=20000)
                        page_detail.wait_for_load_state("networkidle", timeout=10000)
                        detail_html = page_detail.content()
                        detail = parse_detail_from_html(detail_html)
                        page_detail.close()
                    except Exception as e:
                        print(f"[warn] 상세페이지 열기 실패: {it['link']} -> {e}")
                        detail = {"title": it.get("title"), "content": None}
                    record = {
                        "list_title": it.get("title"),
                        "link": it.get("link"),
                        "list_date": it.get("date"),
                        "detail_title": detail.get("title"),
                        "detail_content": detail.get("content")
                    }
                    collected.append(record)
                    print(f"  + 수집: {record['list_title']}")
                    time.sleep(0.3)  # 상세페이지 부담 완화

            # 페이징: '다음' 버튼 클릭 또는 페이지 번호 클릭
            # 우선: "다음" 텍스트 버튼 시도
            try:
                # 흔한 페이징 버튼으로 시도
                # 1) a[rel=next] 또는 텍스트 '다음' 버튼
                nxt = page.query_selector("a[rel=next], a:has-text('다음'), button:has-text('다음'), .paging a.next")
                if nxt:
                    nxt.click()
                    current_page += 1
                    time.sleep(delay_between_pages)
                    continue
                # 2) 숫자 페이지에서 다음 번호 클릭 시도
                # 시도할 수 있도록 JS로 현재 페이지 + 1 링크 찾기
                # fallback: URL에 pageIndex 파라미터 넣기
                parsed = urllib.parse.urlparse(page.url)
                q = urllib.parse.parse_qs(parsed.query)
                # 흔히 쓰이는 파라미터명들 검사
                candidate_names = ["pageIndex", "page", "pageNo", "pageNum", "currentPage"]
                found = False
                for name in candidate_names:
                    if name in q:
                        next_num = int(q.get(name)[0]) + 1
                        q[name] = [str(next_num)]
                        new_q = urllib.parse.urlencode({k: v[0] for k, v in q.items()})
                        new_url = urllib.parse.urlunparse(parsed._replace(query=new_q))
                        page.goto(new_url, timeout=15000)
                        found = True
                        current_page += 1
                        time.sleep(delay_between_pages)
                        break
                if found:
                    continue
                # 3) 마지막 수단: 페이지번호 직접 클릭 (예: //a[text()="2"])
                # 여의치 않으면 종료
                print("[info] 다음 페이지 버튼을 발견하지 못해 크롤링을 종료합니다.")
                break
            except Exception as e:
                print("[warn] 페이징 시도 중 오류:", e)
                break

        # 결과 저장
        with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
            fieldnames = ["list_title", "link", "list_date", "detail_title", "detail_content"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in collected:
                writer.writerow(r)

        browser.close()
        print(f"[done] 수집 완료. 총 {len(collected)}개 항목을 '{output_csv}' 에 저장했습니다.")

if __name__ == "__main__":
    crawl(headless=True, max_pages=2, delay_between_pages=1.0)
