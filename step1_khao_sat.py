#!/usr/bin/env python3
"""BƯỚC 1 — Khảo sát nguồn dữ liệu tin tức tiếng Việt.

Script chỉ kiểm tra:
  - robots.txt của 5 báo;
  - 40 feed RSS (8 lĩnh vực x 5 báo);
  - 40 trang danh mục (8 lĩnh vực x 5 báo);
  - 5 sitemap index.
Không tải nội dung bài viết, không làm sạch, không tạo dataset cuối.

Chạy:  python step1_khao_sat.py
Cần:   pip install requests beautifulsoup4 lxml
"""
from __future__ import annotations

import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "research" / "raw" / "step1"
OUT = ROOT / "outputs"
RAW.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "student-research-bot/1.0 "
    "(do-an-phan-loai-tin-tuc; hoc tap, toc do thap)"
)
DELAY_SECONDS = 1.5
TIMEOUT = 30
VN_TZ = timezone(timedelta(hours=7))
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5",
}

TOPICS = ["Kinh tế", "Thế giới", "Thể thao", "Pháp luật",
          "Giáo dục", "Sức khỏe", "Công nghệ", "Du lịch"]

SLUGS = {
    "Kinh tế": "kinh-doanh",
    "Thế giới": "the-gioi",
    "Thể thao": "the-thao",
    "Pháp luật": "phap-luat",
    "Giáo dục": "giao-duc",
    "Sức khỏe": "suc-khoe",
    "Công nghệ": "cong-nghe",
    "Du lịch": "du-lich",
}

# URL đã được kiểm tra thực tế ngày 20/11/2026.
SITES = {
    "VnExpress": {
        "robots": "https://vnexpress.net/robots.txt",
        "sitemap": "https://vnexpress.net/sitemap.xml",
        "feed_tpl": "https://vnexpress.net/rss/{slug}.rss",
        "cat_tpl": "https://vnexpress.net/{slug}",
        "article_pattern": r"^https?://vnexpress\.net/[a-z0-9-]+-\d{6,}\.html$",
        "category_slugs": {
            "Kinh tế": "kinh-doanh", "Thế giới": "the-gioi",
            "Thể thao": "the-thao", "Pháp luật": "phap-luat",
            "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
            "Công nghệ": "khoa-hoc-cong-nghe", "Du lịch": "du-lich",
        },
        "quota": 150,
        "method": "category_pages",  # p1–p5, khử trùng lặp
    },
    "TuoiTre": {
        "robots": "https://tuoitre.vn/robots.txt",
        "sitemap": "https://tuoitre.vn/sitemaps/index.rss",
        "feed_tpl": "https://tuoitre.vn/{slug}.rss",
        "cat_tpl": "https://tuoitre.vn/{slug}.htm",
        "article_pattern": r"^https?://tuoitre\.vn/[a-z0-9-]+-\d{6,}\.htm$",
        "category_slugs": {
            "Kinh tế": "kinh-doanh", "Thế giới": "the-gioi",
            "Thể thao": "the-thao", "Pháp luật": "phap-luat",
            "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
            "Công nghệ": "nhip-song-so", "Du lịch": "du-lich",
        },
        "quota": 50,
        "method": "rss",
    },
    "ThanhNien": {
        "robots": "https://thanhnien.vn/robots.txt",
        "sitemap": "https://thanhnien.vn/sitemap.xml",
        "feed_tpl": "https://thanhnien.vn/rss/{slug}.rss",
        "cat_tpl": "https://thanhnien.vn/{slug}.htm",
        "article_pattern": r"^https?://thanhnien\.vn/[a-z0-9-]+-\d{6,}\.htm$",
        "category_slugs": {
            "Kinh tế": "kinh-te", "Thế giới": "the-gioi",
            "Thể thao": "the-thao", "Pháp luật": "thoi-su/phap-luat",
            "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
            "Công nghệ": "cong-nghe", "Du lịch": "du-lich",
        },
        "quota": 50,
        "method": "rss",
    },
    "DanTri": {
        "robots": "https://dantri.com.vn/robots.txt",
        "sitemap": "https://dantri.com.vn/sitemap.xml",
        "feed_tpl": "https://dantri.com.vn/rss/{slug}.rss",
        "cat_tpl": "https://dantri.com.vn/{slug}.htm",
        "article_pattern": r"^https?://dantri\.com\.vn/(?:[a-z0-9-]+/)*[a-z0-9-]+-\d{6,}\.htm$",
        "category_slugs": {
            "Kinh tế": "kinh-doanh", "Thế giới": "the-gioi",
            "Thể thao": "the-thao", "Pháp luật": "phap-luat",
            "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
            "Công nghệ": "cong-nghe", "Du lịch": "du-lich",
        },
        "quota": 100,
        "method": "rss",  # KHÔNG dùng /trang-2..9: robots.txt chặn
    },
    "VietnamNet": {
        "robots": "https://vietnamnet.vn/robots.txt",
        "sitemap": "https://vietnamnet.vn/sitemap.xml",
        "feed_tpl": "https://vietnamnet.vn/rss/{slug}.rss",
        "cat_tpl": "https://vietnamnet.vn/{slug}",
        "article_pattern": r"^https?://vietnamnet\.vn/[a-z0-9-]+-\d{6,}\.html$",
        "category_slugs": {
            "Kinh tế": "kinh-doanh", "Thế giới": "the-gioi",
            "Thể thao": "the-thao", "Pháp luật": "thoi-su/phap-luat",
            "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
            "Công nghệ": "cong-nghe", "Du lịch": "du-lich",
        },
        "quota": 400,
        # Riêng Công nghệ: feed đã ngừng cập nhật -> dùng -page0..15
        "method": "rss",
    },
}

