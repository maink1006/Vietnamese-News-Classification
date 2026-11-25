"""Bước rà soát: làm sạch lớp trình bày (caption/UI) và đánh giá nội dung.

Không tokenization, không stopwords, không chuẩn hóa NLP.
Giữ Content_Raw để đối chiếu; tạo Content_Clean cho dataset rà soát.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "audit"
DATA.mkdir(parents=True, exist_ok=True)

UI_EXACT = {
    "chia sẻ", "bình luận", "xem thêm", "đọc tiếp", "tin liên quan",
    "bài viết liên quan", "quảng cáo", "theo dõi báo trên",
}
CAPTION_RE = re.compile(r"\b(Ảnh|Nguồn|Video)\s*:", re.I)
RELATED_RE = re.compile(r"^\s*(Xem thêm về|Tin liên quan|Bài viết liên quan)\s*:?", re.I)
URL_RE = re.compile(r"https?://|www\.")


def clean_content(raw: str, title: str = "") -> tuple:
    removed = {"caption": 0, "ui": 0, "related": 0, "url": 0}
    out = []
    for line in str(raw or "").split("\n"):
        text = re.sub(r"\s+", " ", line).strip()
        if not text:
            continue
        low = text.lower().strip(" .:")
        if CAPTION_RE.search(text):
            removed["caption"] += 1
            continue
        if low in UI_EXACT:
            removed["ui"] += 1
            continue
        if RELATED_RE.search(text):
            removed["related"] += 1
            continue
        if URL_RE.search(text) and len(text) < 400:
            removed["url"] += 1
            continue
        if out and out[-1] == text:
            continue
        out.append(text)
    # Một số parser lặp lại tiêu đề ở đầu Content; bỏ dòng tiêu đề.
    if out and title:
        a = re.sub(r"\s+", " ", out[0]).strip().lower()
        b = re.sub(r"\s+", " ", str(title)).strip().lower()
        if a == b or (a.startswith(b) and len(a) - len(b) <= 90):
            out = out[1:]
    clean = "\n".join(out).strip()
    return clean, removed


def main():
    raw = pd.read_csv(ROOT / "data" / "step4" / "articles.csv", encoding="utf-8-sig")
    rows = []
    for r in raw.itertuples():
        clean, removed = clean_content(r.Content, r.Title)
        paragraphs = [x for x in clean.split("\n") if x.strip()]
        title_key = re.sub(r"\s+", " ", str(r.Title)).strip().lower()
        first_key = re.sub(r"\s+", " ", paragraphs[0]).strip().lower() if paragraphs else ""
        last_char = clean[-1:] if clean else ""
        valid = len(clean) >= 500 and len(paragraphs) >= 2
        rows.append({
            "ID": r.ID, "Title": r.Title, "Content_Raw": r.Content,
            "Content_Clean": clean, "Content_Length_Raw": len(str(r.Content)),
            "Content_Length": len(clean), "Paragraph_Count": len(paragraphs),
            "Content_Hash": hashlib.sha256(clean.encode("utf-8")).hexdigest(),
            "URL": r.URL, "Source": r.Source, "Published_Date": r.Published_Date,
            "Original_Category": r.Original_Category, "Label": r.Label,
            "Content_Valid": valid,
            "Removed_Caption_Lines": removed["caption"],
            "Removed_UI_Lines": removed["ui"],
            "Removed_Related_Lines": removed["related"],
            "Removed_URL_Lines": removed["url"],
            "Starts_With_Title": bool(first_key and first_key == title_key),
            "Ends_With_Terminal_Punctuation": last_char in ".!?…”\"')",
        })
    df = pd.DataFrame(rows)
    # Gắn cờ trùng nội dung chính xác; không xóa tự động ở bước này.
    counts = df.Content_Hash.value_counts()
    df["Exact_Content_Duplicate_Count"] = df.Content_Hash.map(counts) - 1
    df["Exact_Content_Duplicate"] = df["Exact_Content_Duplicate_Count"] > 0
    df.to_csv(DATA / "content_cleaned.csv", index=False, encoding="utf-8-sig")
    summary = {
        "input": len(df),
        "valid": int(df.Content_Valid.sum()),
        "invalid": int((~df.Content_Valid).sum()),
        "removed_caption_lines": int(df.Removed_Caption_Lines.sum()),
        "removed_ui_lines": int(df.Removed_UI_Lines.sum()),
        "removed_related_lines": int(df.Removed_Related_Lines.sum()),
        "removed_url_lines": int(df.Removed_URL_Lines.sum()),
        "starts_with_title": int(df.Starts_With_Title.sum()),
        "exact_duplicate_articles": int(df.Exact_Content_Duplicate.sum()),
        "length_min": int(df.Content_Length.min()),
        "length_max": int(df.Content_Length.max()),
        "length_mean": round(float(df.Content_Length.mean()), 1),
    }
    (DATA / "content_cleaning_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nInvalid/short examples:")
    print(df[~df.Content_Valid][["ID", "Source", "Label", "Title", "Content_Length"]].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
