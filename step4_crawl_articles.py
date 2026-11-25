#!/usr/bin/env python3
"""BƯỚC 4 — Crawl nội dung bài viết từ danh sách URL Bước 3.

Đặc điểm:
- Parser riêng cho 5 báo.
- Checkpoint JSONL sau từng bài; chạy lại chỉ crawl bài chưa thành công.
- Ghi riêng lỗi và lý do; không bỏ qua âm thầm.
- Không xóa bài trùng tiêu đề; chỉ tổng hợp để kiểm tra.
- Không tiền xử lý NLP.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from step4_parsers import parse_article

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "step4"
CHECKPOINTS = DATA / "checkpoints"
FAILURES = DATA / "failures"
for d in (DATA, CHECKPOINTS, FAILURES):
    d.mkdir(parents=True, exist_ok=True)

UA = "student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)"
HEADERS = {"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5"}
TIMEOUT = 35
DELAY = 1.3
VN_TZ = timezone(timedelta(hours=7))
SOURCE_WORKERS = {"VnExpress": 2, "TuoiTre": 1, "ThanhNien": 1,
                  "DanTri": 2, "VietnamNet": 3}
SOURCE_DELAY = {"DanTri": 3.0}
SOURCE_TIMEOUT = {"DanTri": 20}
LABEL_ORDER = ["Kinh tế", "Thế giới", "Thể thao", "Pháp luật",
               "Giáo dục", "Sức khỏe", "Công nghệ", "Du lịch"]
SOURCE_ORDER = ["VnExpress", "TuoiTre", "ThanhNien", "DanTri", "VietnamNet"]

LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
START = time.time()
LAST_PROGRESS = 0.0
STATE = {"success_this_run": 0, "failure_this_run": 0,
         "by_source": {s: 0 for s in SOURCE_ORDER},
         "by_source_fail": {s: 0 for s in SOURCE_ORDER},
         "requests": 0}


def now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def log(message: str) -> None:
    with LOG_LOCK:
        print(message, flush=True)


def load_success() -> dict:
    records = {}
    for path in sorted(CHECKPOINTS.glob("*.jsonl")):
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = rec.get("ID")
                if rid and rid not in records:
                    records[rid] = rec
    return records


def load_failures() -> list:
    rows = []
    for path in sorted(FAILURES.glob("*.jsonl")):
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        fp.flush()
        os.fsync(fp.fileno())


def progress_snapshot(total: int, initial_success: dict) -> dict:
    success = initial_success["total"] + STATE["success_this_run"]
    by_source = dict(initial_success["by_source"])
    for src, n in STATE["by_source"].items():
        by_source[src] += n
    return {
        "updated_at": now_iso(),
        "elapsed_seconds": round(time.time() - START, 1),
        "total_candidates": total,
        "success": success,
        "success_this_run": STATE["success_this_run"],
        "failed_attempts_this_run": STATE["failure_this_run"],
        "remaining": total - success,
        "requests_this_run": STATE["requests"],
        "by_source_success": by_source,
        "by_source_fail_this_run": dict(STATE["by_source_fail"]),
        "percent": round(100 * success / total, 2) if total else 0,
    }


def maybe_progress(total: int, initial_success: dict, force: bool = False) -> None:
    global LAST_PROGRESS
    now = time.time()
    with LOCK:
        if not force and now - LAST_PROGRESS < 20:
            return
        LAST_PROGRESS = now
        snap = progress_snapshot(total, initial_success)
    write_json_atomic(DATA / "progress.json", snap)
    if force:
        log("PROGRESS " + json.dumps(snap, ensure_ascii=False))


def crawl_one(session: requests.Session, row: dict) -> tuple:
    """Trả (record, failure, attempts)."""
    url = row["URL"]
    delay = SOURCE_DELAY.get(row["Source"], DELAY)
    attempts = 0
    last_status = None
    last_error = ""
    for attempt in range(1, 3):
        attempts = attempt
        try:
            r = session.get(url, timeout=SOURCE_TIMEOUT.get(row["Source"], TIMEOUT))
            with LOCK:
                STATE["requests"] += 1
            last_status = r.status_code
            if r.status_code in (428, 429):
                last_error = f"HTTP {r.status_code} rate limit"
                if attempt == 1:
                    time.sleep(120 if r.status_code == 428 else 60)
                    continue
                break
            if r.status_code in (401, 403):
                last_error = f"HTTP {r.status_code} bị chặn"
                break
            if r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                if attempt == 1:
                    time.sleep(3)
                    continue
                break
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                break
            if "html" not in (r.headers.get("content-type") or ""):
                last_error = f"Content-Type không phải HTML: {r.headers.get('content-type')}"
                break
            try:
                rec = parse_article(row["Source"], r.text, url, row)
            except Exception as exc:
                last_error = f"parse: {exc}"
                break
            rec.update({
                "Crawled_At": now_iso(),
                "HTTP_Status": r.status_code,
                "Crawl_Attempts": attempts,
                "Crawl_Worker": row["_worker"],
            })
            return rec, None, attempts
        except requests.exceptions.ChunkedEncodingError as exc:
            last_error = f"chunked: {exc}"
            if attempt == 1:
                # Thử lại với identity như đã áp dụng cho Tuổi Trẻ ở Bước 1.
                session.headers["Accept-Encoding"] = "identity"
                time.sleep(2)
                continue
            break
        except requests.exceptions.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                time.sleep(3)
                continue
            break
        finally:
            time.sleep(delay)
    failure = {
        "ID": row["ID"], "URL": url, "Source": row["Source"],
        "Label": row["Label"], "Original_Category": row["Original_Category"],
        "HTTP_Status": last_status, "Error": last_error,
        "Attempts": attempts, "Last_Attempt": now_iso(),
        "Crawl_Worker": row["_worker"],
    }
    return None, failure, attempts


def worker(source: str, worker_id: int, rows: list, total: int, initial_success: dict) -> dict:
    session = requests.Session()
    session.headers.update(HEADERS)
    success = failure = 0
    consecutive_blocks = 0
    ckpt_path = CHECKPOINTS / f"{source}_w{worker_id}.jsonl"
    fail_path = FAILURES / f"{source}_w{worker_id}.jsonl"
    for idx, row in enumerate(rows, start=1):
        row["_worker"] = f"{source}-w{worker_id}"
        rec, fail, attempts = crawl_one(session, row)
        if rec is not None:
            append_jsonl(ckpt_path, rec)
            success += 1
            consecutive_blocks = 0
            with LOCK:
                STATE["success_this_run"] += 1
                STATE["by_source"][source] += 1
            if success % 25 == 0:
                log(f"[{source}-w{worker_id}] success={success}/{len(rows)}")
        else:
            append_jsonl(fail_path, fail)
            failure += 1
            with LOCK:
                STATE["failure_this_run"] += 1
                STATE["by_source_fail"][source] += 1
            log(f"[FAIL] {source} {row['ID']} {fail.get('HTTP_Status')} {fail.get('Error')[:160]}")
            err = str(fail.get("Error", ""))
            if (fail.get("HTTP_Status") in (428, 429) or
                    "ConnectTimeout" in err or "timed out" in err.lower()):
                consecutive_blocks += 1
            else:
                consecutive_blocks = 0
            if consecutive_blocks >= 4:
                log(f"[CIRCUIT] {source}-w{worker_id} bị chặn/timeout liên tiếp; "
                    f"nghỉ 300 giây rồi dừng worker để tránh hammer.")
                time.sleep(300)
                break
        maybe_progress(total, initial_success)
    log(f"[DONE] {source}-w{worker_id}: success={success}, fail={failure}")
    return {"source": source, "worker": worker_id, "success": success, "failure": failure}


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFC", title or "").lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def write_outputs(candidates: pd.DataFrame) -> dict:
    success = load_success()
    failures = load_failures()
    candidate_map = candidates.set_index("ID").to_dict(orient="index")

    success_rows = []
    for rid, rec in success.items():
        cand = candidate_map.get(rid)
        if cand is None:
            continue
        row = dict(rec)
        row["Source"] = cand.get("Source", row.get("Source"))
        row["Label"] = cand.get("Label", row.get("Label"))
        row["Original_Category"] = cand.get("Original_Category", row.get("Original_Category"))
        row["URL"] = cand.get("URL", row.get("URL"))
        row["Step3_Duplicate_Group"] = cand.get("Duplicate_Group", "")
        row["Step3_Potential_Duplicate"] = cand.get("Potential_Duplicate", "no")
        for field in ("Published_Date", "Author"):
            v = row.get(field)
            if v is None or str(v).strip().lower() in {"", "nan", "none", "nat"}:
                row[field] = ""
        success_rows.append(row)

    # Chỉ giữ lỗi mới nhất của ID chưa thành công.
    latest_fail = {}
    for f in failures:
        if f.get("ID") not in candidate_map:
            continue
        if f.get("ID") in success:
            continue
        prev = latest_fail.get(f["ID"])
        if prev is None or f.get("Last_Attempt", "") >= prev.get("Last_Attempt", ""):
            latest_fail[f["ID"]] = f

    # Hash nội dung: chỉ gắn cờ, KHÔNG xóa.
    hash_groups = {}
    for row in success_rows:
        hash_groups.setdefault(row["Content_Hash"], []).append(row)
    duplicate_hash_rows = []
    for gid, rows in enumerate([v for v in hash_groups.values() if len(v) > 1], start=1):
        for row in rows:
            row["Content_Duplicate_Group"] = f"HASH{gid:05d}"
            duplicate_hash_rows.append({
                "Content_Duplicate_Group": f"HASH{gid:05d}",
                "ID": row["ID"], "Source": row["Source"], "Label": row["Label"],
                "Title": row["Title"], "URL": row["URL"],
                "Content_Length": row["Content_Length"],
            })
    for row in success_rows:
        row.setdefault("Content_Duplicate_Group", "")

    # Nhóm tiêu đề trùng; ghi rõ nội dung giống/khác. Không xóa.
    title_groups = {}
    for row in success_rows:
        key = normalize_title(row.get("Title", ""))
        if key and len(key) >= 25:
            title_groups.setdefault(key, []).append(row)
    same_title_rows = []
    for gid, rows in enumerate([v for v in title_groups.values() if len(v) > 1], start=1):
        hashes = {r["Content_Hash"] for r in rows}
        relation = "identical_content" if len(hashes) == 1 else "different_content"
        for row in rows:
            same_title_rows.append({
                "Title_Duplicate_Group": f"TITLE{gid:05d}",
                "Content_Relation": relation,
                "ID": row["ID"], "Source": row["Source"], "Label": row["Label"],
                "Title": row["Title"], "URL": row["URL"],
                "Content_Hash": row["Content_Hash"],
            })

    success_rows.sort(key=lambda r: (LABEL_ORDER.index(r["Label"]) if r["Label"] in LABEL_ORDER else 99,
                                      SOURCE_ORDER.index(r["Source"]) if r["Source"] in SOURCE_ORDER else 99,
                                      r["ID"]))
    article_fields = [
        "ID", "Title", "Content", "URL", "Source", "Published_Date",
        "Original_Category", "Label", "Author", "Content_Length",
        "Paragraph_Count", "Content_Hash", "Content_Duplicate_Group",
        "Final_URL", "HTTP_Status", "Crawl_Worker", "Crawl_Attempts", "Crawled_At",
        "Parser", "Content_Selector", "Date_Source", "Title_Source",
        "Author_Source", "Step3_Duplicate_Group", "Step3_Potential_Duplicate",
    ]
    with (DATA / "articles.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=article_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(success_rows)

    fail_fields = ["ID", "URL", "Source", "Label", "Original_Category",
                   "HTTP_Status", "Error", "Attempts", "Last_Attempt", "Crawl_Worker"]
    with (DATA / "failed_urls.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fail_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(latest_fail.values(), key=lambda r: r["ID"]))

    attempted_or_done = set(success) | set(latest_fail)
    not_attempted = candidates[~candidates.ID.isin(attempted_or_done)].copy()
    not_attempted_rows = []
    for r in not_attempted.itertuples():
        reason = ("DanTri bị ConnectTimeout/HTTP 428; dừng worker để tránh hammer, chưa thử lại"
                  if r.Source == "DanTri" else "Chưa thử do chương trình dừng trước khi tới URL")
        not_attempted_rows.append({
            "ID": r.ID, "URL": r.URL, "Source": r.Source, "Label": r.Label,
            "Original_Category": r.Original_Category, "Reason": reason,
        })
    with (DATA / "not_attempted_urls.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        fields = ["ID", "URL", "Source", "Label", "Original_Category", "Reason"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(not_attempted_rows)

    with (DATA / "duplicate_content_review.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        fields = ["Content_Duplicate_Group", "ID", "Source", "Label", "Title", "URL", "Content_Length"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(duplicate_hash_rows)

    with (DATA / "same_title_review.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        fields = ["Title_Duplicate_Group", "Content_Relation", "ID", "Source", "Label", "Title", "URL", "Content_Hash"]
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        writer.writerows(same_title_rows)

    # Thống kê theo nguồn/nhãn.
    frames = []
    for label in LABEL_ORDER:
        for source in SOURCE_ORDER:
            target = int(candidates[(candidates.Label == label) &
                                   (candidates.Source == source)].shape[0])
            ok = sum(1 for r in success_rows if r["Label"] == label and r["Source"] == source)
            failed = sum(1 for r in latest_fail.values() if r["Label"] == label and r["Source"] == source)
            frames.append({"Label": label, "Source": source, "Target": target,
                           "Success": ok, "Failed": failed,
                           "Not_Attempted": max(0, target - ok - failed),
                           "Success_Rate_Pct": round(100 * ok / target, 2) if target else 0})
    by_pair = pd.DataFrame(frames)
    by_pair.to_csv(DATA / "stats_by_label_source.csv", index=False, encoding="utf-8-sig")
    by_label = (by_pair.groupby("Label", as_index=False)[["Target", "Success", "Failed", "Not_Attempted"]]
                .sum())
    by_label["Success_Rate_Pct"] = (100 * by_label.Success / by_label.Target).round(2)
    by_label.to_csv(DATA / "stats_by_label.csv", index=False, encoding="utf-8-sig")
    by_source = (by_pair.groupby("Source", as_index=False)[["Target", "Success", "Failed", "Not_Attempted"]]
                 .sum())
    by_source["Success_Rate_Pct"] = (100 * by_source.Success / by_source.Target).round(2)
    by_source.to_csv(DATA / "stats_by_source.csv", index=False, encoding="utf-8-sig")

    lengths = [r["Content_Length"] for r in success_rows]
    manifest = {
        "finished_at": now_iso(),
        "total_candidates": len(candidates),
        "success": len(success_rows),
        "failed": len(latest_fail),
        "not_attempted": max(0, len(candidates) - len(success_rows) - len(latest_fail)),
        "success_rate_pct": round(100 * len(success_rows) / len(candidates), 2),
        "content_length_min": min(lengths) if lengths else None,
        "content_length_max": max(lengths) if lengths else None,
        "content_length_mean": round(sum(lengths) / len(lengths), 1) if lengths else None,
        "missing_published_date": sum(1 for r in success_rows
                                       if str(r.get("Published_Date", "")).strip().lower()
                                       in {"", "nan", "none", "nat"}),
        "missing_author": sum(1 for r in success_rows
                              if str(r.get("Author", "")).strip().lower()
                              in {"", "nan", "none", "nat"}),
        "exact_content_duplicate_groups": len([v for v in hash_groups.values() if len(v) > 1]),
        "same_title_groups": len([v for v in title_groups.values() if len(v) > 1]),
        "not_attempted_by_source": (not_attempted.groupby("Source").size().to_dict()
                                      if len(not_attempted) else {}),
        "by_source": by_source.to_dict(orient="records"),
    }
    write_json_atomic(DATA / "manifest.json", manifest)
    return manifest


def main():
    global START
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-source", type=int, default=0,
                        help="Giới hạn số bài mỗi nguồn cho pilot")
    parser.add_argument("--sources", default="",
                        help="Danh sách nguồn, cách nhau bằng dấu phẩy")
    parser.add_argument("--report-only", action="store_true",
                        help="Chỉ tổng hợp từ checkpoint, không crawl")
    args = parser.parse_args()
    START = time.time()

    candidates = pd.read_csv(ROOT / "data" / "step3" / "url_candidates.csv",
                             encoding="utf-8-sig")
    candidates = candidates.rename(columns={"Candidate_ID": "ID"})
    candidates["ID"] = candidates["ID"].astype(str)
    if args.sources:
        wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
        candidates = candidates[candidates.Source.isin(wanted)]
    total = len(candidates)

    candidate_ids = set(candidates.ID)
    success_all = load_success()
    success = {rid: r for rid, r in success_all.items() if rid in candidate_ids}
    initial_success = {
        "total": len(success),
        "by_source": {s: sum(1 for r in success.values() if r["Source"] == s)
                      for s in SOURCE_ORDER},
    }
    log(f"Đã có {len(success)} bài thành công trong checkpoint. Còn {max(0,total-len(success))} bài.")
    maybe_progress(total, initial_success, force=True)

    if not args.report_only:
        # Chia việc theo nguồn; bỏ các ID đã thành công.
        jobs = []
        for source in SOURCE_ORDER:
            src_rows = candidates[candidates.Source == source]
            remaining = [r for _, r in src_rows.iterrows() if r["ID"] not in success]
            if args.limit_per_source > 0:
                remaining = remaining[:args.limit_per_source]
            if not remaining:
                continue
            workers = min(SOURCE_WORKERS[source], len(remaining))
            partitions = [remaining[i::workers] for i in range(workers)]
            log(f"{source}: còn {len(remaining)} bài, dùng {workers} worker")
            for i, part in enumerate(partitions):
                if part:
                    jobs.append((source, i, part))
        if jobs:
            with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                futures = [pool.submit(worker, source, i, part, total, initial_success)
                           for source, i, part in jobs]
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as exc:
                        log(f"[THREAD ERROR] {exc!r}")

    maybe_progress(total, initial_success, force=True)
    manifest = write_outputs(candidates)
    print("DONE")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
