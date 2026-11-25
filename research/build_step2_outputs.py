"""Tổng hợp bằng chứng Bước 2 thành các bảng bàn giao."""
import csv, json, xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path('.')
OUT=ROOT/'outputs'; OUT.mkdir(exist_ok=True)
harvest=json.load(open('research/raw/vnexpress/category_harvest.json',encoding='utf-8'))
articles=json.load(open('research/raw/vnexpress/article_probe.json',encoding='utf-8'))
sitemaps=json.load(open('research/raw/vnexpress/sitemap_probe.json',encoding='utf-8'))
audit=list(csv.DictReader(open('outputs/step1_source_audit.csv',encoding='utf-8-sig')))

TOPICS=['Kinh tế','Thế giới','Thể thao','Pháp luật','Giáo dục','Sức khỏe','Công nghệ','Du lịch']
FEED={'Kinh tế':'kinh-te','Thế giới':'the-gioi','Thể thao':'the-thao','Pháp luật':'phap-luat',
      'Giáo dục':'giao-duc','Sức khỏe':'suc-khoe','Công nghệ':'cong-nghe','Du lịch':'du-lich'}
QUOTA=150

# 1. 40 dòng trang chuyên mục
cat_rows=[]
for r in harvest['rows']:
    cat_rows.append({
        'Label':r['topic'],'Page':r['page'],'URL':r['url'],'HTTP':r.get('status',''),
        'H1':r.get('h1',''),'Bytes':r.get('bytes',''),'Links_On_Page':r.get('links_on_page',''),
        'New_Unique':r.get('new_unique',''),'Cumulative_Unique':r.get('cumulative_unique',''),
    })
