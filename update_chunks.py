# -*- coding: utf-8 -*-
"""
把 data_*.js / risk_*.js 分块以静态 <script> 标签形式嵌入 index.html，
替代不可靠的 document.write 动态注入。
用法：python update_chunks.py
- 自动扫描同目录所有 data_*.js / risk_*.js（排除 data_index.js）
- 重写 index.html 中 <!-- DATA_CHUNKS --> ... <!-- /DATA_CHUNKS --> 区间
- 同时更新 data_index.js 中的 DATA_FILES / RISK_FILES 数组
"""
import os
import re
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, 'index.html')
DATA_INDEX = os.path.join(BASE, 'data_index.js')


def collect():
    datas = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(BASE, 'data_*.js'))
        if not os.path.basename(p).startswith('data_index')
    )
    risks = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(BASE, 'risk_*.js'))
    )
    return datas, risks


def patch_index(datas, risks):
    with open(INDEX, 'r', encoding='utf-8') as f:
        html = f.read()
    tags = '\n'.join(
        ['    <script src="%s"></script>' % f for f in datas + risks]
    )
    block = '<!-- DATA_CHUNKS -->\n%s\n    <!-- /DATA_CHUNKS -->' % tags
    pattern = re.compile(
        r'<!-- DATA_CHUNKS -->.*?<!-- /DATA_CHUNKS -->', re.S)
    if pattern.search(html):
        html = pattern.sub(lambda m: block, html)
    else:
        # 不存在则插到 data_index.js 之后
        anchor = '<script src="data_index.js"></script>'
        assert anchor in html, 'index.html 缺少 data_index.js 锚点'
        html = html.replace(anchor, anchor + '\n' + block)
    with open(INDEX, 'w', encoding='utf-8') as f:
        f.write(html)
    print('index.html 分块标签: %d + %d' % (len(datas), len(risks)))


def patch_data_index(datas, risks):
    with open(DATA_INDEX, 'r', encoding='utf-8') as f:
        js = f.read()
    js = re.sub(
        r'window\.DATA_FILES=\[[^\]]*\]',
        'window.DATA_FILES=' + repr(datas).replace("'", '"'),
        js, count=1)
    js = re.sub(
        r'window\.RISK_FILES=\[[^\]]*\]',
        'window.RISK_FILES=' + repr(risks).replace("'", '"'),
        js, count=1)
    with open(DATA_INDEX, 'w', encoding='utf-8') as f:
        f.write(js)
    print('data_index.js 已同步 %d + %d' % (len(datas), len(risks)))


if __name__ == '__main__':
    d, r = collect()
    assert d, '未找到 data_*.js 分块'
    patch_index(d, r)
    patch_data_index(d, r)
    print('完成')
