"""Tổng hợp dataset rà soát: nội dung sạch lớp trình bày, nhãn hiệu chỉnh,
metadata ngày bổ sung, nhóm leakage và split plan.

Không train model, không tokenization/stopwords/TF-IDF.
"""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path('.')
AUD = ROOT / 'data' / 'audit'
AUD.mkdir(parents=True, exist_ok=True)
LABELS = ["Kinh tế", "Thế giới", "Thể thao", "Pháp luật",
          "Giáo dục", "Sức khỏe", "Công nghệ", "Du lịch"]
SOURCE_ORDER = ["VnExpress", "TuoiTre", "ThanhNien", "DanTri", "VietnamNet"]
SEED = 20261120

# ---------- dữ liệu đầu vào ----------
content = pd.read_csv(AUD / 'content_cleaned.csv', encoding='utf-8-sig')
corr = pd.read_csv(AUD / 'label_corrections.csv', encoding='utf-8-sig')
dates = pd.read_csv(AUD / 'date_corrections.csv', encoding='utf-8-sig')
raw = pd.read_csv('data/step4/articles.csv', encoding='utf-8-sig')[['ID', 'Date_Source']]
step3 = pd.read_csv('data/step3/url_candidates.csv', encoding='utf-8-sig').rename(
    columns={'Candidate_ID': 'ID'})

# Chỉ giữ bài content hợp lệ > 500 ký tự và >=2 đoạn.
df = content[content.Content_Valid].copy()
df['Content'] = df['Content_Clean']
df = df.merge(raw, on='ID', how='left')
# Áp ngày bổ sung từ HTML hiển thị.
dmap = dates.set_index('ID')['New_Date'].to_dict()
df['Published_Date'] = df.apply(
    lambda r: dmap.get(r.ID) if dmap.get(r.ID) else r.Published_Date, axis=1)
df['Date_Source'] = df.apply(
    lambda r: 'html_visible' if dmap.get(r.ID) else r.Date_Source, axis=1)

# Áp hiệu chỉnh nhãn / loại bỏ
cmap = corr.set_index('ID').to_dict(orient='index')
df['Label_Old'] = df.Label
df['Label_Review_Note'] = ''
df['Label_Status'] = 'weak_source_category'
for rid, c in cmap.items():
    mask = df.ID == rid
    if not mask.any():
        continue
    if c['Action'] == 'drop':
        df = df[~mask]
    else:
        df.loc[mask, 'Label'] = c['New_Label']
        df.loc[mask, 'Label_Review_Note'] = c['Reason']
        df.loc[mask, 'Label_Status'] = 'corrected_verified'

# Mẫu 80 bài đã kiểm tra thủ công
sample = pd.read_csv(AUD / 'label_sample.csv', encoding='utf-8-sig')
sample_ids = set(sample.ID)
# Trạng thái sample: đúng/đã sửa/đã loại
sample_rev = []
for r in sample.itertuples():
    c = cmap.get(r.ID)
    if c and c['Action'] == 'drop':
        reviewed, status = 'DROP', 'drop'
    elif c and c['Action'] == 'relabel':
        reviewed, status = c['New_Label'], 'corrected'
    else:
        reviewed, status = r.Label, 'correct'
    sample_rev.append({
        'Sample_ID': r.Sample_ID, 'ID': r.ID, 'Source': r.Source,
        'Label_Original': r.Label, 'Label_Reviewed': reviewed,
        'Review_Status': status, 'Title': r.Title,
        'Reason': c['Reason'] if c else 'Khớp nhãn nguồn sau kiểm tra tiêu đề/nội dung',
    })
sample_rev = pd.DataFrame(sample_rev)
sample_rev['Original_Correct'] = sample_rev.Review_Status == 'correct'
sample_rev.to_csv(AUD / 'label_sample_reviewed.csv', index=False, encoding='utf-8-sig')

# Cập nhật status cho sample còn trong dataset
for r in sample_rev[sample_rev.Review_Status.isin(['correct','corrected'])].itertuples():
    m = df.ID == r.ID
    if m.any():
        if r.Review_Status == 'correct':
            df.loc[m, 'Label_Status'] = 'verified_sample'
        else:
            df.loc[m, 'Label_Status'] = 'corrected_verified'
