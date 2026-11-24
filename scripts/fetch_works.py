#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 OpenAlex 作者 ID 抓取全部作品。

输入：data/author_ids.csv  列名 name,oa_id（每行一位作者）
输出：data/works.json.gz   [{"oa_id","name","works":[{id,title,year,date,venue,topics,coauthors,cited}, ...]}]

口径说明（写进报告的就是这一套）：
  * 过滤条件只用 author.id，不额外限年份（跨度、空窗、起始年都要用全量）
  * 每页 200 条，cursor 分页直到 next_cursor 为 null
  * 只保留分析需要的字段，避免存整包（原始响应约 400 MB）
  * 主题取 OpenAlex 的 topics[].display_name（三级自动标签），保留前 5 个
  * 合作者只存 display_name，用于算团队规模，不解析机构

依赖：仅标准库。
用法：
  set OPENALEX_KEY=xxxx（可选，无 key 也能跑，只是限速更低）
  python fetch_works.py [--in ../data/author_ids.csv] [--out ../data/works.json.gz] [--sleep 0.2]
"""
import argparse, csv, gzip, json, os, sys, time, urllib.error, urllib.parse, urllib.request

API = "https://api.openalex.org/works"
UA = "lab05-slow-science/1.0 (mailto:student@example.edu)"
FIELDS = "id,title,publication_year,publication_date,primary_location,topics,authorships,cited_by_count"


def get(url, tries=4):
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as f:
                return json.loads(f.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** i)
                continue
            raise
        except Exception:
            time.sleep(2 ** i)
    raise RuntimeError("多次重试后仍失败：" + url)


def one_work(w):
    loc = (w.get("primary_location") or {}).get("source") or {}
    return {
        "id": (w.get("id") or "").rsplit("/", 1)[-1],
        "title": w.get("title") or "",
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "venue": loc.get("display_name") or "",
        "topics": [t.get("display_name") for t in (w.get("topics") or [])][:5],
        "coauthors": [a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])],
        "cited": w.get("cited_by_count") or 0,
    }


def fetch_author(oa_id, key, sleep):
    out, cursor = [], "*"
    base = {"filter": f"author.id:{oa_id}", "per-page": "200", "select": FIELDS, "cursor": cursor}
    if key:
        base["api_key"] = key
    while True:
        url = API + "?" + urllib.parse.urlencode(base)
        d = get(url)
        for w in d.get("results") or []:
            out.append(one_work(w))
        nxt = (d.get("meta") or {}).get("next_cursor")
        if not nxt:
            return out
        base["cursor"] = nxt
        time.sleep(sleep)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(here, "..", "data", "author_ids.csv"))
    ap.add_argument("--out", default=os.path.join(here, "..", "data", "works.json.gz"))
    ap.add_argument("--sleep", type=float, default=0.2)
    a = ap.parse_args()

    key = os.environ.get("OPENALEX_KEY", "").strip()
    rows = [r for r in csv.DictReader(open(a.inp, encoding="utf-8-sig")) if r.get("oa_id")]
    print(f"{len(rows)} 位作者", file=sys.stderr)

    bundle, total = [], 0
    for i, r in enumerate(rows, 1):
        works = fetch_author(r["oa_id"], key, a.sleep)
        bundle.append({"oa_id": r["oa_id"], "name": r.get("name", ""), "works": works})
        total += len(works)
        print(f"  [{i}/{len(rows)}] {r.get('name','')} {r['oa_id']} → {len(works)} 篇", file=sys.stderr)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    data = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    with gzip.open(a.out, "wb", compresslevel=9) as f:
        f.write(data)
    print(f"共 {total} 篇 → {a.out}（未压缩 {len(data)/1e6:.1f} MB）", file=sys.stderr)


if __name__ == "__main__":
    main()
