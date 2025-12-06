from jinja2 import Environment, FileSystemLoader

# -------------------------------
# 1) 뉴스 기사 데이터 예시
# -------------------------------
# articles = [
#     {
#         "title": "정부, 내년도 경제정책 발표",
#         "content": "2025년도 경제정책 방향이 발표되었으며 주요 내용은…",
#         "link": "https://example.com/news1"
#     },
#     {
#         "title": "금융 시장 불안 요인 확대",
#         "content": "최근 금융시장 변동성이 커지고 있으며 전문가들은…",
#         "link": "https://example.com/news2"
#     },
# ]

# consult = {
#     "title": "이번주 상담 안내",
#     "content": "상담 문의는 이메일로 부탁드립니다."
# }

# policy = {
#     "title": "정책자료",
#     "content": "정책자료 문의는 이메일로 부탁드립니다."
# }

# -------------------------------
# 3) 템플릿 렌더링
# -------------------------------
class NewsletterRenderer:
    def __init__(self):
        self.env = Environment(loader=FileSystemLoader('.'))

    def render(self, state):
        template = self.env.get_template('/templates/newsletter_template.html')
        return template.render(**state)
    
# html_output = template.render(main_title=main_title, articles=articles, consult=consult, policy=policy)
