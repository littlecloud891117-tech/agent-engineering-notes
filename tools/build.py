#!/usr/bin/env python3
"""從文章來源建立 Agent 工程筆記靜態網站。"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content" / "posts"
STATIC = ROOT / "static"
OUTPUT = ROOT / "docs"
SITE_NAME = "Agent 工程筆記"
SITE_DESCRIPTION = "拆解 AI Agent、模型路由、工具鏈與可靠性工程的繁體中文技術筆記。"
SITE_URL = "https://littlecloud891117-tech.github.io/agent-engineering-notes"
BASE_PATH = "/agent-engineering-notes/"
REPO_URL = "https://github.com/littlecloud891117-tech/agent-engineering-notes"

MARKDOWN = MarkdownIt(
    "commonmark",
    {"html": False, "linkify": True, "typographer": False},
).enable(["table", "linkify"])


def write(relative: str, content: str) -> None:
    target = OUTPUT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def canonical(path: str = "") -> str:
    return f"{SITE_URL}/{path}" if path else f"{SITE_URL}/"


def navigation() -> str:
    return f"""
<a class="skip-link" href="#main">跳到主要內容</a>
<header class="site-header">
  <nav class="nav" aria-label="主要導覽">
    <a class="brand" href="{BASE_PATH}"><span class="brand-mark" aria-hidden="true">A:</span><span class="brand-name">{SITE_NAME}</span></a>
    <div class="nav-links"><a href="{BASE_PATH}">文章</a><a href="{BASE_PATH}about/">關於</a><a href="{BASE_PATH}feed.xml">RSS</a></div>
  </nav>
</header>""".strip()


def footer() -> str:
    return f"""
<footer class="site-footer">
  <div class="footer-inner">
    <span>© 2026 LittleCloud · {SITE_NAME}</span>
    <div class="footer-links"><a href="{BASE_PATH}privacy/">隱私說明</a><a href="{REPO_URL}">公開原始碼</a></div>
  </div>
</footer>""".strip()


def layout(*, title: str, description: str, path: str, body: str, json_ld: dict | None = None) -> str:
    full_title = SITE_NAME if not title else f"{title}｜{SITE_NAME}"
    structured = ""
    if json_ld is not None:
        structured = f'<script type="application/ld+json">{html.escape(json.dumps(json_ld, ensure_ascii=False), quote=False)}</script>'
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(full_title)}</title>
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta name="robots" content="index,follow">
  <meta name="theme-color" content="#004a3f">
  <link rel="canonical" href="{canonical(path)}">
  <link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{canonical('feed.xml')}">
  <link rel="stylesheet" href="{BASE_PATH}assets/styles.css">
{structured}
</head>
<body>
{navigation()}
<main id="main">{body}</main>
{footer()}
</body>
</html>
"""


def load_posts() -> list[dict]:
    posts: list[dict] = []
    required = {
        "slug",
        "title",
        "description",
        "date_published",
        "date_modified",
        "author",
        "tags",
        "source_id",
        "source_commit",
        "source_sha256",
    }
    for metadata_path in sorted(CONTENT.glob("*.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        missing = required - metadata.keys()
        if missing:
            raise ValueError(f"{metadata_path.name} 缺少欄位：{sorted(missing)}")
        source_path = CONTENT / f"{metadata['slug']}.md"
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        markdown = source_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        if digest != metadata["source_sha256"]:
            raise ValueError(f"{source_path.name} 與 source_sha256 不符")
        heading = re.match(r"^# (.+?)\r?\n", markdown)
        if heading is None or heading.group(1) != metadata["title"]:
            raise ValueError(f"{source_path.name} 的 H1 與 metadata title 不符")
        metadata["markdown"] = markdown
        metadata["body_markdown"] = markdown[heading.end() :].lstrip()
        metadata["reading_minutes"] = max(1, math.ceil(len(re.sub(r"\s+", "", markdown)) / 500))
        posts.append(metadata)
    return sorted(posts, key=lambda item: item["date_published"], reverse=True)


def format_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.year} 年 {parsed.month} 月 {parsed.day} 日"


def render_tags(tags: list[str]) -> str:
    return '<ul class="tag-list" aria-label="文章標籤">' + "".join(
        f'<li class="tag">{html.escape(tag)}</li>' for tag in tags
    ) + "</ul>"


def build_post(post: dict) -> None:
    slug = post["slug"]
    path = f"posts/{slug}/"
    article_body = MARKDOWN.render(post["body_markdown"])
    body = f"""
<header class="article-header">
  <p class="eyebrow">FIELD NOTE / {format_date(post['date_published'])}</p>
  <h1>{html.escape(post['title'])}</h1>
  <p class="article-dek">{html.escape(post['description'])}</p>
  <div class="article-meta"><span>作者：{html.escape(post['author'])}</span><span>閱讀時間：約 {post['reading_minutes']} 分鐘</span><span>更新：{format_date(post['date_modified'])}</span></div>
  {render_tags(post['tags'])}
</header>
<article class="prose" data-source-sha256="{post['source_sha256']}">{article_body}</article>
""".strip()
    json_ld = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": post["title"],
        "description": post["description"],
        "datePublished": post["date_published"],
        "dateModified": post["date_modified"],
        "inLanguage": "zh-Hant",
        "author": {"@type": "Person", "name": post["author"]},
        "mainEntityOfPage": canonical(path),
        "keywords": post["tags"],
    }
    write(
        f"posts/{slug}/index.html",
        layout(title=post["title"], description=post["description"], path=path, body=body, json_ld=json_ld),
    )


