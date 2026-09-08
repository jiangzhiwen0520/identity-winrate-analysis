# -*- coding: utf-8 -*-
"""
监控网页数据预处理：
- output/ 722 JSON -> 时序聚合 data.js (window.OCR_DATA)
- mutation.json + 连续趋势/异常规则 -> risk.js (window.RISK_DATA)
- role_dict.json -> roles.js (window.ROLES)
"""
import json, os, glob
from collections import defaultdict

BASE = r"D:\DoubaoProject\ocr_work"
OUT = os.path.join(BASE, "output")
WEB = r"D:\DoubaoProject\监控网页"

# ---------- 1. 时序聚合 ----------
series = defaultdict(lambda: defaultdict(dict))  # mode -> role -> {date: {...}}
modes_set = set()
dates_set = set()

for p in glob.glob(os.path.join(OUT, "**", "*.json"), recursive=True):
    d = json.load(open(p, encoding="utf-8"))
    mode = d["mode"]
    dt = d["data_date"]
    modes_set.add(mode)
    dates_set.add(dt)
    for r in d["rows"]:
        rid = r.get("role_id")
        if not rid:
            continue
        w, pk = r.get("win_rate"), r.get("pick_rate")
        if w is None and pk is None:
            continue
        wy, py = r.get("win_rate_yoy"), r.get("pick_rate_yoy")
        camp = r.get("camp")
        rec = {"d": dt}
        if w is not None: rec["w"] = round(float(w), 1)
        if pk is not None: rec["p"] = round(float(pk), 1)
        if wy is not None: rec["wy"] = round(float(wy), 1)
        if py is not None: rec["py"] = round(float(py), 1)
        if camp: rec["c"] = camp
        series[mode][rid][dt] = rec

dates = sorted(dates_set)
modes = sorted(modes_set, key=lambda x: ["特别行动单人排位", "诸神排位", "巅峰赛"].index(x) if x in ["特别行动单人排位", "诸神排位", "巅峰赛"] else 99)

# 转 compact：series[mode][role] = {"camp":..., "data": [rec...]}（日期升序）
out_series = {}
for mode in modes:
    out_series[mode] = {}
    for role, by_date in series[mode].items():
        recs = [by_date[k] for k in sorted(by_date.keys())]
        camp = None
        for rr in recs:
            if "c" in rr:
                camp = rr.pop("c")
                break
        out_series[mode][role] = {"camp": camp, "data": recs}

data = {"generated": "2026-09-08", "modes": modes, "dates": dates, "series": out_series}
with open(os.path.join(WEB, "data.js"), "w", encoding="utf-8") as f:
    f.write("window.OCR_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
sz = os.path.getsize(os.path.join(WEB, "data.js"))
print(f"data.js {sz/1024/1024:.1f} MB | modes={modes} | dates={len(dates)} | 序列数={sum(len(v) for v in out_series.values())}")

# ---------- 2. 风险数据 ----------
mutation = json.load(open(os.path.join(BASE, "mutation.json"), encoding="utf-8"))
if isinstance(mutation, dict):
    mutation = mutation.get("mutations", mutation)

alerts = []
for m in mutation:
    fld = "win" if m.get("reason") in ("win", "-win") else "pick" if m.get("reason") in ("pick", "-pick", "+pick") else "win"
    alerts.append({
        "date": m.get("date"), "mode": m.get("mode"), "role": m.get("role"),
        "field": fld, "prev": m.get("win_prev") if fld == "win" else m.get("pick_prev"),
        "cur": m.get("win") if fld == "win" else m.get("pick"),
        "delta": round(float(m.get("win_delta") or m.get("pick_delta") or 0), 1),
        "rule": "single_day", "severity": 2 if abs(float(m.get("win_delta") or m.get("pick_delta") or 0)) >= 10 else 1
    })

# 连续 3 日同向（胜率累计 >5pp）
for mode, roles in out_series.items():
    for role, s in roles.items():
        recs = s["data"]
        for i in range(2, len(recs)):
            w = [recs[j].get("w") for j in range(i - 2, i + 1)]
            if None in w:
                continue
            d1, d2, d3 = w[1] - w[0], w[2] - w[1], w[0] and w[1] and w[2]
            if (d1 > 0 and d2 > 0 and (d1 + d2) >= 5) or (d1 < 0 and d2 < 0 and abs(d1 + d2) >= 5):
                alerts.append({
                    "date": recs[i]["d"], "mode": mode, "role": role, "field": "win",
                    "prev": recs[i - 2]["w"], "cur": recs[i]["w"],
                    "delta": round(recs[i]["w"] - recs[i - 2]["w"], 1),
                    "rule": "trend_3d", "severity": 2 if abs(recs[i]["w"] - recs[i - 2]["w"]) >= 10 else 1
                })

# 7 日异常（近7日均值 vs 前28日，|z|>2.5 且 |均值差|>3pp）
for mode, roles in out_series.items():
    for role, s in roles.items():
        recs = s["data"]
        ws = [(r["d"], r["w"]) for r in recs if "w" in r]
        for i in range(7, len(ws)):
            cur7 = [v for _, v in ws[i - 6:i + 1]]
            prev28 = [v for _, v in ws[max(0, i - 33):i - 6]]
            if len(prev28) < 10:
                continue
            mu = sum(prev28) / len(prev28)
            sd = (sum((v - mu) ** 2 for v in prev28) / len(prev28)) ** 0.5
            m7 = sum(cur7) / len(cur7)
            if sd == 0:
                continue
            z = (m7 - mu) / sd
            if abs(z) > 2.5 and abs(m7 - mu) > 3:
                alerts.append({
                    "date": ws[i][0], "mode": mode, "role": role, "field": "win",
                    "prev": round(mu, 1), "cur": round(m7, 1),
                    "delta": round(m7 - mu, 1), "rule": "zscore_7d", "severity": 3 if abs(z) > 4 else 2
                })

# 去重（同日同角色同字段多条规则取 severity 最高）
keyed = {}
for a in alerts:
    k = (a["date"], a["mode"], a["role"], a["field"])
    if k not in keyed or a["severity"] > keyed[k]["severity"]:
        keyed[k] = a
alerts = sorted(keyed.values(), key=lambda x: (x["date"], -x["severity"], -abs(x["delta"])))

risk = {"threshold": 5, "rules": ["single_day: 单日突变>5pp", "trend_3d: 连续3日同向累计>5pp", "zscore_7d: 7日均值偏离前28日|z|>2.5"], "alerts": alerts}
with open(os.path.join(WEB, "risk.js"), "w", encoding="utf-8") as f:
    f.write("window.RISK_DATA = " + json.dumps(risk, ensure_ascii=False, separators=(",", ":")) + ";\n")
print(f"risk.js 预警 {len(alerts)} 条")

# ---------- 3. 身份词典 ----------
rd = json.load(open(os.path.join(BASE, "role_dict.json"), encoding="utf-8"))
roles = []
for r in rd["roles"]:
    roles.append({
        "id": r.get("canonical_name"), "camp": r.get("camp"),
        "modes": r.get("modes") or [], "active_from": r.get("active_from"),
        "aliases": r.get("aliases") or []
    })
with open(os.path.join(WEB, "roles.js"), "w", encoding="utf-8") as f:
    f.write("window.ROLES = " + json.dumps(roles, ensure_ascii=False, separators=(",", ":")) + ";\n")
print(f"roles.js {len(roles)} 身份")
print("完成")
