#!/usr/bin/env python3
"""取得層ドライバ (DESIGN.md §3)。

Phase 1: 旧リポジトリの App_Data/Population2015 を一次ソースとして、
DATA_CONTRACT.md §2 の中間データを data/ に生成する。

usage: python build_data.py [--source ../eCitizen/eCitizen]
"""
import argparse
import json
from pathlib import Path

from citizenlib import masters, rankings
from citizenlib.ipss import IpssData
from citizenlib.population import (
    SourceData, build_city_model, build_city_pyramid_model, build_country_model,
    build_pref_model,
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

    # --- 国 (Phase 2、日本以外は Eurostat(census/EUROPOP2023)・UKのみ ONS へ切替) ---
    country_dir = ROOT / "data" / "population" / "country"
    for code in masters.COUNTRY_CODE:
        model = build_country_model(source, code)
        assert len(model["projection"]) == 20, code
        if model["is_jp"]:
            assert len(model["census"]) == 21 and len(model["census"][0]["population"]) == 8, code
            assert len(model["projection"][0]["population"]) == 7, code
            assert len(model["index"]) == 15, code
        else:
            assert len(model["census"]) == 20 and len(model["census"][0]["population"]) == 9, code
            assert len(model["projection"][0]["population"]) == 6, code
            assert len(model["index"]) == 15, code
        write_json(country_dir / f"{code}.json", model)
    print(f"国モデル {len(masters.COUNTRY_CODE)} 件")

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

    # --- ランキング系 (Phase 2、既存データからの再計算のみ。新規ソース読込は area/tfr/ranking2045 のみ) ---
    rank_dir = ROOT / "data" / "rankings"

    ranking2045_raw = source.load_ranking2045()
    assert len(ranking2045_raw) == 1682
    write_json(rank_dir / "ranking2045_national.json", ranking2045_raw)
    for pref in masters.PREF_CODE:
        if pref == "07":  # 福島県: 将来推計非公表のため対象外
            continue
        write_json(rank_dir / "ranking2045_pref" / f"{pref}.json",
                   rankings.build_pref_ranking2045(ranking2045_raw, pref))

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
    print("ランキングデータ (ranking2045 全国+47県 / cityarea / citytfr / aging・oldold 2050) を生成しました")


if __name__ == "__main__":
    main()