ORIGINAL_CATEGORY = {
    "VnExpress": {
        "Kinh tế": "Kinh doanh", "Thế giới": "Thế giới", "Thể thao": "Thể thao",
        "Pháp luật": "Pháp luật", "Giáo dục": "Giáo dục", "Sức khỏe": "Sức khỏe",
        "Công nghệ": "Khoa học công nghệ", "Du lịch": "Du lịch",
    },
    "TuoiTre": {
        "Kinh tế": "Kinh doanh", "Thế giới": "Thế giới", "Thể thao": "Thể thao",
        "Pháp luật": "Pháp luật", "Giáo dục": "Giáo dục", "Sức khỏe": "Sức khỏe",
        "Công nghệ": "Nhịp sống số", "Du lịch": "Du lịch",
    },
    "ThanhNien": {
        "Kinh tế": "Kinh tế", "Thế giới": "Thế giới", "Thể thao": "Thể thao",
        "Pháp luật": "Thời sự / Pháp luật", "Giáo dục": "Giáo dục",
        "Sức khỏe": "Sức khỏe", "Công nghệ": "Công nghệ", "Du lịch": "Du lịch",
    },
    "DanTri": {
        "Kinh tế": "Kinh doanh", "Thế giới": "Thế giới", "Thể thao": "Thể thao",
        "Pháp luật": "Pháp luật", "Giáo dục": "Giáo dục", "Sức khỏe": "Sức khỏe",
        "Công nghệ": "Công nghệ", "Du lịch": "Du lịch",
    },
    "VietnamNet": {
        "Kinh tế": "Kinh doanh", "Thế giới": "Thế giới", "Thể thao": "Thể thao",
        "Pháp luật": "Thời sự / Pháp luật", "Giáo dục": "Giáo dục",
        "Sức khỏe": "Sức khỏe", "Công nghệ": "Công nghệ", "Du lịch": "Du lịch",
    },
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch(url: str) -> requests.Response:
    """GET có một lần thử lại khi lỗi kết nối; không thử lại 403/429."""
    try:
        return session.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        time.sleep(2)
        # TuoiTre có thể lỗi ChunkedEncoding; identity giúp tránh nén lỗi.
        return session.get(url, timeout=TIMEOUT,
                           headers={"Accept-Encoding": "identity"})


def parse_date(value: str) -> Optional[datetime]:
    """Đọc cả RFC 822 (4 báo) và M/D/YYYY h:mm:ss AM/PM (TuoiTre)."""
    value = (value or "").strip().replace("\u00a0", " ").replace("\u202f", " ")
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=VN_TZ)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def check_robots(site: str, cfg: dict) -> dict:
    r = fetch(cfg["robots"])
    (RAW / f"robots_{site}.txt").write_text(r.text, encoding="utf-8")
    print(f"[robots] {site:10s} HTTP {r.status_code}")
    time.sleep(DELAY_SECONDS)
    return {"site": site, "url": cfg["robots"],
            "status": r.status_code, "bytes": len(r.content)}


