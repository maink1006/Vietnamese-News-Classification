#!/usr/bin/env python3
"""BƯỚC 3 — Thu thập danh sách URL ứng viên (KHÔNG crawl nội dung).

- Đọc ma trận Bước 2: outputs/step2_source_plan.csv.
- Chỉ GET trang danh mục hoặc RSS để lấy URL + metadata có sẵn.
- Cache từng task để chạy lại không mất tiến trình.
- Khử trùng URL trong nội bộ nguồn và giữa các nguồn.
- Ghi bản ghi trùng vào file riêng để kiểm tra.
- Không bịa URL; nếu thiếu quota thì ghi nhận gap.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "step3"
CACHE = DATA / "cache"
DATA.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

UA = "student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)"
HEADERS = {"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5"}
TIMEOUT = 35
DELAY = 1.5
VN_TZ = timezone(timedelta(hours=7))

LABEL_ORDER = ["Kinh tế", "Thế giới", "Thể thao", "Pháp luật",
               "Giáo dục", "Sức khỏe", "Công nghệ", "Du lịch"]
SOURCE_ORDER = ["VnExpress", "TuoiTre", "ThanhNien", "DanTri", "VietnamNet"]
LABEL_SLUG = {
    "Kinh tế": "kinh-te", "Thế giới": "the-gioi", "Thể thao": "the-thao",
    "Pháp luật": "phap-luat", "Giáo dục": "giao-duc", "Sức khỏe": "suc-khoe",
    "Công nghệ": "cong-nghe", "Du lịch": "du-lich",
}
SOURCE_SLUG = {
    "VnExpress": "vnexpress", "TuoiTre": "tuoitre", "ThanhNien": "thanhnien",
    "DanTri": "dantri", "VietnamNet": "vietnamnet",
}
TOPIC_KEY = {v: k for k, v in LABEL_SLUG.items()}
ARTICLE_PATTERNS = {
    "VnExpress": re.compile(r"^https?://vnexpress\.net/[a-z0-9-]+-\d{6,}(?:-[a-z0-9-]+)*\.html$"),
    "TuoiTre": re.compile(r"^https?://tuoitre\.vn/[a-z0-9-]+-\d{6,}\.htm$"),
    "ThanhNien": re.compile(r"^https?://thanhnien\.vn/[a-z0-9-]+-\d{6,}\.htm$"),
    "DanTri": re.compile(r"^https?://dantri\.com\.vn/(?:[a-z0-9-]+/)*[a-z0-9-]+-\d{6,}\.htm$"),
    "VietnamNet": re.compile(r"^https?://vietnamnet\.vn/[a-z0-9-]+-\d{6,}\.html$"),
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
NETWORK_REQUESTS = 0


def now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def clean_title(value: str) -> str:
    # RSS một số báo có title bị HTML-escape (ví dụ &ocirc;); giải mã metadata.
    return html.unescape(html.unescape(value or "")).strip()


def slug_key(source: str, label: str, method: str, task_id: str) -> Path:
    return CACHE / SOURCE_SLUG[source] / LABEL_SLUG[label] / method / f"{task_id}.json"


def is_boilerplate(rec: dict) -> bool:
    """Loại link chân trang/chính sách bị bắt nhầm từ trang danh mục."""
    title = normalize_title(rec.get("Title", ""))
    bad_titles = (
        "chinh sach bao mat", "dieu khoan su dung", "quy che hoat dong",
        "chinh sach doi tra", "lien he toa soan", "thong tin toa soan",
    )
    if any(title.startswith(x) for x in bad_titles):
        return True
    url = (rec.get("URL_Normalized") or "").lower()
    bad_urls = ("chinh-sach-bao-mat", "dieu-khoan-su-dung", "quy-che-hoat-dong")
    return any(x in url for x in bad_urls)


def is_bad_metadata(rec: dict) -> bool:
    """Loại card video/ảnh có tiêu đề chỉ là thời lượng, không phải headline."""
    title = clean_title(rec.get("Title", ""))
    if re.fullmatch(r"\d{1,2}:\d{2}", title):
        return True
    return title.strip().lower() in {"video", "ảnh", "infographic", "podcast", "livestream"}


def method_priority(rec: dict) -> int:
    """Ưu tiên phương thức chính của từng nguồn khi cùng một URL."""
    source, detail = rec["Source"], rec.get("Collection_Detail", "")
    if source == "VnExpress":
        return 0 if detail == "category_primary" else 1
    if source in {"TuoiTre", "DanTri"}:
        return 0 if detail == "rss" else 1
    if source == "VietnamNet" and rec["Label"] == "Công nghệ":
        return 0 if detail == "category_primary" else 1
    return 0 if detail == "rss" else 1


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def parse_date(value: str) -> Optional[str]:
    value = (value or "").strip().replace("\u00a0", " ").replace("\u202f", " ")
    if not value:
        return None
    try:
        dt = datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")
        return dt.replace(tzinfo=VN_TZ).isoformat(timespec="seconds")
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt.astimezone(VN_TZ).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def fetch(url: str) -> requests.Response:
    global NETWORK_REQUESTS
    last_error = None
    for attempt in range(2):
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            NETWORK_REQUESTS += 1
            time.sleep(DELAY)
            return r
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(2)
    raise last_error


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_category_page(html: str, task_url: str, source: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    pattern = ARTICLE_PATTERNS[source]
    by_url = {}
    order = 0
    for a in soup.find_all("a", href=True):
        link = urljoin(task_url, a["href"]).split("#")[0]
        if not pattern.match(link.split("?")[0]):
            continue
        link = link.split("?")[0]
        order += 1
        cur = by_url.setdefault(link, {
            "URL": link, "Title_Attr": "", "Title_Text": "", "Position": order
        })
        attr_title = clean_title(a.get("title") or "")
        text_title = clean_title(a.get_text(" ", strip=True))
        if attr_title and not cur["Title_Attr"]:
            cur["Title_Attr"] = attr_title
        if text_title and not cur["Title_Text"]:
            cur["Title_Text"] = text_title
    rows = []
    for cur in by_url.values():
        # Ưu tiên title attribute; nếu không có, lấy text đầu tiên (headline),
        # không lấy đoạn mô tả dài hơn ở các thẻ phụ.
        rows.append({"URL": cur["URL"], "Title": cur["Title_Attr"] or cur["Title_Text"],
                     "Position": cur["Position"]})
    return rows


def category_task(plan_row: dict, page_no: int, task_url: str, refresh: bool,
                  method: str = "category", task_id: Optional[str] = None) -> dict:
    source, label = plan_row["Source"], plan_row["Label"]
    task_id = task_id or f"p{page_no:02d}"
    cache_path = slug_key(source, label, method, task_id)
    if not refresh:
        cached = read_json(cache_path)
        if cached is not None:
            return {"status": "cache", "records": cached["records"]}
    try:
        r = fetch(task_url)
        if r.status_code != 200 or "html" not in (r.headers.get("content-type") or ""):
            return {"status": "error", "records": [],
                    "note": f"HTTP {r.status_code}, content-type={r.headers.get('content-type')}"}
        rows = parse_category_page(r.text, r.url, source)
        records = [{
            "Source": source, "Label": label,
            "Original_Category": plan_row["Original_Category"],
            "URL": x["URL"], "URL_Normalized": normalize_url(x["URL"]),
            "Collection_Method": method, "Title": clean_title(x["Title"]),
            "Published_Date": None, "Collected_At": now_iso(),
            "Task_URL": task_url, "Task_Page": page_no, "Position": x["Position"],
        } for x in rows]
        write_json(cache_path, {"task_url": task_url, "fetched_at": now_iso(), "records": records})
        return {"status": "fetched", "records": records}
    except Exception as exc:
        return {"status": "error", "records": [], "note": repr(exc)[:250]}


def feed_rows(source: str, label: str, feed_url: str, feed_path: Path,
              refresh: bool = False) -> list:
    if feed_path.exists() and not refresh:
        content = feed_path.read_bytes()
    else:
        r = fetch(feed_url)
        if r.status_code != 200:
            raise RuntimeError(f"feed HTTP {r.status_code}: {feed_url}")
        content = r.content
        feed_path.parent.mkdir(parents=True, exist_ok=True)
        feed_path.write_bytes(content)
    root = ET.fromstring(content)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed không có channel")
    records = []
    for pos, item in enumerate(channel.findall("item"), start=1):
        link = (item.findtext("link") or "").strip()
        if not link:
            continue
        title = clean_title(item.findtext("title") or "")
        published = parse_date(item.findtext("pubDate") or "")
        records.append({
            "Source": source, "Label": label, "Original_Category": None,
            "URL": link, "URL_Normalized": normalize_url(link),
            "Collection_Method": "rss", "Title": title,
            "Published_Date": published, "Collected_At": now_iso(),
            "Task_URL": feed_url, "Task_Page": 1, "Position": pos,
        })
    return records


def rss_task(plan_row: dict, feed_path: Path, refresh: bool) -> dict:
    source, label = plan_row["Source"], plan_row["Label"]
    cache_path = slug_key(source, label, "rss", "rss")
    if not refresh:
        cached = read_json(cache_path)
        if cached is not None:
            return {"status": "cache", "records": cached["records"]}
    try:
        records = feed_rows(source, label, plan_row["Primary_URL"], feed_path, refresh)
        for rec in records:
            rec["Original_Category"] = plan_row["Original_Category"]
        write_json(cache_path, {"task_url": plan_row["Primary_URL"],
                                "fetched_at": now_iso(), "records": records})
        return {"status": "fetched", "records": records}
    except Exception as exc:
        return {"status": "error", "records": [], "note": repr(exc)[:250]}


def vnexpress_rss_metadata(refresh: bool) -> dict:
    """Đọc RSS VnExpress để bổ sung title/ngày; không dùng để thay quota."""
    all_records = []
    for label in LABEL_ORDER:
        cache_path = slug_key("VnExpress", label, "rss_metadata", "rss")
        if not refresh:
            cached = read_json(cache_path)
            if cached is not None:
                all_records.extend(cached["records"])
                continue
        key = LABEL_SLUG[label]
        feed_path = ROOT / "research" / "raw" / "feeds" / "VnExpress" / f"{key}.xml"
        url = f"https://vnexpress.net/rss/{key}.rss"
        try:
            records = feed_rows("VnExpress", label, url, feed_path, refresh)
            write_json(cache_path, {"task_url": url, "fetched_at": now_iso(), "records": records})
            all_records.extend(records)
        except Exception as exc:
            print("WARN VnExpress RSS", label, repr(exc)[:120])
    return {"records": all_records}


def build_tasks(plan: pd.DataFrame) -> list:
    tasks = []
    for _, row in plan.iterrows():
        row = row.to_dict()
        if row["Primary_Method"] == "category_pages":
            urls = [row["Primary_URL"]]
            extra = row.get("Additional_Pages")
            if isinstance(extra, str) and extra.strip():
                urls += [x.strip() for x in extra.split(";") if x.strip()]
            for page_no, url in enumerate(urls, start=1):
                tasks.append({"kind": "category", "row": row, "page": page_no, "url": url})
        else:
            tasks.append({"kind": "rss", "row": row, "page": 1, "url": row["Primary_URL"]})
    return tasks


def main(refresh: bool = False) -> dict:
    global NETWORK_REQUESTS
    NETWORK_REQUESTS = 0
    plan_path = ROOT / "outputs" / "step2_source_plan.csv"
    plan = pd.read_csv(plan_path, encoding="utf-8-sig")
    assert len(plan) == 40, f"Kế hoạch phải có 40 dòng, đang có {len(plan)}"
    tasks = build_tasks(plan)

    cache_hits = fetched = errors = 0
    errors_detail = []
    raw = []
    for idx, task in enumerate(tasks, start=1):
        row = task["row"]
        if task["kind"] == "category":
            result = category_task(row, task["page"], task["url"], refresh)
        else:
            key = LABEL_SLUG[row["Label"]]
            site_dir = {"TuoiTre": "TuoiTre", "ThanhNien": "ThanhNien",
                        "DanTri": "DanTri", "VietnamNet": "VietnamNet"}[row["Source"]]
            feed_path = ROOT / "research" / "raw" / "feeds" / site_dir / f"{key}.xml"
            result = rss_task(row, feed_path, refresh)
        if result["status"] == "cache":
            cache_hits += 1
        elif result["status"] == "fetched":
            fetched += 1
        else:
            errors += 1
            errors_detail.append({"kind": task["kind"], "source": row["Source"],
                                  "label": row["Label"], "url": task["url"],
                                  "note": result.get("note", "")})
        raw.extend(result["records"])
        print(f"[{idx:02d}/{len(tasks)}] {result['status']:7s} "
              f"{row['Source']:10s} {row['Label']:10s} page={task['page']:02d} "
              f"records={len(result['records'])}", flush=True)

    # Fallback category pages cho 2 nguồn RSS và trang kế tiếp của VNNet Công nghệ.
    # Chỉ dùng khi nguồn chính thiếu 1-2 URL do trùng thật; vẫn giữ đúng quota nguồn.
    fallback_tasks = []
    for _, row in plan.iterrows():
        if row["Source"] in {"TuoiTre", "DanTri"}:
            fallback_tasks.append((row.to_dict(), 99, row["Fallback_URL"],
                                   "category_fallback", "fallback"))
    vn_tech = plan[(plan["Source"] == "VietnamNet") &
                   (plan["Label"] == "Công nghệ")].iloc[0].to_dict()
    fallback_tasks.append((vn_tech, 17, "https://vietnamnet.vn/cong-nghe-page16",
                           "category_fallback", "p17"))
    for row, page_no, url, method, task_id in fallback_tasks:
        result = category_task(row, page_no, url, refresh, method=method, task_id=task_id)
        if result["status"] == "cache":
            cache_hits += 1
        elif result["status"] == "fetched":
            fetched += 1
        else:
            errors += 1
            errors_detail.append({"kind": method, "source": row["Source"],
                                  "label": row["Label"], "url": url,
                                  "note": result.get("note", "")})
        raw.extend(result["records"])
        print(f"[fallback] {result['status']:7s} {row['Source']:10s} "
              f"{row['Label']:10s} page={page_no:02d} records={len(result['records'])}", flush=True)

    # RSS VnExpress: metadata enrichment + fallback; không gửi request nếu file đã có.
    vne_rss = vnexpress_rss_metadata(refresh)["records"]
    orig_map = {(r["Source"], r["Label"]): r["Original_Category"]
                for _, r in plan.iterrows()}
    for rec in vne_rss:
        rec["Original_Category"] = orig_map.get((rec["Source"], rec["Label"]))
        rec["_rss_only"] = True

    # Chuẩn hóa method công khai: chỉ 'rss' hoặc 'category'; chi tiết nằm ở Collection_Detail.
    for rec in raw + vne_rss:
        detail = rec.get("Collection_Detail")
        if not detail:
            m = rec.get("Collection_Method")
            detail = ("category_fallback" if m == "category_fallback"
                      else "category_primary" if m == "category" else "rss")
        rec["Collection_Detail"] = detail
        rec["Collection_Method"] = "category" if detail.startswith("category") else "rss"
        rec["Method_Priority"] = method_priority(rec)

    before_filter = len(raw) + len(vne_rss)
    raw = [r for r in raw if not is_boilerplate(r) and not is_bad_metadata(r)]
    vne_rss = [r for r in vne_rss if not is_boilerplate(r) and not is_bad_metadata(r)]
    boilerplate_dropped = before_filter - len(raw) - len(vne_rss)

    # Gán thứ tự toàn cục theo thứ tự task; category đứng trước RSS.
    for i, rec in enumerate(raw, start=1):
        rec["Global_Order"] = i
    for j, rec in enumerate(vne_rss, start=1):
        rec["Global_Order"] = len(raw) + j
    for rec in raw + vne_rss:
        rec["Pool_ID"] = f"P{rec['Global_Order']:06d}"

    # Khử trùng URL trong pool; ưu tiên bản ghi category và bản ghi có metadata.
    groups = {}
    for rec in raw + vne_rss:
        groups.setdefault(rec["URL_Normalized"], []).append(rec)
    merged = []
    duplicate_url_rows = []
    for gid, records in enumerate(groups.values(), start=1):
        records = sorted(records, key=lambda r: (
            r.get("Method_Priority", 9),
            r["Global_Order"],
        ))
        primary = dict(records[0])
        primary["Title"] = clean_title(primary.get("Title", ""))
        if not primary.get("Title"):
            for alt in records[1:]:
                if alt.get("Title"):
                    primary["Title"] = alt["Title"]; break
        if not primary.get("Published_Date"):
            for alt in records[1:]:
                if alt.get("Published_Date"):
                    primary["Published_Date"] = alt["Published_Date"]; break
        primary["URL_Duplicate_Count"] = len(records) - 1
        primary["URL_Duplicate_Group"] = f"URL{gid:05d}" if len(records) > 1 else ""
        merged.append(primary)
        if len(records) > 1:
            labels = sorted({r["Label"] for r in records})
            sources = sorted({r["Source"] for r in records})
            methods = {r["Collection_Method"] for r in records}
            # Bỏ qua trùng do RSS bổ sung metadata cho cùng bài category.
            # Vẫn ghi nhận nếu khác nhãn/nguồn, hoặc trùng lặp thật trong cùng phương thức.
            if len(labels) == 1 and len(sources) == 1 and len(methods) > 1:
                continue
            for alt in records[1:]:
                alt["Title"] = clean_title(alt.get("Title", ""))
                duplicate_url_rows.append({
                    "Duplicate_Type": "same_url",
                    "Group_ID": f"URL{gid:05d}",
                    "Primary_ID": records[0].get("Pool_ID", ""),
                    "Duplicate_ID": alt.get("Pool_ID", ""),
                    "Source_Primary": records[0]["Source"], "Source_Duplicate": alt["Source"],
                    "Label_Primary": records[0]["Label"], "Label_Duplicate": alt["Label"],
                    "URL_Primary": records[0]["URL"], "URL_Duplicate": alt["URL"],
                    "Title_Primary": records[0].get("Title", ""), "Title_Duplicate": alt.get("Title", ""),
                    "Action": "merged_keep_primary",
                    "Note": ("URL trùng; " +
                             ("khác nhãn: " + ", ".join(labels) if len(labels) > 1 else "cùng nhãn") +
                             ("; khác nguồn" if len(sources) > 1 else "")),
                })

    # Chọn đúng quota theo (Label, Source); không bịa.
    selected = []
    gaps = []
    for label in LABEL_ORDER:
        for source in SOURCE_ORDER:
            quota = int(plan[(plan["Label"] == label) &
                             (plan["Source"] == source)]["Candidate_Quota"].iloc[0])
            pool = [r for r in merged if r["Label"] == label and r["Source"] == source]
            pool.sort(key=lambda r: (r["Global_Order"],))
            chosen = pool[:quota]
            selected.extend(chosen)
            gaps.append({
                "Label": label, "Source": source, "Target": quota,
                "Available_After_URL_Dedupe": len(pool), "Selected": len(chosen),
                "Gap": max(0, quota - len(chosen)),
                "Note": "" if len(chosen) >= quota else "Thiếu URL; không tạo dữ liệu giả",
            })

    # Sắp xếp cuối: Label -> Source -> thứ tự thu thập.
    selected.sort(key=lambda r: (LABEL_ORDER.index(r["Label"]),
                                 SOURCE_ORDER.index(r["Source"]),
                                 r["Global_Order"]))
    for rec in selected:
        rec["Title"] = clean_title(rec.get("Title", ""))
    for i, rec in enumerate(selected, start=1):
        rec["Candidate_ID"] = f"C{i:06d}"
        rec["Potential_Duplicate"] = "no"
        rec["Duplicate_Group"] = ""
        rec["Review_Note"] = ""

    assert len({r["URL_Normalized"] for r in selected}) == len(selected), \
        "URL cuối cùng vẫn còn trùng"
    assert all(r.get("Original_Category") for r in selected), \
        "Có bản ghi thiếu Original_Category"

    # Gắn cờ trùng tiêu đề (khác URL) để rà soát leakage.
    title_groups = {}
    for rec in selected:
        norm = normalize_title(rec.get("Title", ""))
        if norm and len(norm) >= 25:
            title_groups.setdefault(norm, []).append(rec)
    duplicate_title_rows = []
    tgid = 0
    for records in title_groups.values():
        if len(records) < 2:
            continue
        tgid += 1
        group_id = f"TITLE{tgid:05d}"
        records = sorted(records, key=lambda r: r["Candidate_ID"])
        primary = records[0]
        for rec in records:
            rec["Potential_Duplicate"] = "yes"
            rec["Duplicate_Group"] = group_id
            rec["Review_Note"] = "Cùng tiêu đề chuẩn hóa; cần kiểm tra nội dung ở Bước 4/5"
        for alt in records[1:]:
            duplicate_title_rows.append({
                "Duplicate_Type": "same_title",
                "Group_ID": group_id,
                "Primary_ID": primary["Candidate_ID"], "Duplicate_ID": alt["Candidate_ID"],
                "Source_Primary": primary["Source"], "Source_Duplicate": alt["Source"],
                "Label_Primary": primary["Label"], "Label_Duplicate": alt["Label"],
                "URL_Primary": primary["URL"], "URL_Duplicate": alt["URL"],
                "Title_Primary": primary.get("Title", ""), "Title_Duplicate": alt.get("Title", ""),
                "Action": "flagged_keep_both",
                "Note": "Cùng tiêu đề; giữ cả hai để kiểm tra bằng nội dung/hash ở bước sau",
            })

    # Ghi outputs.
    raw_fields = ["Pool_ID", "Global_Order", "Source", "Label", "Original_Category", "URL",
                  "URL_Normalized", "Collection_Method", "Collection_Detail", "Title", "Published_Date",
                  "Collected_At", "Task_URL", "Task_Page", "Position"]
    with (DATA / "raw_pool.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(merged, key=lambda r: r["Global_Order"]))

    final_fields = ["Candidate_ID", "Source", "Label", "Original_Category", "URL",
                    "URL_Normalized", "Collection_Method", "Collection_Detail", "Title", "Published_Date",
                    "Collected_At", "Potential_Duplicate", "Duplicate_Group", "Review_Note"]
    with (DATA / "url_candidates.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=final_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(selected)

    duplicate_fields = ["Duplicate_Type", "Group_ID", "Primary_ID", "Duplicate_ID",
                        "Source_Primary", "Source_Duplicate", "Label_Primary", "Label_Duplicate",
                        "URL_Primary", "URL_Duplicate", "Title_Primary", "Title_Duplicate",
                        "Action", "Note"]
    with (DATA / "duplicates_review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=duplicate_fields)
        w.writeheader()
        w.writerows(duplicate_url_rows + duplicate_title_rows)

    gap_df = pd.DataFrame(gaps)
    gap_df.to_csv(DATA / "gaps.csv", index=False, encoding="utf-8-sig")

    summary = (pd.DataFrame(selected)
               .pivot_table(index="Label", columns="Source", values="Candidate_ID",
                            aggfunc="count", fill_value=0)
               .reindex(LABEL_ORDER)
               .reindex(columns=SOURCE_ORDER, fill_value=0))
    summary["Total"] = summary.sum(axis=1)
    summary["Target"] = 750
    summary["Gap"] = (summary["Target"] - summary["Total"]).clip(lower=0)
    summary.reset_index().to_csv(DATA / "summary_by_label.csv", index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": now_iso(),
        "plan_rows": len(plan),
        "primary_tasks": len(tasks),
        "fallback_tasks": len(fallback_tasks),
        "tasks_total": len(tasks) + len(fallback_tasks),
        "cache_hits": cache_hits,
        "fetched": fetched,
        "errors": errors,
        "errors_detail": errors_detail,
        "article_content_requests": 0,
        "network_requests": NETWORK_REQUESTS,
        "raw_records_including_rss_enrichment": len(raw) + len(vne_rss),
        "unique_urls_after_dedupe": len(merged),
        "boilerplate_or_bad_metadata_dropped": boilerplate_dropped,
        "selected": len(selected),
        "unique_final_urls": len({r["URL_Normalized"] for r in selected}),
        "by_collection_method": pd.Series([r["Collection_Method"] for r in selected]).value_counts().to_dict(),
        "by_collection_detail": pd.Series([r["Collection_Detail"] for r in selected]).value_counts().to_dict(),
        "target": 6000,
        "gap_total": int(gap_df["Gap"].sum()),
        "duplicate_url_cases": len(duplicate_url_rows),
        "potential_title_duplicate_cases": len(duplicate_title_rows),
        "by_label": summary.reset_index().to_dict(orient="records"),
    }
    write_json(DATA / "manifest.json", manifest)
    print("\nDONE")
    print(json.dumps({k: manifest[k] for k in [
        "tasks_total", "cache_hits", "fetched", "errors", "network_requests",
        "raw_records_including_rss_enrichment", "unique_urls_after_dedupe",
        "selected", "gap_total", "duplicate_url_cases",
        "potential_title_duplicate_cases"]}, ensure_ascii=False, indent=2))
    print("Selected by label/source:\n", summary)
    return manifest


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFC", clean_title(title)).lower()
    text = re.sub(r"\[(video|ảnh|infographic|podcast|livestream|đồ họa)\]", " ", text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Tải lại trang/RSS, bỏ qua cache")
    args = ap.parse_args()
    main(refresh=args.refresh)