with (OUT/'step2_vnexpress_categories.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(cat_rows[0])); w.writeheader(); w.writerows(cat_rows)

# 2. RSS vs chuyên mục, 8 dòng
matrix=[]
for topic in TOPICS:
    cat=harvest['links'][topic]
    root=ET.parse(f'research/raw/feeds/VnExpress/{FEED[topic]}.xml').getroot()
    rss=[(it.findtext('link') or '').strip() for it in root.findall('.//item')]
    rss=[x for x in rss if x]
    cs,rs=set(cat),set(rss)
    union=cs|rs
    row=next(x for x in harvest['rows'] if x['topic']==topic and x['page']==1)
    base=row['url']
    pages=[x['url'] for x in harvest['rows'] if x['topic']==topic]
    matrix.append({
        'Label':topic,'Category_Page':base,'Pages_Checked':len(pages),
        'Pages_HTTP_200':sum(1 for x in harvest['rows'] if x['topic']==topic and x.get('status')==200),
        'Unique_Category_URLs':len(cs),'RSS_Items':len(rs),'RSS_Overlap':len(cs&rs),
        'Union_Available':len(union),'Candidate_Quota':QUOTA,
        'Quota_Coverage_Pct':round(min(100,len(cs)/QUOTA*100),1),
        'Primary_Method':'category_pages_p1_p5','Fallback_Method':'rss',
        'Sitemap_Usable':'no (child sitemaps return homepage HTML)',
        'Notes':('Trang p1 gồm cả khoa học; p2-p5 dùng /cong-nghe-pN. Kiểm tra nhãn thủ công.'
                 if topic=='Công nghệ' else
                 'Đủ quota 150 chỉ từ trang chuyên mục; RSS dùng bổ sung/đối chiếu.'),
    })
with (OUT/'step2_vnexpress_matrix.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(matrix[0])); w.writeheader(); w.writerows(matrix)

# 3. 8 bài kiểm tra nội dung
art_rows=[]
for r in articles:
    sel=r.get('selectors',{}).get('.fck_detail',{})
    note=[]
    if not r.get('has_article_wrapper'):
        note.append('Bài tổng thuật/live blog: không có article.fck_detail, dùng .fck_detail')
    if r['topic']=='Sức khỏe':
        note.append('H1 đầu tiên rỗng (logo); lấy h1.title-detail hoặc JSON-LD headline')
    art_rows.append({
        'Label':r['topic'],'URL':r['url'],'HTTP':r.get('status',''),'H1':r.get('h1',''),
        'Content_Selector':'.fck_detail','Content_Chars':r.get('body_chars',sel.get('chars','')),
        'Paragraphs':r.get('paragraphs',sel.get('p','')),'Images':r.get('images',sel.get('img','')),
        'DatePublished':(r.get('datePublished') or [''])[0],
        'Author_Meta':r.get('meta',{}).get('author',''),
        'Has_Article_Wrapper':r.get('has_article_wrapper'),
        'Access':'public (không thấy login/paywall)',
        'Notes':'; '.join(note),
    })
with (OUT/'step2_vnexpress_articles.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(art_rows[0])); w.writeheader(); w.writerows(art_rows)

# 4. Ma trận nguồn cuối cùng 40 dòng
# URL trang phụ của VnExpress
extras={
 'Kinh tế':['kinh-doanh-p2','kinh-doanh-p3','kinh-doanh-p4','kinh-doanh-p5'],
 'Thế giới':['the-gioi-p2','the-gioi-p3','the-gioi-p4','the-gioi-p5'],
 'Thể thao':['the-thao-p2','the-thao-p3','the-thao-p4','the-thao-p5'],
 'Pháp luật':['phap-luat-p2','phap-luat-p3','phap-luat-p4','phap-luat-p5'],
 'Giáo dục':['giao-duc-p2','giao-duc-p3','giao-duc-p4','giao-duc-p5'],
 'Sức khỏe':['suc-khoe-p2','suc-khoe-p3','suc-khoe-p4','suc-khoe-p5'],
 'Công nghệ':['cong-nghe-p2','cong-nghe-p3','cong-nghe-p4','cong-nghe-p5'],
 'Du lịch':['du-lich-p2','du-lich-p3','du-lich-p4','du-lich-p5'],
}
plan=[]
for r in audit:
    label,source=r['Label'],r['Source']
    if source=='VnExpress':
        primary='category_pages'; primary_url=r['Category_URL']
        extra='; '.join(f'https://vnexpress.net/{x}' for x in extras[label])
        fallback='rss'; fallback_url=r['RSS_URL']
        evidence='40/40 trang p1-p5 HTTP 200; 161-184 URL/chuyên mục'
        note=('Trang p1 là Khoa học công nghệ; từ p2 URL chuyển thành /cong-nghe-pN. '
              'Sitemap con không dùng được (trả trang chủ).'
              if label=='Công nghệ' else
              'Sitemap con không dùng được (trả trang chủ); trang chuyên mục đủ 150 URL.')
    elif source=='VietnamNet' and label=='Công nghệ':
        primary='category_pages'; primary_url=r['Category_URL']
        extra='; '.join([f'https://vietnamnet.vn/cong-nghe-page{i}' for i in range(1,16)])
        fallback='rss (cũ)'; fallback_url=r['RSS_URL']
        evidence='31 link trang 1, ~25 link/trang; trang mẫu p1,p2,p10,p15,p20 HTTP 200'
        note='Feed chỉ 36 mục, dừng 06/05/2025; bắt buộc dùng trang chuyên mục.'
    else:
        primary='rss'; primary_url=r['RSS_URL']; extra=''
        fallback='category_page'; fallback_url=r['Category_URL']
        evidence=f"RSS HTTP {r['RSS_HTTP']}, {r['RSS_Items']} item"
        if source=='TuoiTre':
            note='50 URL từ RSS; ngày dùng M/D/YYYY h:mm:ss AM/PM.'
        elif source=='ThanhNien':
            note='50 URL từ RSS.'
        elif source=='DanTri':
            note='100 URL từ RSS; KHÔNG phân trang vì robots.txt chặn.'
        elif source=='VietnamNet':
            note='400 URL mới nhất từ RSS (feed 1.000 mục).'
        else:
            note=r.get('Notes','')
    plan.append({
        'Label':label,'Source':source,'Original_Category':r['Original_Category'],
        'Primary_Method':primary,'Primary_URL':primary_url,'Additional_Pages':extra,
        'Fallback_Method':fallback,'Fallback_URL':fallback_url,
        'Candidate_Quota':r['Candidate_Quota'],'Evidence':evidence,'Notes':note,
    })
with (OUT/'step2_source_plan.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(plan[0])); w.writeheader(); w.writerows(plan)

summary={
 'vnexpress_retained':True,
 'vnexpress_pages_checked':len(cat_rows),
 'vnexpress_pages_200':sum(1 for r in cat_rows if r['HTTP']==200),
 'vnexpress_unique_min':min(x['Unique_Category_URLs'] for x in matrix),
 'vnexpress_unique_max':max(x['Unique_Category_URLs'] for x in matrix),
 'vnexpress_article_samples':len(art_rows),
 'vnexpress_article_samples_200':sum(1 for r in art_rows if r['HTTP']==200),
 'vnexpress_article_chars_min':min(int(r['Content_Chars']) for r in art_rows),
 'vnexpress_article_chars_max':max(int(r['Content_Chars']) for r in art_rows),
 'sitemap_child_usable':False,
 'source_plan_rows':len(plan),
 'candidates_total':sum(int(r['Candidate_Quota']) for r in plan),
 'labels':TOPICS,
 'checked_at':'2026-11-20T13:35:00+07:00',
}
with (OUT/'step2_summary.json').open('w',encoding='utf-8') as f:
    json.dump(summary,f,ensure_ascii=False,indent=2)

print(json.dumps(summary,ensure_ascii=False,indent=2))
print('wrote 4 CSVs + summary')
