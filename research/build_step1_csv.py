"""Tổng hợp bằng chứng Bước 1 đã thu thập thành CSV bàn giao."""
import csv, json, xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT=Path('.')
LABELS=['Kinh tế','Thế giới','Thể thao','Pháp luật','Giáo dục','Sức khỏe','Công nghệ','Du lịch']
TOPIC_KEYS={'Kinh tế':'kinh-te','Thế giới':'the-gioi','Thể thao':'the-thao','Pháp luật':'phap-luat',
            'Giáo dục':'giao-duc','Sức khỏe':'suc-khoe','Công nghệ':'cong-nghe','Du lịch':'du-lich'}
SOURCE_ORDER=['VnExpress','TuoiTre','ThanhNien','DanTri','VietnamNet']
ORIGINAL={
 'VnExpress':{'Kinh tế':'Kinh doanh','Thế giới':'Thế giới','Thể thao':'Thể thao','Pháp luật':'Pháp luật',
              'Giáo dục':'Giáo dục','Sức khỏe':'Sức khỏe','Công nghệ':'Khoa học công nghệ','Du lịch':'Du lịch'},
 'TuoiTre':{'Kinh tế':'Kinh doanh','Thế giới':'Thế giới','Thể thao':'Thể thao','Pháp luật':'Pháp luật',
            'Giáo dục':'Giáo dục','Sức khỏe':'Sức khỏe','Công nghệ':'Nhịp sống số','Du lịch':'Du lịch'},
 'ThanhNien':{'Kinh tế':'Kinh tế','Thế giới':'Thế giới','Thể thao':'Thể thao','Pháp luật':'Thời sự / Pháp luật',
              'Giáo dục':'Giáo dục','Sức khỏe':'Sức khỏe','Công nghệ':'Công nghệ','Du lịch':'Du lịch'},
 'DanTri':{'Kinh tế':'Kinh doanh','Thế giới':'Thế giới','Thể thao':'Thể thao','Pháp luật':'Pháp luật',
           'Giáo dục':'Giáo dục','Sức khỏe':'Sức khỏe','Công nghệ':'Công nghệ','Du lịch':'Du lịch'},
 'VietnamNet':{'Kinh tế':'Kinh doanh','Thế giới':'Thế giới','Thể thao':'Thể thao','Pháp luật':'Thời sự / Pháp luật',
               'Giáo dục':'Giáo dục','Sức khỏe':'Sức khỏe','Công nghệ':'Công nghệ','Du lịch':'Du lịch'},
}
QUOTA={'VnExpress':150,'TuoiTre':50,'ThanhNien':50,'DanTri':100,'VietnamNet':400}

from datetime import timedelta, timezone
VN_TZ=timezone(timedelta(hours=7))

def parse_date(value):
    value=(value or '').strip().replace('\u00a0',' ').replace('\u202f',' ')
    try:
        return datetime.strptime(value,'%m/%d/%Y %I:%M:%S %p').replace(tzinfo=VN_TZ)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError,ValueError):
        return None

feeds=[]
for site in ['VnExpress','TuoiTre','ThanhNien','DanTri','VietnamNet']:
    for f in sorted(Path('research/raw/feeds',site).glob('*.xml')):
        topic_key=f.stem
        root=ET.parse(f).getroot(); ch=root.find('channel'); items=ch.findall('item')
        links=[(it.findtext('link') or '').strip() for it in items if it.findtext('link')]
        ds=[parse_date(it.findtext('pubDate')) for it in items]
        ds=[d for d in ds if d]
        feeds.append({
            'site':site,'topic':topic_key,
            'url': 'https://vietnamnet.vn/rss/phap-luat.rss' if (site=='VietnamNet' and topic_key=='phap-luat') else None,
            'status':200,'items':len(items),'unique_links':len(set(links)),
            'date_min':min(ds).isoformat(),'date_max':max(ds).isoformat(),
            'channel_title':(ch.findtext('title') or '').strip(),
        })
# Lấy URL feed từ probe_results (đã kiểm tra thực tế); feed law lấy URL đã sửa.
probes=json.load(open('research/raw/probe_results.json'))
probe_feed_urls={(r['site'],r['topic']): r['url'] for r in probes if r['kind']=='rss'}
probe_feed_urls[('VietnamNet','phap-luat')]='https://vietnamnet.vn/rss/phap-luat.rss'
for r in feeds:
    r['url']=probe_feed_urls[(r['site'],r['topic'])]

