#!/usr/bin/env python3
"""檢查 Agent 工程筆記的靜態輸出。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs"
CONTENT = ROOT / "content" / "posts"
BASE_PATH = "/agent-engineering-notes/"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []
        self.h1_count = 0
        self.lang = ""
        self.title_count = 0
        self.canonical_count = 0
        self.json_ld: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.lang = values.get("lang") or ""
        elif tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        elif tag == "link" and values.get("href"):
            self.hrefs.append(values["href"] or "")
            if values.get("rel") == "canonical":
                self.canonical_count += 1
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "title":
            self._in_title = True
            self.title_count += 1
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._json_buffer))
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_buffer.append(data)


def local_target(href: str) -> Path | None:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc or href.startswith("#") or href.startswith("mailto:"):
        return None
    path = parsed.path
    if not path.startswith(BASE_PATH):
        raise ValueError(f"站內連結缺少 base path：{href}")
    relative = path[len(BASE_PATH) :]
    if not relative or relative.endswith("/"):
        relative += "index.html"
    return OUTPUT / relative


def check_html() -> list[str]:
    errors: list[str] = []
    pages = sorted(OUTPUT.rglob("*.html"))
    if not pages:
        return ["找不到 HTML"]
    for page in pages:
        raw = page.read_text(encoding="utf-8")
        parser = PageParser()
        parser.feed(raw)
        label = page.relative_to(OUTPUT)
        if parser.lang != "zh-Hant":
            errors.append(f"{label}: html lang 不是 zh-Hant")
        if parser.h1_count != 1:
            errors.append(f"{label}: H1 數量為 {parser.h1_count}")
        if parser.title_count != 1:
            errors.append(f"{label}: title 數量為 {parser.title_count}")
        if parser.canonical_count != 1:
            errors.append(f"{label}: canonical 數量為 {parser.canonical_count}")
        if re.search(r"(?:file://|C:\\Users\\|gho_[A-Za-z0-9_]+)", raw, re.IGNORECASE):
            errors.append(f"{label}: 可能包含本機路徑或秘密")
        for document in parser.json_ld:
            try:
                json.loads(document)
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: JSON-LD 無效：{exc}")
        for href in parser.hrefs:
            try:
                target = local_target(href)
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
                continue
            if target is not None and not target.exists():
                errors.append(f"{label}: 站內連結不存在：{href}")
    return errors


def check_sources() -> list[str]:
    errors: list[str] = []
    for metadata_path in CONTENT.glob("*.json"):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source = CONTENT / f"{metadata['slug']}.md"
        if not source.is_file():
            errors.append(f"缺少文章來源：{source.name}")
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != metadata.get("source_sha256"):
            errors.append(f"{source.name}: SHA-256 不符")
        output = OUTPUT / "posts" / metadata["slug"] / "index.html"
        if not output.is_file():
            errors.append(f"缺少文章頁：{output.relative_to(OUTPUT)}")
    return errors


def main() -> None:
    required = ["index.html", "404.html", "feed.xml", "sitemap.xml", "robots.txt", ".nojekyll"]
    errors = [f"缺少輸出：{name}" for name in required if not (OUTPUT / name).exists()]
    errors.extend(check_html())
    errors.extend(check_sources())
    for xml_name in ("feed.xml", "sitemap.xml"):
        try:
            ET.parse(OUTPUT / xml_name)
        except (ET.ParseError, OSError) as exc:
            errors.append(f"{xml_name}: XML 無效：{exc}")
    if errors:
        print("網站檢查失敗：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("網站檢查通過")


if __name__ == "__main__":
    main()
