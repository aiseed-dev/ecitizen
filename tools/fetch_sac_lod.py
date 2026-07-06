#!/usr/bin/env python3
"""市町村の廃置分合データを e-Stat 統計LOD (標準地域コード) から取得する。

DESIGN.md §18、DATA_CONTRACT.md §1.1。
sacs:succeedingMunicipality (廃止コード → 後継市町村) の全ペアと
廃置分合イベント (施行日・事由) を SPARQL で取得し、
data/masters/municipal_changes.json を生成する (コミットするマスター)。

usage:
  python tools/fetch_sac_lod.py             # SPARQL を叩いて再生成
  python tools/fetch_sac_lod.py --use-raw   # data/raw/lod/ のキャッシュから再生成
"""
import argparse
import datetime
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "lod"
OUT_PATH = ROOT / "data" / "masters" / "municipal_changes.json"

ENDPOINT = "https://data.e-stat.go.jp/lod/sparql/alldata/query"
USER_AGENT = "eCitizenStatic-build/1.0 (+https://github.com/aiseed-dev/ecitizen; local batch)"
PAGE = 1000

PREFIXES = """\
PREFIX sacs: <http://data.e-stat.go.jp/lod/terms/sacs#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX org: <http://www.w3.org/ns/org#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

# 廃止コード → 後継市町村。イベント経由で施行日と事由を取る。
# 表記は rdfs:label の ja (ja-hrkt のふりがなは除外)
PAIRS_QUERY = PREFIXES + """\
SELECT ?oldCode ?oldName ?newCode ?newName ?chdate ?reason WHERE {
  ?old sacs:succeedingMunicipality ?new ;
       dcterms:identifier ?oldCode ;
       rdfs:label ?oldName ;
       org:resultedFrom ?event .
  ?new dcterms:identifier ?newCode ;
       rdfs:label ?newName .
  ?event dcterms:date ?chdate ;
         sacs:reasonForChange ?reason .
  FILTER(lang(?oldName) = "ja")
  FILTER(lang(?newName) = "ja")
}
ORDER BY ?chdate ?oldCode ?newCode
"""

REASONS_QUERY = PREFIXES + """\
SELECT ?reason ?label WHERE {
  ?reason a sacs:ReasonForCodeChange ;
          rdfs:label ?label .
  FILTER(lang(?label) = "ja")
}
"""


def sparql(query: str) -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query})
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bindings(body: dict) -> list:
    return body["results"]["bindings"]


def val(b: dict, name: str) -> str:
    # このエンドポイントは変数名を大文字で返す (?oldCode → OLDCODE)。
    # SQL予約語と衝突する変数名 (date 等) は SQL$n に潰されるため使わないこと
    return b[name.upper()]["value"]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def fetch_all_pairs(use_raw: bool) -> list:
    pages = []
    offset = 0
    while True:
        raw_path = RAW_DIR / f"pairs_{offset}.json"
        if use_raw and raw_path.exists():
            body = json.loads(raw_path.read_text(encoding="utf-8"))
        elif use_raw:
            break
        else:
            body = sparql(PAIRS_QUERY + f"OFFSET {offset} LIMIT {PAGE}")
            write_json(raw_path, body)
            time.sleep(0.5)  # 公共エンドポイントへの負荷抑制
        rows = bindings(body)
        pages.extend(rows)
        if len(rows) < PAGE:
            break
        offset += PAGE
    return pages


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-raw", action="store_true",
                    help="data/raw/lod/ のキャッシュから再生成 (SPARQL を呼ばない)")
    args = ap.parse_args()

    if args.use_raw:
        reasons_body = json.loads(
            (RAW_DIR / "reasons.json").read_text(encoding="utf-8"))
    else:
        reasons_body = sparql(REASONS_QUERY)
        write_json(RAW_DIR / "reasons.json", reasons_body)
    reasons = {val(b, "reason").rsplit("/", 1)[-1]: val(b, "label")
               for b in bindings(reasons_body)}

    rows = fetch_all_pairs(args.use_raw)
    changes = []
    for b in rows:
        changes.append({
            "date": val(b, "chdate"),
            "reason": val(b, "reason").rsplit("/", 1)[-1],
            "old": {"code": val(b, "oldCode").zfill(5),
                    "name": val(b, "oldName")},
            "new": {"code": val(b, "newCode").zfill(5),
                    "name": val(b, "newName")},
        })
    changes.sort(key=lambda c: (c["date"], c["old"]["code"], c["new"]["code"]))

    # 同一ペアの重複排除 (念のため)
    seen = set()
    unique = []
    for c in changes:
        key = (c["date"], c["old"]["code"], c["new"]["code"], c["reason"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    out = {
        "fetched_at": datetime.date.today().isoformat(),
        "source": "e-Stat 統計LOD 標準地域コード (https://data.e-stat.go.jp/lodw/)",
        "reasons": dict(sorted(reasons.items())),
        "changes": unique,
    }
    write_json(OUT_PATH, out)
    n_code_change = sum(1 for c in unique
                        if c["old"]["code"] != c["new"]["code"])
    print(f"事由 {len(reasons)} 種 / 変更ペア {len(unique)} 件 "
          f"(うちコード変更 {n_code_change} 件) → {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