def check_sitemap(site: str, cfg: dict) -> dict:
    r = fetch(cfg["sitemap"])
    info = {"site": site, "url": cfg["sitemap"],
            "status": r.status_code, "bytes": len(r.content),
            "content_type": r.headers.get("content-type")}
    try:
        root = ET.fromstring(r.content)
        info["root"] = root.tag.rsplit("}", 1)[-1]
        info["children"] = sum(
            1 for e in root.iter()
            if e.tag.rsplit("}", 1)[-1] in {"sitemap", "url"}
        )
    except ET.ParseError:
        info["error"] = "Không phải XML hợp lệ"
    print(f"[sitemap] {site:9s} HTTP {r.status_code} "
          f"children={info.get('children', '?')}")
    time.sleep(DELAY_SECONDS)
    return info


def check_feed(site: str, topic: str, cfg: dict) -> dict:
    slug = cfg["category_slugs"][topic]
    if site == "VietnamNet" and topic == "Pháp luật":
        slug = "phap-luat"  # URL đúng đã kiểm tra: /rss/phap-luat.rss
    url = cfg["feed_tpl"].format(slug=slug)
    r = fetch(url)
    info = {"site": site, "topic": topic, "url": url,
            "status": r.status_code, "bytes": len(r.content),
            "content_type": r.headers.get("content-type")}
    try:
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
        links = [(it.findtext("link") or "").strip()
                 for it in items if it.findtext("link")]
        dates = [parse_date(it.findtext("pubDate")) for it in items]
        dates = [d for d in dates if d is not None]
        info.update({
            "root": root.tag.rsplit("}", 1)[-1],
            "channel_title": (channel.findtext("title") or "").strip()
            if channel is not None else None,
            "items": len(items),
            "unique_links": len(set(links)),
            "first_link": links[0] if links else None,
            "date_min": min(dates).isoformat() if dates else None,
            "date_max": max(dates).isoformat() if dates else None,
        })
    except ET.ParseError as exc:
        info["error"] = f"XML lỗi: {exc}"
    print(f"[rss] {site:10s} {topic:10s} HTTP {r.status_code} "
          f"items={info.get('items', '?')}")
    time.sleep(DELAY_SECONDS)
    return info


def check_category(site: str, topic: str, cfg: dict) -> dict:
    slug = cfg["category_slugs"][topic]
    url = cfg["cat_tpl"].format(slug=slug)
    r = fetch(url)
    info = {"site": site, "topic": topic, "url": url,
            "status": r.status_code, "bytes": len(r.content),
            "content_type": r.headers.get("content-type")}
    if r.status_code == 200 and "html" in (r.headers.get("content-type") or ""):
        soup = BeautifulSoup(r.text, "lxml")
        pattern = re.compile(cfg["article_pattern"])
        found = []
        for a in soup.find_all("a", href=True):
            link = urljoin(r.url, a["href"]).split("?")[0].split("#")[0]
            if pattern.match(link):
                found.append(link)
        unique = list(dict.fromkeys(found))
        info.update({
            "title": soup.title.get_text(" ", strip=True) if soup.title else None,
            "article_links": len(unique),
            "article_samples": unique[:3],
        })
    print(f"[cat] {site:10s} {topic:10s} HTTP {r.status_code} "
          f"articles≈{info.get('article_links', '?')}")
    time.sleep(DELAY_SECONDS)
    return info


