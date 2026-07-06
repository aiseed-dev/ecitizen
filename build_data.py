#!/usr/bin/env python3
"""取得層ドライバ (DESIGN.md §3)。

Phase 1: 旧リポジトリの App_Data/Population2015 を一次ソースとして、
DATA_CONTRACT.md §2 の中間データを data/ に生成する。

usage: python build_data.py [--source ../eCitizen/eCitizen]
"""
import argparse
import json
from pathlib import Path

from citizenlib import census2010, masters, rankings
from citizenlib.ipss import IpssData
from citizenlib.population import (
    SourceData, build_city_model, build_city_pyramid_model, build_country_model,
    build_country_pyramid_model, build_pref_model, build_pref_pyramid_model,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent / "eCitizen" / "eCitizen"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.rename(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = ap.parse_args()

    source = SourceData(args.source)
    ipss = IpssData()

    # --- 市町村 (Phase 1、census 2020列・projection全体は IPSS 令和5年推計) ---
    city_dir = ROOT / "data" / "population" / "city"
    city_models = {}
    for code in masters.CITY_DIC:
        model = build_city_model(source, code, ipss)
        # 契約の構造チェック (DATA_CONTRACT §2.1)
        n_census_cols = 8 if model["fukushima"] else 9
        assert len(model["census"]) == 21 and all(
            len(r["population"]) == n_census_cols for r in model["census"]), code
        assert model["projection"] == [] or (
            len(model["projection"]) == 21 and all(len(r["population"]) == 7 for r in model["projection"])), code
        assert len(model["index"]) == (8 if model["fukushima"] else 16), code
        write_json(city_dir / f"{code}.json", model)
        city_models[code] = model
    print(f"市町村モデル {len(city_models)} 件")

    write_json(ROOT / "data" / "cityinfo2015.json", source.load_cityinfo2015())

    # --- 都道府県 (Phase 2、census 2020列・projection全体は IPSS 令和5年推計) ---
    pref_dir = ROOT / "data" / "population" / "pref"
    for pref in masters.PREF_CODE:
        model = build_pref_model(source, pref, ipss)
        assert len(model["census"]) == 21 and len(model["projection"]) == 21, pref
        assert len(model["index"]) == 16, pref
        write_json(pref_dir / f"{pref}.json", model)
    print(f"都道府県モデル {len(masters.PREF_CODE)} 件")

    # --- 都道府県 人口ピラミッド (常に将来推計あり、fukushima相当の欠損なし) ---
    pref_pyramid_dir = ROOT / "data" / "population" / "pyramid" / "pref"
    for pref in masters.PREF_CODE:
        model = build_pref_pyramid_model(source, pref, ipss)
        assert len(model["years"]) == 15, pref
        assert all(len(y["male"]) == 19 and len(y["female"]) == 19 for y in model["years"]), pref
        write_json(pref_pyramid_dir / f"{pref}.json", model)
    print(f"都道府県ピラミッドモデル {len(masters.PREF_CODE)} 件")

    # --- 国 (日本以外は Eurostat/ONS、日本は IPSS令和5年推計の47都道府県合算) ---
    country_dir = ROOT / "data" / "population" / "country"
    for code in masters.COUNTRY_CODE:
        model = build_country_model(source, code, ipss)
        if model["is_jp"]:
            assert len(model["census"]) == 21 and len(model["census"][0]["population"]) == 9, code
            assert len(model["projection"]) == 21 and len(model["projection"][0]["population"]) == 7, code
            assert len(model["index"]) == 16, code
        else:
            assert len(model["census"]) == 20 and len(model["census"][0]["population"]) == 9, code
            assert len(model["projection"]) == 20 and len(model["projection"][0]["population"]) == 6, code
            assert len(model["index"]) == 15, code
        write_json(country_dir / f"{code}.json", model)
    print(f"国モデル {len(masters.COUNTRY_CODE)} 件")

    # --- 国 人口ピラミッド (JP含め全カ国15年分) ---
    country_pyramid_dir = ROOT / "data" / "population" / "pyramid" / "country"
    for code in masters.COUNTRY_CODE:
        model = build_country_pyramid_model(source, code, ipss)
        assert len(model["years"]) == 15, code
        assert all(len(y["male"]) == 19 and len(y["female"]) == 19 for y in model["years"]), code
        write_json(country_pyramid_dir / f"{code}.json", model)
    print(f"国ピラミッドモデル {len(masters.COUNTRY_CODE)} 件")

    # --- 人口ピラミッド (Phase 2、市町村のみ、IPSS 令和5年推計) ---
    pyramid_dir = ROOT / "data" / "population" / "pyramid" / "city"
    for code in masters.CITY_DIC:
        model = build_city_pyramid_model(source, code, ipss)
        expected_years = 8 if model["fukushima"] else 15
        assert len(model["years"]) == expected_years, code
        assert all(len(y["male"]) == 19 and len(y["female"]) == 19 for y in model["years"]), code
        write_json(pyramid_dir / f"{code}.json", model)
    print(f"人口ピラミッドモデル {len(masters.CITY_DIC)} 件")
    ipss.close()

    # --- ランキング系 (既存データからの再計算のみ。新規ソース読込は area/tfr のみ) ---
    rank_dir = ROOT / "data" / "rankings"

    # 2026-07-06: 平成30年推計の旧CityRanking2045.jsonから、IPSS令和5年推計
    # (市町村モデルに取り込み済み) による2050年ランキングに刷新。
    # 福島県も浜通り13町村以外は推計があるため掲載できるようになった
    ranking_national = rankings.build_ranking2050(city_models)
    assert len(ranking_national) == len(masters.CITY_DIC) - 13, len(ranking_national)
    write_json(rank_dir / "ranking2050_national.json", ranking_national)
    for pref in masters.PREF_CODE:
        write_json(rank_dir / "ranking2050_pref" / f"{pref}.json",
                   rankings.build_pref_ranking2050(ranking_national, pref))

    area_ranking = rankings.build_area_ranking(source.load_area())
    assert len(area_ranking) == 1741
    write_json(rank_dir / "cityarea.json", area_ranking)

    tfr_ranking = rankings.build_tfr_ranking(source.load_tfr())
    write_json(rank_dir / "citytfr.json", tfr_ranking)

    # IPSS 令和5年推計への切替後も対象外は福島県浜通り13町村のみ (那珂川市はコード変換で救済済み)
    aging_oldold = rankings.build_aging_oldold_2045(city_models)
    assert len(aging_oldold) == len(masters.CITY_DIC) - 13
    write_json(rank_dir / "city_aging_2045.json", rankings.rank_generation(aging_oldold, "old"))
    write_json(rank_dir / "city_oldold_2045.json", rankings.rank_generation(aging_oldold, "old_old"))
    print("ランキングデータ (ranking2050 全国+47県 / cityarea / citytfr / aging・oldold 2050) を生成しました")

    # --- Census2010 (2010年国勢調査人口と2008年推計の比較。ローカル完結、K5準拠) ---
    census2010_rows = census2010.build_census2010_rows(
        source.load_census2010(), source.load_area_code_list())
    assert len(census2010_rows) == 1878 + 47, len(census2010_rows)
    write_json(rank_dir / "census2010.json", census2010_rows)
    print(f"Census2010 {len(census2010_rows)} 行")


if __name__ == "__main__":
    main()
