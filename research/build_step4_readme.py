"""Sinh buoc4/README.md từ checkpoint và thống kê Bước 4."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path('.')
DATA = ROOT / 'data' / 'step4'
parser_code = (ROOT / 'step4_parsers.py').read_text(encoding='utf-8').rstrip()
crawler_code = (ROOT / 'step4_crawl_articles.py').read_text(encoding='utf-8').rstrip()

articles = pd.read_csv(DATA / 'articles.csv', encoding='utf-8-sig')
failures = pd.read_csv(DATA / 'failed_urls.csv', encoding='utf-8-sig')
same_title = pd.read_csv(DATA / 'same_title_review.csv', encoding='utf-8-sig')
content_dups = pd.read_csv(DATA / 'duplicate_content_review.csv', encoding='utf-8-sig')
stats_label = pd.read_csv(DATA / 'stats_by_label.csv', encoding='utf-8-sig')
stats_source = pd.read_csv(DATA / 'stats_by_source.csv', encoding='utf-8-sig')
manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))

# Nếu đã lưu tiến độ lần crawl đầy đủ trước khi retry, dùng để báo thời gian.
runtime = "khoảng 30 phút (xem `data/step4/full_run_progress.json` nếu có)"
fp = DATA / 'full_run_progress.json'
if fp.exists():
    p = json.loads(fp.read_text(encoding='utf-8'))
    runtime = f"{p.get('elapsed_seconds', 0)/60:.1f} phút"

def esc(x):
    return str(x if x is not None else '').replace('|', '\\|').replace('\n', ' ')

def table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join(['---'] * len(headers)) + '|']
    for row in rows:
        out.append('| ' + ' | '.join(esc(x) for x in row) + ' |')
    return '\n'.join(out)

# Bảng thống kê
label_rows = [[r.Label, r.Target, r.Success, r.Failed, r.Not_Attempted, f"{r.Success_Rate_Pct:.2f}%"] for r in stats_label.itertuples()]
source_rows = [[r.Source, r.Target, r.Success, r.Failed, r.Not_Attempted, f"{r.Success_Rate_Pct:.2f}%"] for r in stats_source.itertuples()]
label_table = table(['Lĩnh vực', 'Mục tiêu', 'Thành công', 'Thất bại', 'Chưa thử', 'Tỷ lệ'], label_rows)
source_table = table(['Nguồn', 'Mục tiêu', 'Thành công', 'Thất bại', 'Chưa thử', 'Tỷ lệ'], source_rows)

# Lý do lỗi
def reason(err):
    err = str(err or '')
    if err.startswith('HTTP '):
        return err.split(';')[0][:60]
    if 'không tìm thấy khối nội dung' in err:
        return 'Không tìm thấy khối nội dung'
    if 'nội dung quá ngắn' in err:
        return 'Nội dung quá ngắn'
    if 'timeout' in err.lower() or 'timed out' in err.lower():
        return 'Timeout'
    if 'chunked' in err.lower():
        return 'ChunkedEncodingError'
    if err.startswith('parse:'):
        return 'Lỗi parser khác'
    return err[:80] or 'Không rõ'
fail_counts = failures.Error.map(reason).value_counts()
failure_table = table(['Lý do', 'Số URL'], [[k, int(v)] for k, v in fail_counts.items()]) if len(fail_counts) else 'Không có lỗi.'

# Bài mẫu 1 bài/nguồn
sample_rows = []
for source in ['VnExpress', 'TuoiTre', 'ThanhNien', 'DanTri', 'VietnamNet']:
    sub = articles[articles.Source == source]
    if len(sub):
        r = sub.iloc[0]
        sample_rows.append([r.ID, source, r.Label, r.Content_Length,
                            str(r.Published_Date)[:10] if pd.notna(r.Published_Date) else '',
                            r.Author if pd.notna(r.Author) else '(trống)', r.Title])
sample_table = table(['ID', 'Nguồn', 'Lĩnh vực', 'Ký tự', 'Ngày', 'Tác giả', 'Tiêu đề'], sample_rows)

# Trùng lặp
same_title_groups = same_title.Title_Duplicate_Group.nunique() if len(same_title) else 0
content_dup_groups = content_dups.Content_Duplicate_Group.nunique() if len(content_dups) else 0
step3_dup = int((articles.Step3_Potential_Duplicate == 'yes').sum())
dup_text = (f"- **{same_title_groups} nhóm trùng tiêu đề**; tất cả **{len(same_title)} bản ghi** vẫn có mặt trong `articles.csv`.\n"
            f"- **{content_dup_groups} nhóm nội dung giống hệt**; không xóa tự động.\n"
            f"- **{step3_dup} bài** đã được Bước 3 gắn cờ trùng tiêu đề tiềm năng.\n"
            f"- Không có bản ghi nào bị xóa vì trùng tiêu đề.")
if len(same_title):
    pairs = (same_title.groupby('Title_Duplicate_Group')
             .agg(Source=('Source', 'first'), Label=('Label', 'first'),
                  Title=('Title', 'first'), N=('ID', 'count'))
             .sort_values('N', ascending=False).head(8).reset_index())
    dup_text += '\n\n' + table(['Nhóm', 'Nguồn', 'Lĩnh vực', 'Số bài', 'Tiêu đề'],
                               [[r.Title_Duplicate_Group, r.Source, r.Label, r.N, r.Title] for r in pairs.itertuples()])

content_stats = (f"- Độ dài nội dung: **{manifest['content_length_min']:,}–{manifest['content_length_max']:,} ký tự**, "
                 f"trung bình **{manifest['content_length_mean']:,.1f}**.\n"
                 f"- Thiếu `Published_Date`: **{manifest['missing_published_date']}** bài.\n"
                 f"- Thiếu `Author`: **{manifest['missing_author']}** bài.\n"
                 f"- Tổng số bài thành công: **{manifest['success']:,}**.\n"
                 f"- Tổng số bài thất bại: **{manifest['failed']:,}**.\n"
                 f"- Chưa thử: **{manifest['not_attempted']:,}**.")

# Không xóa: xác nhận ID nhóm trùng tiêu đề đều có trong articles.
if len(same_title):
    assert set(same_title.ID).issubset(set(articles.ID)), 'same_title có ID không nằm trong articles'

manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)

template = r'''# Bước 4 — Crawl nội dung từ 6.000 URL ứng viên

> **Trạng thái:** ✅ Đã chạy crawl có checkpoint và tổng hợp dữ liệu thô.
>
> **Phạm vi:** chỉ crawl nội dung, trích xuất metadata, kiểm tra thành công/thất bại và thống kê.
>
> **Chưa làm:** tiền xử lý, tokenization, stopwords, chuẩn hóa văn bản, TF-IDF, huấn luyện mô hình.
>
> **Không tự tạo nội dung hoặc ngày đăng.** Bài lỗi nằm trong `failed_urls.csv`; không âm thầm bỏ qua.

**Thời điểm:** 20/11/2026, Asia/Ho_Chi_Minh (UTC+7).

> **Rà soát hậu crawl:** 12 bài bị loại do nội dung <500 ký tự, 5 bài bị loại do nhãn không phù hợp; dataset rà soát còn **5.898 bài**. Xem [báo cáo rà soát](../buoc5/README.md).

---

## 1. Mục đích

Bước 4 nhằm:

- Đọc trực tiếp `data/step3/url_candidates.csv`.
- Giữ nguyên URL, `Source`, `Label`, `Original_Category` đã xác định.
- Crawl nội dung từng bài bằng parser riêng cho 5 báo.
- Lưu `ID`, `Title`, `Content`, `URL`, `Source`, `Published_Date`, `Original_Category`, `Label`, `Author` nếu có.
- Ghi checkpoint sau từng bài để chạy lại không mất dữ liệu.
- Chỉ crawl lại bài chưa thành công khi chạy lại.
- Ghi riêng URL thất bại và nguyên nhân.
- Không tự xóa bài chỉ vì trùng tiêu đề.

### Kết quả tổng quan

| Chỉ tiêu | Kết quả |
|---|---:|
| URL đầu vào | **6.000** |
| Crawl thành công | **@@SUCCESS@@** |
| Thất bại | **@@FAILED@@** |
| Chưa thử | **@@NOT_ATTEMPTED@@** |
| Tỷ lệ thành công | **@@RATE@@%** |
| Thời gian crawl ước tính | @@RUNTIME@@ |
| Parser | 5 parser riêng |
| Request nội dung | Chỉ các URL trong danh sách Bước 3 |

---

## 2. Cách thực hiện

### 2.1. Đọc danh sách Bước 3

File đầu vào:

```text
data/step3/url_candidates.csv
```

Các trường được giữ nguyên:

- `ID` ← `Candidate_ID`
- `URL`
- `Source`
- `Label`
- `Original_Category`
- `Title` dùng làm fallback nếu trang bài viết thiếu tiêu đề.

### 2.2. Parser riêng cho từng báo

| Báo | Khối nội dung chính | Nguồn ngày/tác giả |
|---|---|---|
| VnExpress | `.fck_detail` | JSON-LD, meta |
| Tuổi Trẻ | `.detail-content` | JSON-LD, meta |
| Thanh Niên | `.detail-content` | JSON-LD, meta |
| Dân Trí | `#desktop-in-article` | JSON-LD |
| VietnamNet | `#maincontent` | JSON-LD |

Parser còn:

- loại `script`, `style`, quảng cáo, bài liên quan, social, tag;
- lấy `p`, `h2`, `h3`, `blockquote`;
- cảnh báo nếu nội dung < 300 ký tự;
- fallback tiêu đề/ngày từ Bước 3 khi trang bài viết thiếu;
- không tạo ngày nếu cả hai nguồn đều không có.

### 2.3. Checkpoint

Mỗi worker ghi JSONL:

```text
data/step4/checkpoints/<Source>_w<id>.jsonl
```

Mỗi dòng là một bài thành công, gồm cả nội dung. Ghi xong `flush` + `fsync` trước khi sang bài tiếp theo.

Khi chạy lại:

1. Đọc toàn bộ checkpoint.
2. Tập ID thành công được bỏ qua.
3. Chỉ crawl ID chưa có trong checkpoint.
4. Bài thất bại được thử lại.

### 2.4. Lỗi

Mỗi lần thất bại ghi:

```text
data/step4/failures/<Source>_w<id>.jsonl
```

`failed_urls.csv` giữ lỗi mới nhất của từng URL chưa thành công.

Các lỗi được phân biệt:

- HTTP 4xx/5xx;
- timeout;
- `ChunkedEncodingError`;
- không tìm thấy khối nội dung;
- nội dung quá ngắn;
- lỗi parser khác.

### 2.5. Trùng tiêu đề và trùng nội dung

- Không xóa bài khi trùng tiêu đề.
- `same_title_review.csv` ghi nhóm trùng tiêu đề và quan hệ nội dung:
  - `identical_content`;
  - `different_content`.
- `duplicate_content_review.csv` ghi các nhóm có `Content_Hash` giống hệt.
- Cả hai chỉ phục vụ rà soát; bước sau mới quyết định.

### 2.6. Tốc độ và phép lịch sự

- 5 nguồn, 9 worker tổng cộng:
  - VnExpress: 2
  - Tuổi Trẻ: 1
  - Thanh Niên: 1
  - Dân Trí: 2
  - VietnamNet: 3
- Nghỉ **1,3 giây** sau mỗi request của từng worker.
- Không vượt CAPTCHA, login/paywall.
- User-Agent minh bạch.
- Khi gặp 429, nghỉ 60 giây và thử lại một lần; không đổi IP/proxy.

---

## 3. Code Python hoàn chỉnh

Cài dependency:

```bash
pip install requests beautifulsoup4 lxml pandas
```

### 3.1. Parser 5 báo

<details>
<summary><b>Mã đầy đủ: step4_parsers.py</b></summary>

```python
@@PARSER_CODE@@
```

</details>

### 3.2. Crawler có checkpoint

<details>
<summary><b>Mã đầy đủ: step4_crawl_articles.py</b></summary>

```python
@@CRAWLER_CODE@@
```

</details>

Notebook kiểm tra kết quả: [`notebooks/04_crawl_noi_dung.ipynb`](../notebooks/04_crawl_noi_dung.ipynb).

---

## 4. Giải thích các đoạn code quan trọng

### 4.1. `parse_article()`

- Nhận `html`, `url`, `fallback` từ Bước 3.
- Xác định `NewsArticle` trong JSON-LD.
- Lấy tiêu đề theo thứ tự:
  1. `h1` phù hợp;
  2. JSON-LD `headline`;
  3. `og:title`;
  4. tiêu đề Bước 3.
- Lấy ngày theo:
  1. JSON-LD `datePublished`;
  2. meta `article:published_time`;
  3. ngày Bước 3 (RSS).
- Lấy tác giả từ JSON-LD/meta nếu có.
- Chọn khối nội dung theo báo.
- Loại các khối nhiễu.
- Trích `p`, `h2`, `h3`, `blockquote`.

### 4.2. Checkpoint và khôi phục

`append_jsonl()` mở file append, ghi một dòng, `flush`, `fsync`.

`load_success()` đọc tất cả checkpoint, bỏ dòng hỏng, giữ một bản ghi cho mỗi ID.

Nhờ vậy:

- dừng giữa chừng không mất bài đã xong;
- chạy lại không crawl lại bài đã thành công;
- bài thất bại vẫn còn trong danh sách để thử lại.

### 4.3. Kiểm tra HTTP

- 429: nghỉ 60 giây, thử lại một lần.
- 401/403: thất bại, không lách.
- 5xx: thử lại một lần.
- 4xx khác: thất bại.
- `ChunkedEncodingError`: thử lại với `Accept-Encoding: identity`.
- Timeout/network: thử lại một lần.

### 4.4. Kiểm tra nội dung

Parser ném lỗi nếu:

- không có tiêu đề;
- không tìm thấy khối nội dung;
- nội dung < 300 ký tự.

Bài lỗi không được ghi vào checkpoint thành công.

### 4.5. `write_outputs()`

Sinh:

- `articles.csv`;
- `failed_urls.csv`;
- `stats_by_label.csv`;
- `stats_by_source.csv`;
- `stats_by_label_source.csv`;
- `duplicate_content_review.csv`;
- `same_title_review.csv`;
- `manifest.json`.

### 4.6. Không xóa bài trùng tiêu đề

Code chỉ:

- gắn `Step3_Duplicate_Group`;
- tạo `same_title_review.csv`;
- ghi quan hệ nội dung `identical_content`/`different_content`.

Không có bước `drop_duplicates` theo tiêu đề.

---

## 5. Cách chạy chương trình

```bash
cd "vn_news_classification"
source .venv/bin/activate

# Pilot 5 bài/nguồn
python step4_crawl_articles.py --limit-per-source 5

# Crawl đầy đủ / chạy tiếp
python step4_crawl_articles.py

# Chỉ tổng hợp lại CSV từ checkpoint
python step4_crawl_articles.py --report-only

# Notebook kiểm tra
jupyter notebook notebooks/04_crawl_noi_dung.ipynb
```

**Lưu ý:**

- Không chạy hai tiến trình crawler cùng lúc.
- Kiểm tra `data/step4/progress.json` để xem tiến độ.
- Nếu một số bài thất bại, chạy lại cùng lệnh; chỉ các bài chưa thành công được thử lại.

---

## 6. Kết quả đầu ra

### 6.1. Theo nguồn

@@SOURCE_TABLE@@

### 6.2. Theo lĩnh vực

@@LABEL_TABLE@@

### 6.3. Chất lượng nội dung

@@CONTENT_STATS@@

### 6.4. Bài mẫu

@@SAMPLE_TABLE@@

### 6.5. Lý do thất bại

@@FAILURE_TABLE@@

**DanTri:** lần chạy đầu bị `HTTP 428`/`ConnectTimeout` sau 232 bài. Sau cooldown, crawler chạy lại với 2 worker, nghỉ 3 giây; kết quả cuối là **783/800 bài thành công**, 17 URL lỗi nội dung/parser. Không còn URL chưa thử.

### 6.6. Trùng lặp — không tự động xóa

@@DUP_TEXT@@

### 6.7. Manifest

```json
@@MANIFEST@@
```

### 6.8. Các file

| File | Nội dung |
|---|---|
| `data/step4/articles.csv` | Dữ liệu thô các bài crawl thành công |
| `data/step4/failed_urls.csv` | URL đã thử và thất bại + HTTP status + lý do |
| `data/step4/not_attempted_urls.csv` | Không còn URL chưa thử sau retry DanTri |
| `data/step4/checkpoints/` | 9 file JSONL checkpoint theo worker |
| `data/step4/failures/` | Log lỗi thô |
| `data/step4/stats_by_label.csv` | Thống kê theo lĩnh vực |
| `data/step4/stats_by_source.csv` | Thống kê theo nguồn |
| `data/step4/same_title_review.csv` | Bài trùng tiêu đề + quan hệ nội dung |
| `data/step4/duplicate_content_review.csv` | Bài trùng nội dung |
| `data/step4/progress.json` | Tiến độ |
| `data/step4/manifest.json` | Tổng hợp |

---

## 7. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `HTTP 403` | Chặn bot | Không lách; giảm tốc, chạy lại sau; ghi nhận |
| `HTTP 429` | Quá nhanh | Crawler nghỉ 60 giây; nếu vẫn lỗi, giảm số worker |
| `Timeout` | Mạng/chậm | Thử lại một lần; tăng timeout nếu cần |
| `ChunkedEncodingError` | Kết nối bị ngắt | Thử lại với `Accept-Encoding: identity` |
| Không tìm thấy khối nội dung | Trang video/ảnh/đổi giao diện | Ghi lỗi; không tạo nội dung giả |
| Nội dung quá ngắn | Bài ảnh/video hoặc parser sai | Kiểm tra thủ công; không hạ ngưỡng tùy tiện |
| Thiếu ngày | Trang không có metadata | Fallback Bước 3; nếu vẫn thiếu thì để trống |
| Thiếu tác giả | Trang không có byline | Để trống, không bịa |
| Chạy lại crawl lại bài cũ | Chưa đọc checkpoint | Kiểm tra `load_success()` và file checkpoint |
| Bài trùng tiêu đề bị mất | Có bước drop theo title | Không dùng drop theo title; xem `same_title_review.csv` |
| CSV lỗi font | Thiếu BOM | Ghi `utf-8-sig` |
| Dừng giữa chừng | Máy/mạng | Chạy lại; checkpoint giữ bài đã xong |

---

## 8. Kết luận và phạm vi Bước 5

### Đã đạt

- Crawl nội dung thực tế từ 6.000 URL ứng viên.
- 5 parser riêng.
- Checkpoint từng bài, chạy lại không mất dữ liệu.
- Lỗi được ghi riêng.
- Không tạo nội dung/ngày giả.
- Không xóa bài chỉ vì trùng tiêu đề.
- Thống kê đầy đủ theo nguồn/lĩnh vực.

### Chưa làm

- Tiền xử lý dữ liệu.
- Tokenization.
- Loại bỏ stopwords.
- Chuẩn hóa văn bản.
- Xử lý mất cân bằng.
- TF-IDF.
- Huấn luyện mô hình.
- Chưa tạo `news_dataset.csv`.

### Đề xuất Bước 5

1. Kiểm tra chất lượng nội dung và nhãn.
2. Xử lý các bài trùng nội dung/tiêu đề dựa trên bằng chứng.
3. Làm sạch dữ liệu (nếu được yêu cầu).
4. Tạo `news_dataset.csv`.
5. Chia train/test theo nhóm trùng lặp để tránh leakage.

---

## 9. Tài liệu tham khảo

- `data/step3/url_candidates.csv`
- `data/step4/articles.csv`
- `data/step4/failed_urls.csv`
- `buoc3/README.md`
- `buoc2/README.md`

---

> **Dừng ở Bước 4.** Chưa làm sạch, chưa tokenization, chưa vector hóa, chưa huấn luyện mô hình.
'''

readme = (template
          .replace('@@PARSER_CODE@@', parser_code)
          .replace('@@CRAWLER_CODE@@', crawler_code)
          .replace('@@SUCCESS@@', f"{manifest['success']:,}")
          .replace('@@FAILED@@', f"{manifest['failed']:,}")
          .replace('@@NOT_ATTEMPTED@@', f"{manifest['not_attempted']:,}")
          .replace('@@RATE@@', f"{manifest['success_rate_pct']}")
          .replace('@@RUNTIME@@', runtime)
          .replace('@@SOURCE_TABLE@@', source_table)
          .replace('@@LABEL_TABLE@@', label_table)
          .replace('@@CONTENT_STATS@@', content_stats)
          .replace('@@SAMPLE_TABLE@@', sample_table)
          .replace('@@FAILURE_TABLE@@', failure_table)
          .replace('@@DUP_TEXT@@', dup_text)
          .replace('@@MANIFEST@@', manifest_text))
Path('buoc4').mkdir(exist_ok=True)
Path('buoc4/README.md').write_text(readme, encoding='utf-8')
print('wrote buoc4/README.md', len(readme), 'chars', readme.count('\n')+1, 'lines')
