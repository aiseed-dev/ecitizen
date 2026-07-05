"""data/masters/*.json のローダ。抽出元は旧 PopulationClass.cs (tools/extract_masters.py)。"""
import json
from pathlib import Path

MASTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "masters"


def _load(name: str, default=None):
    path = MASTERS_DIR / name
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


PREF_CODE: dict = _load("prefcode.json")            # {"01": "北海道", ...} 47件
CITY_DIC: dict = _load("citydic20161010.json")      # {"01100": "札幌市", ...} 1741件
AGES2: list = _load("ages2.json")                   # 総数〜年齢不詳 20件 (日本以外の国用)
AGES3: list = _load("ages3.json")                   # 総数〜年齢不詳 21件
CODETRANS_PD: dict = _load("codetrans20151001.json")  # pd(国勢調査)用コード変換
CODETRANS_PP: dict = _load("codetrans20180401.json", default={})  # pp用(現行C#では空)
COUNTRY_CODE: dict = _load("countrycode.json")        # 33カ国 (JP含む)

# 旧サイトの RedirectToActionPermanent (PopulationController.City)
CITY_REDIRECTS = {
    "03305": "03216",  # 滝沢村 → 滝沢市
    "04423": "04216",  # 富谷町 → 富谷市
    "09367": "09203",  # 岩舟町 → 栃木市
}

# 旧 Utils.ChangeCodeAfter2010 (Models/Utils.cs)。ListOfCitiesByTfr のリンク先解決用
# (TFR統計は2010年以前のコードのままだが、City ページへのリンクは合併後コードにする)
CHANGE_CODE_AFTER_2010 = {
    "03422": "03209", "09321": "09203", "11226": "11203", "11445": "11246",
    "12402": "12239", "17344": "17212", "23304": "23238", "23481": "23213",
    "23482": "23213", "23483": "23213", "32304": "32203", "32401": "32203",
    "43201": "43100",
}


def cities_of_pref(pref: str) -> dict:
    """都道府県コード(2桁)配下の市町村 (定義順=コード順)。"""
    return {k: v for k, v in CITY_DIC.items() if k.startswith(pref)}
