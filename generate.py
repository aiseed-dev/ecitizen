#!/usr/bin/env python3
"""描画層ドライバ (DESIGN.md §3)。data/ から public/ を生成する。

usage:
  python generate.py --clean                 # 全 1,741 市町村
  python generate.py --codes 01100 13104     # 指定市町村のみ (開発用)
  python generate.py --limit 20              # 先頭 N 件のみ (開発用)
"""
import argparse
import datetime
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from citizenlib import masters
from citizenlib.filters import FILTERS
from citizenlib.population import citydata_series

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent / "eCitizen" / "eCitizen"
PUBLIC = ROOT / "public"
DATA_CITY = ROOT / "data" / "population" / "city"

# city ページ指数表の行定義 (pct=True は f1 書式)
INDEX_ROWS = [
    {"label": "年少人口", "key": "young", "pct": False},
    {"label": "年少人口割合(%)", "key": "young_pct", "pct": True},
    {"label": "生産年齢人口", "key": "working", "pct": False},
    {"label": "生産年齢人口割合(%)", "key": "working_pct", "pct": True},
    {"label": "老年人口", "key": "old", "pct": False},
    {"label": "老年人口割合(%)", "key": "old_pct", "pct": True},
    {"label": "後期老年人口", "key": "old_old", "pct": False},
    {"label": "後期老年人口割合(%)", "key": "old_old_pct", "pct": True},
    {"label": "年少人口指数", "key": "young_index", "pct": True},
    {"label": "老年人口指数", "key": "old_index", "pct": True},
    {"label": "従属人口指数", "key": "dependency_index", "pct": True},
    {"label": "老年化指数", "key": "aging_index", "pct": True},
]

REDIRECTS = """\
# 旧サイトの RedirectToActionPermanent (市町村合併)
/Population/City/03305 /Population/City/03216 301
/Population/City/04423 /Population/City/04216 301
/Population/City/09367 /Population/City/09203 301
"""

HEADERS = """\
# 人口系データは確定済みのため長期キャッシュ
/Population/CityData/*
  Cache-Control: public, max-age=86400
/Population/CityList/*
  Cache-Control: public, max-age=86400
/css/*
  Cache-Control: public, max-age=86400
/js/*
  Cache-Control: public, max-age=86400
/images/*
  Cache-Control: public, max-age=604800
/fonts/*
  Cache-Control: public, max-age=31536000, immutable
"""

# ワーカープロセス内で初期化されるグローバル
_env = None
_ctx_common = None


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=True, undefined=StrictUndefined)
    env.filters.update(FILTERS)
    return env


def load_config(path: Path) -> dict:
    defaults = {"ga4_id": "", "adsense_client": "",
                "adsense_slot_banner": "", "adsense_slot_rect": ""}
    if path.exists():
        defaults.update(json.loads(path.read_text(encoding="utf-8")))
    return defaults


def write_text(rel: str, text: str) -> None:
    path = PUBLIC / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _init_worker(config: dict, build_year: int, cityinfo: dict) -> None:
    global _env, _ctx_common
    _env = make_env()
    _ctx_common = {
        "config": config,
        "build_year": build_year,
        "nav_active": "population",
        "prefs": masters.PREF_CODE,
        "ages3": masters.AGES3,
        "index_rows": INDEX_ROWS,
        "_cityinfo": cityinfo,
    }


def _build_city(code: str) -> str:
    """1 市町村分: HTML + CityData JSON を生成 (ワーカープロセスで実行)。"""
    from citizenlib.charts import city_stack_svg  # matplotlib はワーカー側で import

    model = json.loads((DATA_CITY / f"{code}.json").read_text(encoding="utf-8"))
    series = citydata_series(model)

    write_text(f"Population/CityData/{code}.json", compact_json(series))

    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "page_title": f"{model['pref_name']}{model['name']} - 市町村別の5歳年齢階級別人口の推移",
        "chart_svg": city_stack_svg(model["name"], series),
        "pref_cities": masters.cities_of_pref(model["pref"]),
        "info": ctx["_cityinfo"].get(code),
    })
    html = _env.get_template("population/city.html").render(ctx)
    write_text(f"Population/City/{code}/index.html", html)
    return code


def copy_assets(source: Path) -> None:
    shutil.copytree(ROOT / "assets" / "css", PUBLIC / "css", dirs_exist_ok=True)
    shutil.copytree(ROOT / "assets" / "js", PUBLIC / "js", dirs_exist_ok=True)
    # フォントは woff2 と OFL ライセンスのみ配信 (ttf はビルド用)
    (PUBLIC / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "assets" / "fonts").iterdir():
        if f.suffix == ".woff2" or f.name == "OFL.txt":
            shutil.copy2(f, PUBLIC / "fonts" / f.name)
    (PUBLIC / "images").mkdir(parents=True, exist_ok=True)
    wwwroot = source / "wwwroot"
    for name in ("icon36x36.png", "excel.svg"):
        shutil.copy2(wwwroot / "images" / name, PUBLIC / "images" / name)
    for name in ("favicon.ico", "robots.txt"):
        shutil.copy2(wwwroot / name, PUBLIC / name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--codes", nargs="*")
    ap.add_argument("--build-year", type=int, default=datetime.date.today().year)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--config", type=Path, default=ROOT / "config.json")
    args = ap.parse_args()

    if args.clean and PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(exist_ok=True)

    config = load_config(args.config)
    cityinfo = {c["code"]: c for c in json.loads(
        (ROOT / "data" / "cityinfo2015.json").read_text(encoding="utf-8"))}

    codes = args.codes or list(masters.CITY_DIC)
    if args.limit:
        codes = codes[:args.limit]

    # CityList JSON (47 都道府県)
    for pref in masters.PREF_CODE:
        cities = [{"code": k, "name": v} for k, v in masters.cities_of_pref(pref).items()]
        write_text(f"Population/CityList/{pref}.json", compact_json(cities))

    # 市町村ページ + CityData JSON (チャート描画が重いので並列)
    with ProcessPoolExecutor(max_workers=args.jobs,
                             initializer=_init_worker,
                             initargs=(config, args.build_year, cityinfo)) as ex:
        done = 0
        for _ in ex.map(_build_city, codes, chunksize=16):
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(codes)}")

    copy_assets(args.source)
    write_text("_redirects", REDIRECTS)
    write_text("_headers", HEADERS)

    # スモークチェック (DESIGN.md §10)
    n_html = len(list(PUBLIC.glob("Population/City/*/index.html")))
    n_json = len(list(PUBLIC.glob("Population/CityData/*.json")))
    n_list = len(list(PUBLIC.glob("Population/CityList/*.json")))
    n_files = sum(1 for p in PUBLIC.rglob("*") if p.is_file())
    assert n_html == len(codes), f"HTML {n_html} != {len(codes)}"
    assert n_json == len(codes), f"JSON {n_json} != {len(codes)}"
    assert n_list == 47
    print(f"HTML {n_html} / CityData {n_json} / CityList {n_list} / 総ファイル数 {n_files}")
    if n_files > 15000:
        print(f"警告: ファイル数 {n_files} — Cloudflare Pages の上限 20,000 に接近 (DESIGN.md §9.1)")


if __name__ == "__main__":
    main()
