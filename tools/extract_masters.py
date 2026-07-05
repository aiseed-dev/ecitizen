#!/usr/bin/env python3
"""PopulationClass.cs などの C# ソースからマスター辞書を抽出して data/masters/*.json に保存する。

国勢調査データが更新されない限り再実行は不要。抽出結果はリポジトリにコミットする。

usage: python tools/extract_masters.py [--source /path/to/eCitizen/eCitizen]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT.parent / "eCitizen" / "eCitizen"

DICT_RE = re.compile(
    r'Dictionary<string,\s*string>\s+(\w+)\s*=\s*new\s+Dictionary<string,\s*string>\(\)\s*\{(.*?)\};',
    re.S,
)
PAIR_RE = re.compile(r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\}')
ARRAY_RE = re.compile(r'string\[\]\s+(\w+)\s*=\s*new\[\]\s*\{(.*?)\};', re.S)
ITEM_RE = re.compile(r'"([^"]*)"')

# 抽出対象: C#の変数名 → 出力ファイル名
DICTS = {
    "PrefCode": "prefcode.json",
    "CityDic20161010": "citydic20161010.json",
    "CodeTrans20151001": "codetrans20151001.json",
    "CodeTrans20140401": "codetrans20140401.json",
    "CountryCode": "countrycode.json",
}
ARRAYS = {
    "Ages": "ages.json",
    "Ages2": "ages2.json",
    "Ages3": "ages3.json",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help="eCitizen の ASP.NET プロジェクトルート")
    args = ap.parse_args()

    cs = (args.source / "Models" / "Population2015" / "PopulationClass.cs").read_text(encoding="utf-8")
    out_dir = ROOT / "data" / "masters"
    out_dir.mkdir(parents=True, exist_ok=True)

    found = set()
    for m in DICT_RE.finditer(cs):
        name, body = m.group(1), m.group(2)
        if name not in DICTS:
            continue
        d = {k: v for k, v in PAIR_RE.findall(body)}
        (out_dir / DICTS[name]).write_text(
            json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        found.add(name)
        print(f"{name}: {len(d)} 件 -> {DICTS[name]}")

    for m in ARRAY_RE.finditer(cs):
        name, body = m.group(1), m.group(2)
        if name not in ARRAYS:
            continue
        arr = ITEM_RE.findall(body)
        (out_dir / ARRAYS[name]).write_text(
            json.dumps(arr, ensure_ascii=False, indent=1), encoding="utf-8")
        found.add(name)
        print(f"{name}: {len(arr)} 件 -> {ARRAYS[name]}")

    missing = (set(DICTS) | set(ARRAYS)) - found
    if missing:
        raise SystemExit(f"抽出できなかったマスター: {sorted(missing)}")


if __name__ == "__main__":
    main()