feed_idx={(r['site'],r['topic']):r for r in feeds}
probe_idx={(r['site'],r['topic'],r['kind']):r for r in probes}

def notes(site,topic):
    if site=='VnExpress':
        if topic=='Công nghệ':
            return ('Trang p1 là Khoa học công nghệ; từ p2 URL chuyển thành /cong-nghe-pN và H1 là Công nghệ. '
                    'Cần kiểm tra thủ công các bài khoa học thuần túy. Dùng p1–p5, lấy tối đa 150 URL.')
        return 'Dùng trang danh mục p1–p5 (p1 50 link; p2–p5 khoảng 30 link/trang), khử trùng lặp; RSS là dự phòng.'
    if site=='TuoiTre':
        if topic=='Công nghệ':
            return ('RSS Nhịp sống số có 50 mục nhưng bài cũ nhất 30/09/2026; ngày RSS dùng M/D/YYYY h:mm:ss AM/PM. '
                    'Lấy 50 URL từ RSS, không dựa vào phân trang danh mục chưa xác minh.')
        return 'Lấy 50 URL từ RSS; ngày RSS dùng định dạng M/D/YYYY h:mm:ss AM/PM (không phải RFC 822).'
    if site=='ThanhNien':
        return 'Lấy 50 URL từ RSS. Một số bài du lịch cũ nhất cách ngày khảo sát khoảng 17 ngày.'
    if site=='DanTri':
        return ('Lấy 100 URL từ RSS. KHÔNG dùng phân trang /trang-2..9 vì robots.txt chặn các đường dẫn này.')
    if site=='VietnamNet':
        if topic=='Công nghệ':
            return ('RSS Công nghệ chỉ còn 36 mục, bài mới nhất 06/05/2025 (feed ngừng cập nhật). '
                    'Dùng 16 trang danh mục /cong-nghe-page0..15; trang đầu 31 link, các trang sau khoảng 25 link.')
        if topic=='Pháp luật':
            return ('URL /rss/thoi-su-phap-luat.rss trả 404. Feed đúng là /rss/phap-luat.rss (1.000 mục). '
                    'Lấy 400 URL mới nhất từ feed.')
        return 'RSS trả 1.000 mục, đủ dùng; lấy 400 URL mới nhất để giữ cân bằng nguồn.'
    return ''

rows=[]
for label in LABELS:
    key=TOPIC_KEYS[label]
    for site in SOURCE_ORDER:
        f=feed_idx[(site,key)]; c=probe_idx[(site,key,'cat')]
        method='category_pages' if (site=='VnExpress' or (site=='VietnamNet' and label=='Công nghệ')) else 'rss'
        rows.append({
            'Label':label,'Source':site,'Original_Category':ORIGINAL[site][label],
            'RSS_URL':f.get('url'),'RSS_HTTP':f.get('status'),'RSS_Items':f.get('items'),
            'RSS_Unique_Links':f.get('unique_links'),'RSS_Date_Min':f.get('date_min'),'RSS_Date_Max':f.get('date_max'),
            'Category_URL':c.get('url'),'Category_HTTP':c.get('status'),
            'Category_Link_Count_Approx':c.get('article_links'),
            'Selected_Method':method,'Candidate_Quota':QUOTA[site],'Notes':notes(site,label),
        })

out=Path('outputs'); out.mkdir(exist_ok=True)
with open(out/'step1_source_audit.csv','w',encoding='utf-8-sig',newline='') as fp:
    w=csv.DictWriter(fp,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
with open(out/'step1_source_audit.json','w',encoding='utf-8') as fp:
    json.dump(rows,fp,ensure_ascii=False,indent=2)
print('rows',len(rows))
print('statuses rss', {x:sum(1 for r in rows if r['Source']==x and r['RSS_HTTP']==200) for x in SOURCE_ORDER})
print('statuses cat', {x:sum(1 for r in rows if r['Source']==x and r['Category_HTTP']==200) for x in SOURCE_ORDER})
print('quota total',sum(QUOTA.values())*8)
