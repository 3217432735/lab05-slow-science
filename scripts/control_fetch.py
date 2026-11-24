# -*- coding: utf-8 -*-
"""抓对照组作者的 works，逐作者落盘（可中断续跑）。"""
import csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(BASE, "key.txt")).read().strip()
OUT = os.path.join(BASE, "control_works")
os.makedirs(OUT, exist_ok=True)
FIELDS = "id,title,publication_year,publication_date,primary_location,topics,authorships,cited_by_count"
UA = {"User-Agent": "lab05-control/1.0"}


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as f:
                return json.loads(f.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** i * 2)
                continue
            raise
        except Exception:
            time.sleep(2 ** i)
    raise RuntimeError("failed " + url)


def simplify(w):
    src = (w.get("primary_location") or {}).get("source") or {}
    return {"id": (w.get("id") or "").rsplit("/", 1)[-1], "title": w.get("title") or "",
            "year": w.get("publication_year"), "date": w.get("publication_date"),
            "venue": src.get("display_name") or "",
            "topics": [t.get("display_name") for t in (w.get("topics") or [])][:5],
            "coauthors": [a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])],
            "cited": w.get("cited_by_count") or 0}


def fetch(row):
    aid, name = row["oa_id"], row["name"]
    path = os.path.join(OUT, f"{aid}.json")
    if os.path.exists(path):
        return aid, None
    works, cursor = [], "*"
    while True:
        q = {"filter": f"author.id:{aid}", "per-page": "200", "select": FIELDS,
             "cursor": cursor, "api_key": KEY}
        d = get("https://api.openalex.org/works?" + urllib.parse.urlencode(q))
        works += [simplify(w) for w in (d.get("results") or [])]
        cursor = (d.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.2)
    json.dump({"oa_id": aid, "name": name, "works": works},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return aid, len(works)


rows = [r for r in csv.DictReader(open(os.path.join(BASE, "control_roster.csv"), encoding="utf-8-sig")) if r.get("oa_id")]
print(f"对照组 {len(rows)} 人，已有 {len(os.listdir(OUT))} 个文件", flush=True)
done = 0
with ThreadPoolExecutor(max_workers=6) as ex:
    for aid, n in ex.map(fetch, rows):
        done += 1
        if n:
            print(f"[{done}/{len(rows)}] {aid} {n} 篇", flush=True)
print("DONE", len(os.listdir(OUT)), flush=True)
