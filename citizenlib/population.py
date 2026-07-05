"""旧 PopulationChart / PopulationController の移植 (Phase 1: 市町村)。

入力: 旧リポジトリ App_Data/Population2015/City/pd{code}.json (国勢調査、1980-2015)
出力: DATA_CONTRACT.md §2.1 の市町村モデル / §3.1 の CityData 系列

2026-07-05: 2020年国勢調査(census最終列)と将来推計(projection全体)は、
IPSS「日本の地域別将来推計人口(令和5(2023)年推計)」に切替 (citizenlib/ipss.py)。
City/Pref が対象。Country (海外) は対象外で旧データ (2015年国勢調査 + 平成30年推計)
のまま (DATA_CONTRACT §2.4)。
"""
import json
from pathlib import Path

from . import masters

CENSUS_YEARS = list(range(1980, 2025, 5))      # 9列 (1980..2020)。2020列は IPSS 実績値。City/Pref 用
PROJECTION_YEARS = list(range(2020, 2055, 5))  # 7列 (2020..2050、IPSS 令和5年推計)。City/Pref 用
COUNTRY_CENSUS_YEARS = list(range(1980, 2020, 5))  # 8列 (1980..2015)。Country は IPSS 対象外のため旧仕様のまま


class SourceData:
    """旧 App_Data/Population2015 を一次ソースとして読む。"""

    def __init__(self, source_root: Path):
        base = Path(source_root) / "App_Data" / "Population2015"
        self.city_dir = base / "City"
        self.city_m_dir = base / "CityM"
        self.city_f_dir = base / "CityF"
        self.pref_dir = base / "Pref"
        self.pref_m_dir = base / "PrefM"
        self.pref_f_dir = base / "PrefF"
        self.country_dir = base / "Country"
        self.country_m_dir = base / "CountryM"
        self.country_f_dir = base / "CountryF"
        self.info2015 = base / "2015" / "population2015.json"
        self.ranking2045 = base / "Ranking" / "CityRanking2045.json"
        self.area = base / "Area" / "CityAreaData2015.json"
        self.tfr = base / "Tfr" / "CityTfr.xml"
        root = Path(source_root) / "App_Data"
        self.area_code_list = root / "NAreaCode" / "StandardAreaCodeList.json"
        self.census2010 = root / "Population2010" / "2010" / "census2010List.json"

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

    def load_pref_pd(self, pref: str) -> list:
        return self._load_rows(self.pref_dir, "pd", pref)

    def load_country_ed(self, code: str) -> list:
        return self._load_rows(self.country_dir, "ed", code)

    def load_country_ep(self, code: str) -> list:
        return self._load_rows(self.country_dir, "ep", code)

    def load_country_gender_ed(self, sex: str, code: str) -> list:
        """JP(Country)専用の男女別 census。非JP は Eurostat 側で取得するため未使用。"""
        d = self.country_m_dir if sex == "M" else self.country_f_dir
        return self._load_rows(d, "ed", code)

    def load_country_gender_ep(self, sex: str, code: str) -> list:
        d = self.country_m_dir if sex == "M" else self.country_f_dir
        return self._load_rows(d, "ep", code)

    def load_city_gender_pd(self, sex: str, code: str) -> list:
        d = self.city_m_dir if sex == "M" else self.city_f_dir
        return self._load_merged(d, "pd", code, masters.CODETRANS_PD)

    def load_pref_gender_pd(self, sex: str, pref: str) -> list:
        d = self.pref_m_dir if sex == "M" else self.pref_f_dir
        return self._load_rows(d, "pd", pref)

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

    def load_area_code_list(self) -> list:
        return json.loads(self.area_code_list.read_text(encoding="utf-8-sig"))

    def load_census2010(self) -> list:
        return json.loads(self.census2010.read_text(encoding="utf-8-sig"))


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


def _append_ipss_census(census: list, ipss_total: list) -> list:
    """census (21行×8列, 1980-2015) に IPSS の2020年列 (実績値) を1列追加する。

    census と ipss_total は共に Ages3 準拠の21行構成 (行の並びが一致)。
    """
    for row, ipss_row in zip(census, ipss_total):
        row["population"] = list(row["population"]) + [ipss_row["population"][0]]
    return census


