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
        base = Path(source_root) / "App_Data" / "Population2015"
        self.city_dir = base / "City"
        self.city_m_dir = base / "CityM"
        self.city_f_dir = base / "CityF"
        self.pref_dir = base / "Pref"
        self.country_dir = base / "Country"
        self.info2015 = base / "2015" / "population2015.json"
        self.ranking2045 = base / "Ranking" / "CityRanking2045.json"
        self.area = base / "Area" / "CityAreaData2015.json"
        self.tfr = base / "Tfr" / "CityTfr.xml"

    @staticmethod
    def _read_rows(path: Path) -> list:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
        return [{"series": r["Series"], "population": list(r["Population"])} for r in rows]

    def _load_rows(self, directory: Path, prefix: str, code: str) -> list:
        return self._read_rows(directory / f"{prefix}{code}.json")

    def _load_merged(self, directory: Path, prefix: str, code: str, trans: dict) -> list:
        """旧 PopulationChart.LoadCityData: コード変換表にあれば旧コードの値を合算。"""
        if code in trans:
            merged = None
            for old in trans[code].split(":"):
                rows = self._load_rows(directory, prefix, old)
                if merged is None:
                    merged = rows
                else:
                    for m, r in zip(merged, rows):
                        m["population"] = [a + b for a, b in zip(m["population"], r["population"])]
            return merged
        return self._load_rows(directory, prefix, code)

    def load_pd(self, code: str) -> list:
        return self._load_merged(self.city_dir, "pd", code, masters.CODETRANS_PD)

    def load_pp(self, code: str) -> list:
        if code.startswith("07"):  # 福島県: 将来推計は非公表
            return []
        return self._load_merged(self.city_dir, "pp", code, masters.CODETRANS_PP)

    def load_pref_pd(self, pref: str) -> list:
        return self._load_rows(self.pref_dir, "pd", pref)

    def load_pref_pp(self, pref: str) -> list:
        return self._load_rows(self.pref_dir, "pp", pref)

    def load_country_ed(self, code: str) -> list:
        return self._load_rows(self.country_dir, "ed", code)

    def load_country_ep(self, code: str) -> list:
        return self._load_rows(self.country_dir, "ep", code)

    def load_city_gender_pd(self, sex: str, code: str) -> list:
        d = self.city_m_dir if sex == "M" else self.city_f_dir
        return self._load_merged(d, "pd", code, masters.CODETRANS_PD)

    def load_city_gender_pp(self, sex: str, code: str) -> list:
        if code.startswith("07"):
            return []
        d = self.city_m_dir if sex == "M" else self.city_f_dir
        return self._load_merged(d, "pp", code, masters.CODETRANS_PP)

    def load_cityinfo2015(self) -> list:
        return json.loads(self.info2015.read_text(encoding="utf-8-sig"))

    def load_ranking2045(self) -> list:
        return json.loads(self.ranking2045.read_text(encoding="utf-8-sig"))

    def load_area(self) -> list:
        return json.loads(self.area.read_text(encoding="utf-8-sig"))

    def load_tfr(self) -> list:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.tfr.read_text(encoding="utf-8-sig"))
        return [{"code": el.find("Code").text, "name": el.find("Name").text,
                 "tfr": el.find("Tfr").text} for el in root.findall("CityTfr")]


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


def stacked_series(model: dict) -> list:
    """公開 JSON `Population/CityData` / `PrefData` / (JP の) `CountryData` (DATA_CONTRACT §3.1/3.3)。

    系列順は 年齢不詳 → 90歳以上 → … → 0～4歳 (旧 CityData / PrefData / HukushimaCityData)。
    census/projection とも 21行/20行の Ages3 構成であること (Pref・City・国JP用)。
    """
    pds = model["census"][1:][::-1]   # [年齢不詳, 90歳以上, ..., 0～4歳] 20行
    out = [{"name": "年齢不詳", "data": pds[0]["population"][:8]}]

    if not model["projection"]:
        # 旧 HukushimaCityData (福島県の市町村専用の分岐。将来推計なし)。
        # 注意: 旧実装は name=pds[r] / data=pds[r+1] という1行ずれのバグがあった
        # (年齢不詳が2系列出る)。ここでは修正済み。
        for r in range(19):
            out.append({"name": pds[r + 1]["series"],
                        "data": pds[r + 1]["population"][:8] + [0] * 5})
        return out

    pps = model["projection"][1:][::-1]  # [90歳以上, ..., 0～4歳] 19行
    for r in range(19):
        out.append({"name": pps[r]["series"],
                    "data": pds[r + 1]["population"][:8] + pps[r]["population"][1:7]})
    return out