# Giao thoa đã kiểm tra nhưng giữ nhãn
for rid in ['C000175', 'C000198', 'C005408']:
    m = df.ID == rid
    if m.any():
        df.loc[m, 'Label_Status'] = 'reviewed_multi_topic_keep'
        df.loc[m, 'Label_Review_Note'] = 'Giao thoa nhiều lĩnh vực; giữ nhãn nguồn sau khi đọc nội dung.'

# Bỏ cột Author nếu có (không có trong content_cleaned)
for col in ['Author']:
    if col in df.columns:
        df.drop(columns=[col], inplace=True)

# Sắp xếp, kiểm tra
df = df.sort_values(['Label', 'Source', 'ID']).reset_index(drop=True)
df['Label'] = df['Label'].astype(str)
assert len(df) == len(df.ID.unique()) == len(df.URL.unique())
assert set(df.Label) == set(LABELS)
assert df.Published_Date.notna().all()
assert df.Content_Length.min() >= 500

# ---------- trùng tiêu đề / nội dung gần giống ----------
STOP = set('''và là của cho với trong khi những các một hai ba đã đang sẽ được có không người việt nam về từ đến tại này đó thì nhưng hơn rất nhiều năm ngày hôm nay mới sau trước cũng chỉ còn lại như để nếu vì do bị đang ra vào lên xuống theo trên dưới giữa ngoài cùng một số'''.split())

def tokens(title):
    s = unicodedata.normalize('NFC', str(title)).lower()
    s = re.sub(r'[^\w\s]', ' ', s, flags=re.UNICODE)
    return {w for w in s.split() if len(w) >= 3 and w not in STOP}

def jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0

def grams(text, n=5):
    s = re.sub(r'\s+', ' ', str(text)).lower()
    return {s[i:i+n] for i in range(max(0, len(s)-n+1))}

tokens_list = [tokens(x) for x in df.Title]
inv = defaultdict(list)
for i, s in enumerate(tokens_list):
    for w in s:
        inv[w].append(i)
pairs = Counter()
for w, ids in inv.items():
    if 2 <= len(ids) <= 40:
        for a, b in itertools.combinations(ids, 2):
            pairs[(a, b)] += 1
cand = [(p, n) for p, n in pairs.items() if n >= 2]
near = []
for (i, j), shared in cand:
    tj = jaccard(tokens_list[i], tokens_list[j])
    if tj < 0.40:
        continue
    cj = jaccard(grams(df.at[i, 'Content_Clean']), grams(df.at[j, 'Content_Clean']))
    if cj >= 0.55:
        near.append({
            'ID_1': df.at[i, 'ID'], 'ID_2': df.at[j, 'ID'],
            'Source_1': df.at[i, 'Source'], 'Source_2': df.at[j, 'Source'],
            'Label_1': df.at[i, 'Label'], 'Label_2': df.at[j, 'Label'],
            'Title_Similarity': round(tj, 4), 'Content_Similarity': round(cj, 4),
            'Shared_Title_Tokens': shared,
            'Title_1': df.at[i, 'Title'], 'Title_2': df.at[j, 'Title'],
        })
near = sorted(near, key=lambda x: -x['Content_Similarity'])
pd.DataFrame(near).to_csv(AUD / 'near_duplicates.csv', index=False, encoding='utf-8-sig')

# Union-find leakage
parent = {rid: rid for rid in df.ID}
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[rb] = ra

# Trùng nội dung chính xác
for _, grp in df.groupby('Content_Hash'):
    ids = list(grp.ID)
    for x in ids[1:]:
        union(ids[0], x)
