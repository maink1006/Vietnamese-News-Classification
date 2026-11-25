"""Kiểm tra sitemap VnExpress với UA minh bạch; không giả UA search bot."""
import csv, json, time, xml.etree.ElementTree as ET
from pathlib import Path
import requests

OUT=Path('outputs'); OUT.mkdir(exist_ok=True)
RAW=Path('research/raw/vnexpress'); RAW.mkdir(parents=True,exist_ok=True)
UA='student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept':'application/xml,text/xml;q=0.9,*/*;q=0.8'})
URLS=[
 ('sitemap_index','https://vnexpress.net/sitemap.xml'),
 ('daily_2026_11_20','https://vnexpress.net/articles-2026-sitemap.xml?m=11&d=20'),
 ('daily_2026_11_19','https://vnexpress.net/articles-2026-sitemap.xml?m=11&d=19'),
 ('google_news','https://vnexpress.net/google-news-sitemap.xml'),
 ('topics','https://vnexpress.net/topics-sitemap.xml'),
 ('categories','https://vnexpress.net/categories-sitemap.xml'),
]
rows=[]
for name,url in URLS:
    rec={'name':name,'url':url}
    try:
        r=S.get(url,timeout=40)
        rec.update(status=r.status_code,final_url=r.url,bytes=len(r.content),
                   content_type=r.headers.get('content-type'),is_xml=False,entries=None)
        try:
            root=ET.fromstring(r.content)
            rec['is_xml']=True
            rec['root']=root.tag.rsplit('}',1)[-1]
            rec['entries']=sum(1 for e in root.iter() if e.tag.rsplit('}',1)[-1] in {'sitemap','url'})
        except ET.ParseError:
            rec['html_title']=' '.join(r.text.split('<title>')[-1].split('</title>')[:1])[:120] if '<title>' in r.text else None
            rec['starts_with']=r.text[:80].replace('\n',' ')
        (RAW/f'sitemap_{name}.response').write_bytes(r.content)
    except Exception as e:
        rec['error']=repr(e)[:250]
    rows.append(rec)
    print(rec,flush=True)
    time.sleep(2)

(RAW/'sitemap_probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'step2_vnexpress_sitemaps.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['name','url','status','final_url','bytes','content_type','is_xml','root','entries','html_title','starts_with','error'], extrasaction='ignore')
    w.writeheader(); w.writerows(rows)
print('saved',len(rows))
