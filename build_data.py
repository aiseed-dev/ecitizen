#!/usr/bin/env python3
"""取得層ドライバ (DESIGN.md §3)。

Phase 1: 旧リポジトリの App_Data/Population2015 を一次ソースとして、
DATA_CONTRACT.md §2 の中間データを data/ に生成する。

usage: python build_data.py [--source ../eCitizen/eCitizen]
"""
import argparse
import json
from pathlib import Path

from citizenlib import masters
from citizenlib.population import SourceData, build_city_model

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
    out_dir = ROOT / "data" / "population" / "city"

    count = 0
    for code in masters.CITY_DIC:
        model = build_city_model(source, code)
        # 契約の構造チェック (DATA_CONTRACT §2.1)
        assert len(model["census"]) == 21 and all(len(r["population"]) == 8 for r in model["census"]), code
        assert model["projection"] == [] or (
            len(model["projection"]) == 20 and all(len(r["population"]) == 7 for r in model["projection"])), code
        assert len(model["index"]) == (8 if model["fukushima"] else 15), code
        write_json(out_dir / f"{code}.json", model)
        count += 1

    write_json(ROOT / "data" / "cityinfo2015.json", source.load_cityinfo2015())
    print(f"市町村モデル {count} 件 / cityinfo2015 を data/ に生成しました")


if __name__ == "__main__":
    main()
