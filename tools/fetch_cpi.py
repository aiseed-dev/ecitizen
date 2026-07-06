#!/usr/bin/env python3
"""消費者物価指数 (CPI、2020年基準 0003427113) の取得 (DESIGN.md §22)。

全国と東京都区部の主要3系列 (総合/生鮮食品を除く総合/生鮮食品及びエネルギーを
除く総合) × (指数/前年同月比) をフィルタ付き getStatsData で取得し、
data/cpi.json を生成する。月次更新はこのツールの再実行のみ。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from citizenlib.estat import EstatClient  # noqa: E402

TABLE = "0003427113"
SERIES = ["総合", "生鮮食品を除く総合", "生鮮食品及びエネルギーを除く総合"]
AREAS = {"全国": "japan", "東京都区部": "tokyo"}
TABS = {"指数": "index", "前年同月比": "yoy"}


def main() -> None:
    client = EstatClient.from_secrets()
    meta = client._get("getMetaInfo", {"statsDataId": TABLE})["GET_META_INFO"]
    objs = {o["@id"]: o["CLASS"] if isinstance(o["CLASS"], list) else [o["CLASS"]]
            for o in meta["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]}
    def name_of(c):  # "0001 総合" → "総合" (コード接頭辞を除去)
        n = c["@name"]
        return n.split(" ", 1)[1] if " " in n and n.split(" ")[0].isdigit() else n
    cat = {name_of(c): c["@code"] for c in objs["cat01"]}
    area = {name_of(c): c["@code"] for c in objs["area"]}
    tab = {c["@name"]: c["@code"] for c in objs["tab"]}
    cats = {n: cat[n] for n in SERIES}
    tabs = {n: tab[n] for n in TABS}
    areas = {n: area[n] for n in AREAS}

    body = client.get_stats_data(
        TABLE, cdTab=",".join(tabs.values()), cdArea=",".join(areas.values()),
        cdCat01=",".join(cats.values()), limit=100_000)
    values = body["STATISTICAL_DATA"]["DATA_INF"]["VALUE"]
    times = {c["@code"]: c["@name"] for c in
             next(o for o in body["STATISTICAL_DATA"]["CLASS_INF"]["CLASS_OBJ"]
                  if o["@id"] == "time")["CLASS"]}

    out = {AREAS[a]: {TABS[t]: {n: {} for n in SERIES} for t in TABS} for a in AREAS}
    rev_c = {v: k for k, v in cats.items()}
    rev_a = {v: k for k, v in areas.items()}
    rev_t = {v: k for k, v in tabs.items()}
    for v in values:
        tname = times[v["@time"]]  # 例 "2026年5月"
        if "月" not in tname:
            continue  # 年平均・年度平均は除く
        y, m = tname.replace("月", "").split("年")
        key = f"{y}-{int(m):02d}"
        out[AREAS[rev_a[v["@area"]]]][TABS[rev_t[v["@tab"]]]][rev_c[v["@cat01"]]][key] = v["$"]

    path = ROOT / "data" / "cpi.json"
    path.write_text(json.dumps({"table": TABLE, "series": SERIES, "data": out},
                               ensure_ascii=False), encoding="utf-8")
    n = sum(len(d) for a in out.values() for t in a.values() for d in t.values())
    months = sorted(out["japan"]["index"][SERIES[0]])
    print(f"CPI {n:,}値 / {months[0]}〜{months[-1]} → data/cpi.json")


if __name__ == "__main__":
    main()
