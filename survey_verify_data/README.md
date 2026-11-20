# Đồ án: Phân loại tin tức tiếng Việt bằng Machine Learning và Deep Learning

## Bước 1 — Khảo sát và xác minh nguồn dữ liệu

> **Trạng thái:** Bước 1 hoàn thành. Bước 2 hoàn thành. Bước 3 hoàn thành. Bước 4 hoàn thành — xem [Bước 2](buoc2/README.md), [Bước 3](buoc3/README.md), [Bước 4](buoc4/README.md).
>
> **VnExpress vẫn được giữ:** lỗi `categories-sitemap.xml` chỉ loại bỏ một endpoint, không loại bỏ nguồn. Bước 2 đã xác minh lại VnExpress bằng sitemap, RSS, 40 trang chuyên mục và 8 bài viết mẫu. Bước 3 đã dùng VnExpress cho 1.200 URL ứng viên.
>
> **Bước 3:** đã tạo **6.000 URL ứng viên**, đúng **750 URL/lĩnh vực**, không crawl nội dung. Dữ liệu tại `data/step3/url_candidates.csv`.
>
> **Bước 4:** đã crawl được **5.364 bài**, **185 URL thất bại** và **451 URL DanTri chưa thử** do host chặn/timeout. Không tạo dữ liệu giả. Dữ liệu thô tại `data/step4/articles.csv`.
>
> **Thời điểm khảo sát:** 20/11/2026, múi giờ Asia/Ho_Chi_Minh (UTC+7).
>
> **Phạm vi tài liệu này:** Bước 1 — khảo sát nguồn, RSS, sitemap, trang danh mục và cấu trúc HTML mẫu.
> **Chưa crawl nội dung hàng loạt, chưa làm sạch, chưa tạo `news_dataset.csv`.**

---

## 1. Kết luận nhanh

1. **5/5 báo** truy cập được, `robots.txt` đều trả HTTP 200 và cho phép các trang cần dùng.
2. **40/40 feed RSS** và **40/40 trang danh mục** cho 8 lĩnh vực trả HTTP 200.
3. **5/5 sitemap index** hợp lệ, nhưng phương án chính đề xuất là **RSS + trang danh mục** vì ánh xạ nhãn trực tiếp và ít request hơn.
4. Đề xuất lấy **750 URL ứng viên/lĩnh vực**, tổng **6.000 URL**. Sau khi loại bài lỗi/trùng, kỳ vọng còn khoảng **600–680 bài hợp lệ/lĩnh vực**. Đây là mục tiêu nằm trong khoảng khuyến nghị 600–800.
5. **4 nguồn đủ dùng RSS**. Riêng **VietnamNet Công nghệ** phải dùng trang danh mục vì feed đã ngừng cập nhật từ tháng 5/2025.
6. **Không dùng phân trang Dân Trí** (`/trang-1*.htm` … `/trang-9*.htm`) vì `robots.txt` chặn rõ ràng. Dân Trí chỉ lấy 100 URL từ RSS.
7. **Không dùng Scrapy cho VnExpress** vì `robots.txt` chặn user-agent `Scrapy`. Hệ thống dùng `requests` với User-Agent minh bạch.
8. Chưa thấy CAPTCHA, đăng nhập hay paywall ở 5 bài mẫu. Tuy nhiên **điều khoản bản quyền vẫn là rủi ro cần lưu ý** (mục 6.7).

---

## 2. Mục đích của Bước 1

Bước 1 trả lời các câu hỏi sau **bằng kiểm tra thực tế**, không dựa vào trí nhớ hay URL tự đoán:

- Báo nào truy cập được? `robots.txt` có cho phép không?
- Mỗi báo có RSS, sitemap hoặc trang danh mục nào cho 8 lĩnh vực?
- Trang danh mục nào thực sự tồn tại và trả HTTP 200?
- Mỗi nguồn cung cấp được bao nhiêu bài? Có đủ 500–800 bài/lĩnh vực không?
- Cấu trúc HTML bài viết có lấy được tiêu đề, nội dung, ngày đăng không?
- Có cơ chế bảo vệ (CAPTCHA, login, paywall) hoặc điều khoản cấm crawl không?
- Phương án thu thập nào đơn giản nhất nhưng vẫn đủ dữ liệu và có thể bảo vệ trước hội đồng?

### Tiêu chí của một nguồn được chọn

- Trang danh mục hoặc feed **trả HTTP 200**, nội dung đúng lĩnh vực.
- Bài viết truy cập công khai, không cần đăng nhập, không vượt CAPTCHA/paywall.
- `robots.txt` không chặn đường dẫn dự định thu thập.
- Có thể ánh xạ danh mục gốc sang một trong 8 nhãn của đề tài.
- Có đủ số bài để đạt mục tiêu sau khi loại bài lỗi/trùng.
- Cách thu thập đủ đơn giản để sinh viên năm 3 tự triển khai, bảo trì và giải thích.

---

## 3. Cách thực hiện

### 3.1. Nguyên tắc

- **Không tự tạo URL.** Mọi URL trong báo cáo đều đã được gửi request thực tế và kiểm tra mã HTTP.
- **Không vượt bảo vệ:** không đăng nhập, không giải CAPTCHA, không tìm cách lách paywall.
- **Không dùng concurrency:** crawler chạy tuần tự, nghỉ **1,5–2 giây/request**.
- **User-Agent minh bạch:**
  `student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)`.
- **Không dùng UA giả trình duyệt/Googlebot** để tránh né kiểm soát của website.
- **Không thử lại các mã 403/429** bằng cách đổi IP/proxy. Nếu gặp, dừng và giảm tốc độ.

### 3.2. Quy trình khảo sát

1. Tải `robots.txt` của 5 báo, ghi nhận quy tắc `Allow`, `Disallow`, `Crawl-delay`, `Sitemap`.
2. Tìm các trang RSS chính thức:
   - VnExpress: `/rss`
   - Tuổi Trẻ: `/rss.htm`
   - Thanh Niên: `/rss.html`
   - Dân Trí: `/rss/` chỉ trả một dòng chữ, không phải trang index
   - VietnamNet: `/rss/` trả 404