def note_for(site: str, topic: str) -> str:
    """Ghi chú ngắn cho các trường hợp đặc biệt của từng nguồn."""
    if site == "VnExpress":
        if topic == "Công nghệ":
            return ("Trang p1 là Khoa học công nghệ; từ p2 URL chuyển thành "
                    "/cong-nghe-pN và H1 là Công nghệ. Cần kiểm tra thủ công "
                    "các bài khoa học thuần túy.")
        return ("Dùng trang danh mục p1–p5, khử trùng lặp; RSS là nguồn dự phòng.")
    if site == "TuoiTre":
        return ("Lấy 50 URL từ RSS. Ngày RSS dùng định dạng "
                "M/D/YYYY h:mm:ss AM/PM, không phải RFC 822.")
    if site == "ThanhNien":
        return "Lấy 50 URL từ RSS."
    if site == "DanTri":
        return ("Lấy 100 URL từ RSS. KHÔNG dùng phân trang /trang-*.htm "
                "vì robots.txt chặn.")
    if site == "VietnamNet":
        if topic == "Công nghệ":
            return ("RSS Công nghệ chỉ còn 36 mục, bài mới nhất 06/05/2025. "
                    "Dùng 16 trang danh mục /cong-nghe-page0..15.")
        if topic == "Pháp luật":
            return ("Feed đúng là /rss/phap-luat.rss; URL "
                    "/rss/thoi-su-phap-luat.rss trả 404.")
        return "RSS trả 1.000 mục; lấy 400 URL mới nhất để giữ cân bằng nguồn."
    return ""


def main() -> None:
    robots, sitemaps, feeds, cats = [], [], [], []
    for site, cfg in SITES.items():
        robots.append(check_robots(site, cfg))
        sitemaps.append(check_sitemap(site, cfg))

    for label in TOPICS:
        for site, cfg in SITES.items():
            feeds.append(check_feed(site, label, cfg))
            cats.append(check_category(site, label, cfg))

    (RAW / "robots.json").write_text(
        json.dumps(robots, ensure_ascii=False, indent=2), encoding="utf-8")
    (RAW / "sitemaps.json").write_text(
        json.dumps(sitemaps, ensure_ascii=False, indent=2), encoding="utf-8")
    (RAW / "feeds.json").write_text(
        json.dumps(feeds, ensure_ascii=False, indent=2), encoding="utf-8")
    (RAW / "categories.json").write_text(
        json.dumps(cats, ensure_ascii=False, indent=2), encoding="utf-8")

    feed_idx = {(x["site"], x["topic"]): x for x in feeds}
    cat_idx = {(x["site"], x["topic"]): x for x in cats}
    rows = []
    for label in TOPICS:
        for site, cfg in SITES.items():
            f, c = feed_idx[(site, label)], cat_idx[(site, label)]
            rows.append({
                "Label": label,
                "Source": site,
                "Original_Category": ORIGINAL_CATEGORY[site][label],
                "RSS_URL": f["url"],
                "RSS_HTTP": f.get("status"),
                "RSS_Items": f.get("items"),
                "RSS_Unique_Links": f.get("unique_links"),
                "RSS_Date_Min": f.get("date_min"),
                "RSS_Date_Max": f.get("date_max"),
                "Category_URL": c["url"],
                "Category_HTTP": c.get("status"),
                "Category_Article_Links": c.get("article_links"),
                "Selected_Method": (
                    "category_pages"
                    if site == "VnExpress"
                    or (site == "VietnamNet" and label == "Công nghệ")
                    else "rss"
                ),
                "Candidate_Quota": cfg["quota"],
                "Notes": note_for(site, label),
            })

    path = OUT / "step1_source_audit.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nĐã lưu {len(rows)} dòng vào {path}")
    print("Lưu ý: quota là số URL ứng viên, không phải số bài hợp lệ.")


if __name__ == "__main__":
    main()