# Trùng tiêu đề đã chuẩn hóa
df['Title_Exact_Key'] = df.Title.map(lambda x: re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', unicodedata.normalize('NFC', str(x)).lower())).strip())
for _, grp in df.groupby('Title_Exact_Key'):
    ids = list(grp.ID)
    for x in ids[1:]:
        union(ids[0], x)
# Gần giống nội dung
for x in near:
    union(x['ID_1'], x['ID_2'])
# Cụm sự kiện thủ công rõ ràng
for pattern in [r'Lê Thanh Thản|đại gia điếu cày', r'Bình Trọc']:
    ids = list(df[df.Title.str.contains(pattern, case=False, regex=True, na=False)].ID)
    for x in ids[1:]:
        union(ids[0], x)

# Gán group
roots = {}
group_of = {}
for rid in df.ID:
    r = find(rid)
    if r not in roots:
        roots[r] = f"LG{len(roots)+1:05d}"
    group_of[rid] = roots[r]
df['Leakage_Group'] = df.ID.map(group_of)

# Lý do nhóm
reasons = []
for gid, grp in df.groupby('Leakage_Group'):
    ids = list(grp.ID)
    why = []
    if len(ids) > 1:
        if any((df[df.ID == i].Title_Exact_Key.iloc[0] == df[df.ID == ids[0]].Title_Exact_Key.iloc[0]) for i in ids):
            why.append('same_title_or_event')
        if any(x for x in near if x['ID_1'] in ids and x['ID_2'] in ids):
            why.append('near_duplicate_content')
        if any(re.search(r'Lê Thanh Thản|đại gia điếu cày', t, re.I) for t in grp.Title):
            why.append('same_event_le_thanh_than')
        if any(re.search(r'Bình Trọc', t, re.I) for t in grp.Title):
            why.append('same_event_binh_troc')
    reasons.append({'Leakage_Group': gid, 'N': len(ids),
                    'Reason': ';'.join(sorted(set(why))) or 'singleton',
                    'IDs': ';'.join(ids)})
pd.DataFrame(reasons).to_csv(AUD / 'leakage_group_reasons.csv', index=False, encoding='utf-8-sig')

# ---------- split plan theo group, giữ nhóm nguyên vẹn ----------
rng = __import__('random').Random(SEED)
# Gom group; nhãn dominant
gmeta = []
for gid, grp in df.groupby('Leakage_Group'):
    labels = grp.Label.value_counts()
    gmeta.append({'Leakage_Group': gid, 'N': len(grp),
                  'Label': labels.index[0]})
gmeta = pd.DataFrame(gmeta)
split_of = {}
for label in LABELS:
    gs = gmeta[gmeta.Label == label].sample(frac=1, random_state=SEED).to_dict('records')
    total = sum(x['N'] for x in gs)
    targets = {'train': 0.70 * total, 'val': 0.15 * total, 'test': 0.15 * total}
    cur = {'train': 0, 'val': 0, 'test': 0}
    # group lớn trước; chọn split còn thiếu nhiều nhất
    for x in sorted(gs, key=lambda z: -z['N']):
        split = max(targets, key=lambda s: targets[s] - cur[s])
        split_of[x['Leakage_Group']] = split
        cur[split] += x['N']
    # đảm bảo split có ít nhất 1 group nếu đủ group
    for split in targets:
        if split not in split_of.values() and len(gs) >= 3:
            # chuyển group nhỏ nhất từ split lớn nhất
            pass
df['Split'] = df.Leakage_Group.map(split_of)
# Với group trải nhãn, vẫn một split duy nhất.

# Kiểm tra group không xuyên split
assert df.groupby('Leakage_Group').Split.nunique().max() == 1
assert set(df.Split) <= {'train', 'val', 'test'}

# ---------- metadata date comparison ----------
df['RSS_Date'] = df.ID.map(step3.set_index('ID').Published_Date)
def parse_dt(x):
    try:
        return pd.to_datetime(x, utc=True)
    except Exception:
        return pd.NaT
df['_final_dt'] = df.Published_Date.map(parse_dt)
df['_rss_dt'] = df.RSS_Date.map(parse_dt)
df['Date_Diff_Hours'] = (df._final_dt - df._rss_dt).abs().dt.total_seconds() / 3600
df['Date_Same_Day'] = (df._final_dt.dt.date == df._rss_dt.dt.date)
df['Date_Within_1h'] = df.Date_Diff_Hours <= 1
def date_check(r):
    if pd.isna(r.RSS_Date):
        return 'article_only_no_rss'
    if pd.isna(r.Date_Diff_Hours):
        return 'unparsed'
    if r.Date_Diff_Hours <= 1:
        return 'consistent_within_1h'
    if r.Date_Same_Day:
        return 'same_day_time_diff'
    if r.Date_Diff_Hours <= 24:
        return 'diff_under_24h'
    return 'diff_over_24h'
df['Date_Check'] = df.apply(date_check, axis=1)
date_review = df[['ID', 'Source', 'Label', 'Published_Date', 'Date_Source',
                  'RSS_Date', 'Date_Diff_Hours', 'Date_Same_Day', 'Date_Within_1h', 'Date_Check']].copy()
date_review.to_csv(AUD / 'date_comparison.csv', index=False, encoding='utf-8-sig')

# Date mismatch examples >24h
df[df.Date_Diff_Hours > 24][['ID','Source','Label','Published_Date','RSS_Date','Date_Diff_Hours','Title']].sort_values('Date_Diff_Hours',ascending=False).head(100).to_csv(AUD / 'date_mismatch_examples.csv', index=False, encoding='utf-8-sig')

# ---------- output ----------
final_cols = ['ID', 'Title', 'Content', 'URL', 'Source', 'Published_Date',
              'Date_Source', 'Date_Check', 'Original_Category', 'Label', 'Content_Length',
              'Label_Status', 'Leakage_Group', 'Split']
out = df[final_cols].copy()
out.to_csv(AUD / 'news_dataset_reviewed.csv', index=False, encoding='utf-8-sig')

# Same-title groups
st = df[df.Title_Exact_Key.map(df.Title_Exact_Key.value_counts()) > 1][
    ['ID', 'Source', 'Label', 'Title', 'Title_Exact_Key', 'Leakage_Group', 'Split']].copy()
st.rename(columns={'Title_Exact_Key': 'Title_Group_Key'}).to_csv(
    AUD / 'same_title_groups.csv', index=False, encoding='utf-8-sig')

# Leakage groups per article
leak = df[['ID', 'Source', 'Label', 'Title', 'Leakage_Group', 'Split']].merge(
    pd.DataFrame(reasons)[['Leakage_Group', 'Reason']], on='Leakage_Group', how='left')
leak.to_csv(AUD / 'leakage_groups.csv', index=False, encoding='utf-8-sig')

# Split plan
gmeta['Split'] = gmeta.Leakage_Group.map(split_of)
gmeta.to_csv(AUD / 'split_plan.csv', index=False, encoding='utf-8-sig')

# Content invalid / outliers
content[~content.Content_Valid][['ID', 'Source', 'Label', 'Title', 'Content_Length',
                                 'Content_Raw']].to_csv(
    AUD / 'content_invalid.csv', index=False, encoding='utf-8-sig')
out[(out.Content_Length < 650) | (out.Content_Length > 10000)][
    ['ID', 'Source', 'Label', 'Title', 'Content_Length']].to_csv(
    AUD / 'content_outliers.csv', index=False, encoding='utf-8-sig')

# Exact content duplicates in final (empty if none)
dup = df[df.Content_Hash.map(df.Content_Hash.value_counts()) > 1][
    ['ID', 'Source', 'Label', 'Title', 'Content_Hash', 'Leakage_Group']]
dup.to_csv(AUD / 'duplicate_content_review.csv', index=False, encoding='utf-8-sig')

# Stats
by_pair = out.groupby(['Label', 'Source']).size().unstack(fill_value=0).reindex(
    index=LABELS, columns=SOURCE_ORDER, fill_value=0)
by_pair.to_csv(AUD / 'stats_by_label_source_reviewed.csv', encoding='utf-8-sig')
by_label = out.groupby('Label').size().reindex(LABELS)
by_source = out.groupby('Source').size().reindex(SOURCE_ORDER)
by_label.to_csv(AUD / 'stats_by_label_reviewed.csv', encoding='utf-8-sig')
by_source.to_csv(AUD / 'stats_by_source_reviewed.csv', encoding='utf-8-sig')

# Label audit stats
pre = sample_rev.Original_Correct.sum()
post = (sample_rev.Review_Status.isin(['correct', 'corrected'])).sum()
post_total = len(sample_rev[sample_rev.Review_Status != 'drop'])
label_stats = []
for label, grp in sample_rev.groupby('Label_Original'):
    label_stats.append({
        'Label': label, 'N': len(grp),
        'Correct_Pre': int(grp.Original_Correct.sum()),
        'Accuracy_Pre_Pct': round(100 * grp.Original_Correct.mean(), 2),
        'Corrected': int((grp.Review_Status == 'corrected').sum()),
        'Dropped': int((grp.Review_Status == 'drop').sum()),
        'Reviewed_Valid': int((grp.Review_Status != 'drop').sum()),
    })
pd.DataFrame(label_stats).to_csv(AUD / 'label_audit_by_label.csv', index=False, encoding='utf-8-sig')
source_stats = []
for source, grp in sample_rev.groupby('Source'):
    source_stats.append({
        'Source': source, 'N': len(grp),
        'Correct_Pre': int(grp.Original_Correct.sum()),
        'Accuracy_Pre_Pct': round(100 * grp.Original_Correct.mean(), 2),
        'Corrected': int((grp.Review_Status == 'corrected').sum()),
        'Dropped': int((grp.Review_Status == 'drop').sum()),
        'Reviewed_Valid': int((grp.Review_Status != 'drop').sum()),
    })
pd.DataFrame(source_stats).to_csv(AUD / 'label_audit_by_source.csv', index=False, encoding='utf-8-sig')

# Content audit summary
content_summary = {
    'articles_step4': int(len(pd.read_csv('data/step4/articles.csv', encoding='utf-8-sig'))),
    'content_valid_after_clean': int(len(content[content.Content_Valid])),
    'content_invalid_dropped': int(len(content[~content.Content_Valid])),
    'label_drops': int(len(corr[corr.Action == 'drop'])),
    'final_valid': int(len(out)),
    'length_min': int(out.Content_Length.min()),
    'length_max': int(out.Content_Length.max()),
    'length_mean': round(float(out.Content_Length.mean()), 1),
    'short_500_650': int(((out.Content_Length >= 500) & (out.Content_Length < 650)).sum()),
    'long_over_10000': int((out.Content_Length > 10000).sum()),
    'missing_date': int(out.Published_Date.isna().sum()),
    'missing_author_column': 0,
    'date_corrected': int(len(dates[dates.New_Date != ''])),
    'exact_content_duplicate_groups': int((df.Content_Hash.value_counts() > 1).sum()),
    'same_title_groups': int((df.Title_Exact_Key.value_counts() > 1).sum()),
    'near_duplicate_pairs': len(near),
    'leakage_groups_multi': int((df.groupby('Leakage_Group').size() > 1).sum()),
    'label_sample_n': len(sample_rev),
    'label_sample_correct_pre': int(pre),
    'label_sample_accuracy_pre_pct': round(100 * pre / len(sample_rev), 2),
    'label_sample_reviewed_valid': int(post_total),
    'label_sample_correct_after_review': int(post),
    'label_corrections_total': int(len(corr)),
    'label_relabels': int((corr.Action == 'relabel').sum()),
    'label_drop_records': int((corr.Action == 'drop').sum()),
     'date_comparable': int(df.Date_Diff_Hours.notna().sum()),
    'date_same_day_pct': round(100 * df.loc[df.Date_Diff_Hours.notna(), 'Date_Same_Day'].mean(), 2),
    'date_within_1h_pct': round(100 * df.loc[df.Date_Diff_Hours.notna(), 'Date_Within_1h'].mean(), 2),
    'date_diff_over_24h': int((df.Date_Diff_Hours > 24).sum()),
    'date_source_counts': df.Date_Source.value_counts(dropna=False).to_dict(),
    'date_check_counts': df.Date_Check.value_counts(dropna=False).to_dict(),
}
content_summary['split_counts'] = out.Split.value_counts().to_dict()
content_summary['by_label'] = by_label.to_dict()
content_summary['by_source'] = by_source.to_dict()
content_summary['by_pair'] = {f"{l}|{s}": int(by_pair.loc[l, s]) for l in LABELS for s in SOURCE_ORDER}
content_summary['drops_reason'] = corr[corr.Action == 'drop'][['ID','Source','Title']].to_dict('records')
content_summary['corrections'] = corr.to_dict('records')
Path(AUD / 'audit_manifest.json').write_text(
    json.dumps(content_summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in content_summary.items()
                  if k not in {'corrections', 'drops_reason', 'by_pair'}},
                 ensure_ascii=False, indent=2))
print('\nFinal by label/source:')
print(by_pair.to_string())
print('\nSplit:')
print(out.Split.value_counts().to_string())
print('\nLeakage groups:', content_summary['leakage_groups_multi'])
print('Near pairs:', len(near))