3. Từ trang RSS chính thức, lấy các feed con. Kiểm tra từng feed bằng `GET`, parse XML, đếm `<item>`.
4. Kiểm tra 8 trang danh mục/báo bằng `GET`, xác nhận HTTP 200 và tiêu đề trang.
5. Kiểm tra sitemap index được khai báo trong robots.
6. Tải thử **1 bài viết/nguồn**, kiểm tra:
   - HTTP 200, không bị chặn;
   - có `<h1>`, JSON-LD `NewsArticle`, thẻ `article:published_time`;
   - có khối nội dung chính với độ dài hợp lý.
7. Đọc trang điều khoản/chính sách nếu tìm thấy; ghi nhận giới hạn bản quyền.
8. Tổng hợp thành bảng audit và đề xuất quota.

### 3.3. Các URL đã kiểm tra nhưng **không dùng**

| URL | Kết quả | Lý do |
|---|---|---|
| `https://vietnamnet.vn/rss/` | 404 | Không có trang index RSS |
| `https://vietnamnet.vn/rss/thoi-su-phap-luat.rss` | 404 | Slug sai; feed đúng là `/rss/phap-luat.rss` (200) |
| `https://tuoitre.vn/sitemap.xml` | 404 | Sitemap chính thức nằm ở `/sitemaps/index.rss` |
| `https://vnexpress.net/categories-sitemap.xml` | 200 nhưng `text/html` | Trả về trang chủ, không phải XML; không dùng |
| `https://dantri.com.vn/rss/` | 200 nhưng chỉ là dòng chữ | Không phải index feed; vẫn dùng được từng feed con |

> Bài học: một URL trả 200 **chưa chắc** là dữ liệu đúng. Phải kiểm tra thêm `Content-Type` và nội dung thực tế.



## 4. Giải thích các đoạn code quan trọng

### 4.1. `SITES`

Mỗi báo có cấu hình riêng, **không giả định cấu trúc giống nhau**:

- `feed_tpl`, `cat_tpl`: mẫu URL feed và danh mục.
- `category_slugs`: slug riêng cho từng lĩnh vực.
- `article_pattern`: regex nhận diện URL bài viết của từng báo.
- `quota`: số URL ứng viên dự kiến lấy.

Ví dụ, cùng là “Pháp luật” nhưng:

- Thanh Niên dùng `/thoi-su/phap-luat.htm`
- VietnamNet dùng `/thoi-su/phap-luat`
- VnExpress dùng `/phap-luat`

Không thể dùng một mẫu URL chung cho cả 5 báo.

### 4.2. `fetch()`

- `timeout=30` tránh treo vô hạn.
- Có **một lần thử lại khi lỗi kết nối**.
- Riêng Tuổi Trẻ từng trả lỗi `ChunkedEncodingError`; lần thử lại dùng `Accept-Encoding: identity` và thành công.
- **Không thử lại 403/429** để tránh thành crawler lách kiểm soát.

### 4.3. `parse_date()`

RSS không dùng cùng một định dạng ngày:

- VnExpress, Thanh Niên, Dân Trí, VietnamNet: RFC 822, ví dụ
  `Fri, 20 Nov 2026 11:11:51 +0700`.
- Tuổi Trẻ: `11/20/2026 12:00:00 PM` (M/D/YYYY, giờ 12).

Hàm thử định dạng Tuổi Trẻ trước, sau đó mới dùng `parsedate_to_datetime`. Naive datetime của Tuổi Trẻ được gắn timezone `+07:00` để CSV nhất quán.

### 4.4. `check_feed()`

- Parse XML bằng `xml.etree.ElementTree` (không cần thêm `feedparser`).
- Lấy `channel`, đếm `<item>`, đếm URL duy nhất.
- Lấy `date_min`, `date_max` để biết feed có còn cập nhật không.
- Nếu server trả HTML thay vì XML, ghi lỗi thay vì làm sập toàn bộ chương trình.

### 4.5. `check_category()`

- Chỉ đếm link **ứng viên** khớp regex bài viết.
- Không coi số link trên trang danh mục là số bài hợp lệ.
- Không tải nội dung bài trong bước này.

### 4.6. `check_sitemap()`

- Chỉ kiểm tra sitemap index có parse được XML không.
- Không duyệt toàn bộ sitemap con vì không cần cho phương án chính.

### 4.7. `main()`

- Chạy tuần tự 5 robots + 5 sitemap + 40 feed + 40 danh mục.
- Nghỉ 1,5 giây sau mỗi request.
- Ghi JSON bằng chứng và CSV tổng hợp.
- Không ghi đè dữ liệu bài viết vì bước này chưa crawl bài.

### 4.8. Vì sao không dùng Scrapy?

`robots.txt` của VnExpress có:

```text
User-agent: Scrapy
Disallow: /
```

Nếu dùng Scrapy mặc định, hành vi là vi phạm robots. Với quy mô 6.000 URL và nhu cầu lưu tiến trình đơn giản, `requests` + CSV/JSON là đủ, dễ giải thích hơn và không cần cài đặt framework.

---

## 5. Cách chạy chương trình

```bash
cd "vn_news_classification"

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install requests beautifulsoup4 lxml pandas

# Kiểm tra lại toàn bộ nguồn (khoảng 3–5 phút do nghỉ 1,5 giây/request)
python step1_khao_sat.py
```

Kết quả:

- `outputs/step1_source_audit.csv`
- `research/raw/step1/feeds.json`
- `research/raw/step1/categories.json`
- `research/raw/step1/sitemaps.json`
- `research/raw/step1/robots.json`

Mở notebook:

```bash
jupyter notebook notebooks/01_khao_sat_nguon.ipynb
```

Trong notebook, `RUN_LIVE = False` sẽ đọc kết quả đã lưu. Đổi thành `True` nếu muốn chạy lại kiểm tra trực tiếp.

