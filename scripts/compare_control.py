# -*- coding: utf-8 -*-
"""对照组 vs 签署者：同一套指标、同一套清洗，比较分布。

产出
  output/control_metrics.csv    对照组逐人指标
  output/comparison.json        两组中位数、Mann-Whitney U、bootstrap CI
  output/fig6_control.png       两组 ECDF（专注度 / 速度）
"""
import csv, importlib.util, json, math, os, random, statistics as st
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("an", os.path.join(BASE, "code", "analyze.py"))
an = importlib.util.module_from_spec(spec)
spec.loader.exec_module(an)

OUT = os.path.join(BASE, "output")


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _erf(x):
    t = 1 / (1 + 0.3275911 * abs(x))
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
             + 0.254829592) * t * math.exp(-x * x)
    return y if x >= 0 else -y


def mannwhitney(a, b):
    n1, n2 = len(a), len(b)
    allv = list(a) + list(b)
    r = ranks(allv)
    U = sum(r[:n1]) - n1 * (n1 + 1) / 2
    cnt = Counter(allv)
    tie = sum(t ** 3 - t for t in cnt.values() if t > 1)
    n = n1 + n2
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return U, 0.0, 1.0
    z = (U - n1 * n2 / 2) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + _erf(abs(z) / math.sqrt(2))))
    return U, z, max(p, 0.0)


def boot_ci(a, b, n=4000, seed=20261117):
    rnd = random.Random(seed)
    d = []
    for _ in range(n):
        d.append(st.median([rnd.choice(a) for _ in a]) - st.median([rnd.choice(b) for _ in b]))
    d.sort()
    return round(d[int(0.025 * n)], 3), round(d[int(0.975 * n) - 1], 3)


ctrl_dir = os.path.join(BASE, "control_works")
ctrl_raw = [json.load(open(os.path.join(ctrl_dir, f), encoding="utf-8"))
            for f in sorted(os.listdir(ctrl_dir)) if f.endswith(".json")]
crows_all, _ = an.build(ctrl_raw)
dropped = [(r["name"], r["flag"]) for r in crows_all if r["flag"]]
crows = [r for r in crows_all if not r["flag"]]
print(f"对照组：抓取 {len(ctrl_raw)} 人，可用 {len(crows)} 人，标记剔除 {len(dropped)} 人")
for n, f in dropped[:10]:
    print(f"   剔除 {n}（{f}）")

cols = ["name", "oa_id", "n_uniq", "first_year", "last_year", "span_years", "active_years",
        "pace_per_year", "recent5_per_year", "max_gap_years", "cv_yearly", "topic_stability",
        "topic_conc", "team_median", "solo_share", "cite_median", "cite_total", "flag"]
with open(os.path.join(OUT, "control_metrics.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    fh.write(",".join(cols) + "\n")
    for r in sorted(crows, key=lambda r: r["name"]):
        fh.write(",".join("" if r.get(c) is None else str(r[c]) for c in cols) + "\n")

sig = [r for r in csv.DictReader(open(os.path.join(OUT, "author_metrics.csv"), encoding="utf-8-sig"))
       if not r["flag"]]
num = lambda r, k: (float(r[k]) if str(r[k]).strip() not in ("", "None") else None)

KEYS = [("topic_stability", "专注度 S"), ("recent5_per_year", "近五年篇/年"),
        ("pace_per_year", "全程篇/年"), ("team_median", "团队规模中位"),
        ("solo_share", "独作占比"), ("max_gap_years", "最长空窗(年)"),
        ("cv_yearly", "年度 CV"), ("cite_median", "单篇被引中位"),
        ("n_uniq", "总篇数"), ("span_years", "学术跨度(年)")]

comp = {"_meta": {"n_signatory": len(sig), "n_control": len(crows),
                  "control_dropped": [{"name": n, "flag": f} for n, f in dropped],
                  "control_sample": "同主题（签署者高频主题 top30）、篇数 80–700 的随机作者，排除签署者本人"}}
print(f"\n{'指标':<14}{'签署者':>9}{'对照':>9}{'差值':>8}{'  95%CI':>18}{'     p':>9}")
for k, label in KEYS:
    a = [v for v in (num(r, k) for r in sig) if v is not None]
    b = [v for v in (num(r, k) for r in crows) if v is not None]
    if not a or not b:
        continue
    ma, mb = st.median(a), st.median(b)
    U, z, p = mannwhitney(a, b)
    lo, hi = boot_ci(a, b)
    comp[k] = {"label": label, "signatory_median": round(ma, 3), "control_median": round(mb, 3),
               "diff": round(ma - mb, 3), "ci95": [lo, hi], "p": round(p, 4),
               "n_signatory": len(a), "n_control": len(b)}
    mark = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
    print(f"{label:<14}{ma:>9.2f}{mb:>9.2f}{ma-mb:>+8.2f}   [{lo:+.2f}, {hi:+.2f}]{p:>9.4f} {mark}")

json.dump(comp, open(os.path.join(OUT, "comparison.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

FONT = "C:/Windows/Fonts/msyh.ttc"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
plt.rcParams["axes.unicode_minus"] = False
INK, RED = "#2b2118", "#b03a2e"


def ecdf(ax, a, b, xlabel, title):
    for data, lab, col in ((b, "对照组", "#8a6a2c"), (a, "签署者", RED)):
        v = sorted(data)
        if not v:
            continue
        y = [(i + 1) / len(v) for i in range(len(v))]
        ax.step(v, y, where="post", color=col, lw=1.8, label=f"{lab}（n={len(v)}）")
        ax.axvline(st.median(v), color=col, lw=1, ls=":", alpha=.8)
    ax.set_xlabel(xlabel, color=INK)
    ax.set_ylabel("累积比例", color=INK)
    ax.set_title(title, color=INK)
    ax.legend(fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))
S_a = [v for v in (num(r, "topic_stability") for r in sig) if v is not None]
S_b = [r["topic_stability"] for r in crows if r["topic_stability"] is not None]
V_a = [v for v in (num(r, "recent5_per_year") for r in sig) if v is not None]
V_b = [r["recent5_per_year"] for r in crows if r["recent5_per_year"] is not None]
ecdf(axes[0], S_a, S_b, "专注度 S（年际主题 Jaccard）", "专注度：签署者略高")
ecdf(axes[1], V_a, V_b, "近五年年均篇数", "速度：签署者明显更快")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig6_control.png"), dpi=200)
plt.close(fig)
print("\n→ output/control_metrics.csv, output/comparison.json, output/fig6_control.png")
