#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取《学生"慢"科研联合声明》签署名单。

来源：https://gaplab.cuhk.edu.cn/slow_research/
若原页不可达，可用课程仓库的备份说明：
https://github.com/DaSE-ML/Course-2026Fall/blob/main/assignments/resources/README.md

输出：data/signatories_raw.json  —  [{"name_en":..., "name_zh":..., "affiliation":..., "role":...}]

依赖：仅标准库。
用法：python fetch_roster.py [--out ../data/signatories_raw.json]
"""
import argparse, json, os, re, sys, urllib.request

URL = "https://gaplab.cuhk.edu.cn/slow_research/"
UA = "Mozilla/5.0 (compatible; lab05-slow-science/1.0; +course assignment)"


def fetch(url=URL, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as f:
        raw = f.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def parse(html):
    """表格行 → 记录。签署页的名单在 <table> 或 <li> 里，两种都试。"""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [strip_tags(td) for td in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and not re.match(r"^(no\.?|序|#)$", cells[0], re.I):
            rows.append(cells)
    if not rows:
        for li in re.findall(r"<li[^>]*>(.*?)</li>", html, re.S | re.I):
            t = strip_tags(li)
            if t and len(t) < 120:
                rows.append([t])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "signatories_raw.json"))
    a = ap.parse_args()

    html = fetch(a.url)
    rows = parse(html)
    print(f"抓到 {len(rows)} 行原始记录", file=sys.stderr)
    if not rows:
        sys.exit("解析为空——页面结构可能已改，或原页不可达。请用课程仓库的备份快照。")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"写入 {a.out}", file=sys.stderr)
    print("注意：下一步需要人工/规则做 OpenAlex 作者消歧（见 data/author_ids.csv 与本目录说明）。", file=sys.stderr)


if __name__ == "__main__":
    main()