**Lưu ý:** Không chạy script nhiều lần liên tiếp. Không chạy song song nhiều notebook để tránh tăng tải lên báo.

---

## 6. Kết quả đầu ra dự kiến

### 6.1. Môi trường và quy mô kiểm tra

| Hạng mục | Kết quả |
|---|---|
| Python | 3.9.6 |
| Thư viện | requests 2.32.5, beautifulsoup4 4.15.0, lxml 6.1.3, pandas 2.3.3 |
| Số báo | 5 |
| Số lĩnh vực | 8 |
| Feed kiểm tra | 40 (8 × 5) |
| Trang danh mục kiểm tra | 40 (8 × 5) |
| Sitemap index kiểm tra | 5 |
| Bài viết mẫu kiểm tra | 5 |
| Request trong script | 90 |
| Kết quả chạy end-to-end | **90/90 request HTTP 200**, script exit code 0 |

### 6.2. Kết quả robots.txt

| Báo | HTTP | Quy tắc đáng chú ý | Sitemap khai báo |
|---|---:|---|---|
| VnExpress | 200 | `Allow: /`; chặn `Scrapy`, nhiều bot AI, một số crawler | `/sitemap.xml`, `/google-news-sitemap.xml` |
| Tuổi Trẻ | 200 | `Allow: /`; chặn tìm kiếm, `/print/`, một số file JS | `/sitemaps/index.rss`, `/sitemaps/latest-news.rss` |
| Thanh Niên | 200 | `Allow: /`; chặn `/tim-kiem.htm`, `/news-*.htm` | `/sitemap.xml`, `/google-news-sitemap.xml` |
| Dân Trí | 200 | `Allow: /`; **chặn `/trang-1*.htm` … `/trang-9*.htm`**, print, tag, tìm kiếm | `/sitemap.xml`, `/google-news-sitemap.xml` |
| VietnamNet | 200 | `Allow: /`; chặn tìm kiếm và `/sportapi` | `/sitemap.xml`, `/sitemap-categories.xml` |

**Hệ quả trực tiếp:**

- Không dùng Scrapy cho VnExpress.
- Không dùng phân trang Dân Trí; chỉ lấy RSS.
- Tất cả request đều nghỉ 1,5 giây, cao hơn `Crawl-delay: 1` mà Dân Trí áp cho một số bot.

### 6.3. Kết quả RSS: 40/40 feed hợp lệ

Số dưới đây là **số `<item>` thô**, không phải số bài hợp lệ sau kiểm tra nội dung.

| Lĩnh vực | VnExpress | Tuổi Trẻ | Thanh Niên | Dân Trí | VietnamNet |
|---|---:|---:|---:|---:|---:|
| Kinh tế | 60 | 50 | 50 | 100 | 1.000 |
| Thế giới | 60 | 50 | 50 | 100 | 1.000 |
| Thể thao | 60 | 50 | 50 | 100 | 1.000 |
| Pháp luật | 60 | 50 | 50 | 100 | 1.000 |
| Giáo dục | 60 | 50 | 50 | 100 | 1.000 |
| Sức khỏe | 60 | 50 | 50 | 100 | 1.000 |
| Công nghệ | 60 | 50 | 50 | 100 | **36** ⚠️ |
| Du lịch | 60 | 50 | 50 | 100 | 1.000 |

**Khoảng ngày ghi nhận trong feed:**

| Báo | Khoảng ngày | Ghi chú |
|---|---|---|
| VnExpress | 12/11–20/11/2026 | Feed ngắn, khoảng 3–8 ngày gần nhất |
| Tuổi Trẻ | 15/11–20/11/2026 | Riêng Công nghệ: 30/09–17/11/2026 |
| Thanh Niên | 03/11–20/11/2026 | Du lịch có bài cũ nhất 03/11 |
| Dân Trí | 03/11–20/11/2026 | Công nghệ và Du lịch có bài cũ nhất 03/11 |
| VietnamNet | 28/01–20/11/2026 | 7 feed có 1.000 mục; 6 feed trải 1,5–3,5 tháng, Du lịch trải từ 28/01 |
| VietnamNet Công nghệ | 03/02–06/05/2025 | ⚠️ **Feed đã ngừng cập nhật**; không dùng làm nguồn chính |

**Nhận xét quan trọng:**

- VnExpress chỉ có 60 item/feed, không đủ 500 nếu chỉ dùng RSS → cần trang danh mục.
- Tuổi Trẻ và Thanh Niên chỉ 50 item/feed → chỉ lấy 50/báo/lĩnh vực, phần còn lại bù từ nguồn khác.
- Dân Trí 100 item/feed → đủ 100/lĩnh vực.
- VietnamNet 1.000 item/feed → nguồn bù chính, nhưng không nên lạm dụng vì sẽ làm mất cân bằng nguồn.
- Feed VietnamNet Công nghệ có 36 mục và dừng từ 06/05/2025 → **bắt buộc dùng trang danh mục** cho lĩnh vực này.

### 6.4. Kết quả 40/40 trang danh mục

Tất cả trang dưới đây trả **HTTP 200** và đúng tiêu đề lĩnh vực tại thời điểm khảo sát.

#### VnExpress — `https://vnexpress.net`

| Nhãn | Danh mục gốc | URL danh mục | RSS |
|---|---|---|---|
| Kinh tế | Kinh doanh | https://vnexpress.net/kinh-doanh | https://vnexpress.net/rss/kinh-doanh.rss |
| Thế giới | Thế giới | https://vnexpress.net/the-gioi | https://vnexpress.net/rss/the-gioi.rss |
| Thể thao | Thể thao | https://vnexpress.net/the-thao | https://vnexpress.net/rss/the-thao.rss |
| Pháp luật | Pháp luật | https://vnexpress.net/phap-luat | https://vnexpress.net/rss/phap-luat.rss |
| Giáo dục | Giáo dục | https://vnexpress.net/giao-duc | https://vnexpress.net/rss/giao-duc.rss |
| Sức khỏe | Sức khỏe | https://vnexpress.net/suc-khoe | https://vnexpress.net/rss/suc-khoe.rss |
| Công nghệ | Khoa học công nghệ | https://vnexpress.net/khoa-hoc-cong-nghe | https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss |
| Du lịch | Du lịch | https://vnexpress.net/du-lich | https://vnexpress.net/rss/du-lich.rss |

