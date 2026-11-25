"""Kiểm tra khả năng crawl nội dung 8 bài VnExpress (1 bài/lĩnh vực).

Có 2 chế độ:
  - mặc định: tải 8 URL và lưu HTML;
  - --from-html: chỉ parse lại các HTML đã lưu (không gửi request).
"""
import argparse, json, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

RAW=Path('research/raw/vnexpress'); ART=RAW/'articles'; ART.mkdir(parents=True,exist_ok=True)
UA='student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)'
HEADERS={'User-Agent':UA,'Accept-Language':'vi-VN,vi;q=0.9'}

SAMPLES=[
 ('Kinh tế','https://vnexpress.net/moi-luong-vang-mieng-giam-toi-4-trieu-dong-5146938.html'),
 ('Thế giới - tổng thuật','https://vnexpress.net/lanh-dao-nga-my-trung-sap-hop-ba-ben-lan-dau-tien-5146594-tong-thuat.html'),
 ('Thể thao - tổng thuật','https://vnexpress.net/viet-nam-vs-kyrgyzstan-5145800-tong-thuat.html'),
 ('Pháp luật','https://vnexpress.net/vks-de-nghi-bac-don-kien-benh-vien-phu-san-ha-noi-cua-san-phu-mat-hai-con-5146789.html'),
 ('Công nghệ','https://vnexpress.net/cu-bat-tau-vu-tru-starship-bang-dua-gap-nhin-tu-thap-phong-5147012.html'),
 ('Du lịch','https://vnexpress.net/du-khach-do-den-tham-quyen-xem-trung-quoc-nam-2050-5146978.html'),
 ('Giáo dục','https://vnexpress.net/co-giao-bat-khoc-khi-hoc-tro-xach-muc-ghe-oc-den-tang-ngay-20-11-5147020.html'),
 ('Sức khỏe','https://vnexpress.net/be-gai-viem-thi-than-kinh-do-sot-xuat-huyet-5146708.html'),
]


def parse_article(html, label, url, status=200, content_type='text/html; charset=utf-8'):
    soup=BeautifulSoup(html,'lxml')
    rec={'topic':label,'url':url,'status':status,'final_url':url,
         'bytes':len(html.encode('utf-8')),'content_type':content_type}
    rec['title']=soup.title.get_text(' ',strip=True) if soup.title else None
    h1=soup.select_one('h1.title-detail')
    if h1 is None:
        h1=next((x for x in soup.find_all('h1') if x.get_text(' ',strip=True)),None)
    rec['h1']=h1.get_text(' ',strip=True) if h1 else ''
    can=soup.find('link',rel='canonical'); rec['canonical']=can.get('href') if can else None
    rec['meta']={}
    for key in ['og:title','article:published_time','article:modified_time','author']:
        m=soup.find('meta',attrs={'property':key}) or soup.find('meta',attrs={'name':key})
        if m: rec['meta'][key]=m.get('content')
    types=[]; dates=[]; authors=[]
    for sc in soup.find_all('script',type='application/ld+json'):
        try: obj=json.loads(sc.string or '')
        except Exception: continue
        stack=[obj]
        while stack:
            x=stack.pop()
            if isinstance(x,dict):
                typ=x.get('@type')
                if typ: types.append(str(typ))
                if x.get('datePublished'): dates.append(x['datePublished'])
                if x.get('author'): authors.append(x['author'])
                stack.extend(x.values())
            elif isinstance(x,list): stack.extend(x)
    rec['jsonld_types']=types[:10]; rec['datePublished']=dates[:2]; rec['author']=authors[:1]
    selectors={}
    for sel in ['article.fck_detail','.fck_detail','#main-detail-body','article']:
        el=soup.select_one(sel)
        if el is None: continue
        text=re.sub(r'\s+',' ',el.get_text(' ',strip=True))
        selectors[sel]={'chars':len(text),'p':len(el.find_all('p')),
                        'h2':len(el.find_all('h2')),'img':len(el.find_all('img')),
                        'links':len(el.find_all('a'))}
    rec['selectors']=selectors
    rec['has_article_wrapper']=soup.select_one('article.fck_detail') is not None
    body=soup.select_one('.fck_detail')
    if body is not None:
        text=body.get_text('\n',strip=True)
        rec['body_preview']=re.sub(r'\n+',' | ',text)[:350]
        rec['body_chars']=len(re.sub(r'\s+',' ',text))
        rec['paragraphs']=len(body.find_all('p'))
        rec['images']=len(body.find_all('img'))
    return rec


def fetch_all():
    session=requests.Session(); session.headers.update(HEADERS)
    records=[]
    for idx,(label,url) in enumerate(SAMPLES,start=1):
        try:
            r=session.get(url,timeout=40)
            (ART/f'{idx:02d}.html').write_text(r.text,encoding='utf-8')
            rec=parse_article(r.text,label,url,r.status_code,r.headers.get('content-type'))
            rec['final_url']=r.url; rec['bytes']=len(r.content)
        except Exception as e:
            rec={'topic':label,'url':url,'error':repr(e)[:300]}
        records.append(rec)
        print(f'{idx:02d} {label:22s} {rec.get("status")} {rec.get("h1","")[:60]}',flush=True)
        time.sleep(2)
    return records


def parse_cached():
    records=[]
    for idx,(label,url) in enumerate(SAMPLES,start=1):
        p=ART/f'{idx:02d}.html'
        if not p.exists():
            records.append({'topic':label,'url':url,'error':'missing cached HTML'})
            continue
        rec=parse_article(p.read_text(encoding='utf-8',errors='ignore'),label,url)
        records.append(rec)
        print(f'{idx:02d} {label:22s} {rec.get("body_chars")}',flush=True)
    return records


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--from-html',action='store_true')
    args=ap.parse_args()
    data=parse_cached() if args.from_html else fetch_all()
    (RAW/'article_probe.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('saved',len(data))
