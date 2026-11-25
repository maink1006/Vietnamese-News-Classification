"""Bổ sung ngày đăng cho 32 bài VietnamNet thiếu metadata, chỉ từ HTML hiển thị."""
import re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT=Path('.'); OUT=ROOT/'data'/'audit'; OUT.mkdir(exist_ok=True)
UA='student-research-bot/1.0 (do-an-phan-loai-tin-tuc; hoc tap, toc do thap)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'vi-VN,vi;q=0.9'})
TZ=timezone(timedelta(hours=7))
a=pd.read_csv('data/step4/articles.csv',encoding='utf-8-sig')
missing=a[a.Published_Date.isna()]
print('missing',len(missing))
rows=[]
for r in missing.itertuples():
    try:
        x=S.get(r.URL,timeout=30)
        text=''
        if x.status_code==200:
            soup=BeautifulSoup(x.text,'lxml')
            for sel in ['.publish-date','.bread-crumb-detail__time','.content-detail-date','.date-time']:
                el=soup.select_one(sel)
                if el is not None:
                    text=el.get_text(' ',strip=True)
                    if text: break
        parsed=None
        m=re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s*[-–]?\s*(\d{1,2}):(\d{2})',text)
        if m:
            d,mo,y,h,mi=map(int,m.groups())
            parsed=datetime(y,mo,d,h,mi,tzinfo=TZ).isoformat(timespec='seconds')
        rows.append({'ID':r.ID,'URL':r.URL,'Old_Date':'','New_Date':parsed or '',
                     'Date_Text':text[:120],'HTTP':x.status_code})
        print(r.ID,x.status_code,text[:80],'->',parsed)
    except Exception as e:
        rows.append({'ID':r.ID,'URL':r.URL,'Old_Date':'','New_Date':'',
                     'Date_Text':'','HTTP':None,'Error':repr(e)[:150]})
        print(r.ID,'ERR',repr(e)[:120])
    time.sleep(1.5)
df=pd.DataFrame(rows)
df.to_csv(OUT/'date_corrections.csv',index=False,encoding='utf-8-sig')
print('filled',int((df.New_Date!='').sum()),'/',len(df))