**Lưu ý Công nghệ:** trang 1 có H1 “Khoa học công nghệ”, gồm cả tin khoa học thuần túy. Từ trang 2, URL chuyển thành:

- https://vnexpress.net/cong-nghe-p2
- https://vnexpress.net/cong-nghe-p3
- https://vnexpress.net/cong-nghe-p4
- https://vnexpress.net/cong-nghe-p5

Các trang này đã kiểm tra HTTP 200. Bước 3 phải thống nhất URL chuẩn và Bước 5 phải kiểm tra thủ công các bài khoa học không phù hợp nhãn Công nghệ.

#### Tuổi Trẻ — `https://tuoitre.vn`

| Nhãn | Danh mục gốc | URL danh mục | RSS |
|---|---|---|---|
| Kinh tế | Kinh doanh | https://tuoitre.vn/kinh-doanh.htm | https://tuoitre.vn/kinh-doanh.rss |
| Thế giới | Thế giới | https://tuoitre.vn/the-gioi.htm | https://tuoitre.vn/the-gioi.rss |
| Thể thao | Thể thao | https://tuoitre.vn/the-thao.htm | https://tuoitre.vn/the-thao.rss |
| Pháp luật | Pháp luật | https://tuoitre.vn/phap-luat.htm | https://tuoitre.vn/phap-luat.rss |
| Giáo dục | Giáo dục | https://tuoitre.vn/giao-duc.htm | https://tuoitre.vn/giao-duc.rss |
| Sức khỏe | Sức khỏe | https://tuoitre.vn/suc-khoe.htm | https://tuoitre.vn/suc-khoe.rss |
| Công nghệ | Nhịp sống số | https://tuoitre.vn/nhip-song-so.htm | https://tuoitre.vn/nhip-song-so.rss |
| Du lịch | Du lịch | https://tuoitre.vn/du-lich.htm | https://tuoitre.vn/du-lich.rss |

Tuổi Trẻ dùng tên **Nhịp sống số** cho công nghệ/đời sống số, không phải `cong-nghe`.

#### Thanh Niên — `https://thanhnien.vn`

| Nhãn | Danh mục gốc | URL danh mục | RSS |
|---|---|---|---|
| Kinh tế | Kinh tế | https://thanhnien.vn/kinh-te.htm | https://thanhnien.vn/rss/kinh-te.rss |
| Thế giới | Thế giới | https://thanhnien.vn/the-gioi.htm | https://thanhnien.vn/rss/the-gioi.rss |
| Thể thao | Thể thao | https://thanhnien.vn/the-thao.htm | https://thanhnien.vn/rss/the-thao.rss |
| Pháp luật | Thời sự / Pháp luật | https://thanhnien.vn/thoi-su/phap-luat.htm | https://thanhnien.vn/rss/thoi-su/phap-luat.rss |
| Giáo dục | Giáo dục | https://thanhnien.vn/giao-duc.htm | https://thanhnien.vn/rss/giao-duc.rss |
| Sức khỏe | Sức khỏe | https://thanhnien.vn/suc-khoe.htm | https://thanhnien.vn/rss/suc-khoe.rss |
| Công nghệ | Công nghệ | https://thanhnien.vn/cong-nghe.htm | https://thanhnien.vn/rss/cong-nghe.rss |
| Du lịch | Du lịch | https://thanhnien.vn/du-lich.htm | https://thanhnien.vn/rss/du-lich.rss |

#### Dân Trí — `https://dantri.com.vn`

| Nhãn | Danh mục gốc | URL danh mục | RSS |
|---|---|---|---|
| Kinh tế | Kinh doanh | https://dantri.com.vn/kinh-doanh.htm | https://dantri.com.vn/rss/kinh-doanh.rss |
| Thế giới | Thế giới | https://dantri.com.vn/the-gioi.htm | https://dantri.com.vn/rss/the-gioi.rss |
| Thể thao | Thể thao | https://dantri.com.vn/the-thao.htm | https://dantri.com.vn/rss/the-thao.rss |
| Pháp luật | Pháp luật | https://dantri.com.vn/phap-luat.htm | https://dantri.com.vn/rss/phap-luat.rss |
| Giáo dục | Giáo dục | https://dantri.com.vn/giao-duc.htm | https://dantri.com.vn/rss/giao-duc.rss |
| Sức khỏe | Sức khỏe | https://dantri.com.vn/suc-khoe.htm | https://dantri.com.vn/rss/suc-khoe.rss |
| Công nghệ | Công nghệ | https://dantri.com.vn/cong-nghe.htm | https://dantri.com.vn/rss/cong-nghe.rss |
| Du lịch | Du lịch | https://dantri.com.vn/du-lich.htm | https://dantri.com.vn/rss/du-lich.rss |

**Không dùng** `https://dantri.com.vn/kinh-doanh/trang-2.htm` hoặc các trang `/trang-1*.htm` … `/trang-9*.htm` vì robots chặn. Kế hoạch chỉ lấy 100 URL RSS/ngành.

#### VietnamNet — `https://vietnamnet.vn`

| Nhãn | Danh mục gốc | URL danh mục | RSS |
|---|---|---|---|
| Kinh tế | Kinh doanh | https://vietnamnet.vn/kinh-doanh | https://vietnamnet.vn/rss/kinh-doanh.rss |
| Thế giới | Thế giới | https://vietnamnet.vn/the-gioi | https://vietnamnet.vn/rss/the-gioi.rss |
| Thể thao | Thể thao | https://vietnamnet.vn/the-thao | https://vietnamnet.vn/rss/the-thao.rss |
| Pháp luật | Thời sự / Pháp luật | https://vietnamnet.vn/thoi-su/phap-luat | https://vietnamnet.vn/rss/phap-luat.rss |
| Giáo dục | Giáo dục | https://vietnamnet.vn/giao-duc | https://vietnamnet.vn/rss/giao-duc.rss |
| Sức khỏe | Sức khỏe | https://vietnamnet.vn/suc-khoe | https://vietnamnet.vn/rss/suc-khoe.rss |
| Công nghệ | Công nghệ | https://vietnamnet.vn/cong-nghe | https://vietnamnet.vn/rss/cong-nghe.rss *(cũ)* |
| Du lịch | Du lịch | https://vietnamnet.vn/du-lich | https://vietnamnet.vn/rss/du-lich.rss |

