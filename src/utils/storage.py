def save_html(path, html):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)