def build_pref_model(source: SourceData, pref: str) -> dict:
    """DATA_CONTRACT §2.3 の都道府県モデルを構築する。"""
    census = source.load_pref_pd(pref)
    projection = source.load_pref_pp(pref)
    assert len(census) == 21 and len(projection) == 20, pref

    index = [_index_of(census, c, y, "census", True) for c, y in enumerate(CENSUS_YEARS)]
    index += [_index_of(projection, c, y, "projection", True) for c, y in enumerate(PROJECTION_YEARS)]

    return {
        "code": pref,
        "name": masters.PREF_CODE[pref],
        "census": census,
        "projection": projection,
        "index": index,
    }


def build_country_model(source: SourceData, code: str) -> dict:
    """DATA_CONTRACT §2.4 の国モデルを構築する。

    日本 (kaikyu=90): census 21行 (Ages3, 90歳以上を分離)。
    日本以外 (kaikyu=85): census 20行 (Ages2, 85歳以上で合算)。
    projection はどの国も20行 (90歳以上まで分離済み) だが、列数(何年まで推計が
    あるか)は国ごとに異なる (CH・IS のみ2045年分が無く6列、他は7列。旧 C# の
    SetIndexProjectionAll も列数固定ではなく実データ依存だったため踏襲する)。
    """
    is_jp = code == "JP"
    census = source.load_country_ed(code)
    projection = source.load_country_ep(code)
    assert len(projection) == 20, code
    if is_jp:
        assert len(census) == 21, code
    else:
        assert len(census) == 20, code

    proj_cols = len(projection[1]["population"])
    proj_years = [2015 + 5 * c for c in range(proj_cols)]

    index = [_index_of(census, c, y, "census", is_jp) for c, y in enumerate(CENSUS_YEARS)]
    index += [_index_of(projection, c, y, "projection", True) for c, y in enumerate(proj_years)]

    return {
        "code": code,
        "name": masters.COUNTRY_CODE[code],
        "is_jp": is_jp,
        "census": census,
        "projection": projection,
        "index": index,
    }


def countrydata_series(model: dict) -> list:
    """公開 JSON `Population/CountryData/{code}.json` (DATA_CONTRACT §3.4)。

    JP は stacked_series と同一。JP 以外は census(Ages2,85歳以上で合算)と
    projection(常に90歳以上まで分離)の粒度がずれるため、旧 CountryData の
    分岐をそのまま再現する。
    """
    if model["is_jp"]:
        return stacked_series(model)

    pds = model["census"][1:][::-1]      # [年齢不詳, 85歳以上, ..., 0～4歳] 19行
    pps = model["projection"][1:][::-1]  # [90歳以上, 85～89歳, ..., 0～4歳] 19行

    out = [{"name": "年齢不詳", "data": pds[0]["population"][:8]}]
    # "90歳以上" は census 側に対応データがないため 0 を8個 (旧実装のまま)。
    # projection の列数は国により異なる (CH・IS は2045年分なし、6列) ため [1:] で可変長のまま渡す。
    out.append({"name": pps[0]["series"], "data": [0] * 8 + pps[0]["population"][1:]})
    for r in range(1, 19):
        out.append({"name": pps[r]["series"],
                    "data": pds[r]["population"][:8] + pps[r]["population"][1:]})
    return out


PYRAMID_YEARS = [(y, "census", c) for c, y in enumerate(CENSUS_YEARS)] + \
                [(y, "projection", c) for c, y in enumerate(PROJECTION_YEARS) if y >= 2020]


def build_city_pyramid_model(source: SourceData, code: str) -> dict:
    """DATA_CONTRACT §2.5 の人口ピラミッドモデル (男女別) を構築する。"""
    census_m = source.load_city_gender_pd("M", code)
    census_f = source.load_city_gender_pd("F", code)
    projection_m = source.load_city_gender_pp("M", code)
    projection_f = source.load_city_gender_pp("F", code)
    fukushima = code.startswith("07")

    years = []
    max_value = 0
    for year, kind, col in PYRAMID_YEARS:
        if kind == "projection" and fukushima:
            continue
        cm, cf = (census_m, census_f) if kind == "census" else (projection_m, projection_f)
        male = [r["population"][col] for r in cm[1:20]]
        female = [r["population"][col] for r in cf[1:20]]
        years.append({"year": year, "kind": kind, "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))

    return {
        "code": code,
        "max_value": max_value,
        "years": years,
        # 生表示用の全列データ (テーブルは "years" の年別スライスではなく
        # こちらをそのまま描画する。census 21行×8列、projection 20行×7列 or [])
        "census_m": census_m,
        "census_f": census_f,
        "projection_m": projection_m,
        "projection_f": projection_f,
    }