- Feed Pháp luật đúng: `https://vietnamnet.vn/rss/phap-luat.rss` (1.000 mục).
- Feed thay thế cũng trả 200: `https://vietnamnet.vn/rss/thoi-su/phap-luat.rss`.
- Với Công nghệ, **không dùng feed**; dùng 16 trang:
  `https://vietnamnet.vn/cong-nghe`, `.../cong-nghe-page1`, ..., `.../cong-nghe-page15`.
  Trang đầu 31 link, các trang sau khoảng 25 link. Đã kiểm tra mẫu `page0`, `page1`, `page2`, `page10`, `page15`, `page20`; tất cả trả 200 và có bài. Bước 3 sẽ kiểm tra liên tục các trang trong dải cần lấy.

**Phân trang đã xác minh thêm:**

- VnExpress Kinh doanh: trang 1 khoảng 50 link; `-p2`, `-p3`, `-p4`, `-p5` trả 200, khoảng 30 link/trang, không trùng giữa p1/p2/p3.
- VnExpress Công nghệ: 48 link trang 1, 27–30 link/trang ở p2–p5.
- Cơ chế `-pN` mới được xác minh đầy đủ trên Kinh doanh và Công nghệ; 6 chuyên mục VnExpress còn lại sẽ được kiểm tra đủ p1–p5 ở Bước 2–3.
- VietnamNet Công nghệ: 31 link trang 1, khoảng 25 link/trang ở các trang mẫu p1, p2, p10, p15, p20.
- Tuổi Trẻ và Thanh Niên: chưa xác minh cơ chế phân trang danh mục; kế hoạch không dùng phân trang cho hai báo này.

### 6.5. Kết quả sitemap

| Báo | Sitemap index | HTTP | Số mục con | Quyết định |
|---|---|---:|---:|---|
| VnExpress | https://vnexpress.net/sitemap.xml | 200 | 9.468 | Không dùng làm nguồn chính |
| Tuổi Trẻ | https://tuoitre.vn/sitemaps/index.rss | 200 | 1.144 | Không dùng làm nguồn chính |
| Thanh Niên | https://thanhnien.vn/sitemap.xml | 200 | 1.117 | Không dùng làm nguồn chính |
| Dân Trí | https://dantri.com.vn/sitemap.xml | 200 | 487 | Không dùng làm nguồn chính |
| VietnamNet | https://vietnamnet.vn/sitemap.xml | 200 | 1.523 | Không dùng làm nguồn chính |

**Vì sao không chọn sitemap?**

- Sitemap trả về danh sách URL nhưng **không kèm nhãn lĩnh vực** thống nhất.
- Muốn biết bài thuộc lĩnh vực nào, phải tải thêm bài hoặc suy luận từ path — tốn request và dễ sai.
- Với 6.000 URL, RSS + trang danh mục cho ánh xạ nhãn trực tiếp, dễ giải thích và dễ bảo trì hơn.
- Sitemap vẫn là **phương án dự phòng** nếu một ngày RSS bị cắt hoặc trang danh mục đổi cấu trúc.

**Cảnh báo:** `https://vnexpress.net/categories-sitemap.xml` trả HTTP 200 nhưng thực chất là trang chủ (`text/html`), không phải XML. Không dùng URL này. **Đây là lỗi của một endpoint sitemap, không phải lý do loại bỏ VnExpress.** Bước 2 đã khảo sát lại: 40/40 trang chuyên mục p1–p5 trả 200, mỗi lĩnh vực có 161–184 URL, và 8/8 bài mẫu crawl được nội dung. Chi tiết: [buoc2/README.md](buoc2/README.md).

### 6.6. Kiểm tra cấu trúc bài viết mẫu

Mỗi báo được tải thử 1 bài để chắc chắn không bị chặn và có nội dung thật.

| Báo | HTTP | Tiêu đề / JSON-LD | Khối nội dung mẫu (chưa phải selector cuối) | Ngày đăng |
|---|---:|---|---|---|
| VnExpress | 200 | Có `<h1>`, `NewsArticle` | `article.fck_detail` | JSON-LD `datePublished` |
| Tuổi Trẻ | 200 sau 1 lần thử lại | Có `<h1>`, `NewsArticle`, `article:published_time` | `.detail-content` | Meta + JSON-LD |
| Thanh Niên | 200 | Có `<h1>`, `NewsArticle`, `article:published_time` | `.detail-content` trong `.detail__cmain` | Meta + JSON-LD |
| Dân Trí | 200 | Có `<h1>`, `NewsArticle` | `#desktop-in-article` trong `article#articleContent` | JSON-LD `datePublished` |
| VietnamNet | 200 | Có `<h1>`, `NewsArticle` | `#maincontent` | JSON-LD `datePublished` |

**Bài viết mẫu đã dùng để kiểm tra:**

- VnExpress: https://vnexpress.net/moi-luong-vang-mieng-giam-toi-4-trieu-dong-5146938.html
- Tuổi Trẻ: https://tuoitre.vn/el-nino-bai-toan-nuoc-va-nguoi-dan-biet-bien-nguy-thanh-co-100261116112948918.htm
- Thanh Niên: https://thanhnien.vn/nang-nong-gay-gat-tphcm-va-nam-bo-da-vao-mua-kho-chua-185261120113405183.htm
- Dân Trí: https://dantri.com.vn/kinh-doanh/4-ngan-hang-co-lai-suat-cho-vay-binh-quan-vuot-11nam-20261120110325612.htm
- VietnamNet: https://vietnamnet.vn/lai-suat-ngan-hang-hom-nay-gui-100-trieu-nhan-ve-8-8-trieu-2576993.html

