"""Khảo sát sâu VnExpress: 8 chuyên mục x 5 trang + RSS + bài mẫu.
Chỉ thu thập URL, chưa crawl hàng loạt nội dung.
"""
import json, re, time
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

RAW=Path('research/raw/vnexpress'); RAW.mkdir(parents=True,exist_ok=True)
UA='student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'vi-VN,vi;q=0.9'})
PAT=re.compile(r'^https?://vnexpress\.net/[a-z0-9-]+-\d{6,}\.html$')

TOPICS={
 'Kinh tế':   {'cat':'kinh-doanh',        'pages':['kinh-doanh','kinh-doanh-p2','kinh-doanh-p3','kinh-doanh-p4','kinh-doanh-p5']},
 'Thế giới':  {'cat':'the-gioi',          'pages':['the-gioi','the-gioi-p2','the-gioi-p3','the-gioi-p4','the-gioi-p5']},
 'Thể thao':  {'cat':'the-thao',          'pages':['the-thao','the-thao-p2','the-thao-p3','the-thao-p4','the-thao-p5']},
 'Pháp luật': {'cat':'phap-luat',         'pages':['phap-luat','phap-luat-p2','phap-luat-p3','phap-luat-p4','phap-luat-p5']},
 'Giáo dục':  {'cat':'giao-duc',          'pages':['giao-duc','giao-duc-p2','giao-duc-p3','giao-duc-p4','giao-duc-p5']},
 'Sức khỏe':  {'cat':'suc-khoe',          'pages':['suc-khoe','suc-khoe-p2','suc-khoe-p3','suc-khoe-p4','suc-khoe-p5']},
 'Công nghệ': {'cat':'khoa-hoc-cong-nghe','pages':['khoa-hoc-cong-nghe','cong-nghe-p2','cong-nghe-p3','cong-nghe-p4','cong-nghe-p5']},
 'Du lịch':   {'cat':'du-lich',           'pages':['du-lich','du-lich-p2','du-lich-p3','du-lich-p4','du-lich-p5']},
}


def get(url):
    r=S.get(url,timeout=35)
    return r

rows=[]; all_links={}
for topic,cfg in TOPICS.items():
    seen=[]
    for page,slug in enumerate(cfg['pages'], start=1):
        url=f'https://vnexpress.net/{slug}'
        try:
            r=get(url)
            soup=BeautifulSoup(r.text,'lxml')
            links=[]
            for a in soup.find_all('a',href=True):
                u=urljoin(r.url,a['href']).split('?')[0].split('#')[0]
                if PAT.match(u): links.append(u)
            uniq=list(dict.fromkeys(links))
            new=[u for u in uniq if u not in seen]
            seen.extend(new)
            row={'topic':topic,'page':page,'url':url,'status':r.status_code,
                 'content_type':r.headers.get('content-type'),'bytes':len(r.content),
                 'h1':soup.find('h1').get_text(' ',strip=True) if soup.find('h1') else None,
                 'links_on_page':len(uniq),'new_unique':len(new),'cumulative_unique':len(seen),
                 'sample':uniq[:2]}
        except Exception as e:
            row={'topic':topic,'page':page,'url':url,'error':repr(e)[:250]}
        rows.append(row); print(topic,page,row.get('status'),row.get('links_on_page'),'new',row.get('new_unique'),'total',row.get('cumulative_unique'),flush=True)
        time.sleep(1.5)
    all_links[topic]=seen

Path(RAW/'category_harvest.json').write_text(json.dumps({'rows':rows,'links':all_links},ensure_ascii=False,indent=2),encoding='utf-8')
print('\nTotals:')
for t,v in all_links.items(): print(f'{t:10s} {len(v)}')
