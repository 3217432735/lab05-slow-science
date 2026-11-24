# -*- coding: utf-8 -*-
"""构建对照组：同主题、篇数同区间的非签署者。

步骤
 1. 从签署者作品里统计高频主题（top_topics.json，已生成）
 2. 主题名 → OpenAlex topic id
 3. 每个主题按 works_count 区间抽 12 位作者（sample 随机）
 4. 排除签署者本人 / 重名，得到 control_roster.csv
"""
import json, os, urllib.parse, urllib.request
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(BASE, "key.txt")).read().strip()
UA = {"User-Agent": "lab05-control/1.0"}


def get(path, **params):
    params["api_key"] = KEY
    url = "https://api.openalex.org" + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as f:
        return json.loads(f.read().decode())


top = json.load(open(os.path.join(BASE, "top_topics.json"), encoding="utf-8"))
roster = json.load(open(os.path.join(BASE, "final_roster.json"), encoding="utf-8"))
sig_ids = {r["oa_id"] for r in roster if r.get("oa_id")}
sig_names = {(r.get("name") or "").strip().lower() for r in roster}

# 1) 主题名 → id
tid = {}
for name, cnt in top:
    d = get("/topics", search=name, **{"per-page": "5"})
    for t in d["results"]:
        if t["display_name"].strip().lower() == name.strip().lower():
            tid[name] = t["id"].split("/")[-1]
            break
print(f"解析到 {len(tid)}/{len(top)} 个主题 id")

# 2) 每主题抽样
WMIN, WMAX, PER = 80, 700, 12       # 与签署者篇数中位 154 / 四分位 98–257 同量级
picked, seen_topic = {}, Counter()
for name, cnt in top:
    t = tid.get(name)
    if not t:
        continue
    try:
        d = get("/authors", filter=f"topics.id:{t},works_count:{WMIN}-{WMAX}",
                **{"per-page": str(PER), "sample": str(PER)})
    except Exception as e:
        print("  抽样失败", name, e)
        continue
    for a in d.get("results") or []:
        aid = a["id"].split("/")[-1]
        if aid in sig_ids or aid in picked:
            continue
        if (a.get("display_name") or "").strip().lower() in sig_names:
            continue
        if (a.get("works_count") or 0) < WMIN:
            continue
        picked[aid] = {"oa_id": aid, "name": a.get("display_name", ""),
                       "works_count": a.get("works_count"),
                       "matched_topic": name}
        seen_topic[name] += 1

print(f"对照组候选 {len(picked)} 人（共 {sum(seen_topic.values())} 次命中）")
out = os.path.join(BASE, "control_roster.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as fh:
    fh.write("name,oa_id,works_count,matched_topic\n")
    for v in sorted(picked.values(), key=lambda x: x["name"]):
        fh.write(f"{v['name']},{v['oa_id']},{v['works_count']},{v['matched_topic']}\n")
print("→", out)