**Quan sát:**

- Cả 5 bài đều có tiêu đề, ngày đăng, tác giả (ở nhiều mức khác nhau) và nội dung chính.
- VnExpress có meta `author = VnExpress`, không phải tên tác giả cụ thể trong một số bài.
- Tuổi Trẻ có `article:published_time` và JSON-LD.
- Dân Trí dùng JSON-LD; meta `author` có thể là “Dân trí”.
- Không thấy CAPTCHA, đăng nhập, paywall ở 5 bài mẫu.
- Tuổi Trẻ lần đầu trả lỗi `ChunkedEncodingError`; thử lại với `Accept-Encoding: identity` thành công. Đây là lỗi mạng, không phải chặn.

**Chưa chốt selector:** mỗi selector mới chỉ kiểm tra trên 1 bài. Bước 4 sẽ kiểm tra 5–10 bài/nguồn, so sánh nhiều selector và dùng JSON-LD/`article:published_time` làm nguồn ngày đăng dự phòng.

### 6.7. Điều khoản sử dụng và bản quyền

| Báo | Trang đã kiểm tra | Ghi nhận |
|---|---|---|
| VnExpress | https://vnexpress.net/dieu-khoan-su-dung | Cấm sao chép/phân phối/xuất bản nội dung **vì mục đích thương mại** mà không có văn bản chấp thuận |
| Tuổi Trẻ | Không tìm thấy liên kết điều khoản sử dụng công khai trong footer | Footer chỉ có nhãn “Điều khoản bảo mật” nhưng không gắn `href`; chưa xác minh được điều khoản nội dung |
| Thanh Niên | https://thanhnien.vn/user/policy.html và https://thanhnien.vn/policy.html | Trang điều khoản tài khoản/chính sách bảo mật; footer ghi “Cấm sao chép dưới mọi hình thức nếu không có sự chấp thuận bằng văn bản” |
| Dân Trí | https://dantri.com.vn/cong-nghe/chinh-sach-bao-mat-du-lieu-ca-nhan-20190514153010649.htm | Chính sách bảo mật dữ liệu cá nhân; footer cũng ghi hạn chế sao chép |
| VietnamNet | https://account.vietnamnet.vn/terms | Điều khoản dịch vụ tài khoản; không phải giấy phép tái sử dụng nội dung |

**Kết luận cần nói rõ trong báo cáo:**

- Điều kiện **kỹ thuật** cho phép crawl: robots không chặn các URL đã chọn.
- Điều kiện **pháp lý** không thể kết luận chỉ từ robots. Các báo giữ bản quyền nội dung.
- Chỉ nên dùng bộ dữ liệu cho **học tập/nghiên cứu nội bộ**, không đăng lại toàn văn, không dùng thương mại.
- Không đưa file CSV chứa toàn văn lên GitHub public. Nếu cần công bố, hãy xin phép tòa soạn hoặc chỉ công bố URL, thống kê và mô hình.
- Đây là ghi nhận kỹ thuật, **không phải tư vấn pháp lý**.

### 6.8. File audit tổng hợp

File: [`outputs/step1_source_audit.csv`](outputs/step1_source_audit.csv)

- 40 dòng = 8 lĩnh vực × 5 báo.
- Encoding: `UTF-8-SIG` để mở đúng tiếng Việt trong Excel.
- Các cột chính:
  - `Label`, `Source`, `Original_Category`
  - `RSS_URL`, `RSS_HTTP`, `RSS_Items`, `RSS_Date_Min`, `RSS_Date_Max`
  - `Category_URL`, `Category_HTTP`
  - `Selected_Method`, `Candidate_Quota`, `Notes`

**Lưu ý:** `Category_Article_Links` là số link bài viết nhận diện bằng regex tại trang danh mục, **không phải số bài hợp lệ**. Cột này có thể chưa bao phủ hết URL bài của một số báo; chỉ dùng để tham khảo.

### 6.9. Kế hoạch lấy URL đề xuất cho Bước 2–3

**Mục tiêu:** 750 URL ứng viên/lĩnh vực → 6.000 URL → kỳ vọng 600–680 bài hợp lệ/lĩnh vực.

| Nguồn | Cách lấy | URL ứng viên/lĩnh vực | Tổng 8 lĩnh vực |
|---|---|---:|---:|
| VnExpress | Trang danh mục p1–p5, khử trùng lặp | 150 | 1.200 |
| Tuổi Trẻ | RSS | 50 | 400 |
| Thanh Niên | RSS | 50 | 400 |
| Dân Trí | RSS (không phân trang) | 100 | 800 |
| VietnamNet | RSS 7 lĩnh vực; Công nghệ lấy 16 trang danh mục | 400 | 3.200 |
| **Tổng** |  | **750** | **6.000** |

**Lý do chọn quota này:**

- 750 > 500 tối thiểu, có buffer cho bài lỗi/trùng/nội dung ngắn.
- Nếu tỷ lệ loại bỏ 15–20%, vẫn còn khoảng 600–640 bài/lĩnh vực.
- Tổng 6.000 URL nằm trong khoảng 4.000–6.400 mục tiêu.
- Không cần phân trang Tuổi Trẻ/Thanh Niên — giảm rủi ro và giữ hệ thống đơn giản.

**Cảnh báo về cân bằng nguồn:** VietnamNet chiếm 400/750 URL mỗi lớp (khoảng 53%). Vì vậy không nên đánh giá mô hình chỉ trên một nguồn; khi chia train/test nên stratify theo `Source` và `Label`. Nếu hội đồng yêu cầu cân bằng nguồn hơn, có thể giảm VietnamNet và tăng VnExpress bằng các trang p6 trở đi, **nhưng phải kiểm tra lại từng URL p6+ trước khi dùng** (Bước 1 mới xác minh đến p5).

