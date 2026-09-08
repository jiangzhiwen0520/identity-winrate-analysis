// 验证：分块合并结果 vs 原始 data.js / risk.js 一致性
const fs = require('fs');
const path = 'D:/DoubaoProject/监控网页/';

// 模拟 window
global.window = {};
function loadScript(fn) {
  const code = fs.readFileSync(path + fn, 'utf-8');
  eval(code); // 在全局执行，设置 window.DP / window.RP / window.DATA_FILES 等
}
function loadRaw(fn) {
  const code = fs.readFileSync(path + fn, 'utf-8');
  const s = code.indexOf('='), e = code.lastIndexOf(';');
  return JSON.parse(code.substring(s + 1, e).trim());
}

// 1. 加载清单与分块
loadScript('data_index.js');
for (const f of window.DATA_FILES) loadScript(f);
for (const f of window.RISK_FILES) loadScript(f);

// 2. 复制 index.html 的合并逻辑（V3：mode/role 数字索引 + rid 角色表）
let _dates = [], _series = {};
Object.keys(window.DP).sort().forEach(function (key) {
  const p = window.DP[key];
  _dates = _dates.concat(p.d);
  Object.keys(p.s).forEach(function (modeIdx) {
    const mi = parseInt(modeIdx, 10);
    const ridArr = window.OCR_META.rid[mi];
    _series[window.OCR_META.modes[mi]] = _series[window.OCR_META.modes[mi]] || {};
    Object.keys(p.s[modeIdx]).forEach(function (roleIdx) {
      const info = p.s[modeIdx][roleIdx];
      const roleName = ridArr[parseInt(roleIdx, 10)][0];
      const camp = ridArr[parseInt(roleIdx, 10)][1];
      const ent = _series[window.OCR_META.modes[mi]][roleName] || (_series[window.OCR_META.modes[mi]][roleName] = { camp: camp, data: [] });
      const mask = info[0];
      const maskStr = (mask === '1' || mask === '0') ? null : mask;
      for (let k = 0; k < p.d.length; k++) {
        if (info[1][k] != null || info[2][k] != null) {
          const rec = { d: p.d[k] };
          if (info[1][k] != null) rec.w = info[1][k];
          if (info[2][k] != null) rec.p = info[2][k];
          if (info[3][k] != null) rec.wy = info[3][k];
          if (info[4][k] != null) rec.py = info[4][k];
          const hasC = (mask === '1') || (maskStr && maskStr.charAt(k) === '1');
          if (hasC) rec.c = camp;
          ent.data.push(rec);
        }
      }
    });
  });
});
const D = { generated: window.OCR_META.generated, modes: window.OCR_META.modes, dates: _dates, series: _series };
const M = window.OCR_META, _alerts = [];
Object.keys(window.RP).sort().forEach(function (key) {
  window.RP[key].forEach(function (rec) {
    const mi = parseInt(rec[1], 10);
    _alerts.push({ date: rec[0], mode: M.modes[mi], role: M.rid[mi][parseInt(rec[2], 10)][0], field: M.f[rec[3]], prev: rec[4], cur: rec[5], delta: rec[6], rule: M.k[rec[7]], severity: rec[8] });
  });
});
const R = { threshold: M.threshold, rules: [], alerts: _alerts };

// 3. 加载原始文件对比
const O = loadRaw('data.js');
const OR = loadRaw('risk.js');

let errors = 0;
function check(cond, msg) {
  if (!cond) { errors++; console.log('FAIL:', msg); }
}

// dates 对比
check(D.dates.length === O.dates.length, `dates len ${D.dates.length} vs ${O.dates.length}`);
check(JSON.stringify(D.dates) === JSON.stringify(O.dates), 'dates content mismatch');
console.log('dates OK:', D.dates.length);

// series 对比：模式数、身份数、每身份记录数、抽查记录
const ms = new Set(Object.keys(O.series));
for (const mode of Object.keys(D.series)) {
  check(ms.has(mode), `extra mode ${mode}`);
  const s1 = D.series[mode], s2 = O.series[mode];
  check(Object.keys(s1).length === Object.keys(s2).length, `mode ${mode} role count ${Object.keys(s1).length} vs ${Object.keys(s2).length}`);
  for (const role of Object.keys(s2)) {
    if (!s1[role]) { errors++; console.log('FAIL: missing role', mode, role); continue; }
    const a = s1[role].data, b = s2[role].data;
    check(a.length === b.length, `mode ${mode} role ${role} rec ${a.length} vs ${b.length}`);
    check(s1[role].camp === s2[role].camp, `camp mismatch ${mode}/${role}: ${s1[role].camp} vs ${s2[role].camp}`);
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      const rec_a = a[i], rec_b = b[i];
      // 语义等价：字段缺失与 null 视为相同；整数与同值浮点视为相同
      const eq = (x, y) => (x == null && y == null) || x === y || (typeof x === 'number' && typeof y === 'number' && x === y);
      const ok = eq(rec_a.d, rec_b.d) && eq(rec_a.w, rec_b.w) && eq(rec_a.p, rec_b.p) &&
                 eq(rec_a.wy, rec_b.wy) && eq(rec_a.py, rec_b.py) && eq(rec_a.c, rec_b.c);
      if (!ok) {
        errors++;
        console.log('FAIL rec:', mode, role, i, JSON.stringify(rec_a), JSON.stringify(rec_b));
        break;
      }
    }
  }
}

// risk 对比
check(R.alerts.length === OR.alerts.length, `risk alerts ${R.alerts.length} vs ${OR.alerts.length}`);
for (let i = 0; i < Math.min(R.alerts.length, OR.alerts.length); i++) {
  const a = R.alerts[i], b = OR.alerts[i];
  const ok = a.date === b.date && a.mode === b.mode && a.role === b.role && a.field === b.field &&
    a.prev === b.prev && a.cur === b.cur && a.delta === b.delta && a.rule === b.rule && a.severity === b.severity;
  if (!ok) { errors++; console.log('FAIL risk rec:', i, a, b); break; }
}

console.log(errors === 0 ? 'ALL CONSISTENT ✓' : ('ERRORS: ' + errors));