def build_index(posts: list[dict]) -> None:
    cards = []
    for post in posts:
        url = f"{BASE_PATH}posts/{post['slug']}/"
        cards.append(
            f"""
<article class="article-card">
  <time datetime="{post['date_published']}">{format_date(post['date_published'])}</time>
  <h3><a href="{url}">{html.escape(post['title'])}</a></h3>
  <p>{html.escape(post['description'])}</p>
  <div class="card-footer"><a class="read-link" href="{url}">閱讀全文 →</a><span class="article-meta">約 {post['reading_minutes']} 分鐘</span></div>
</article>""".strip()
        )
    body = f"""
<section class="hero">
  <div><p class="eyebrow">AI SYSTEMS / FIELD NOTES</p><h1>Agent 工程筆記</h1></div>
  <div class="hero-note"><p>拆解模型、工具與自動化流程。保留失敗證據，也保留可重現的修法。</p></div>
</section>
<section class="section" aria-labelledby="latest"><div class="section-heading"><h2 id="latest">最新文章</h2></div><div class="article-list">{''.join(cards)}</div></section>
""".strip()
    web_site = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": canonical(),
        "description": SITE_DESCRIPTION,
        "inLanguage": "zh-Hant",
    }
    write("index.html", layout(title="", description=SITE_DESCRIPTION, path="", body=body, json_ld=web_site))


def build_pages() -> None:
    about_body = """
<header class="page-hero"><p class="eyebrow">ABOUT</p><h1>從失敗證據理解 Agent</h1><p class="page-intro">這裡整理 AI Agent、模型路由、本機推論與可靠性工程的實作筆記。</p></header>
<section class="page-content"><p>文章聚焦可重現的故障、可驗證的設定與可追溯的流程。技術主張會連回官方文件或本機版本證據。</p><p>文章先完成文風檢查、事實查核與格式校訂，再同步到公開網站。</p></section>
""".strip()
    privacy_body = """
<header class="page-hero"><p class="eyebrow">PRIVACY</p><h1>隱私說明</h1><p class="page-intro">本網站不放置自訂分析工具、廣告追蹤碼或留言系統。</p></header>
<section class="page-content"><p>網站由 GitHub Pages 代管。GitHub 可能基於安全目的記錄訪客 IP 位址。資料處理方式以 <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub 一般隱私權聲明</a>為準。</p><p>外部連結由各網站自行管理。離開本站後，請參閱目標網站的隱私規則。</p><p>本說明更新日期：2026 年 8 月 21 日。</p></section>
""".strip()
    write("about/index.html", layout(title="關於", description="關於 Agent 工程筆記。", path="about/", body=about_body))
    write("privacy/index.html", layout(title="隱私說明", description="Agent 工程筆記的隱私說明。", path="privacy/", body=privacy_body))


def build_feed(posts: list[dict]) -> None:
    items = []
    for post in posts:
        url = canonical(f"posts/{post['slug']}/")
        published = datetime.combine(
            date.fromisoformat(post["date_published"]),
            datetime.min.time(),
            tzinfo=timezone(timedelta(hours=8)),
        )
        items.append(
            f"""<item><title>{xml_escape(post['title'])}</title><link>{url}</link><guid>{url}</guid><pubDate>{format_datetime(published)}</pubDate><description>{xml_escape(post['description'])}</description></item>"""
        )
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{SITE_NAME}</title><link>{canonical()}</link><description>{SITE_DESCRIPTION}</description><language>zh-TW</language>{''.join(items)}</channel></rss>
"""
    write("feed.xml", feed)


def build_sitemap(posts: list[dict]) -> None:
    paths = [("", "2026-08-21"), ("about/", "2026-08-21"), ("privacy/", "2026-08-21")]
    paths.extend((f"posts/{post['slug']}/", post["date_modified"]) for post in posts)
    urls = "".join(f"<url><loc>{canonical(path)}</loc><lastmod>{modified}</lastmod></url>" for path, modified in paths)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {canonical('sitemap.xml')}\n")


def build_404() -> None:
    body = f"""<header class="page-hero"><p class="eyebrow">404</p><h1>找不到這一頁</h1><p class="page-intro">網址可能已變更，或內容尚未發布。</p></header><section class="page-content"><p><a class="read-link" href="{BASE_PATH}">返回文章首頁 →</a></p></section>"""
    write("404.html", layout(title="找不到頁面", description="找不到指定頁面。", path="404.html", body=body))


def main() -> None:
    if OUTPUT.resolve() != (ROOT / "docs").resolve():
        raise RuntimeError(f"拒絕清除非預期路徑：{OUTPUT}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    shutil.copytree(STATIC, OUTPUT / "assets")
    (OUTPUT / ".nojekyll").write_text("", encoding="utf-8")
    posts = load_posts()
    if not posts:
        raise RuntimeError("沒有可發布文章")
    for post in posts:
        build_post(post)
    build_index(posts)
    build_pages()
    build_feed(posts)
    build_sitemap(posts)
    build_404()
    print(f"已建立 {len(posts)} 篇文章：{OUTPUT}")


if __name__ == "__main__":
    main()
