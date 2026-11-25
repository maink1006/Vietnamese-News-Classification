"""Kiểm tra tính nhất quán giữa Bước 3, Bước 4 và dataset rà soát."""
import hashlib, json
from pathlib import Path
import pandas as pd

ROOT=Path('.')
AUD=ROOT/'data'/'audit'
s3=pd.read_csv(ROOT/'data/step3/url_candidates.csv',encoding='utf-8-sig').rename(columns={'Candidate_ID':'ID'})
s4=pd.read_csv(ROOT/'data/step4/articles.csv',encoding='utf-8-sig')
f4=pd.read_csv(ROOT/'data/step4/failed_urls.csv',encoding='utf-8-sig')
n4=pd.read_csv(ROOT/'data/step4/not_attempted_urls.csv',encoding='utf-8-sig')
final=pd.read_csv(AUD/'news_dataset_reviewed.csv',encoding='utf-8-sig')
corr=pd.read_csv(AUD/'label_corrections.csv',encoding='utf-8-sig')
manifest=json.loads((AUD/'audit_manifest.json').read_text(encoding='utf-8'))
checks=[]
def chk(name, ok, detail):
    checks.append({'Check':name,'Pass':bool(ok),'Detail':str(detail)})
    return bool(ok)

chk('Step3 6000', len(s3)==6000, len(s3))
chk('Step3 unique URL', s3.URL.nunique()==6000, s3.URL.nunique())
chk('Step3 750/label', (s3.groupby('Label').size()==750).all(), s3.groupby('Label').size().to_dict())
chk('Step4 counted', len(s4)+len(f4)+len(n4)==6000, f'{len(s4)}+{len(f4)}+{len(n4)}')
chk('Step4 no unattempted', len(n4)==0, len(n4))
chk('Step4 IDs subset Step3', set(s4.ID).issubset(set(s3.ID)), len(set(s4.ID)-set(s3.ID)))
chk('Final = Step4 - invalid - drops', len(final)==len(s4)-12-5, f'{len(s4)}-12-5={len(final)}')
chk('Final unique ID', final.ID.nunique()==len(final), len(final))
chk('Final unique URL', final.URL.nunique()==len(final), final.URL.nunique())
chk('Final 8 labels', set(final.Label)=={'Kinh tế','Thế giới','Thể thao','Pháp luật','Giáo dục','Sức khỏe','Công nghệ','Du lịch'}, sorted(final.Label.unique()))
chk('Final >=500/label', (final.groupby('Label').size()>=500).all(), final.groupby('Label').size().to_dict())
chk('No Author column', 'Author' not in final.columns, list(final.columns))
chk('No missing date', final.Published_Date.isna().sum()==0, final.Published_Date.isna().sum())
chk('All labels corrected in file', set(corr[corr.Action=='relabel'].New_Label).issubset(set(final.Label)), '')
chk('Corrections applied', len(corr)==88, len(corr))
chk('5 drops', (corr.Action=='drop').sum()==5, int((corr.Action=='drop').sum()))
chk('No exact content dup', final.Content.duplicated().sum()==0, int(final.Content.duplicated().sum()))
chk('5 same-title groups', manifest['same_title_groups']==5, manifest['same_title_groups'])
chk('Near duplicate pairs', manifest['near_duplicate_pairs']==17, manifest['near_duplicate_pairs'])
chk('Leakage groups intact', final.groupby('Leakage_Group').Split.nunique().max()==1, int(final.groupby('Leakage_Group').Split.nunique().max()))
chk('Split sums', final.Split.value_counts().sum()==len(final), final.Split.value_counts().to_dict())
chk('Split ratio ~70/15/15', abs(final.Split.value_counts(normalize=True).get('train',0)-0.70)<0.01, final.Split.value_counts(normalize=True).round(4).to_dict())
chk('Label sample 80', manifest['label_sample_n']==80, manifest['label_sample_n'])
chk('Label sample pre accuracy', manifest['label_sample_accuracy_pre_pct']==92.5, manifest['label_sample_accuracy_pre_pct'])
chk('Label sample reviewed 78/78', manifest['label_sample_correct_after_review']==78 and manifest['label_sample_reviewed_valid']==78, [manifest['label_sample_correct_after_review'], manifest['label_sample_reviewed_valid']])
chk('Date corrected 32', manifest['date_corrected']==32, manifest['date_corrected'])
chk('Date diff >24h', manifest['date_diff_over_24h']==313, manifest['date_diff_over_24h'])
chk('Content min 500', final.Content_Length.min()>=500, final.Content_Length.min())
chk('Content raw no delete', len(s4)==5915, len(s4))
chk('Input file exists', (ROOT/'data/step3/url_candidates.csv').exists(), '')
chk('Raw Step4 exists', (ROOT/'data/step4/articles.csv').exists(), '')
chk('No final training', not (ROOT/'models').exists(), '')

final_hash=hashlib.sha256((AUD/'news_dataset_reviewed.csv').read_bytes()).hexdigest()
report={
 'checks_total':len(checks),'checks_passed':sum(c['Pass'] for c in checks),
 'checks_failed':sum(not c['Pass'] for c in checks),
 'counts':{
  'step3_candidates':len(s3),'step4_success':len(s4),'step4_failed':len(f4),
  'step4_not_attempted':len(n4),'final_valid':len(final),
  'content_invalid':12,'label_drops':5,'corrections':len(corr),
  'by_label':final.groupby('Label').size().to_dict(),
  'by_source':final.groupby('Source').size().to_dict(),
  'by_label_source':pd.crosstab(final.Label,final.Source).to_dict(orient='index'),
  'split':final.Split.value_counts().to_dict(),
  'label_status':final.Label_Status.value_counts().to_dict(),
  'date_check':final.Date_Check.value_counts().to_dict(),
 },
 'final_csv_sha256':final_hash,
 'checks':checks,
}
(AUD/'consistency_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
pd.DataFrame(checks).to_csv(AUD/'consistency_checks.csv',index=False,encoding='utf-8-sig')
print(json.dumps({'checks_total':report['checks_total'],'passed':report['checks_passed'],'failed':report['checks_failed'],'final':len(final),'hash':final_hash[:16]},ensure_ascii=False,indent=2))
if report['checks_failed']:
    print(pd.DataFrame([c for c in checks if not c['Pass']]).to_string(index=False))
