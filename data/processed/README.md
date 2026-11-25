# Dataset chính thức

**File:** `data/processed/news_dataset.csv`

**Nguồn:** `data/audit/news_dataset_reviewed.csv` (5.898 bài đã rà soát).

File được sao chép **nguyên byte** từ dataset nguồn. Không crawl lại, không sửa nội dung/nhãn, không thêm/bớt bản ghi.

## Số liệu

- Tổng số dòng dữ liệu: **5,898** (không tính header).
- Số cột: **14**.
- URL duy nhất: **5,898**.
- ID duy nhất: **5,898**.
- Nhãn: **8** lĩnh vực.
- Thiếu trường bắt buộc: **0**.
- Thiếu `Published_Date`: **0**.
- Cột `Author`: **không có**.

## Cột

| Cột | Vai trò |
|---|---|
| `ID` | Định danh; chỉ truy xuất/kiểm tra |
| `Title` | Tiêu đề bài viết |
| `Content` | Nội dung đã rà soát lớp trình bày; chưa xử lý NLP |
| `URL` | URL gốc; truy xuất nguồn |
| `Source` | Nguồn báo |
| `Published_Date` | Ngày đăng; giữ nguyên từ dataset rà soát |
| `Date_Source` | Nguồn ngày; **chỉ kiểm toán** |
| `Date_Check` | Trạng thái đối chiếu ngày; **chỉ kiểm toán** |
| `Original_Category` | Chuyên mục gốc của nguồn; **không dùng làm feature** |
| `Label` | Nhãn đích 8 lĩnh vực |
| `Content_Length` | Độ dài đã tính; metadata/kiểm toán |
| `Label_Status` | Trạng thái kiểm định nhãn; **chỉ kiểm toán** |
| `Leakage_Group` | Nhóm chống leakage; **chỉ chia tập, không làm feature** |
| `Split` | Phân tập train/val/test; **chỉ dùng chia tập** |

## Lưu ý sử dụng

- `Leakage_Group` và `Split` phải được giữ để kiểm tra/chia tập nhưng **không được đưa vào mô hình như đặc trưng**.
- `Date_Source`, `Date_Check`, `Label_Status`, `Original_Category`, `Content_Length`, `ID`, `URL` là metadata/kiểm toán, không dùng làm đặc trưng đầu vào.
- `Title` và `Content` là văn bản thô đã rà soát; **chưa** tokenization, stopwords, TF-IDF hay vectorization.
- File nguồn `data/audit/news_dataset_reviewed.csv` **không bị sửa/xóa**.

## Kiểm tra

- SHA-256 file nguồn: `c68e24ec673cefc34fb7e697c60f404debce1e70178af6fa45d3ad7abd269dd8`
- SHA-256 dataset mới: `c68e24ec673cefc34fb7e697c60f404debce1e70178af6fa45d3ad7abd269dd8`
- Hai file **giống nhau từng byte**; `Content`, `Label`, `ID`, `URL` không đổi.
- Kiểm tra split: không có `Leakage_Group` nào xuất hiện ở 2 tập.