def build_city_model(source: SourceData, code: str, ipss) -> dict:
    """DATA_CONTRACT §2.1 の市町村モデルを構築する。

    ipss: citizenlib.ipss.IpssData。2020年census列と将来推計全体の一次ソース。
    """
    ipss_city = ipss.city(code)
    fukushima = ipss_city is None  # IPSS未推計 = 福島県浜通り13町村 (2020年実績値も非公表)
    census = source.load_pd(code)
    projection = []
    years = CENSUS_YEARS[:-1]  # 8列 (1980-2015)。fukushima 以外は末尾に2020を追加
    if not fukushima:
        census = _append_ipss_census(census, ipss_city["total"])
        projection = ipss_city["total"]
        years = CENSUS_YEARS

    index = [_index_of(census, c, y, "census", True) for c, y in enumerate(years)]
    if projection:
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
    census は常に Ages3 構成 (21行)。projection は City/Pref(新IPSS方式、
    年齢不詳行ありの21行)と Country-JP(旧方式、年齢不詳行なしの20行)の
    どちらもありうるため、行数を見て自動判定する。
    """
    pds = model["census"][1:][::-1]   # [年齢不詳, 90歳以上, ..., 0～4歳] 20行
    n_cols = len(pds[0]["population"])
    out = [{"name": "年齢不詳", "data": pds[0]["population"][:n_cols]}]

    if not model["projection"]:
        # 旧 HukushimaCityData (福島県浜通り13町村専用の分岐。将来推計なし)。
        # 注意: 旧実装は name=pds[r] / data=pds[r+1] という1行ずれのバグがあった
        # (年齢不詳が2系列出る)。ここでは修正済み。
        # ゼロ埋め数は「非fukushimaと同じ15点(CENSUS_YEARS+PROJECTION_YEARS[1:])」に
        # 揃うように、census の不足分(9-n_cols)も含める (2020年国勢調査も非公表のため)。
        pad = (len(CENSUS_YEARS) - n_cols) + (len(PROJECTION_YEARS) - 1)
        for r in range(19):
            out.append({"name": pds[r + 1]["series"],
                        "data": pds[r + 1]["population"][:n_cols] + [0] * pad})
        return out

    pps = model["projection"][1:][::-1]  # 20行(新IPSS、年齢不詳含む) or 19行(旧Country-JP)
    if len(pps) == 20:
        pps = pps[1:]  # 年齢不詳行(常にゼロ)を落として90歳以上以降に揃える
    for r in range(19):
        out.append({"name": pds[r + 1]["series"],
                    "data": pds[r + 1]["population"][:n_cols] + pps[r]["population"][1:]})
    return out


def build_pref_model(source: SourceData, pref: str, ipss) -> dict:
    """DATA_CONTRACT §2.3 の都道府県モデルを構築する。都道府県は必ず IPSS 推計がある。"""
    ipss_pref = ipss.prefecture(pref)
    census = _append_ipss_census(source.load_pref_pd(pref), ipss_pref["total"])
    projection = ipss_pref["total"]
    assert len(census) == 21 and len(projection) == 21, pref

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

    日本 (kaikyu=90): census 21行×8列(1980-2015、Ages3) + projection 20行×7列
    (2015-2045、平成30年推計)。旧データのまま変更なし。
    日本以外 (kaikyu=85、2026-07-05 Eurostat/ONS へ切替): census 20行×9列
    (1980-2020、Ages2、Eurostat demo_pjangroup) + projection 20行×6列
    (2025-2050、90歳以上まで分離。EU/EFTA は EUROPOP2023、UK のみ
    Eurostat対象外のため ONS 2024年基準 Principal projection)。
    """
    from . import eurostat

    is_jp = code == "JP"
    if is_jp:
        census = source.load_country_ed(code)
        projection = source.load_country_ep(code)
        assert len(census) == 21 and len(projection) == 20, code
        census_years = COUNTRY_CENSUS_YEARS
        proj_years = list(range(2015, 2050, 5))
    else:
        census = eurostat.load_census(eurostat.GEO_CODES.get(code, code))
        projection = (eurostat.load_projection_uk() if code == "UK"
                     else eurostat.load_projection_eurostat(eurostat.GEO_CODES.get(code, code)))
        assert len(census) == 20 and len(census[0]["population"]) == 9, code
        assert len(projection) == 20 and len(projection[0]["population"]) == 6, code
        census_years = CENSUS_YEARS  # City/Pref と同じ 1980-2020 (9点)
        proj_years = eurostat.COUNTRY_PROJECTION_YEARS

    index = [_index_of(census, c, y, "census", is_jp) for c, y in enumerate(census_years)]
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

    2026-07-05 の Eurostat/ONS 切替後、非JPの census 最終年(2020)と
    projection 開始年(2025)は重複しない(旧データは両方 2015 年で重複していた)
    ため、projection 側の列は先頭を捨てずに全列使う。
    """
    if model["is_jp"]:
        return stacked_series(model)

    pds = model["census"][1:][::-1]      # [年齢不詳, 85歳以上, ..., 0～4歳] 19行
    pps = model["projection"][1:][::-1]  # [90歳以上, 85～89歳, ..., 0～4歳] 19行
    n_cols = len(pds[0]["population"])

    out = [{"name": "年齢不詳", "data": pds[0]["population"][:n_cols]}]
    # "90歳以上" は census 側に対応データがないため 0 を n_cols 個 (旧実装のまま)。
    out.append({"name": pps[0]["series"], "data": [0] * n_cols + pps[0]["population"]})
    for r in range(1, 19):
        out.append({"name": pps[r]["series"],
                    "data": pds[r]["population"][:n_cols] + pps[r]["population"]})
    return out


PYRAMID_CENSUS_YEARS = [(y, c) for c, y in enumerate(CENSUS_YEARS)]  # 9件 (1980..2020)
PYRAMID_PROJECTION_YEARS = [(y, c) for c, y in enumerate(PROJECTION_YEARS) if y > 2020]  # 6件 (2025..2050)


def build_city_pyramid_model(source: SourceData, code: str, ipss) -> dict:
    """DATA_CONTRACT §2.5 の人口ピラミッドモデル (男女別) を構築する。"""
    ipss_city = ipss.city(code)
    fukushima = ipss_city is None

    census_m = source.load_city_gender_pd("M", code)
    census_f = source.load_city_gender_pd("F", code)
    if not fukushima:
        census_m = _append_ipss_census(census_m, ipss_city["male"])
        census_f = _append_ipss_census(census_f, ipss_city["female"])
    projection_m = ipss_city["male"] if ipss_city else []
    projection_f = ipss_city["female"] if ipss_city else []

    census_years = PYRAMID_CENSUS_YEARS[:-1] if fukushima else PYRAMID_CENSUS_YEARS

    years = []
    max_value = 0
    for year, col in census_years:
        male = [r["population"][col] for r in census_m[1:20]]
        female = [r["population"][col] for r in census_f[1:20]]
        years.append({"year": year, "kind": "census", "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))
    if not fukushima:
        for year, col in PYRAMID_PROJECTION_YEARS:
            male = [r["population"][col] for r in projection_m[1:20]]
            female = [r["population"][col] for r in projection_f[1:20]]
            years.append({"year": year, "kind": "projection", "male": male, "female": female})
            max_value = max(max_value, max(male), max(female))

    return {
        "code": code,
        "fukushima": fukushima,
        "max_value": max_value,
        "years": years,
        # 生表示用の全列データ (テーブルは "years" の年別スライスではなく
        # こちらをそのまま描画する。census 21行×9列(fukushimaは8列)、
        # projection 21行×7列 or (fukushima 時) [])
        "census_m": census_m,
        "census_f": census_f,
        "projection_m": projection_m,
        "projection_f": projection_f,
    }


def build_pref_pyramid_model(source: SourceData, pref: str, ipss) -> dict:
    """DATA_CONTRACT §2.5 相当の都道府県版人口ピラミッドモデル。

    都道府県は市町村と異なり将来推計が必ずある (fukushima 相当の欠損なし)。
    """
    ipss_pref = ipss.prefecture(pref)
    census_m = _append_ipss_census(source.load_pref_gender_pd("M", pref), ipss_pref["male"])
    census_f = _append_ipss_census(source.load_pref_gender_pd("F", pref), ipss_pref["female"])
    projection_m = ipss_pref["male"]
    projection_f = ipss_pref["female"]

    years = []
    max_value = 0
    for year, col in PYRAMID_CENSUS_YEARS:
        male = [r["population"][col] for r in census_m[1:20]]
        female = [r["population"][col] for r in census_f[1:20]]
        years.append({"year": year, "kind": "census", "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))
    for year, col in PYRAMID_PROJECTION_YEARS:
        male = [r["population"][col] for r in projection_m[1:20]]
        female = [r["population"][col] for r in projection_f[1:20]]
        years.append({"year": year, "kind": "projection", "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))

    return {
        "code": pref,
        "max_value": max_value,
        "years": years,
        "census_m": census_m,
        "census_f": census_f,
        "projection_m": projection_m,
        "projection_f": projection_f,
    }


def build_country_pyramid_model(source: SourceData, code: str) -> dict:
    """DATA_CONTRACT §2.5 相当の国版人口ピラミッドモデル。

    JP: census 21行(Ages3、90歳以上を含む19区分)×8列(1980-2015、旧データ)、
    projection 20行×7列(2015-2045、旧データ)。census最終年とprojection先頭年
    が重複(2015年)するため1点スキップ(旧 stacked_series と同じ扱い)。
    非JP: census 20行(Ages2、90歳以上を含まない18区分)×9列(1980-2020、
    Eurostat)、projection 20行×6列(2025-2050、Eurostat/ONS)。census年は
    90歳以上に対応するデータがないため0で埋めて19区分に揃える
    (countrydata_series と同じ扱い)。census最終年(2020)とprojection先頭年
    (2025)は重複しないため全列使う。
    """
    from . import eurostat

    is_jp = code == "JP"
    if is_jp:
        census_m = source.load_country_gender_ed("M", code)
        census_f = source.load_country_gender_ed("F", code)
        projection_m = source.load_country_gender_ep("M", code)
        projection_f = source.load_country_gender_ep("F", code)
        census_years = list(enumerate(COUNTRY_CENSUS_YEARS))
        proj_years = list(range(2015, 2050, 5))
        proj_year_cols = [(c, y) for c, y in enumerate(proj_years) if y > 2015]
    else:
        geo = eurostat.GEO_CODES.get(code, code)
        census_m = eurostat.load_census(geo, "M")
        census_f = eurostat.load_census(geo, "F")
        projection_m = (eurostat.load_projection_uk("M") if code == "UK"
                        else eurostat.load_projection_eurostat(geo, "M"))
        projection_f = (eurostat.load_projection_uk("F") if code == "UK"
                        else eurostat.load_projection_eurostat(geo, "F"))
        census_years = list(enumerate(CENSUS_YEARS))
        proj_year_cols = list(enumerate(eurostat.COUNTRY_PROJECTION_YEARS))

    n_age_rows = len(census_m) - 2  # 総数・年齢不詳を除く実年齢区分数 (JP=19, 非JP=18)

    years = []
    max_value = 0
    for c, year in census_years:
        male = [r["population"][c] for r in census_m[1:1 + n_age_rows]]
        female = [r["population"][c] for r in census_f[1:1 + n_age_rows]]
        if n_age_rows == 18:  # 非JP: 90歳以上のデータが無いため0を足して19区分に揃える
            male.append(0)
            female.append(0)
        years.append({"year": year, "kind": "census", "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))
    for c, year in proj_year_cols:
        male = [r["population"][c] for r in projection_m[1:20]]
        female = [r["population"][c] for r in projection_f[1:20]]
        years.append({"year": year, "kind": "projection", "male": male, "female": female})
        max_value = max(max_value, max(male), max(female))

    return {
        "code": code,
        "is_jp": is_jp,
        "max_value": max_value,
        "years": years,
        "census_m": census_m,
        "census_f": census_f,
        "projection_m": projection_m,
        "projection_f": projection_f,
    }
