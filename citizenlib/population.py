"""旧 PopulationChart / PopulationController の移植 (Phase 1: 市町村)。

入力: 旧リポジトリ App_Data/Population2015/City/pd{code}.json (国勢調査 21行×8列)
                                             pp{code}.json (将来推計 20行×7列)
出力: DATA_CONTRACT.md §2.1 の市町村モデル / §3.1 の CityData 系列
"""
import json
from pathlib import Path

from . import masters

CENSUS_YEARS = list(range(1980, 2020, 5))      # 8列
PROJECTION_YEARS = list(range(2015, 2050, 5))  # 7列


class SourceData:
    """旧 App_Data/Population2015 を一次ソースとして読む。"""

    def __init__(self, source_root: Path):
        self.city_dir = Path(source_root) / "App_Data" / "Population2015" / "City"
        self.info2015 = Path(source_root) / "App_Data" / "Population2015" / "2015" / "population2015.json"

    def _load_rows(self, prefix: str, code: str) -> list:
        rows = json.loads((self.city_dir / f"{prefix}{code}.json").read_text(encoding="utf-8-sig"))
        return [{"series": r["Series"], "population": list(r["Population"])} for r in rows]

    def _load_merged(self, prefix: str, code: str, trans: dict) -> list:
        """旧 PopulationChart.LoadCityData: コード変換表にあれば旧コードの値を合算。"""
        if code in trans:
            merged = None
            for old in trans[code].split(":"):
                rows = self._load_rows(prefix, old)
                if merged is None:
                    merged = rows
                else:
                    for m, r in zip(merged, rows):
                        m["population"] = [a + b for a, b in zip(m["population"], r["population"])]
            return merged
        return self._load_rows(prefix, code)

    def load_pd(self, code: str) -> list:
        return self._load_merged("pd", code, masters.CODETRANS_PD)

    def load_pp(self, code: str) -> list:
        if code.startswith("07"):  # 福島県: 将来推計は非公表
            return []
        return self._load_merged("pp", code, masters.CODETRANS_PP)

    def load_cityinfo2015(self) -> list:
        return json.loads(self.info2015.read_text(encoding="utf-8-sig"))


def _index_of(rows: list, column: int, year: int, kind: str, include90_in_old: bool) -> dict:
    """1列(1調査年)分の人口指数。旧 SetIndexCensusAll / SetIndexProjectionAll の中身。

    行 index は総数(0)を含む: 1..3=0-14歳, 4..13=15-64歳, 14..19=65歳以上。
    census(kaikyu=90)とprojectionはどちらも90歳以上(行19)を老年・後期老年に含める。
    """
    pop = [r["population"][column] for r in rows]
    young = pop[1] + pop[2] + pop[3]
    working = sum(pop[4:14])
    old = sum(pop[14:19]) + (pop[19] if include90_in_old else 0)
    old_old = pop[16] + pop[17] + pop[18] + (pop[19] if include90_in_old else 0)
    total = young + working + old  # 年齢不詳は分母に含めない

    def ratio(a, b):
        # 避難等で人口 0 の調査年 (福島6町村の2015年・三宅村の2000年) は null。
        # 旧 C# は NaN/∞ を表示していたが、描画層で「-」表示に置き換える。
        return a / b * 100.0 if b else None

    return {
        "year": year,
        "kind": kind,
        "young": young,
        "working": working,
        "old": old,
        "old_old": old_old,
        "young_pct": ratio(young, total),
        "working_pct": ratio(working, total),
        "old_pct": ratio(old, total),
        "old_old_pct": ratio(old_old, total),
        "young_index": ratio(young, working),
        "old_index": ratio(old, working),
        "dependency_index": ratio(young + old, working),
        "aging_index": ratio(old, young),
    }


def build_city_model(source: SourceData, code: str) -> dict:
    """DATA_CONTRACT §2.1 の市町村モデルを構築する。"""
    census = source.load_pd(code)
    projection = source.load_pp(code)
    fukushima = code.startswith("07")

    index = [_index_of(census, c, y, "census", True)
             for c, y in enumerate(CENSUS_YEARS)]
    if not fukushima:
        # 将来推計行は 90歳以上が老年に必ず含まれる (旧 SetIndexProjectionAll)
        index += [_index_of(projection, c, y, "projection", True)
                  for c, y in enumerate(PROJECTION_YEARS)]

    pref = code[:2]
    return {
        "code": code,
        "name": masters.CITY_DIC[code],
        "pref": pref,
        "pref_name": masters.PREF_CODE[pref],
        "fukushima": fukushima,
        "census": census,
        "projection": projection,
        "index": index,
    }


def citydata_series(model: dict) -> list:
    """公開 JSON `Population/CityData/{code}.json` (DATA_CONTRACT §3.1)。

    系列順は 年齢不詳 → 90歳以上 → … → 0～4歳 (旧 CityData / HukushimaCityData)。
    """
    pds = model["census"][1:][::-1]   # [年齢不詳, 90歳以上, ..., 0～4歳] 20行
    out = [{"name": "年齢不詳", "data": pds[0]["population"][:8]}]

    if model["fukushima"]:
        # 注意: 旧 HukushimaCityData は name=pds[r] / data=pds[r+1] という
        # 1行ずれのバグがあった (年齢不詳が2系列出る)。ここでは修正済み。
        for r in range(19):
            out.append({"name": pds[r + 1]["series"],
                        "data": pds[r + 1]["population"][:8] + [0] * 5})
        return out

    pps = model["projection"][1:][::-1]  # [90歳以上, ..., 0～4歳] 19行
    for r in range(19):
        out.append({"name": pps[r]["series"],
                    "data": pds[r + 1]["population"][:8] + pps[r]["population"][1:7]})
    return out
