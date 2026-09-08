# -*- coding: utf-8 -*-
"""将 data.js / risk.js 拆分为按半月分块的紧凑格式文件 + data_index.js 清单

分块格式（V3）：
- data_<YYYY-MM{a,b}>.js: window.DP["key"]={"d":[日期...],"s":{"<modeIdx>":{"<roleIdx>":[mask,w,p,wy,py]}}}
  - modeIdx 对应 OCR_META.modes 下标；roleIdx 对应 OCR_META.rid[<modeIdx>][i]=[角色名,camp]
  - mask: 记录级 c 掩码字符串（'1'=有记录级c），w/p/wy/py 数组，缺失为 null，.0 压为整数
- risk_<YYYY-MM{a,b}>.js: window.RP["key"]=[[date,modeIdx,roleIdx,fieldIdx,prev,cur,delta,ruleIdx,severity],...]
  - roleIdx 同上，field 用 ['win','pick'] 下标，rule 用 ['single_day','trend_3d','zscore_7d'] 下标
- data_index.js: OCR_META(含 rid 角色索引) + DATA_FILES + RISK_FILES
"""
import json, collections, os

def load_js(path):
    with open(path, 'r', encoding='utf-8') as f:
        txt = f.read()
    s = txt.find('=')
    e = txt.rfind(';')
    return json.loads(txt[s + 1:e].strip())

def half_of(ymd):
    d = int(ymd[8:10])
    if d <= 7:
        return 'a'
    if d <= 14:
        return 'b'
    if d <= 21:
        return 'c'
    return 'd'

def num(v):
    """数字压缩：整数 float 转 int（JS 中 61===61.0），其余原样"""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v

def enc_mask(m):
    """掩码压缩：全1→'1'，全0→'0'，否则原样（多数记录是全1）"""
    s = set(m)
    if s == {'1'}:
        return '1'
    if s == {'0'}:
        return '0'
    return m

data = load_js('D:/DoubaoProject/监控网页/data.js')
risk = load_js('D:/DoubaoProject/监控网页/risk.js')
roles = load_js('D:/DoubaoProject/监控网页/roles.js')

modes = data['modes']
mode_index = {m: i for i, m in enumerate(modes)}

# 角色索引表：RID[modeIdx] = [[角色名, camp], ...]，顺序 = roles.js 全局顺序 ∩ 该模式有数据的角色
role_order = [r['id'] for r in roles]
rid = []
for mi, mode in enumerate(modes):
    mode_roles = data['series'].get(mode, {})
    arr = []
    for rid_name in role_order:
        if rid_name in mode_roles:
            arr.append([rid_name, mode_roles[rid_name].get('camp', '')])
    # 兜底：roles.js 未收录但数据中存在的角色（按数据插入顺序追加）
    for rname in mode_roles:
        if rname not in role_order:
            arr.append([rname, mode_roles[rname].get('camp', '')])
    rid.append(arr)

# 按半月分组日期
dp = collections.OrderedDict()
for date in data['dates']:
    key = date[:7] + half_of(date)
    dp.setdefault(key, collections.OrderedDict()).setdefault('dates', []).append(date)

# 填充 series（分块内 mode/role 用索引）
for mode, roles_map in data['series'].items():
    mi = mode_index[mode]
    rid_arr = rid[mi]
    rid_idx = {r[0]: i for i, r in enumerate(rid_arr)}
    for role, rinfo in roles_map.items():
        by_part = collections.defaultdict(list)
        for rec in rinfo['data']:
            key = rec['d'][:7] + half_of(rec['d'])
            by_part[key].append(rec)
        for key, recs in by_part.items():
            p = dp[key]
            p.setdefault('series', collections.OrderedDict()).setdefault(str(mi), collections.OrderedDict())
            dlist = p['dates']
            w, pk, wy, py = [], [], [], []
            cmask = []
            for d in dlist:
                rec = next((r for r in recs if r['d'] == d), None)
                w.append(num(rec['w']) if rec and rec.get('w') is not None else None)
                pk.append(num(rec['p']) if rec and rec.get('p') is not None else None)
                wy.append(num(rec['wy']) if rec and rec.get('wy') is not None else None)
                py.append(num(rec['py']) if rec and rec.get('py') is not None else None)
                cmask.append(1 if (rec is not None and rec.get('c') is not None) else 0)
            p['series'][str(mi)][str(rid_idx[role])] = [enc_mask(''.join(map(str, cmask))), w, pk, wy, py]

# risk part
RULE_INDEX = {'single_day': 0, 'trend_3d': 1, 'zscore_7d': 2}
rp = collections.defaultdict(list)
for a in risk['alerts']:
    mi = mode_index.get(a['mode'], 0)
    rid_arr = rid[mi]
    rid_idx = {r[0]: i for i, r in enumerate(rid_arr)}
    rp[a['date'][:7] + half_of(a['date'])].append([
        a['date'], mi, rid_idx.get(a['role'], 0),
        0 if a['field'] == 'win' else 1,
        a['prev'], a['cur'], a['delta'],
        RULE_INDEX.get(a['rule'], 0), a['severity']
    ])

outdir = 'D:/DoubaoProject/监控网页'
os.makedirs(outdir, exist_ok=True)

def dump(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

data_files = []
risk_files = []
sizes = []
for key in sorted(dp.keys()):
    fn = 'data_%s.js' % key
    part = {'d': dp[key]['dates'], 's': dp[key]['series']}
    content = 'window.DP=window.DP||{};window.DP["%s"]=%s;' % (key, json.dumps(part, ensure_ascii=False, separators=(',', ':')))
    dump(os.path.join(outdir, fn), content)
    data_files.append(fn)
    sizes.append((fn, os.path.getsize(os.path.join(outdir, fn))))

for key in sorted(rp.keys()):
    fn = 'risk_%s.js' % key
    content = 'window.RP=window.RP||{};window.RP["%s"]=%s;' % (key, json.dumps(rp[key], ensure_ascii=False, separators=(',', ':')))
    dump(os.path.join(outdir, fn), content)
    risk_files.append(fn)
    sizes.append((fn, os.path.getsize(os.path.join(outdir, fn))))

meta = {'generated': data.get('generated', ''), 'modes': modes,
        'rid': rid, 'dates': len(data['dates']), 'threshold': risk.get('threshold', 5),
        'f': ['win', 'pick'], 'k': ['single_day', 'trend_3d', 'zscore_7d']}
idx = 'window.OCR_META=%s;window.DATA_FILES=%s;window.RISK_FILES=%s;' % (
    json.dumps(meta, ensure_ascii=False, separators=(',', ':')),
    json.dumps(data_files), json.dumps(risk_files))
dump(os.path.join(outdir, 'data_index.js'), idx)

print('total parts:', len(sizes))
total = 0
for fn, sz in sizes:
    total += sz
    print('  %-20s %8d' % (fn, sz))
print('index size:', os.path.getsize(os.path.join(outdir, 'data_index.js')))
print('total bytes:', total)
print('max file size:', max(sz for _, sz in sizes))
