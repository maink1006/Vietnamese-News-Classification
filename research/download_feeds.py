"""Tai va kiem tra 40 feed da xac minh. Chi phuc vu Buoc 1."""
import json, re, time
from pathlib import Path
from email.utils import parsedate_to_datetime
import requests, xml.etree.ElementTree as ET

ROOT = Path("research/raw/feeds")
ROOT.mkdir(parents=True, exist_ok=True)
UA = "student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)"
S = requests.Session(); S.headers.update({"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9"})

FEEDS = {
 "VnExpress": ("https://vnexpress.net/rss/{slug}.rss", {
   "kinh-te":"kinh-doanh","the-gioi":"the-gioi","the-thao":"the-thao","phap-luat":"phap-luat",
   "giao-duc":"giao-duc","suc-khoe":"suc-khoe","cong-nghe":"khoa-hoc-cong-nghe","du-lich":"du-lich"}),
 "TuoiTre": ("https://tuoitre.vn/{slug}.rss", {
   "kinh-te":"kinh-doanh","the-gioi":"the-gioi","the-thao":"the-thao","phap-luat":"phap-luat",
   "giao-duc":"giao-duc","suc-khoe":"suc-khoe","cong-nghe":"nhip-song-so","du-lich":"du-lich"}),
 "ThanhNien": ("https://thanhnien.vn/rss/{slug}.rss", {
   "kinh-te":"kinh-te","the-gioi":"the-gioi","the-thao":"the-thao","phap-luat":"thoi-su/phap-luat",
   "giao-duc":"giao-duc","suc-khoe":"suc-khoe","cong-nghe":"cong-nghe","du-lich":"du-lich"}),
 "DanTri": ("https://dantri.com.vn/rss/{slug}.rss", {
   "kinh-te":"kinh-doanh","the-gioi":"the-gioi","the-thao":"the-thao","phap-luat":"phap-luat",
   "giao-duc":"giao-duc","suc-khoe":"suc-khoe","cong-nghe":"cong-nghe","du-lich":"du-lich"}),
 "VietnamNet": ("https://vietnamnet.vn/rss/{slug}.rss", {
   "kinh-te":"kinh-doanh","the-gioi":"the-gioi","the-thao":"the-thao","phap-luat":"phap-luat",
   "giao-duc":"giao-duc","suc-khoe":"suc-khoe","cong-nghe":"cong-nghe","du-lich":"du-lich"}),
}

def local(tag): return tag.rsplit("}", 1)[-1]
def clean(s): return re.sub(r"\s+", " ", s or "").strip()

audit=[]
for site,(pattern,slugs) in FEEDS.items():
    (ROOT/site).mkdir(parents=True, exist_ok=True)
    for topic, slug in slugs.items():
        url = pattern.format(slug=slug)
        rec={"site":site,"topic":topic,"url":url}
        try:
            r=S.get(url,timeout=40)
            rec.update(status=r.status_code, bytes=len(r.content), content_type=r.headers.get("content-type"), final_url=r.url)
            path=ROOT/site/f"{topic}.xml"; path.write_bytes(r.content)
            root=ET.fromstring(r.content)
            channel=root.find("channel")
            rec["root"]=local(root.tag)
            rec["channel_title"]=clean(channel.findtext("title")) if channel is not None else None
            items=channel.findall("item") if channel is not None else []
            links=[clean(it.findtext("link")) for it in items if clean(it.findtext("link"))]
            dates=[]
            for it in items:
                d=clean(it.findtext("pubDate"))
                if not d: continue
                try: dates.append(parsedate_to_datetime(d))
                except Exception: pass
            rec.update(items=len(items), unique_links=len(set(links)),
                       duplicate_links=len(links)-len(set(links)),
                       first_link=links[0] if links else None,
                       first_title=clean(items[0].findtext("title")) if items else None,
                       date_min=min(dates).isoformat() if dates else None,
                       date_max=max(dates).isoformat() if dates else None,
                       has_description=any(it.findtext("description") for it in items))
        except Exception as e:
            rec["error"]=repr(e)[:300]
        audit.append(rec)
        print(f"{site:10s} {topic:10s} {rec.get('status')} items={rec.get('items')} dates={rec.get('date_min')} -> {rec.get('date_max')}", flush=True)
        time.sleep(1.2)

Path("research/raw/feed_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
print("DONE")
