# -*- coding: utf-8 -*-
"""Lab5 指标 v2：先去重、再标污染、再算"慢"的五维画像。

相对 v1 的改动：
1. 同一作者内按归一化标题去重（预印本/会议版重复），保留最早日期。
2. 标出疑似身份合并的作者（年均 >40 篇 或 总量 >1500），不删，只标记。
3. 空窗改成"年粒度"：活跃区间内连续无产出的最长年数——比"篇间隔"抗预印本噪声。
4. 增加产量变异系数 CV（匀速/爆发）。
5. 输出 tidy 表 + summary.json 供画图和写报告。
"""
import json, glob, os, re, statistics as st
from datetime import date
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
WORKS = os.path.join(BASE, "works")
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)
SNAP = date(2026, 11, 11)


def parse_date(w):
    d = w.get("date")
    if d:
        try:
            y, m, dd = (int(x) for x in d.split("-"))
            return date(y, m, dd)
        except Exception:
            pass
    y = w.get("year")
    return date(y, 7, 1) if isinstance(y, int) else None


def norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def jaccard(a, b):
    if not a or not b:
        return None
    A, B = set(a), set(b)
    return len(A & B) / len(A | B)


rows, per_year_all = [], defaultdict(int)
for f in sorted(glob.glob(os.path.join(WORKS, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    name, oa = d.get("name"), d.get("oa_id")
    raw = []
    for w in d.get("works") or []:
        dt = parse_date(w)
        if dt is None:
            continue
        raw.append({
            "dt": dt,
            "title": norm_title(w.get("title")),
            "topics": [t for t in (w.get("topics") or []) if isinstance(t, str)],
            "coauthors": [c for c in (w.get("coauthors") or []) if isinstance(c, str)],
            "cited": int(w.get("cited") or 0),
        })
    if not raw:
        rows.append({"name": name, "oa_id": oa, "n_raw": 0, "n_uniq": 0, "flagged_merge": 1})
        continue

    # 标题去重（保留最早出现的版本）
    by_title = {}
    for r in sorted(raw, key=lambda r: r["dt"]):
        key = r["title"] or f"__notitle_{r['dt']}"
        if key not in by_title:
            by_title[key] = r
    recs = sorted(by_title.values(), key=lambda r: r["dt"])
    # 匿名标题（无标题条目）单独计，避免被并成一条
    notitle = sum(1 for r in raw if not r["title"])
    n_raw, n = len(raw), len(recs)

    first, last = recs[0]["dt"], recs[-1]["dt"]
    span = (last - first).days / 365.25
    yrs = sorted({r["dt"].year for r in recs})
    ycount = Counter(r["dt"].year for r in recs)
    year_ns = [ycount[y] for y in yrs]

    # 最长空窗（年粒度，活跃区间内）
    max_gap = 0
    if len(yrs) > 1:
        for y1, y2 in zip(yrs, yrs[1:]):
            max_gap = max(max_gap, y2 - y1 - 1)

    pace = round(n / span, 2) if span > 0.5 else None
    recent = sum(1 for r in recs if (SNAP - r["dt"]).days <= 1826)
    early = sum(1 for r in recs if (SNAP - r["dt"]).days > 1826)
    rec5_rate = round(recent / 5.0, 2)
    early_rate = round(early / max(span - 5.0, 1.0), 2) if span > 6 else None

    # 产量波动（只在活跃年上算 CV）
    cv = round(st.pstdev(year_ns) / st.mean(year_ns), 3) if len(year_ns) >= 3 else None

    # 主题稳定性
    by_year_topics = defaultdict(list)
    for r in recs:
        by_year_topics[r["dt"].year].extend(r["topics"])
    sims = []
    for y1, y2 in zip(yrs, yrs[1:]):
        if y2 - y1 > 4:
            continue
        top1 = [t for t, _ in Counter(by_year_topics[y1]).most_common(3)]
        top2 = [t for t, _ in Counter(by_year_topics[y2]).most_common(3)]
        s = jaccard(top1, top2)
        if s is not None:
            sims.append(s)
    topic_stab = round(st.mean(sims), 3) if sims else None
    # 主题集中度：全部 topic 的归一化熵（0=只做一件事）
    all_topics = Counter(t for y in by_year_topics.values() for t in y)
    tot = sum(all_topics.values())
    if tot > 0 and len(all_topics) > 1:
        import math
        ent = -sum((c / tot) * math.log(c / tot) for c in all_topics.values())
        topic_conc = round(1 - ent / math.log(len(all_topics)), 3)
    else:
        topic_conc = None

    team = [max(len(r["coauthors"]), 1) for r in recs]
    team_med = round(st.median(team), 1)
    solo = round(sum(1 for t in team if t <= 1) / n, 3)
    cite_med = round(st.median([r["cited"] for r in recs]), 1)

    flagged = 1 if (n > 1500 or (pace or 0) > 40) else 0
    rows.append({
        "name": name, "oa_id": oa,
        "n_raw": n_raw, "n_uniq": n, "n_dup_removed": n_raw - n, "n_notitle": notitle,
        "first_year": first.year, "last_year": last.year, "span_years": round(span, 1),
        "active_years": len(yrs),
        "pace_per_year": pace, "recent5_per_year": rec5_rate,
        "early_per_year": early_rate,
        "max_gap_years": max_gap, "cv_yearly": cv,
        "topic_stability": topic_stab, "topic_conc": topic_conc,
        "team_median": team_med, "solo_share": solo,
        "cite_median": cite_med, "cite_total": sum(r["cited"] for r in recs),
        "flagged_merge": flagged,
    })
    for y in yrs:
        per_year_all[y] += ycount[y]

cols = ["name", "oa_id", "n_raw", "n_uniq", "n_dup_removed", "n_notitle",
        "first_year", "last_year", "span_years", "active_years",
        "pace_per_year", "recent5_per_year", "early_per_year",
        "max_gap_years", "cv_yearly", "topic_stability", "topic_conc",
        "team_median", "solo_share", "cite_median", "cite_total", "flagged_merge"]

with open(os.path.join(OUT, "author_metrics_v2.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    fh.write(",".join(cols) + "\n")
    for r in rows:
        fh.write(",".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")

clean = [r for r in rows if r.get("n_uniq", 0) > 0 and not r.get("flagged_merge")]
print(f"作者 {len(rows)}  清洗后 {len(clean)}  剔除/标记 {len(rows)-len(clean)}")
print(f"去重前作品 {sum(r.get('n_raw',0) for r in rows)}  去重后 {sum(r.get('n_uniq',0) for r in rows)}")
print(f"清洗后作品 {sum(r['n_uniq'] for r in clean)}")


def q(key, data=clean):
    v = sorted(r[key] for r in data if r.get(key) is not None)
    if not v:
        return None
    pct = lambda p: v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]
    return {"n": len(v), "min": round(v[0], 2), "p25": round(pct(.25), 2),
            "median": round(st.median(v), 2), "p75": round(pct(.75), 2),
            "p90": round(pct(.90), 2), "max": round(v[-1], 2)}


summary = {}
for k in ["n_uniq", "pace_per_year", "recent5_per_year", "max_gap_years",
          "cv_yearly", "topic_stability", "topic_conc", "team_median",
          "solo_share", "cite_median", "span_years"]:
    summary[k] = q(k)
    print(k, summary[k])

summary["_meta"] = {
    "authors_total": len(rows), "authors_clean": len(clean),
    "flagged": [r["name"] for r in rows if r.get("flagged_merge")],
    "works_raw": sum(r.get("n_raw", 0) for r in rows),
    "works_uniq": sum(r.get("n_uniq", 0) for r in rows),
    "snapshot": SNAP.isoformat(),
}
summary["_per_year"] = dict(sorted(per_year_all.items()))
json.dump(summary, open(os.path.join(OUT, "summary_v2.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("flagged:", summary["_meta"]["flagged"])
