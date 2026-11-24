# -*- coding: utf-8 -*-
"""稳健性：把两组都限制在相近的学术跨度内再比一次，看差距会不会被
'对照组里混进年长/低活跃的人' 解释掉。结果追加到 comparison.json 的 _matched 键。"""
import csv, json, os, statistics as st

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")

sig = [r for r in csv.DictReader(open(os.path.join(OUT, "author_metrics.csv"), encoding="utf-8-sig"))
       if not r["flag"]]
ctr = [r for r in csv.DictReader(open(os.path.join(OUT, "control_metrics.csv"), encoding="utf-8-sig"))
       if not r["flag"]]
num = lambda r, k: float(r[k]) if str(r[k]).strip() not in ("", "None") else None

LO, HI = 15.0, 25.0
sub_sig = [r for r in sig if LO <= (num(r, "span_years") or 0) <= HI]
sub_ctr = [r for r in ctr if LO <= (num(r, "span_years") or 0) <= HI]
print(f"跨度 {LO:.0f}–{HI:.0f} 年：签署者 {len(sub_sig)} 人，对照 {len(sub_ctr)} 人")

res = {}
for k, label in [("topic_stability", "专注度 S"), ("recent5_per_year", "近五年篇/年"),
                 ("team_median", "团队规模中位"), ("cite_median", "单篇被引中位"),
                 ("n_uniq", "总篇数")]:
    a = [v for v in (num(r, k) for r in sub_sig) if v is not None]
    b = [v for v in (num(r, k) for r in sub_ctr) if v is not None]
    res[k] = {"label": label, "signatory_median": round(st.median(a), 3),
              "control_median": round(st.median(b), 3),
              "diff": round(st.median(a) - st.median(b), 3),
              "n_signatory": len(a), "n_control": len(b)}
    print(f"  {label:<12} {res[k]['signatory_median']:>7.3f} vs {res[k]['control_median']:>7.3f} "
          f"= {res[k]['diff']:+.3f}")

# 学术跨度本身的分布，用来说明匹配前的差距
print(f"\n跨度中位：签署者 {st.median([num(r,'span_years') for r in sig]):.1f} 年，"
      f"对照 {st.median([num(r,'span_years') for r in ctr]):.1f} 年")

p = os.path.join(OUT, "comparison.json")
c = json.load(open(p, encoding="utf-8"))
c["_matched"] = {"window": [LO, HI], "n_signatory": len(sub_sig), "n_control": len(sub_ctr), **res}
json.dump(c, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("→ comparison.json 已追加 _matched")
