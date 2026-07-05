#!/usr/bin/env python3
"""Eurostat から Country(海外)ページ用の census/projection を1回限り取得し、
data/raw/eurostat/ にキャッシュする (再生成可能。git 管理外)。

- census: demo_pjangroup (男女，年齢(5歳階級)別人口。年次実績値、appId不要)
- projection: proj_23np (EUROPOP2023、1歳刻み。基準シナリオ BSL のみ取得)

男女計(T)・男(M)・女(F)を1回のリクエストにまとめて取得する
(CountryPyramid 用。sex 次元を複数指定可能)。

出典:
  https://ec.europa.eu/eurostat/databrowser/view/demo_pjangroup
  https://ec.europa.eu/eurostat/databrowser/view/proj_23np

usage: python tools/fetch_eurostat.py
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from citizenlib.eurostat import COUNTRY_PROJECTION_YEARS, GEO_CODES  # noqa: E402
from citizenlib.population import CENSUS_YEARS  # noqa: E402

OUT_DIR = ROOT / "data" / "raw" / "eurostat"
API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
USER_AGENT = "Mozilla/5.0 (eCitizenStatic build; https://github.com/aiseed-dev/ecitizen)"
SEXES = ["T", "M", "F"]


def _get(dataset: str, params: dict, geos: list) -> dict:
    query = (urllib.parse.urlencode(params)
            + "".join(f"&geo={g}" for g in geos)
            + "".join(f"&sex={s}" for s in SEXES))
    url = f"{API_BASE}/{dataset}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("error"):
        raise RuntimeError(f"Eurostat API エラー ({dataset}): {body['error']}")
    return body


def fetch_census() -> None:
    """demo_pjangroup: 年ごとに32地域分(EU集計込み)×男女計/男/女を一括取得。"""
    geos = list(GEO_CODES.values())
    by_year = {}
    for year in CENSUS_YEARS:
        body = _get("demo_pjangroup", {"format": "JSON", "lang": "EN", "time": year}, geos)
        by_year[year] = body
        print(f"census {year}年 取得完了")
        time.sleep(0.3)
    (OUT_DIR / "census.json").write_text(json.dumps(by_year), encoding="utf-8")


def fetch_projection() -> None:
    """proj_23np: 年ごとに一括取得 (UK は EUROPOP2023 対象外なので自動的に除外される)。"""
    geos = [g for code, g in GEO_CODES.items() if code != "UK"]
    by_year = {}
    for year in COUNTRY_PROJECTION_YEARS:
        body = _get("proj_23np", {"format": "JSON", "lang": "EN", "projection": "BSL", "time": year}, geos)
        by_year[year] = body
        print(f"projection {year}年 取得完了")
        time.sleep(0.3)
    (OUT_DIR / "projection.json").write_text(json.dumps(by_year), encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetch_census()
    fetch_projection()


if __name__ == "__main__":
    main()
