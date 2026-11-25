"""Parser nội dung bài viết cho 5 báo. Không làm sạch NLP.

Mỗi parser trả về:
  Title, Content, Published_Date, Author, Final_URL,
  Parser, Content_Selector, Content_Length, Paragraph_Count,
  Date_Source, Title_Source, Author_Source
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bs4 import BeautifulSoup

VN_TZ = timezone(timedelta(hours=7))

CONTENT_SELECTORS = {
    "VnExpress": [".fck_detail", "article.fck_detail", "article"],
    "TuoiTre": [".detail-content", ".detail-cmain", "article"],
    "ThanhNien": [".detail-content", ".detail__cmain", "article"],
    "DanTri": ["#desktop-in-article", "#articleContent", "article"],
    "VietnamNet": ["#maincontent", ".maincontent", ".content-detail"],
}
NOISE_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg",
    ".kbwscwl-relatedbox", ".readmore-body-box", ".box-category",
    ".box-comment", ".boxcommentlogin", ".author-info", ".box-author-detail",
    ".detail-author", ".detail-fb-like-share", ".social", ".share",
    ".tags", ".tag", ".ads", ".advertisement", ".banner", ".related",
    ".tin-lien-quan", ".link-content-footer", ".comment", ".comments",
]
UI_LINES = {
    "chia sẻ", "bình luận", "xem thêm", "đọc tiếp", "quảng cáo",
    "bài viết liên quan", "tin liên quan", "theo dõi báo trên",
}


def _jsonld_objects(soup: BeautifulSoup) -> list:
    objects = []
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(node.string or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                objects.append(x)
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return objects


def _jsonld_article(soup: BeautifulSoup) -> dict:
    for obj in _jsonld_objects(soup):
        typ = obj.get("@type")
        types = typ if isinstance(typ, list) else [typ]
        if any(str(t).endswith("Article") or t == "NewsArticle" for t in types if t):
            return obj
    return {}


def _author_names(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return (value.get("name") or "").strip()
    if isinstance(value, list):
        names = [_author_names(x) for x in value]
        return ", ".join([x for x in names if x])
    return ""


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_date(value) -> Optional[str]:
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt.astimezone(VN_TZ).isoformat(timespec="seconds")
    except ValueError:
        return None


def _title(soup, article, fallback: str) -> tuple:
    for sel in ["h1.title-detail", "h1.detail-title", "h1.content-detail-title", "h1"]:
        el = soup.select_one(sel)
        if el is not None:
            text = _clean_text(el.get_text(" ", strip=True))
            if text:
                return text, "html"
    headline = _clean_text(article.get("headline"))
    if headline:
        return headline, "jsonld"
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return _clean_text(og["content"]), "og"
    return fallback or "", "step3"


def _date(soup, article, fallback) -> tuple:
    for key in ["datePublished", "dateCreated", "dateModified"]:
        parsed = _parse_date(article.get(key))
        if parsed:
            return parsed, f"jsonld:{key}"
    for attrs in [{"property": "article:published_time"}, {"name": "article:published_time"},
                  {"name": "pubdate"}, {"name": "date"}]:
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content"):
            parsed = _parse_date(meta["content"])
            if parsed:
                return parsed, "meta"
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip(), "step3"
    return None, ""


def _author(soup, article, fallback_author="") -> tuple:
    names = _author_names(article.get("author"))
    if names:
        return names, "jsonld"
    for attrs in [{"name": "author"}, {"property": "article:author"}]:
        meta = soup.find("meta", attrs=attrs)
        if meta is not None:
            text = _clean_text(meta.get("content"))
            if text and text.lower() not in {"vnexpress", "dân trí", "thanh niên", "tuổi trẻ", "vietnamnet"}:
                return text, "meta"
    for sel in [".author-info .author-item-name", ".detail-author", ".author"]:
        el = soup.select_one(sel)
        if el is None:
            continue
        text = _clean_text(el.get_text(" ", strip=True))
        if text and text.lower() not in {"vnexpress", "dân trí", "thanh niên", "tuổi trẻ", "vietnamnet"}:
            return text, "html"
    if isinstance(fallback_author, str) and fallback_author.strip():
        return fallback_author.strip(), "step3"
    return "", ""


def _content(soup, site: str) -> tuple:
    block = None
    used = ""
    for sel in CONTENT_SELECTORS[site]:
        block = soup.select_one(sel)
        if block is not None:
            used = sel
            break
    if block is None:
        raise ValueError("không tìm thấy khối nội dung")
    for sel in NOISE_SELECTORS:
        for node in block.select(sel):
            node.decompose()
    paragraphs = []
    for el in block.find_all(["p", "h2", "h3", "blockquote"]):
        text = _clean_text(el.get_text(" ", strip=True))
        if not text:
            continue
        if text.lower().strip(" .:") in UI_LINES:
            continue
        if text not in paragraphs:
            paragraphs.append(text)
    content = "\n".join(paragraphs).strip()
    if len(content) < 300:
        raise ValueError(f"nội dung quá ngắn ({len(content)} ký tự)")
    return content, used, len(paragraphs)


def parse_article(site: str, html: str, url: str, fallback: dict) -> dict:
    soup = BeautifulSoup(html, "lxml")
    article = _jsonld_article(soup)
    title, title_source = _title(soup, article, fallback.get("Title", ""))
    published, date_source = _date(soup, article, fallback.get("Published_Date"))
    author, author_source = _author(soup, article, fallback.get("Author", ""))
    content, selector, paragraphs = _content(soup, site)
    if not title:
        raise ValueError("không tìm thấy tiêu đề")
    canonical = soup.find("link", rel="canonical")
    final_url = canonical.get("href").strip() if canonical and canonical.get("href") else url
    return {
        "ID": fallback.get("ID"),
        "Title": title,
        "Content": content,
        "URL": url,
        "Final_URL": final_url,
        "Source": site,
        "Published_Date": published,
        "Original_Category": fallback.get("Original_Category"),
        "Label": fallback.get("Label"),
        "Author": author,
        "Content_Length": len(content),
        "Paragraph_Count": paragraphs,
        "Content_Hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "Parser": site,
        "Content_Selector": selector,
        "Date_Source": date_source,
        "Title_Source": title_source,
        "Author_Source": author_source,
    }
