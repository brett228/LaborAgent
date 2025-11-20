import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains


_id = "stipe228"
_pw = "adidas2@"

options = Options()
# options.add_argument("--headless")
options.add_argument(
    'user-agent=Mozilla/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
)

def login_naver(id_, pw_):
    driver = webdriver.Chrome(options=options)
    driver.get("https://nid.naver.com/nidlogin.login")
    time.sleep(1)

    # 아이디
    id_input = driver.find_element(By.ID, "id")
    id_input.click()
    driver.execute_script(f"document.getElementById('id').value = '{_id}';")
    time.sleep(1)

    # 비밀번호
    pw_input = driver.find_element(By.ID, "pw")
    driver.execute_script(f"document.getElementById('pw').value = '{_pw}';")
    pw_input.click()
    time.sleep(1)
    # driver.save_screenshot("screenshot1.png")

    # 로그인
    driver.find_element(By.ID, "log.login").click()
    time.sleep(2)

    return driver


def posting(driver, _id, posttitle, postdes):
    driver.get(f"https://blog.naver.com/{_id}?Redirect=Write")
    frame = driver.find_element(By.ID, "mainFrame")
    driver.switch_to.frame(frame)
    time.sleep(4)

    # 작성중인 글 취소
    try:
        cancel_2 =driver.find_element(By.CSS_SELECTOR, ".se-popup-button.se-popup-button-cancel")
        if cancel_2:
            cancel_2.click()
    except:
        pass
        
    cancel_1 = driver.find_element(By.CSS_SELECTOR, '.se-help-panel-close-button')
    cancel_1.click()
    
    title = driver.find_element(By.CSS_SELECTOR, ".se-placeholder.__se_placeholder.se-fs32")
    action = ActionChains(driver)
    post_title = posttitle
    action.move_to_element(title).pause(1).click().send_keys(post_title).perform()
    print("제목 작성 완료")
    
    description = driver.find_element(By.CSS_SELECTOR, "span.se-placeholder.__se_placeholder.se-fs15")
    action = ActionChains(driver)
    post_description = postdes
    action.move_to_element(description).pause(1).click().send_keys(post_description).perform()
    print("내용 작성 완료")
    
    send = driver.find_elements(By.TAG_NAME, "button")[3]
    send.click()
    time.sleep(1)
    
    post = driver.find_elements(By.TAG_NAME, "button")[9]
    post.click()

post = """
<h2> 네이버 블로그 서식 테스트 포스트 </h2>
"""

post = """
<h2>✨ 네이버 블로그 서식 테스트 포스트 ✨</h2>
<blockquote>
  <strong>포스트 제목:</strong> 블로그 서식 테스트 포스트<br>
  <strong>작성 목적:</strong> 네이버 블로그에서 지원하는 서식 기능을 한눈에 확인하기
</blockquote>

<hr>

<h3>🖋️ 1. 글자 서식 테스트</h3>
<ul>
  <li><b>굵게 (Bold)</b></li>
  <li><i>기울임 (Italic)</i></li>
  <li><s>취소선 (Strike)</s></li>
  <li><span style="color:#2b8a3e;">색상 변경 (초록)</span></li>
  <li><span style="background-color:#fff3cd;">배경색 강조</span></li>
  <li><span style="font-size:20px;">글자 크기 변경</span></li>
  <li><u>밑줄</u></li>
</ul>

<hr>

<h3>🧩 2. 제목 서식 (Heading Levels)</h3>
<h4>🟩 소제목 (H4)</h4>
<h5>🟦 세부항목 (H5)</h5>
<h6>🟨 더 작은 제목 (H6)</h6>

<hr>

<h3>📋 3. 목록 (List)</h3>
<p><b>순서 없는 목록</b></p>
<ul>
  <li>사과 🍎</li>
  <li>바나나 🍌</li>
  <li>포도 🍇</li>
</ul>

<p><b>순서 있는 목록</b></p>
<ol>
  <li>첫 번째 단계</li>
  <li>두 번째 단계</li>
  <li>세 번째 단계</li>
</ol>

<hr>

<h3>💬 4. 인용구 (Quote)</h3>
<blockquote>
  "성공은 준비된 자에게 온다."<br>
  — <i>루이 파스퇴르</i>
</blockquote>

<hr>

<h3>🧾 5. 표 (Table)</h3>
<table border="1" cellspacing="0" cellpadding="6">
  <tr>
    <th>구분</th>
    <th>내용</th>
    <th>비고</th>
  </tr>
  <tr>
    <td>날짜</td>
    <td>2025-11-08</td>
    <td>오늘 날짜</td>
  </tr>
  <tr>
    <td>작성자</td>
    <td>ChatGPT</td>
    <td>테스트용</td>
  </tr>
  <tr>
    <td>상태</td>
    <td>✅ 정상 표시</td>
    <td>완료</td>
  </tr>
</table>

<hr>

<h3>🔗 6. 링크 (Link)</h3>
<ul>
  <li><a href="https://www.naver.com" target="_blank">네이버</a></li>
  <li><a href="https://blog.naver.com/" target="_blank">내 블로그 홈으로 가기</a></li>
</ul>

<hr>

<h3>🖼️ 7. 이미지 위치 테스트</h3>
<p>📷 이미지 예시 (직접 삽입해보세요!)</p>
<blockquote>예: 여행 사진, 제품 이미지, 캡처 화면 등</blockquote>

<hr>

<h3>🧠 8. 코드 / 인용 박스 스타일</h3>
<pre style="background-color:#f8f9fa; border:1px solid #ddd; padding:10px; border-radius:8px;">
<code># 파이썬 코드 예시
for i in range(3):
    print("Hello, Naver Blog!")</code>
</pre>

<hr>

<h3>💡 9. 강조 문구 및 구분선</h3>
<p>⚠️ <b>주의:</b> 이 영역은 테스트용입니다.</p>
<hr>
<p>✅ <b>팁:</b> 복사 후 글자 크기, 색상, 정렬 등을 자유롭게 수정해보세요.</p>

<hr>

<h3>🎯 마무리</h3>
<p>이 포스트는 네이버 블로그의 <b>다양한 서식 적용 예시</b>를 확인하기 위한 테스트용 글입니다.<br>
글쓰기 에디터의 <b>서식 도구</b>를 직접 눌러보며 결과를 확인해보세요 ✨</p>
"""

drv = login_naver(_id, _pw)

posting(drv, _id, "테스트", post)


