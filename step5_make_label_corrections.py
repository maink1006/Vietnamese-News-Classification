"""Tạo danh sách hiệu chỉnh nhãn có căn cứ từ tiêu đề/nội dung.

- 80 bài mẫu stratified (2 bài mỗi Lĩnh vực x Nguồn).
- Rà soát toàn bộ VNNet Công nghệ có dấu hiệu quân sự.
- Rà soát các bài VnExpress Công nghệ thiên khoa học/sức khỏe.
- Các bài giao thoa đã phát hiện ở Bước 3.
"""
import re
from pathlib import Path
import pandas as pd

ROOT = Path('.')
A = pd.read_csv('data/step4/articles.csv', encoding='utf-8-sig')
OUT = ROOT / 'data' / 'audit'
OUT.mkdir(exist_ok=True)
corr = []

def add(rid, new, action, reason, review_type):
    row = A[A.ID == rid]
    if len(row) == 0:
        return
    r = row.iloc[0]
    corr.append({
        'ID': rid, 'Title': r.Title, 'Source': r.Source,
        'Old_Label': r.Label, 'New_Label': new, 'Action': action,
        'Review_Type': review_type, 'Reason': reason,
    })

# 1) Lỗi phát hiện trong 80 bài mẫu + giao thoa đã biết
add('C000883', 'Công nghệ', 'relabel', 'Bài về chiến dịch/Nvidia, thuộc chủ đề công nghệ; không phải thế giới chính trị.', 'sample')
add('C001057', 'Giáo dục', 'relabel', 'Chính sách thi cử Hàn Quốc; trọng tâm giáo dục, không phải thế giới.', 'sample')
add('C003416', 'Công nghệ', 'relabel', 'Tuần lễ khoa học công nghệ VinFuture; không phải giáo dục.', 'sample')
add('C004916', 'Thế giới', 'relabel', 'USV quân sự Indonesia; chủ đề quốc phòng/quân sự.', 'sample')
add('C004801', 'DROP', 'drop', 'Bài về đời tư lãnh đạo Nvidia, không thuộc 8 lĩnh vực; chất lượng thấp.', 'sample')
add('C005576', 'DROP', 'drop', 'Bài sinh vật biển sâu, không thuộc Du lịch hay 8 lĩnh vực.', 'sample')

# 2) Giao thoa nhãn trong các URL trùng Bước 3
add('C003163', 'Du lịch', 'relabel', 'Nhân sự Phú Quốc phục vụ APEC 2027; trọng tâm du lịch/điểm đến.', 'cross_topic')
add('C003178', 'Sức khỏe', 'relabel', 'Vụ ngộ độc học sinh; trọng tâm an toàn thực phẩm/sức khỏe.', 'cross_topic')

# 3) VnExpress Công nghệ thiên khoa học/sức khỏe
add('C004512', 'Sức khỏe', 'relabel', 'Phỏng vấn về phòng ngừa ung thư; phù hợp Sức khỏe.', 'high_risk_source')
add('C004726', 'Thể thao', 'relabel', 'Giải đấu thể thao điện tử Predator League; nhãn Thể thao thống nhất với bài cùng sự kiện.', 'near_duplicate_label_conflict')
add('C004754', 'Du lịch', 'relabel', 'Bài về du lịch cộng đồng/chuyển đổi số của xã Long Cốc; trọng tâm du lịch.', 'high_risk_source')
add('C004566', 'Sức khỏe', 'relabel', 'Ảnh hưởng sóng điện thoại lên cơ thể; phù hợp Sức khỏe.', 'high_risk_source')
add('C004523', 'DROP', 'drop', 'Bẫy ảnh thú rừng; khoa học tự nhiên, không thuộc 8 lĩnh vực.', 'high_risk_source')
add('C004529', 'DROP', 'drop', 'Tấm chắn Mặt Trời/khí hậu; khoa học, không thuộc 8 lĩnh vực.', 'high_risk_source')

# 4) VNNet Công nghệ: rà soát toàn bộ bài quân sự/tên lửa
mil = re.compile(r'(tên lửa|vũ khí|quân sự|phòng không|xe tăng|bọc thép|tiêm kích|UAV|USV|drone|tàu chiến|tàu sân bay|pháo|đạn|chiến tranh|tác chiến|quốc phòng|hải quân|không quân|radar|S-400|S-500|Patriot|Iskander|BrahMos|HIMARS|NATO|chiến trường|quân đội|vệ tinh quân sự)', re.I)
exceptions = {'C004891','C005020','C005069','C005098','C005198','C005245'}
sub = A[(A.Source == 'VietnamNet') & (A.Label == 'Công nghệ')]
for r in sub.itertuples():
    if mil.search(r.Title) and r.ID not in exceptions:
        add(r.ID, 'Thế giới', 'relabel', 'Tin quân sự/vũ khí/tên lửa; phù hợp Thế giới hơn Công nghệ dân sự.', 'full_high_risk_category')

# 5) Bài công nghệ không phù hợp nhãn, bị loại
add('C005083', 'DROP', 'drop', 'Tai nạn gia đình doanh nhân; không phải tin công nghệ.', 'full_high_risk_category')

# Ghi file
df = pd.DataFrame(corr).drop_duplicates('ID')
df.to_csv(OUT / 'label_corrections.csv', index=False, encoding='utf-8-sig')
print('corrections', len(df))
print(df.groupby(['Action','Review_Type']).size().to_string())
print('\nRelabel source -> target:')
print(df[df.Action=='relabel'].groupby(['Old_Label','New_Label']).size().to_string())
print('\nDrops:')
print(df[df.Action=='drop'][['ID','Source','Old_Label','Title']].to_string(index=False))
