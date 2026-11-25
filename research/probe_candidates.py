"""Khao sat RSS + trang danh muc cho 5 bao. Chi GET, khong crawl bai.
Chi tiet: 1 request cach nhau 1.5 giay, UA minh bach.
"""
import json, re, time
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

OUT = Path("research/raw")
OUT.mkdir(parents=True, exist_ok=True)
UA = "student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)"
HEADERS = {"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5"}
S = requests.Session()
S.headers.update(HEADERS)

TOPICS = ["kinh-te", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe", "cong-nghe", "du-lich"]

CANDIDATES = {
    "VnExpress": {
        "base": "https://vnexpress.net",
        "feeds": {t: f"https://vnexpress.net/rss/{slug}.rss" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "khoa-hoc-cong-nghe", "du-lich"])},
        "cats": {t: f"https://vnexpress.net/{slug}" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "khoa-hoc-cong-nghe", "du-lich"])},
    },
    "TuoiTre": {
        "base": "https://tuoitre.vn",
        "feeds": {t: f"https://tuoitre.vn/{slug}.rss" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "nhip-song-so", "du-lich"])},
        "cats": {t: f"https://tuoitre.vn/{slug}.htm" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "nhip-song-so", "du-lich"])},
    },
    "ThanhNien": {
        "base": "https://thanhnien.vn",
        "feeds": {t: f"https://thanhnien.vn/rss/{slug}.rss" for t, slug in zip(TOPICS, [
            "kinh-te", "the-gioi", "the-thao", "thoi-su/phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
        "cats": {t: f"https://thanhnien.vn/{slug}.htm" for t, slug in zip(TOPICS, [
            "kinh-te", "the-gioi", "the-thao", "thoi-su/phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
    },
    "DanTri": {
        "base": "https://dantri.com.vn",
        "feeds": {t: f"https://dantri.com.vn/rss/{slug}.rss" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
        "cats": {t: f"https://dantri.com.vn/{slug}.htm" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
    },
    "VietnamNet": {
        "base": "https://vietnamnet.vn",
        "feeds": {t: f"https://vietnamnet.vn/rss/{slug}.rss" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "thoi-su-phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
        "cats": {t: f"https://vietnamnet.vn/{slug}" for t, slug in zip(TOPICS, [
            "kinh-doanh", "the-gioi", "the-thao", "thoi-su/phap-luat", "giao-duc", "suc-khoe",
            "cong-nghe", "du-lich"])},
    },
}

def xml_info(resp):
    info = {"items": None, "first_title": None, "first_link": None, "is_xml": False}
    if not resp.content:
        return info
    try:
        root = ET.fromstring(resp.content)
    except Exception:
        return info
    info["is_xml"] = True
    info["root"] = root.tag.rsplit("}", 1)[-1]
    items = root.findall(".//item")
    if not items:
        # urlset sitemap
        locs = [e.text.strip() for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "loc" and e.text]
        info["items"] = len(locs)
        info["first_link"] = locs[0] if locs else None
        return info
    info["items"] = len(items)
    info["first_title"] = (items[0].findtext("title") or "").strip()
    link = items[0].findtext("link")
    if not link:
        guid = items[0].findtext("guid")
        link = guid if guid and guid.startswith("http") else None
    info["first_link"] = (link or "").strip()
    dates = [x.findtext("pubDate") for x in items if x.findtext("pubDate")]
    if dates:
        info["first_pubdate"] = dates[0].strip()
        info["last_pubdate"] = dates[-1].strip()
    return info

ARTICLE_RE = {
    "VnExpress": re.compile(r"^https?://vnexpress\.net/[a-z0-9-]+(?:-[a-z0-9-]+)*\.html$"),
    "TuoiTre": re.compile(r"^https?://tuoitre\.vn/[a-z0-9-]+\.htm$"),
    "ThanhNien": re.compile(r"^https?://thanhnien\.vn/[a-z0-9-]+\.htm$"),
    "DanTri": re.compile(r"^https?://dantri\.com\.vn/[a-z0-9-]+\.htm$|^https?://dantri\.com\.vn/[a-z0-9-]+/[a-z0-9-]+\.htm$"),
    "VietnamNet": re.compile(r"^https?://vietnamnet\.vn/[a-z0-9-]+\.html$"),
}

def html_info(site, resp):
    soup = BeautifulSoup(resp.text, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    links = []
    for a in soup.find_all("a", href=True):
        href = requests.compat.urljoin(resp.url, a["href"].strip())
        href = href.split("?")[0].split("#")[0]
        if ARTICLE_RE[site].match(href):
            links.append(href)
    uniq = list(dict.fromkeys(links))
    nexts = []
    for a in soup.find_all("a", href=True):
        txt = (a.get_text(" ", strip=True) + " " + a.get("rel", [""])[0] if isinstance(a.get("rel"), list) else a.get_text(" ", strip=True)).lower()
        if "trang 2" in txt or "trang-2" in a["href"].lower() or "page=2" in a["href"].lower() or "p2" == a["href"].lower()[-2:]:
            nexts.append(requests.compat.urljoin(resp.url, a["href"]))
    return {"title": title, "article_links": len(uniq), "article_samples": uniq[:3],
            "next_page_candidates": list(dict.fromkeys(nexts))[:3],
            "final_url": resp.url}

results = []
for site, cfg in CANDIDATES.items():
    for topic, url in cfg["feeds"].items():
        rec = {"site": site, "topic": topic, "kind": "rss", "url": url}
        try:
            r = S.get(url, timeout=25)
            rec.update(status=r.status_code, content_type=r.headers.get("content-type"), bytes=len(r.content), final_url=r.url)
            rec.update(xml_info(r))
        except Exception as e:
            rec["error"] = repr(e)[:300]
        results.append(rec)
        print(f"RSS {site:10s} {topic:10s} {rec.get('status','ERR')} items={rec.get('items')} {url}", flush=True)
        time.sleep(1.5)
    for topic, url in cfg["cats"].items():
        rec = {"site": site, "topic": topic, "kind": "cat", "url": url}
        try:
            r = S.get(url, timeout=25)
            rec.update(status=r.status_code, content_type=r.headers.get("content-type"), bytes=len(r.content), final_url=r.url)
            if r.status_code == 200 and "html" in (r.headers.get("content-type") or ""):
                rec.update(html_info(site, r))
        except Exception as e:
            rec["error"] = repr(e)[:300]
        results.append(rec)
        print(f"CAT {site:10s} {topic:10s} {rec.get('status','ERR')} articles={rec.get('article_links')} {url}", flush=True)
        time.sleep(1.5)

(OUT / "probe_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("Saved", OUT / "probe_results.json")
