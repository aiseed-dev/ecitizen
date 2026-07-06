#!/usr/bin/env python3
"""社会・人口統計体系 (Ssds) の都道府県データを e-Stat から取得・加工する。

DESIGN.md §21。都道府県データ26表 (基礎データA〜M + 社会生活統計指標A〜M) を
getStatsData (NEXT_KEY ページング) で取得し、data/ssds/ に加工済み JSON を生成。

usage:
  python tools/fetch_ssds.py             # 取得 + 加工 (初回 約10〜20分)
  python tools/fetch_ssds.py --use-raw   # data/raw/ssds/ のキャッシュから加工のみ
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from citizenlib.estat import EstatClient  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "ssds"
OUT_DIR = ROOT / "data" / "ssds"
LIMIT = 100_000

# 都道府県データの statsDataId (社会・人口統計体系 00200502)。
# 0000010101..13 = 基礎データ A..M、0000010201..13 = 社会生活統計指標 A..M
MAJORS = "ABCDEFGHIJKLM"
TABLES = [(f"00000101{n:02d}", MAJORS[n - 1], "basic") for n in range(1, 14)] + \
         [(f"00000102{n:02d}", MAJORS[n - 1], "indicator") for n in range(1, 14)]
MAJOR_NAMES = {"A": "人口・世帯", "B": "自然環境", "C": "経済基盤", "D": "行政基盤",
               "E": "教育", "F": "労働", "G": "文化・スポーツ", "H": "居住",
               "I": "健康・医療", "J": "福祉・社会保障", "K": "安全", "L": "家計",
               "M": "生活時間"}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def fetch_table(client, table_id: str, use_raw: bool) -> list:
    """1表分の生レスポンス (ページのリスト) を返す。"""
    pages = []
    start = 1
    while True:
        raw_path = RAW_DIR / f"{table_id}_{start}.json"
        if raw_path.exists():
            body = json.loads(raw_path.read_text(encoding="utf-8"))
        elif use_raw:
            break
        else:
            body = client.get_stats_data(table_id, limit=LIMIT, startPosition=start)
            write_json(raw_path, body)
        pages.append(body)
        nxt = body["STATISTICAL_DATA"]["RESULT_INF"].get("NEXT_KEY")
        if not nxt:
            break
        start = int(nxt)
    return pages


def class_map(page: dict, class_id: str) -> dict:
    """CLASS_INF から {code: attrs} を引く。"""
    for obj in page["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"]:
        if obj["@id"] == class_id:
            cls = obj["CLASS"]
            if isinstance(cls, dict):
                cls = [cls]
            return {c["@code"]: c for c in cls}
    raise KeyError(class_id)


def parse_table(pages: list, major: str, kind: str, items: dict, series: dict) -> None:
    """表の全ページを items (メタ) と series (項目→{year→{pref→値}}) に流し込む。"""
    cats = class_map(pages[0], "cat01")
    times = class_map(pages[0], "time")
    for code, c in cats.items():
        items[code] = {
            "code": code,
            "name": (c["@name"].split("_", 1)[-1] if "_" in c["@name"]
                     else c["@name"].split("　", 1)[-1]).strip(),  # 先頭の項目コード表記を除去
            "unit": c.get("@unit", ""),
            "major": major,
            "kind": kind,
        }
    year_of = {t: v["@name"][:4] for t, v in times.items()}
    for page in pages:
        values = page["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
        if isinstance(values, dict):
            values = [values]
        for v in values:
            area = v["@area"]
            if area == "00000":  # 全国は順位対象外 (v1では保持しない)
                continue
            pref = area[:2]
            series.setdefault(v["@cat01"], {}).setdefault(
                year_of[v["@time"]], {})[pref] = v["$"]


def rank_years(item_series: dict) -> dict:
    """{year: {pref: 値}} → {year: {pref: 順位}} (降順・同値同順位・非数値は順位なし)。"""
    orders = {}
    for year, prefs in item_series.items():
        nums = {}
        for pref, val in prefs.items():
            try:
                nums[pref] = float(str(val).replace(",", ""))
            except ValueError:
                pass
        orders[year] = {pref: 1 + sum(1 for x in nums.values() if x > n)
                        for pref, n in nums.items()}
    return orders


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-raw", action="store_true")
    args = ap.parse_args()
    client = None if args.use_raw else EstatClient.from_secrets()

    items: dict = {}
    series: dict = {}
    for i, (table_id, major, kind) in enumerate(TABLES, 1):
        pages = fetch_table(client, table_id, args.use_raw)
        parse_table(pages, major, kind, items, series)
        print(f"  {i}/{len(TABLES)} {table_id} ({kind} {major}) "
              f"{sum(len(p['STATISTICAL_DATA']['DATA_INF']['VALUE']) for p in pages):,}件")

    # 項目別ファイル: 年の昇順、値と順位
    n_items = 0
    for code, item in items.items():
        s = series.get(code, {})
        orders = rank_years(s)
        years = sorted(s)
        write_json(OUT_DIR / "items" / f"{code}.json", {
            **item, "years": years,
            "values": {y: s[y] for y in years},
            "orders": {y: orders[y] for y in years},
        })
        n_items += 1

    # 分野×種別の項目リスト
    majors = {}
    for code, item in sorted(items.items()):
        majors.setdefault(f"{item['kind']}_{item['major']}", []).append(
            {"code": code, "name": item["name"], "unit": item["unit"]})
    write_json(OUT_DIR / "majors.json",
               {"major_names": MAJOR_NAMES, "groups": majors})

    # 県×分野×種別: 各項目の最新年の値・年・全国順位
    for pref_n in range(1, 48):
        pref = f"{pref_n:02d}"
        for key, group in majors.items():
            rows = []
            for g in group:
                data = series.get(g["code"], {})
                years = sorted(data)
                latest = years[-1] if years else None
                val = data.get(latest, {}).get(pref) if latest else None
                order = rank_years({latest: data[latest]})[latest].get(pref) \
                    if latest and pref in data.get(latest, {}) else None
                rows.append({"code": g["code"], "name": g["name"], "unit": g["unit"],
                             "year": latest, "value": val, "order": order})
            write_json(OUT_DIR / "pref" / f"{pref}_{key}.json", rows)

    print(f"項目 {n_items:,} 件 / 分野グループ {len(majors)} / 県別 {47 * len(majors)} ファイル")


if __name__ == "__main__":
    main()