### 6.10. Ánh xạ danh mục gốc → nhãn đề tài

| Nhãn đề tài | VnExpress | Tuổi Trẻ | Thanh Niên | Dân Trí | VietnamNet |
|---|---|---|---|---|---|
| Kinh tế | Kinh doanh | Kinh doanh | Kinh tế | Kinh doanh | Kinh doanh |
| Thế giới | Thế giới | Thế giới | Thế giới | Thế giới | Thế giới |
| Thể thao | Thể thao | Thể thao | Thể thao | Thể thao | Thể thao |
| Pháp luật | Pháp luật | Pháp luật | Thời sự/Pháp luật | Pháp luật | Thời sự/Pháp luật |
| Giáo dục | Giáo dục | Giáo dục | Giáo dục | Giáo dục | Giáo dục |
| Sức khỏe | Sức khỏe | Sức khỏe | Sức khỏe | Sức khỏe | Sức khỏe |
| Công nghệ | Khoa học công nghệ | Nhịp sống số | Công nghệ | Công nghệ | Công nghệ |
| Du lịch | Du lịch | Du lịch | Du lịch | Du lịch | Du lịch |

Đây là **nhãn yếu (weak label)** từ danh mục nguồn, không phải nhãn vàng đã kiểm định. Bước 5 phải kiểm tra thủ công.

### 6.11. Chất lượng nhãn và rủi ro dữ liệu

**Rủi ro đã quan sát:**

1. **Bài PR/advertorial:** feed Kinh doanh Tuổi Trẻ có bài giới thiệu sản phẩm doanh nghiệp. Cần loại các bài quảng cáo, advertorial, “giới thiệu sản phẩm”.
2. **Tin khoa học trong chuyên mục Công nghệ:** VnExpress `Khoa học công nghệ` có thể chứa tin thiên văn, khảo cổ, không phù hợp nhãn Công nghệ.
3. **Bài quá ngắn/ảnh/video:** cần đặt ngưỡng nội dung tối thiểu ở Bước 4 và loại bài không có nội dung chính.
4. **Trùng nội dung giữa các báo:** khác URL nhưng cùng nội dung; cần kiểm tra trùng ở Bước 3 (URL) và Bước 4 (hash nội dung).
5. **Lệch nguồn:** VietnamNet chiếm tỷ trọng lớn; cần stratify khi chia tập.
6. **Ngày giờ:** Tuổi Trẻ dùng định dạng ngày Mỹ; phải gắn UTC+7 và chuẩn hóa ISO 8601.

**Kế hoạch kiểm tra nhãn ở Bước 5:**

- Lấy ngẫu nhiên **10%** mỗi lớp, stratify theo `Source` (khoảng 75 bài/lớp nếu có 750 bài).
- Kiểm tra thủ công tiêu đề + nội dung + danh mục gốc.
- Ưu tiên kiểm tra 100% bài có tiêu đề mơ hồ hoặc giao thoa (ví dụ “kinh tế số”, “AI trong giáo dục”, “du lịch và bất động sản”).
- Ghi lại các trường hợp sai vào `manual_review.csv`, không tự ý sửa im lặng.
- Nếu hai người gán nhãn, báo cáo Cohen’s kappa; nếu một người, mô tả quy trình và tỷ lệ đồng ý với nhãn nguồn.

---

## 7. Những lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `403 Forbidden` | Chặn bot, UA không phù hợp | Dừng, kiểm tra robots/ToS; không đổi proxy để lách. Dùng UA minh bạch, giảm tốc độ |
| `429 Too Many Requests` | Gửi quá nhanh | Dừng ngay, tăng delay, chạy lại sau; không dùng nhiều IP |
| `404 Not Found` | URL tự đoán hoặc đổi cấu trúc | Đọc lại RSS index/robots; chỉ dùng URL đã kiểm tra 200 |
| `ChunkedEncodingError` | Kết nối bị ngắt, thường gặp ở Tuổi Trẻ | Thử lại 1–2 lần với `Accept-Encoding: identity`; kiểm tra độ dài HTML |
| `XML ParseError` | Server trả HTML (404/trang chủ) thay vì XML | Kiểm tra `Content-Type`, 100 ký tự đầu; không coi HTTP 200 là thành công |
| Feed có 0 item | Feed cũ/đổi định dạng | Kiểm tra `channel`, `pubDate`; thử trang danh mục |
| Ngày Tuổi Trẻ không parse được | Định dạng M/D/YYYY, không phải RFC 822 | Dùng `%m/%d/%Y %I:%M:%S %p`, gắn `+07:00` |
| Ngày lệch múi giờ | Trộn naive datetime và UTC | Chuẩn hóa tất cả về ISO 8601 có offset `+07:00` |
| VnExpress trả 403 khi dùng Scrapy | `robots.txt` chặn `Scrapy` | Dùng `requests` hoặc đổi framework; không giả UA Googlebot |
| Dân Trí không phân trang được | robots chặn `/trang-1*.htm` … `/trang-9*.htm` | Không phân trang; chỉ dùng RSS 100 bài/ngành |
| VietnamNet Công nghệ chỉ có 36 bài cũ | Feed ngừng cập nhật | Dùng `cong-nghe-page0..15` |
| CSV mở Excel bị lỗi font | Thiếu BOM | Ghi `encoding="utf-8-sig"` |
| Số link danh mục nhiều hơn số bài | Regex bắt cả link menu/sidebar | Lọc theo URL bài viết, khử trùng; không dùng `article_links` làm số bài hợp lệ |
| Selector nội dung trả về rỗng | Website đổi giao diện | Fallback JSON-LD, meta, nhiều selector; ghi lỗi, không lưu bài rỗng |

---

## 8. Bước 2, 3 và 4 — đã hoàn thành

Bạn đã xác nhận 4 điểm: giữ 5 nguồn, quota 750 URL/lĩnh vực, dùng trang chuyên mục cho VnExpress và VietnamNet Công nghệ, chỉ dùng cho học tập.

**Bước 2:**

