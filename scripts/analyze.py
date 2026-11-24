#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lab5「慢科研」指标计算与出图（一次运行完成全部重算）。

输入    data/works.json.gz（或 data/works/*.json）
输出    data/author_metrics.csv   逐人指标（含 quadrant 与 flag 列）
        data/headline.json        报告中所有分位数、剔除名单、逐年总量
        figures/fig1..fig5.png    报告用图

四维指标
  S 专注度  相邻年份 top3 主题集合的 Jaccard 均值（跨 4 年以上断档不计）
  V 速度    近五年（快照日前 1826 天）篇数 ÷ 5
  团队      每篇合作者人数（含本人）的中位数；独作占比
  节奏      活跃区间内最长连续无产出年数；逐年篇数变异系数 CV

用法：python analyze.py [--data ../data] [--fig ../figures]
依赖：matplotlib、numpy；中文字体用 C:/Windows/Fonts/msyh.ttc
"""
import argparse, glob, gzip, json, math, os, re, statistics as st
from collections import Counter, defaultdict
from datetime import date

SNAP = date(2026, 11, 11)          # 数据快照日，所有"近五年"以此为准
RECENT_DAYS = 1826                 # ≈ 5 年


# ---------------------------------------------------------------- 载入
def load_authors(data_dir):
    src = os.path.join(data_dir, "works")
    if os.path.isdir(src) and glob.glob(os.path.join(src, "*.json")):
        out = []
        for f in sorted(glob.glob(os.path.join(src, "*.json"))):
            out.append(json.load(open(f, encoding="utf-8")))
        return out
    gz = os.path.join(data_dir, "works.json.gz")
    if not os.path.exists(gz):
        raise SystemExit(f"找不到 {os.path.join(src, '*.json')} 或 {gz}；先跑 fetch_works.py")
    with gzip.open(gz, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


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
    t = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def jaccard(a, b):
    if not a or not b:
        return None
    A, B = set(a), set(b)
    return len(A & B) / len(A | B)


# ---------------------------------------------------------------- 指标
def build(authors):
    rows, per_year = [], Counter()
    for d in authors:
        name, oa = d.get("name"), d.get("oa_id")
        raw = []
        for w in d.get("works") or []:
            dt = parse_date(w)
            if dt is None:
                continue
            raw.append({"dt": dt, "title": norm_title(w.get("title")),
                        "topics": [t for t in (w.get("topics") or []) if isinstance(t, str)],
                        "co": [c for c in (w.get("coauthors") or []) if isinstance(c, str)],
                        "cited": int(w.get("cited") or 0)})
        if not raw:
            continue

        # 同一篇论文的预印本/会议版/期刊版：按归一化标题去重，保留最早日期
        seen, recs = set(), []
        for r in sorted(raw, key=lambda r: r["dt"]):
            k = r["title"] or f"__anon{r['dt']}"
            if k not in seen:
                seen.add(k)
                recs.append(r)

        n = len(recs)
        first, last = recs[0]["dt"], recs[-1]["dt"]
        span = (last - first).days / 365.25
        ycount = Counter(r["dt"].year for r in recs)
        yrs = sorted(ycount)
        max_gap = max((y2 - y1 - 1 for y1, y2 in zip(yrs, yrs[1:])), default=0)
        pace = round(n / span, 2) if span > 0.5 else None
        recent = sum(1 for r in recs if (SNAP - r["dt"]).days <= RECENT_DAYS)
        rec5 = round(recent / 5.0, 2)
        year_ns = [ycount[y] for y in yrs]
        cv = round(st.pstdev(year_ns) / st.mean(year_ns), 3) if len(year_ns) >= 3 else None

        by_y = defaultdict(list)
        for r in recs:
            by_y[r["dt"].year].extend(r["topics"])
        sims = []
        for y1, y2 in zip(yrs, yrs[1:]):
            if y2 - y1 > 4:          # 断档太久，主题变化无法归因于"换方向"
                continue
            t1 = [t for t, _ in Counter(by_y[y1]).most_common(3)]
            t2 = [t for t, _ in Counter(by_y[y2]).most_common(3)]
            s = jaccard(t1, t2)
            if s is not None:
                sims.append(s)
        stab = round(st.mean(sims), 3) if sims else None

        all_t = Counter(t for v in by_y.values() for t in v)
        tot = sum(all_t.values())
        conc = None
        if tot and len(all_t) > 1:
            ent = -sum((c / tot) * math.log(c / tot) for c in all_t.values())
            conc = round(1 - ent / math.log(len(all_t)), 3)
        elif tot:
            conc = 1.0

        team = [max(len(r["co"]), 1) for r in recs]
        team_med = st.median(team)
        solo = round(sum(1 for t in team if t <= 1) / n, 3)

        # 数据质量标记：标记而不删除，汇总时排除，全部列进附录
        flag = ""
        if n > 1500 or (pace or 0) > 40:
            flag = "疑似身份合并"
        elif first.year < 1990:
            flag = "起始年异常"
        elif n <= 3:
            flag = "碎片ID"

        rows.append({"name": name, "oa_id": oa, "n_raw": len(raw), "n_uniq": n,
                     "first_year": first.year, "last_year": last.year,
                     "span_years": round(span, 1), "active_years": len(yrs),
                     "pace_per_year": pace, "recent5_per_year": rec5,
                     "max_gap_years": max_gap, "cv_yearly": cv,
                     "topic_stability": stab, "topic_conc": conc,
                     "team_median": round(team_med, 1), "solo_share": solo,
                     "cite_median": round(st.median([r["cited"] for r in recs]), 1),
                     "cite_total": sum(r["cited"] for r in recs), "flag": flag})
        for y, c in ycount.items():
            per_year[y] += c
    return rows, per_year


def add_quadrant(rows):
    clean = [r for r in rows if not r["flag"]]
    med_v = st.median(r["recent5_per_year"] for r in clean)
    med_s = st.median(r["topic_stability"] for r in clean if r["topic_stability"] is not None)
    for r in rows:
        s, v = r["topic_stability"], r["recent5_per_year"]
        if s is None:
            r["quadrant"] = ""
        elif s >= med_s and v < med_v:
            r["quadrant"] = "深耕慢产"
        elif s >= med_s:
            r["quadrant"] = "深耕快产"
        elif v < med_v:
            r["quadrant"] = "广撒慢产"
        else:
            r["quadrant"] = "广撒快产"
    return clean, med_v, med_s


# ---------------------------------------------------------------- 图
def make_figures(clean, per_year, fig_dir, med_v, med_s):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    FONT = "C:/Windows/Fonts/msyh.ttc"
    font_manager.fontManager.addfont(FONT)
    plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    INK, ACC = "#2b2118", "#d9a24a"
    os.makedirs(fig_dir, exist_ok=True)

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(os.path.join(fig_dir, name), dpi=200)
        plt.close(fig)

    def clean_axes(ax):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)

    # 图 1 近五年年均产出
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    vals = sorted(r["recent5_per_year"] for r in clean)
    ax.hist(vals, bins=24, color=ACC, edgecolor="#8a6a2c", linewidth=.5)
    ax.axvline(st.median(vals), color="#b03a2e", lw=1.4, ls="--")
    ax.annotate(f"中位数 {st.median(vals):.1f} 篇/年",
                xy=(st.median(vals), ax.get_ylim()[1] * .9),
                xytext=(st.median(vals) + 8, ax.get_ylim()[1] * .9),
                color="#b03a2e", fontsize=8)
    ax.set_xlabel("近五年年均发表篇数（2021-11 至 2026-11）", color=INK)
    ax.set_ylabel("人数", color=INK)
    ax.set_title(f"签署者近五年产出：中位 {st.median(vals):.1f} 篇/年", color=INK)
    clean_axes(ax)
    save(fig, "fig1_dist.png")

    # 图 2 四象限
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    for r in clean:
        if r["topic_stability"] is None:
            continue
        col = "#8a6a2c" if r["quadrant"] == "深耕慢产" else "#c9bda9"
        ax.scatter(r["recent5_per_year"], r["topic_stability"], s=22, c=col,
                   edgecolors="#5b4a33", linewidths=.4, alpha=.9, zorder=3)
    ax.axvline(med_v, color="#7a6a55", lw=.9, ls=":")
    ax.axhline(med_s, color="#7a6a55", lw=.9, ls=":")
    xmax = max(r["recent5_per_year"] for r in clean)
    for px, py, t in [(2, .70, "深耕慢产"), (xmax * .62, .70, "深耕快产"),
                      (2, .10, "广撒慢产"), (xmax * .62, .10, "广撒快产")]:
        ax.text(px, py, t, fontsize=10, color="#7a6a55", alpha=.85)
    for r in sorted([r for r in clean if r["topic_stability"] is not None],
                    key=lambda r: (-r["topic_stability"], r["recent5_per_year"]))[:4]:
        ax.annotate(r["name"], (r["recent5_per_year"], r["topic_stability"]),
                    textcoords="offset points", xytext=(5, 3), fontsize=7, color=INK)
    ax.set_xlabel("速度：近五年年均篇数", color=INK)
    ax.set_ylabel("专注：相邻年份主题稳定度（Jaccard）", color=INK)
    ax.set_title(f"「慢」不是一件事：{len(clean)} 位签署者的专注 × 速度", color=INK)
    clean_axes(ax)
    save(fig, "fig2_quadrant.png")

    # 图 3 年度总量
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ys = [y for y in sorted(per_year) if 1990 <= y <= SNAP.year]
    ax.plot(ys, [per_year[y] for y in ys], color="#8a6a2c", lw=1.6)
    ax.fill_between(ys, [per_year[y] for y in ys], color=ACC, alpha=.25)
    ax.annotate(f"{SNAP.year} 仅约 10 个月", xy=(SNAP.year, per_year.get(SNAP.year, 0)),
                xytext=(SNAP.year - 10, max(per_year[y] for y in ys) * .85),
                fontsize=7.5, color="#b03a2e")
    ax.set_xlabel("发表年份", color=INK)
    ax.set_ylabel("篇数（总和）", color=INK)
    ax.set_title("全部作者的年度产出总和", color=INK)
    clean_axes(ax)
    save(fig, "fig3_yearly.png")

    # 图 4 团队规模
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    tv = sorted(r["team_median"] for r in clean)
    ax.hist(tv, bins=[i for i in range(1, 12)], color=ACC, edgecolor="#8a6a2c", linewidth=.5)
    ax.set_xlabel("每篇合作者数中位数（含本人）", color=INK)
    ax.set_ylabel("人数", color=INK)
    ax.set_title(f"团队规模：中位 {st.median(tv):.0f} 人", color=INK)
    clean_axes(ax)
    save(fig, "fig4_team.png")

    # 图 5 最长空窗
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    gv = Counter(r["max_gap_years"] for r in clean)
    ks = sorted(k for k in gv if k <= 8)
    ax.bar([str(k) for k in ks], [gv[k] for k in ks], color=ACC, edgecolor="#8a6a2c", linewidth=.5)
    ax.set_xlabel("最长连续无产出年数", color=INK)
    ax.set_ylabel("人数", color=INK)
    ax.set_title("空窗：多数人没有停过一年以上", color=INK)
    clean_axes(ax)
    save(fig, "fig5_gap.png")


# ---------------------------------------------------------------- 主流程
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(here, "..", "data"))
    ap.add_argument("--fig", default=os.path.join(here, "..", "figures"))
    a = ap.parse_args()

    authors = load_authors(a.data)
    rows, per_year = build(authors)
    clean, med_v, med_s = add_quadrant(rows)
    print(f"总 {len(rows)} 人，可用 {len(clean)} 人，剔除 {len(rows) - len(clean)} 人")

    cols = ["name", "oa_id", "n_uniq", "first_year", "last_year", "span_years",
            "active_years", "pace_per_year", "recent5_per_year", "max_gap_years",
            "cv_yearly", "topic_stability", "topic_conc", "team_median",
            "solo_share", "cite_median", "cite_total", "quadrant", "flag"]
    csv_path = os.path.join(a.data, "author_metrics.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(",".join(cols) + "\n")
        for r in rows:
            fh.write(",".join("" if r.get(c) is None else str(r[c]) for c in cols) + "\n")

    def q(key):
        v = sorted(r[key] for r in clean if r.get(key) is not None)
        pct = lambda p: v[min(len(v) - 1, int(round(p * (len(v) - 1))))]
        return {"n": len(v), "min": round(v[0], 2), "p25": round(pct(.25), 2),
                "median": round(st.median(v), 2), "p75": round(pct(.75), 2),
                "p90": round(pct(.90), 2), "max": round(v[-1], 2)}

    head = {k: q(k) for k in ["n_uniq", "pace_per_year", "recent5_per_year", "max_gap_years",
                              "cv_yearly", "topic_stability", "topic_conc", "team_median",
                              "solo_share", "cite_median", "span_years"]}
    head["_quadrant"] = dict(Counter(r["quadrant"] for r in clean if r["quadrant"]))
    head["_meta"] = {"authors_total": len(rows), "authors_usable": len(clean),
                     "excluded": [{"name": r["name"], "flag": r["flag"]} for r in rows if r["flag"]],
                     "works_uniq_usable": sum(r["n_uniq"] for r in clean),
                     "snapshot": SNAP.isoformat(),
                     "med_speed": round(med_v, 2), "med_stab": round(med_s, 3),
                     "n_under5": sum(1 for r in clean if r["recent5_per_year"] < 5),
                     "n_zero_recent": sum(1 for r in clean if r["recent5_per_year"] < 1)}
    head["_per_year"] = dict(sorted(per_year.items()))
    json.dump(head, open(os.path.join(a.data, "headline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    make_figures(clean, per_year, a.fig, med_v, med_s)
    print(f"→ {csv_path}\n→ {os.path.join(a.data,'headline.json')}\n→ {a.fig}/fig1..5.png")


if __name__ == "__main__":
    main()
