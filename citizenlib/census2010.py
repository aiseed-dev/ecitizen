"""旧 Population2010Controller.Census2010 の移植 (DATA_CONTRACT.md §2.8)。

2010年国勢調査人口と、国立社会保障・人口問題研究所「市区町村別将来推計人口
(2008年12月推計)」の2010年推計値との比較。新規の外部データ取得は不要
(旧 App_Data/Population2010・App_Data/NAreaCode をそのまま一次ソースとして
使う。ローカル完結、K5準拠)。
"""
from . import masters

_WARD = 8  # StandardAreaCode.種別 の enum 値 (自治体種別.区)
_CENSUS2010_DATE = "2010-10-01"


def _area_index(area_code_list: list) -> dict:
    """id -> 2010-10-01時点で有効な名称・種別 (旧 NAreaCodeService.GetAreaCode)。"""
    idx = {}
    for a in area_code_list:
        if a["施行年月日"][:10] <= _CENSUS2010_DATE < a["廃止年月日"][:10]:
            idx[a["id"]] = {"name": a["名称"], "type": a["種別"]}
    return idx


def _calc(popu2010: int, popu2005: int, popu2000: int, est2010: int, closed2010: int) -> dict:
    inc = popu2010 - popu2005
    est_diff = popu2010 - est2010
    net_inc = popu2010 - closed2010
    return {
        "popu2010": popu2010, "popu2005": popu2005, "popu2000": popu2000,
        "est2010": est2010, "closed2010": closed2010,
        "inc": inc, "est_diff": est_diff, "net_inc": net_inc,
        "inc_rate": inc * 100.0 / popu2005 if popu2005 else None,
        "est_diff_rate": est_diff * 100.0 / est2010 if est2010 else None,
        "net_inc_rate": net_inc * 100.0 / closed2010 if closed2010 else None,
    }


def build_census2010_rows(census: list, area_code_list: list) -> list:
    """1行 = 都道府県ヘッダー行(is_pref=True、傘下市区町村の合計)、または
    市区町村・行政区の行。コード順(=引数 census の順序どおり)。

    行政区(政令指定都市の区。種別==8)は都道府県合計に含めない
    (親の市の行が既に計上済みのため。旧実装の分岐と同じ)。
    """
    area_idx = _area_index(area_code_list)
    rows = []
    pref = 0
    pref_row = None
    sums = [0, 0, 0, 0, 0]

    for c in census:
        code = c["Id"]
        if pref != code // 1000:
            if pref_row is not None:
                pref_row.update(_calc(*sums))
            pref = code // 1000
            pref_row = {"code": pref * 1000, "name": masters.PREF_CODE[f"{pref:02d}"], "is_pref": True, "is_ward": False}
            rows.append(pref_row)
            sums = [0, 0, 0, 0, 0]

        area = area_idx.get(code)
        is_ward = bool(area) and area["type"] == _WARD
        name = area["name"] if area else f"(コード{code})"
        values = (c["Popu2010"], c["Popu2005"], c["Popu2000"], c["Est2010"], c["Closed2010"])
        row = {"code": code, "name": ("　" + name) if is_ward else name,
               "is_pref": False, "is_ward": is_ward}
        row.update(_calc(*values))
        rows.append(row)
        if not is_ward:
            sums = [s + v for s, v in zip(sums, values)]

    if pref_row is not None:
        pref_row.update(_calc(*sums))

    return rows