Kết quả bổ sung:

- VnExpress **không bị loại**; đã kiểm tra sitemap, RSS, 8×5 trang chuyên mục và 8 bài mẫu.
- **40/40 trang chuyên mục p1–p5** trả HTTP 200; mỗi lĩnh vực có **161–184 URL**.
- **8/8 bài mẫu** thuộc 8 lĩnh vực crawl được nội dung; selector chính là `.fck_detail`.
- Sitemap con của VnExpress trả trang chủ HTML, nên **không dùng sitemap**; trang chuyên mục và RSS thay thế đủ.
- Ma trận cuối: **5 nguồn × 8 lĩnh vực = 6.000 URL ứng viên**, VnExpress đóng góp 1.200.
- Chi tiết và code: [buoc2/README.md](buoc2/README.md) và [notebook Bước 2](notebooks/02_xac_dinh_nguon_va_url.ipynb).

**Bước 3:**

- Đã sinh **6.000 URL ứng viên**, đúng **750/lĩnh vực**.
- Không có URL trùng trong danh sách cuối; 20 trường hợp trùng URL và 6 nhóm trùng tiêu đề đã ghi vào `duplicates_review.csv`.
- Cache **104 task**; chạy lại cuối cùng dùng **0 request mạng**.
- **Không crawl nội dung.**
- Chi tiết: [buoc3/README.md](buoc3/README.md), [notebook Bước 3](notebooks/03_danh_sach_url_ung_vien.ipynb), [danh sách URL](data/step3/url_candidates.csv).

**Bước 4:**

- Crawl **5.364/6.000** URL thành công; **185** URL đã thử và thất bại; **451** URL DanTri chưa thử do `HTTP 428/ConnectTimeout` ở tầng mạng.
- Không tạo nội dung/ngày giả; danh sách lỗi và chưa thử được lưu riêng.
- Không xóa bài chỉ vì trùng tiêu đề; 4 nhóm trùng tiêu đề được giữ lại để rà soát.
- Chi tiết: [buoc4/README.md](buoc4/README.md), [notebook Bước 4](notebooks/04_crawl_noi_dung.ipynb), [bài crawl được](data/step4/articles.csv).

**Bước tiếp theo:** Bước 5 — kiểm tra chất lượng nhãn, xử lý trùng lặp dựa trên bằng chứng, tạo `news_dataset.csv`; chưa huấn luyện mô hình.

---

## 9. Tài liệu tham khảo

Truy cập ngày **20/11/2026**:

- VnExpress robots: https://vnexpress.net/robots.txt
- VnExpress điều khoản: https://vnexpress.net/dieu-khoan-su-dung
- VnExpress RSS: https://vnexpress.net/rss
- Tuổi Trẻ robots: https://tuoitre.vn/robots.txt
- Tuổi Trẻ RSS index: https://tuoitre.vn/rss.htm
- Thanh Niên robots: https://thanhnien.vn/robots.txt
- Thanh Niên RSS index: https://thanhnien.vn/rss.html
- Thanh Niên chính sách: https://thanhnien.vn/policy.html
- Dân Trí robots: https://dantri.com.vn/robots.txt
- Dân Trí sitemap: https://dantri.com.vn/sitemap.xml
- Dân Trí chính sách bảo mật: https://dantri.com.vn/cong-nghe/chinh-sach-bao-mat-du-lieu-ca-nhan-20190514153010649.htm
- VietnamNet robots: https://vietnamnet.vn/robots.txt
- VietnamNet sitemap: https://vietnamnet.vn/sitemap.xml
- VietnamNet điều khoản tài khoản: https://account.vietnamnet.vn/terms

---

## 10. Cấu trúc thư mục hiện tại

```text
vn_news_classification/
├── README.md
├── step1_khao_sat.py
├── step3_collect_urls.py
├── step4_parsers.py
├── step4_crawl_articles.py
├── buoc2/
│   └── README.md
├── buoc3/
│   └── README.md
├── buoc4/
│   └── README.md
├── notebooks/
│   ├── 01_khao_sat_nguon.ipynb
│   ├── 02_xac_dinh_nguon_va_url.ipynb
│   ├── 03_danh_sach_url_ung_vien.ipynb
│   └── 04_crawl_noi_dung.ipynb
├── data/
│   ├── step3/
│   │   ├── cache/                  # 104 task cache
│   │   ├── url_candidates.csv      # 6.000 URL
│   │   ├── raw_pool.csv
│   │   ├── duplicates_review.csv
│   │   ├── gaps.csv
│   │   ├── summary_by_label.csv
│   │   └── manifest.json
│   └── step4/
│       ├── checkpoints/            # 9 JSONL checkpoint theo worker
│       ├── failures/               # log lỗi thô
│       ├── articles.csv            # 5.364 bài crawl thành công
│       ├── failed_urls.csv         # 185 URL đã thử, thất bại
│       ├── not_attempted_urls.csv  # 451 URL DanTri chưa thử
│       ├── stats_by_label.csv
│       ├── stats_by_source.csv
│       ├── same_title_review.csv
│       ├── duplicate_content_review.csv
│       ├── progress.json
│       └── manifest.json
├── outputs/
│   ├── step1_source_audit.csv
│   ├── step1_source_audit.json
│   ├── step2_vnexpress_categories.csv
│   ├── step2_vnexpress_matrix.csv
│   ├── step2_vnexpress_sitemaps.csv
│   ├── step2_vnexpress_articles.csv
│   ├── step2_source_plan.csv
│   └── step2_summary.json
└── research/
    ├── probe_candidates.py
    ├── download_feeds.py
    ├── build_step1_csv.py
    ├── vnexpress_sitemap_probe.py
    ├── vnexpress_category_harvest.py
    ├── vnexpress_article_probe.py
    ├── build_step2_outputs.py
    └── raw/
```

---

> **Dữ liệu cuối `news_dataset.csv` chưa được tạo.** Đó là đầu ra của Bước 5 sau khi crawl, kiểm tra nội dung, kiểm tra nhãn và khử trùng.
