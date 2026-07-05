"""ランキング系ページのデータ構築 (DATA_CONTRACT §2.6)。

旧 PopulationClass の各 GetXxxRanking()/AreaSort() の移植。
同順位は同じ順位を共有し、次の順位は人数分飛ぶ (競技順位方式)。
"""
from . import masters
from .population import CENSUS_YEARS, PROJECTION_YEARS  # noqa: F401 (年ラベル用に再輸出)


def assign_rank(items: list, key: callable, reverse: bool = True) -> None:
    """旧コードの繰り返し実装 (Ranking2045.PrefRanking, AreaSort, GetListOfCitiesByTfr,
    GetAging2045 等) を1箇所に集約した競技順位付け。items は事前にソート済みであること。
    """
    order = 0
    sentinel = float("-inf") if reverse else float("inf")
    prev = sentinel
    for n, item in enumerate(items, start=1):
        v = key(item)
        newly_lower = (v < prev) if reverse else (v > prev)
        if n == 1 or newly_lower:
            order = n
            prev = v
        item["order"] = order


def build_pref_ranking2045(national: list, pref: str) -> dict:
    """旧 Ranking2045.PrefRanking(pref) の移植。都道府県別ランキングビュー。"""
    rows = [r for r in national if str(r["Code"] // 1000).zfill(2) == pref]
    rows = sorted(rows, key=lambda r: -r["Value2015"])
    pref_rows = []
    for r in rows:
        pref_rows.append({
            "code": str(r["Code"]).zfill(5), "name": r["Name"],
            "value": r["Value"], "value2015": r["Value2015"],
            "order_national": r["Order"], "order2015_national": r["Order2015"],
        })
    assign_rank(pref_rows, key=lambda r: r["value2015"])
    for r in pref_rows:
        r["pref_order2015"] = r.pop("order")

    pref_rows.sort(key=lambda r: -r["value"])
    assign_rank(pref_rows, key=lambda r: r["value"])
    for r in pref_rows:
        r["pref_order"] = r.pop("order")

    return {
        "pref": pref, "pref_name": masters.PREF_CODE[pref],
        "total": sum(r["value"] for r in pref_rows),
        "total2015": sum(r["value2015"] for r in pref_rows),
        "cities": pref_rows,
    }


def build_area_ranking(raw: list) -> list:
    """旧 PopulationClass.AreaSort() の移植 (面積降順・同順位あり)。"""
    rows = [{"code": r["団体コード"], "name": r["団体名"], "area": r["面積"], "note": r["参考値"]}
            for r in raw]
    rows.sort(key=lambda r: -r["area"])
    assign_rank(rows, key=lambda r: r["area"])
    return rows


_TFR_EXCLUDE_CODE = "13100"  # 東京都区部 (合計値。個別区と二重計上になるため除外)


def build_tfr_ranking(raw: list) -> list:
    """旧 PopulationClass.GetListOfCitiesByTfr() の移植。

    東京都区部合計 (13100) を除外。「区」は東京都(13始まり)以外は除外
    (政令市の行政区は特殊出生率データの単位ではないため)。
    """
    rows = []
    for r in raw:
        code, name = r["code"], r["name"]
        if code == _TFR_EXCLUDE_CODE:
            continue
        if name.endswith("区") and not code.startswith("13"):
            continue
        rows.append({
            "code": code, "name": name, "tfr": float(r["tfr"]),
            "url_code": masters.CHANGE_CODE_AFTER_2010.get(code, code),
        })
    rows.sort(key=lambda r: -r["tfr"])
    assign_rank(rows, key=lambda r: r["tfr"])
    return rows


def build_aging_oldold_2045(city_models: dict) -> list:
    """旧 PopulationClass.GetAging2045()/GetOldOld2045() の移植。

    新規の外部データ読み込みは不要 — 既に構築済みの市町村モデル
    (data/population/city/*.json 相当。引数は {code: model} の dict) の
    projection index (kind=projection, 7点) から老年人口/後期老年人口の
    推移を取り出すだけで再現できる (DATA_CONTRACT §2.6)。
    """
    rows = []
    for code, model in city_models.items():
        proj_index = [e for e in model["index"] if e["kind"] == "projection"]
        if not proj_index:  # 福島県: 将来推計なし
            continue
        rows.append({
            "code": code, "name": model["name"],
            "old": [e["old"] for e in proj_index],
            "old_old": [e["old_old"] for e in proj_index],
        })
    return rows


def rank_generation(rows: list, field: str) -> list:
    """CityAging2045/CityOldOld2045: (2045値 - 2015値) の降順ランキング。"""
    ranked = sorted(rows, key=lambda r: -(r[field][6] - r[field][0]))
    assign_rank(ranked, key=lambda r: r[field][6] - r[field][0])
    return ranked


# 旧 PopulationController.Population2015 の order パラメータ (4種)。
# "順位"列(2015年順位/2010年順位)は旧実装と同じく全国順位を表示するのみで、
# 都道府県フィルタ時でも再計算しない(ソートのみ都道府県内で行う)。
POPULATION2015_ORDERS = {
    "popu": ("人口順", lambda r: -r["popu2015"]),
    "inc": ("増減数順", lambda r: -(r["popu2015"] - r["popu2010"])),
    "rate": ("増減率順", lambda r: -(r["popu2015"] / r["popu2010"])),
    "code": ("コード順", lambda r: r["code"]),
}


def build_population2015_ranking(cityinfo: list, order: str, pref: str | None) -> list:
    """旧 PopulationController.Population2015(id, order) の移植。

    cityinfo は data/cityinfo2015.json (旧 App_Data/Population2015/2015/
    population2015.json、Phase 1 で読み込み済みのもの) をそのまま渡す。
    """
    rows = [r for r in cityinfo if pref is None or r["code"].startswith(pref)]
    _, key = POPULATION2015_ORDERS[order]
    return sorted(rows, key=key)
