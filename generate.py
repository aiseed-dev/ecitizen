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
import re
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from citizenlib import masters, rankings
from citizenlib.charts import (
    SOURCE_NOTE_EUROSTAT, SOURCE_NOTE_IPSS, age4_stack_svg, city_pyramid_svg, city_stack_svg,
)
from citizenlib.eurostat import COUNTRY_PROJECTION_YEARS as EUROSTAT_PROJECTION_YEARS
from citizenlib.filters import FILTERS
from citizenlib.population import (
    CENSUS_YEARS, PROJECTION_YEARS, age4_series, countrydata_series,
    stacked_series,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT.parent / "eCitizen" / "eCitizen"
PUBLIC = ROOT / "public"
DATA_CITY = ROOT / "data" / "population" / "city"
DATA_PREF = ROOT / "data" / "population" / "pref"
DATA_COUNTRY = ROOT / "data" / "population" / "country"
DATA_PYRAMID = ROOT / "data" / "population" / "pyramid" / "city"
DATA_PREF_PYRAMID = ROOT / "data" / "population" / "pyramid" / "pref"
DATA_COUNTRY_PYRAMID = ROOT / "data" / "population" / "pyramid" / "country"
DATA_RANKINGS = ROOT / "data" / "rankings"

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
# 旧 X-12-ARIMA 記事はアーカイブへ (DESIGN.md §19)
/x-12-arima/win-x-12* /x-12-arima/archive/win-x-12/ 301
/x-12-arima/gdp* /x-12-arima/archive/gdp/ 301
/x-12-arima/x-12-arima-examples* /x-12-arima/archive/x-12-arima-examples/ 301
/x-12-arima/x-12-arima* /x-12-arima/archive/x-12-arima/ 301
# 旧 Aging2015/Young2015 (e-Stat直叩き) は2020年版へ
/Population/Aging2015* /Population/Aging2020/ 301
/Population/Young2015* /Population/Young2020/ 301
/population/Aging2015* /Population/Aging2020/ 301
/population/Young2015* /Population/Young2020/ 301
# 旧サイトの RedirectToActionPermanent (市町村合併)
/Population/City/03305 /Population/City/03216 301
/Population/City/04423 /Population/City/04216 301
/Population/City/09367 /Population/City/09203 301
/Population/CityPyramid/03305 /Population/CityPyramid/03216 301
/Population/CityPyramid/04423 /Population/CityPyramid/04216 301
/Population/CityPyramid/09367 /Population/CityPyramid/09203 301
"""

HEADERS = """\
# 人口系データは確定済みのため長期キャッシュ
/Population/CityData/*
  Cache-Control: public, max-age=86400
/Population/CityList/*
  Cache-Control: public, max-age=86400
/Population/PrefData/*
  Cache-Control: public, max-age=86400
/Population/CountryData/*
  Cache-Control: public, max-age=86400
# Statdb カタログ (スナップショット。再取得までは不変)
/Statdb/data/*
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
        "countries": masters.COUNTRY_CODE,
        "ages2": masters.AGES2,
        "ages3": masters.AGES3,
        "index_rows": INDEX_ROWS,
        "_cityinfo": cityinfo,
    }


def _build_city(code: str) -> str:
    """1 市町村分: City + CityPyramid の HTML と CityData JSON を生成 (ワーカープロセスで実行)。"""
    model = json.loads((DATA_CITY / f"{code}.json").read_text(encoding="utf-8"))
    series = stacked_series(model)
    write_text(f"Population/CityData/{code}.json", compact_json(series))

    census_years = CENSUS_YEARS[:-1] if model["fukushima"] else CENSUS_YEARS
    # グラフは fukushima でも常に15点 (CENSUS_YEARS+PROJECTION_YEARS[1:]) に揃える。
    # stacked_series 側もゼロ埋め数を合わせている (citizenlib/population.py 参照)
    chart_years = CENSUS_YEARS + PROJECTION_YEARS[1:]

    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "census_years": census_years,
        "page_title": f"{model['pref_name']}{model['name']} - 市町村別の5歳年齢階級別人口の推移",
        "chart_svg": city_stack_svg(model["name"], series, chart_years),
        "pref_cities": masters.cities_of_pref(model["pref"]),
        "info": ctx["_cityinfo"].get(code),
    })
    html = _env.get_template("population/city.html").render(ctx)
    write_text(f"Population/City/{code}/index.html", html)

    pyramid = json.loads((DATA_PYRAMID / f"{code}.json").read_text(encoding="utf-8"))
    svgs = [(y["year"], y["kind"],
             city_pyramid_svg(model["name"], y["year"], y["male"], y["female"], pyramid["max_value"]))
            for y in pyramid["years"]]
    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "pyramid": pyramid,
        "svgs": svgs,
        "census_years": census_years,
        "page_title": f"{model['pref_name']}{model['name']} - 市町村別の男女別5歳年齢階級別人口 人口ピラミッド",
        "pref_cities": masters.cities_of_pref(model["pref"]),
    })
    html = _env.get_template("population/city_pyramid.html").render(ctx)
    write_text(f"Population/CityPyramid/{code}/index.html", html)
    return code


def _build_pref(pref: str) -> str:
    model = json.loads((DATA_PREF / f"{pref}.json").read_text(encoding="utf-8"))
    series = stacked_series(model)
    write_text(f"Population/PrefData/{pref}.json", compact_json(series))
    chart_years = CENSUS_YEARS + PROJECTION_YEARS[1:]

    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "page_title": f"{model['name']} - 都道府県別の5歳年齢階級別人口の推移",
        "chart_svg": city_stack_svg(model["name"], series, chart_years),
    })
    html = _env.get_template("population/prefecture.html").render(ctx)
    write_text(f"Population/Prefecture/{pref}/index.html", html)

    pyramid = json.loads((DATA_PREF_PYRAMID / f"{pref}.json").read_text(encoding="utf-8"))
    svgs = [(y["year"], y["kind"],
             city_pyramid_svg(model["name"], y["year"], y["male"], y["female"], pyramid["max_value"]))
            for y in pyramid["years"]]
    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "pyramid": pyramid,
        "svgs": svgs,
        "page_title": f"{model['name']} - 都道府県別の男女別5歳年齢階級別人口 人口ピラミッド",
    })
    html = _env.get_template("population/pref_pyramid.html").render(ctx)
    write_text(f"Population/PrefPyramid/{pref}/index.html", html)
    return pref


def _build_country(code: str) -> str:
    model = json.loads((DATA_COUNTRY / f"{code}.json").read_text(encoding="utf-8"))
    series = countrydata_series(model)
    write_text(f"Population/CountryData/{code}.json", compact_json(series))

    if model["is_jp"]:
        # 2026-07-06: JP も IPSS 令和5年推計 (47都道府県合算) へ更新。
        # City/Pref と同じく census 最終年(2020)と projection 開始年(2020)が
        # 重複するため [1:] で1点飛ばす。
        census_years = CENSUS_YEARS
        proj_years = PROJECTION_YEARS
        source_note = SOURCE_NOTE_IPSS
        chart_years = census_years + proj_years[1:]
    else:
        # Eurostat(EUROPOP2023)/ONS(UKのみ) へ切替。census は City/Pref と同じ1980-2020だが、
        # census 最終年(2020)と projection 開始年(2025)は重複しないため丸ごと連結する。
        census_years = CENSUS_YEARS
        proj_years = EUROSTAT_PROJECTION_YEARS
        source_note = SOURCE_NOTE_EUROSTAT
        chart_years = census_years + proj_years

    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "census_years": census_years,
        "proj_years": proj_years,
        "page_title": f"{model['name']} - 各国の5歳年齢階級別人口の推移",
        "chart_svg": city_stack_svg(model["name"], series, chart_years, source_note=source_note),
    })
    html = _env.get_template("population/country.html").render(ctx)
    write_text(f"Population/Country/{code}/index.html", html)

    # 人口ピラミッド用の推計年 (JP は census 最終年と重複する2020年を除く6点、
    # 非JP は重複がないため6点そのまま。country.html 用の proj_years とは別物)
    pyramid_proj_years = proj_years[1:] if model["is_jp"] else proj_years

    pyramid = json.loads((DATA_COUNTRY_PYRAMID / f"{code}.json").read_text(encoding="utf-8"))
    svgs = [(y["year"], y["kind"],
             city_pyramid_svg(model["name"], y["year"], y["male"], y["female"], pyramid["max_value"]))
            for y in pyramid["years"]]
    ctx = dict(_ctx_common)
    ctx.update({
        "m": model,
        "pyramid": pyramid,
        "svgs": svgs,
        "census_years": census_years,
        "proj_years": pyramid_proj_years,
        "page_title": f"{model['name']} - 各国の男女別5歳年齢階級別人口 人口ピラミッド",
    })
    html = _env.get_template("population/country_pyramid.html").render(ctx)
    write_text(f"Population/CountryPyramid/{code}/index.html", html)
    return code


def build_rankings(ctx_common: dict) -> None:
    """ランキング系ページ (地域別データなし、非並列で十分高速)。"""
    env = make_env()

    national = json.loads((DATA_RANKINGS / "ranking2050_national.json").read_text(encoding="utf-8"))
    html = env.get_template("population/ranking2050.html").render(
        dict(ctx_common, ranking=national, page_title="2050年市町村将来推計人口ランキング"))
    write_text("Population/Ranking/index.html", html)

    for pref in masters.PREF_CODE:
        r = json.loads((DATA_RANKINGS / "ranking2050_pref" / f"{pref}.json").read_text(encoding="utf-8"))
        html = env.get_template("population/ranking2050_pref.html").render(
            dict(ctx_common, r=r, page_title=f"2050年{r['pref_name']}の市町村将来推計人口ランキング"))
        write_text(f"Population/Ranking/{pref}/index.html", html)

    area = json.loads((DATA_RANKINGS / "cityarea.json").read_text(encoding="utf-8"))
    html = env.get_template("population/cityarea.html").render(
        dict(ctx_common, rows=area, page_title="市区町村の面積ランキング"))
    write_text("Population/ListOfCitiesByArea/index.html", html)

    tfr = json.loads((DATA_RANKINGS / "citytfr.json").read_text(encoding="utf-8"))
    html = env.get_template("population/citytfr.html").render(
        dict(ctx_common, rows=tfr, page_title="市区町村の特殊合計出生率ランキング"))
    write_text("Population/ListOfCitiesByTfr/index.html", html)

    # IPSS 令和5年推計 (2020→2050) を使って再計算 (data/rankings/*.json 参照。旧ファイル名の
    # "2045" は据え置きだが、中身は2050年までの推計値)
    aging = json.loads((DATA_RANKINGS / "city_aging_2045.json").read_text(encoding="utf-8"))
    html = env.get_template("population/city_generation_ranking.html").render(dict(
        ctx_common, rows=aging, field="old", page_title="今後高齢者が増加する市町村ランキング",
        page_h2="今後高齢者が増加する市町村のランキング",
        page_lead="国立社会保障・人口問題研究所の『日本の地域別将来推計人口(令和5(2023)年推計)』を使って、"
                  "2020年から2050年の30年間で65歳以上の人口が増加する市区町村のランキングを作成してみました。"
                  "首都圏では高齢者がまだ急増すると推計される市区町村が多い一方、地方では高齢者の人口が減少すると"
                  "推計されている市町村も多く、数からいえば減少する市町村が多くなっています。"
                  "今後は、75歳以上の後期高齢者の人口が急増します"
                  "(参照 <a href=\"/Population/CityOldOld2045/\">今後高齢者が増加する市町村のランキング</a>)。"))
    write_text("Population/CityAging2045/index.html", html)

    oldold = json.loads((DATA_RANKINGS / "city_oldold_2045.json").read_text(encoding="utf-8"))
    html = env.get_template("population/city_generation_ranking.html").render(dict(
        ctx_common, rows=oldold, field="old_old", page_title="今後後期高齢者が増加する市町村ランキング",
        page_h2="今後後期高齢者(75歳以上)が増加する市町村のランキング",
        page_lead="国立社会保障・人口問題研究所の『日本の地域別将来推計人口(令和5(2023)年推計)』を使って、"
                  "2020年から2050年の30年間で75歳以上の人口が増加する市区町村のランキングを作成してみました。"))
    write_text("Population/CityOldOld2045/index.html", html)

    # 2020年 高齢化率/年少人口割合ランキング (旧Aging2015/Young2015の後継)
    for name, rel, h2, vlabel, rlabel, lead in (
        ("aging2020", "Population/Aging2020",
         "2020年市町村別高齢化率ランキング", "老年人口(65歳以上)", "高齢化率(%)",
         "2020年国勢調査による市区町村別の高齢化率(65歳以上人口の割合)のランキングです。"
         "市町村名をクリックすると年齢階級別人口の推移が表示されます。"),
        ("young2020", "Population/Young2020",
         "2020年市町村別年少人口割合ランキング", "年少人口(15歳未満)", "年少人口割合(%)",
         "2020年国勢調査による市区町村別の年少人口(15歳未満)割合のランキングです。"
         "市町村名をクリックすると年齢階級別人口の推移が表示されます。"),
    ):
        rows = json.loads((DATA_RANKINGS / f"{name}.json").read_text(encoding="utf-8"))
        html = env.get_template("population/pct_ranking2020.html").render(dict(
            ctx_common, rows=rows, page_h2=h2, page_lead=lead,
            value_label=vlabel, rate_label=rlabel, page_title=h2))
        write_text(f"{rel}/index.html", html)

    # Population2015 ランキング (人口順/増減数順/増減率順/コード順 × 全国+47都道府県)
    cityinfo = json.loads((ROOT / "data" / "cityinfo2015.json").read_text(encoding="utf-8"))
    scopes = [None] + [p for p in masters.PREF_CODE]
    for pref in scopes:
        for order, (label, _) in rankings.POPULATION2015_ORDERS.items():
            rows = rankings.build_population2015_ranking(cityinfo, order, pref)
            title = "2015年市区町村別人口ランキング" + (f" - {masters.PREF_CODE[pref]}" if pref else "")
            html = env.get_template("population/population2015.html").render(dict(
                ctx_common, rows=rows, order=order, pref=pref,
                orders={k: v[0] for k, v in rankings.POPULATION2015_ORDERS.items()},
                page_title=title))
            rel = f"Population/Population2015/{(pref + '/') if pref else ''}{order}/index.html"
            write_text(rel, html)
    print(f"Population2015ランキング {len(scopes) * len(rankings.POPULATION2015_ORDERS)} 件")

    # Census2010 (2010年国勢調査人口と2008年推計の比較。1ページ完結)
    census2010_rows = json.loads((DATA_RANKINGS / "census2010.json").read_text(encoding="utf-8"))
    html = env.get_template("population/census2010.html").render(dict(
        ctx_common, rows=census2010_rows, page_title="2010年国勢調査人口と将来推計人口の比較"))
    write_text("Population/Census2010/index.html", html)


def build_home(ctx_common: dict) -> None:
    """サイトトップと人口トップ (DESIGN.md §6 Phase 4)。

    旧HomeController.Index / PopulationController.Index の移植。
    JP/EU の4区分チャートはビルド時SVG (K8、旧 CountryBy4AgeGroup)。
    """
    env = make_env()

    charts = {}
    for code, note in (("JP", SOURCE_NOTE_IPSS), ("EU", SOURCE_NOTE_EUROSTAT)):
        model = json.loads((DATA_COUNTRY / f"{code}.json").read_text(encoding="utf-8"))
        if model["is_jp"]:
            chart_years = CENSUS_YEARS + PROJECTION_YEARS[1:]
            title = "日本の年齢階級別人口の推移"
        else:
            chart_years = CENSUS_YEARS + list(EUROSTAT_PROJECTION_YEARS)
            title = "EUの年齢階級別人口の推移"
        charts[code] = age4_stack_svg(title, age4_series(model), chart_years,
                                      note, id_prefix=f"h{code}_")

    ctx = dict(ctx_common, chart_jp=charts["JP"], chart_eu=charts["EU"],
               countries=masters.COUNTRY_CODE)
    write_text("index.html", env.get_template("home.html").render(
        dict(ctx, nav_active="", page_title="統計メモ帳 - 日本と世界の統計データをグラフで")))
    write_text("Population/index.html", env.get_template("population/index.html").render(
        dict(ctx, nav_active="population",
             tokyo_cities=masters.cities_of_pref("13"),
             kyoto_cities=masters.cities_of_pref("26"),
             page_title="人口を可視化してみました - 統計メモ帳")))
    print("トップ + 人口トップ")


def build_static_pages(ctx_common: dict, source: Path) -> None:
    """静的コンテンツ (About/Privacy/Gdp/Io/ExcelVba) と 404 (DESIGN.md §6 Phase 4/5)。

    本文は旧 Razor から抽出済みの素の HTML (templates/static/)。
    参照している旧 /images/ アセットもコピーする。
    旧 /Search (Google AFS の廃止API) は移植しない — ヘッダーの検索フォームが
    google.co.jp/cse に直接POSTするため専用ページは不要。
    /contacts/ は廃止 (K2)。Pages は 410 を返せないため 404 に落ちる。
    """
    env = make_env()
    static_dir = ROOT / "templates" / "static"
    titles = json.loads((static_dir / "_titles.json").read_text(encoding="utf-8"))
    media_refs = set()
    for slug, title in titles.items():
        body = (static_dir / (slug.replace("/", "__") + ".html")).read_text(encoding="utf-8")
        media_refs.update(re.findall(r'(?:src|href)="(/images/[^"]+)"', body))
        html = env.get_template("static_page.html").render(
            dict(ctx_common, nav_active="", body=body, page_title=title))
        write_text(f"{slug}/index.html", html)

    wwwroot = source / "wwwroot"
    for ref in sorted(media_refs):
        src = wwwroot / ref.lstrip("/")
        if src.exists():
            dst = PUBLIC / ref.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    write_text("404.html", env.get_template("404.html").render(
        dict(ctx_common, nav_active="", page_title="ページが見つかりません - 統計メモ帳")))
    print(f"静的ページ {len(titles)} + 404 / 画像 {len(media_refs)} 枚")


def build_sitemap() -> None:
    """sitemap.xml (Phase 5)。public/ 内の index.html から生成する。"""
    urls = []
    for p in sorted(PUBLIC.rglob("index.html")):
        rel = p.parent.relative_to(PUBLIC).as_posix()
        rel = "" if rel == "." else rel + "/"
        urls.append(f"  <url><loc>https://ecitizen.jp/{rel}</loc></url>")
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")
    write_text("sitemap.xml", body)
    print(f"sitemap.xml {len(urls)} URL")


def build_x12arima(ctx_common: dict, source: Path) -> None:
    """季節調整 (X-13ARIMA-SEATS) セクション (DESIGN.md §19)。

    新3ページ + 旧X-12-ARIMA記事のアーカイブ4ページ。旧記事の画像
    (wwwroot の /images/x12arima/ と参照されている /media/{id}/) もコピーする。
    """
    env = make_env()
    ctx = dict(ctx_common, nav_active="x12arima")

    pages = [
        ("x12arima/index.html", "x-12-arima/index.html",
         "季節調整法 X-13ARIMA-SEATS について"),
        ("x12arima/x13_install.html", "x-12-arima/x-13arima-seats/index.html",
         "X-13ARIMA-SEATS のインストール (Linux)"),
        ("x12arima/x13_usage.html", "x-12-arima/x-13arima-seats-usage/index.html",
         "X-13ARIMA-SEATS の使い方"),
    ]
    for tpl, rel, title in pages:
        write_text(rel, env.get_template(tpl).render(dict(ctx, page_title=title)))

    archive_dir = ROOT / "templates" / "x12arima" / "archive"
    titles = json.loads((archive_dir / "_titles.json").read_text(encoding="utf-8"))
    media_refs = set()
    for slug, title in titles.items():
        body = (archive_dir / f"{slug}.html").read_text(encoding="utf-8")
        media_refs.update(re.findall(r'src="(/(?:media|images)/[^"]+)"', body))
        html = env.get_template("x12arima/archive_page.html").render(
            dict(ctx, body=body, page_title=f"{title} (アーカイブ)"))
        write_text(f"x-12-arima/archive/{slug}/index.html", html)

    wwwroot = source / "wwwroot"
    n_img = 0
    for ref in sorted(media_refs):
        src = wwwroot / ref.lstrip("/")
        if not src.exists():
            print(f"警告: 旧画像なし {ref}")
            continue
        dst = PUBLIC / ref.lstrip("/")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n_img += 1
    print(f"x-12-arima {len(pages)}+{len(titles)} ページ / 旧画像 {n_img} 枚")


def _ssdsnum(v):
    """Ssds の値 (e-Stat 文字列) の表示: 整数はカンマ区切り、小数・記号はそのまま。"""
    if v is None:
        return "-"
    s = str(v)
    try:
        f = float(s)
    except ValueError:
        return s  # "-", "...", "X" 等の欠損記号
    if "." in s:
        i, d = s.split(".", 1)
        return f"{int(i):,}.{d}"
    return f"{int(f):,}"


def build_ssds(ctx_common: dict) -> None:
    """Ssds 都道府県ランキング (DESIGN.md §21)。data/ssds/ が無ければスキップ。"""
    ssds_dir = ROOT / "data" / "ssds"
    if not (ssds_dir / "majors.json").exists():
        print("Ssds データなし (tools/fetch_ssds.py 未実行) — スキップ")
        return
    env = make_env()
    env.filters["ssdsnum"] = _ssdsnum
    majors = json.loads((ssds_dir / "majors.json").read_text(encoding="utf-8"))
    major_names = majors["major_names"]
    ctx = dict(ctx_common, nav_active="ssds", major_names=major_names)

    write_text("Ssds/index.html", env.get_template("ssds/index.html").render(
        dict(ctx, page_title="統計指標で都道府県ランキングを作ってみた - 統計メモ帳")))

    kinds = [("indicator", "IndicatorCat", "社会生活統計指標", "Pref"),
             ("basic", "BasicCat", "基礎データ", "PrefBasic")]
    for kind, cat_base, kind_label, pref_base in kinds:
        for m, mname in major_names.items():
            items = majors["groups"].get(f"{kind}_{m}", [])
            write_text(f"Ssds/{cat_base}/{m}/index.html",
                       env.get_template("ssds/cat.html").render(dict(
                           ctx, items=items, major=m, major_name=mname,
                           kind_label=kind_label,
                           page_title=f"{kind_label} {m} {mname} の項目一覧 - 都道府県ランキング")))
            for pref, pname in masters.PREF_CODE.items():
                rows = json.loads((ssds_dir / "pref" / f"{pref}_{kind}_{m}.json")
                                  .read_text(encoding="utf-8"))
                html = env.get_template("ssds/pref.html").render(dict(
                    ctx, rows=rows, pref=pref, pref_name=pname, major=m,
                    major_name=mname, kind_label=kind_label, base=pref_base,
                    page_title=f"{pname}の{kind_label} ({m} {mname}) - 都道府県ランキング"))
                write_text(f"Ssds/{pref_base}/{pref}/{m}/index.html", html)
                if m == "A":  # 分野省略時の旧URL互換 (A にフォールバック)
                    write_text(f"Ssds/{pref_base}/{pref}/index.html", html)

    n = 0
    for f in sorted((ssds_dir / "items").glob("*.json")):
        item = json.loads(f.read_text(encoding="utf-8"))
        if not item["years"]:
            continue
        slug = item["code"].replace("#", "_")
        write_text(f"Ssds/Indicators/{slug}/index.html",
                   env.get_template("ssds/indicator.html").render(dict(
                       ctx, item=item, major_name=major_names[item["major"]],
                       page_title=f"{item['name']} の都道府県ランキング - 統計メモ帳")))
        n += 1
    print(f"Ssds: カタログ26 + 県別{47 * len(kinds) * len(major_names)} + 項目{n}")


def copy_statdb_data() -> None:
    """Statdb アプリとカタログのスナップショットを配信物に含める (DESIGN.md §17.5)。

    - statdb_app/build/web (Flutter Web 版、`flutter build web --base-href
      /Statdb/` の成果物) → public/Statdb/
    - data/statdb/ (カタログ JSON) → public/Statdb/data/
      Flet/Flutter アプリ (Web・ネイティブとも) がデータソースとして fetch する

    どちらも無ければスキップ (未ビルドの開発環境でもサイト生成可能にするため)。
    """
    web_build = ROOT / "statdb_app" / "build" / "web"
    if (web_build / "index.html").exists():
        # .last_build_id 等の隠しファイルは配信不要 (cf-publish もアップロード
        # しない仕様のため、コピーするとファイル数の集計がズレる)
        shutil.copytree(web_build, PUBLIC / "Statdb", dirs_exist_ok=True,
                        ignore=lambda d, names: [n for n in names
                                                 if n.startswith(".")])
        print("Statdb Web アプリを配置")
    else:
        print("Statdb Web アプリ未ビルド (flutter build web) — スキップ")
    src = ROOT / "data" / "statdb"
    if not (src / "catalog.json").exists():
        print("Statdb データなし (tools/fetch_statdb.py 未実行) — スキップ")
        return
    dst = PUBLIC / "Statdb" / "data"
    shutil.copytree(src, dst, dirs_exist_ok=True)
    n = sum(1 for p in dst.rglob("*") if p.is_file())
    print(f"Statdb データ {n} ファイル")


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

    # 市町村ページ (City + CityPyramid) + CityData JSON (チャート描画が重いので並列)
    with ProcessPoolExecutor(max_workers=args.jobs,
                             initializer=_init_worker,
                             initargs=(config, args.build_year, cityinfo)) as ex:
        done = 0
        for _ in ex.map(_build_city, codes, chunksize=16):
            done += 1
            if done % 200 == 0:
                print(f"  市町村 {done}/{len(codes)}")

    # 都道府県 + 国 (件数が少ないため同じプールを使い回す)
    with ProcessPoolExecutor(max_workers=args.jobs,
                             initializer=_init_worker,
                             initargs=(config, args.build_year, cityinfo)) as ex:
        list(ex.map(_build_pref, masters.PREF_CODE))
        list(ex.map(_build_country, masters.COUNTRY_CODE))
    print(f"都道府県 {len(masters.PREF_CODE)} 件 / 国 {len(masters.COUNTRY_CODE)} 件")

    # ランキング系 (地図・チャートなし、非並列で十分高速)
    build_rankings({
        "config": config, "build_year": args.build_year, "nav_active": "population",
        "prefs": masters.PREF_CODE,
    })

    copy_assets(args.source)
    copy_statdb_data()
    build_home({
        "config": config, "build_year": args.build_year,
        "prefs": masters.PREF_CODE,
    })
    build_ssds({
        "config": config, "build_year": args.build_year,
        "prefs": masters.PREF_CODE,
    })
    build_x12arima({
        "config": config, "build_year": args.build_year,
        "prefs": masters.PREF_CODE,
    }, args.source)
    build_static_pages({
        "config": config, "build_year": args.build_year,
        "prefs": masters.PREF_CODE,
    }, args.source)
    population2015_redirects = "".join(
        f"/Population/Population2015/{(p + '/') if p else ''} "
        f"/Population/Population2015/{(p + '/') if p else ''}popu/ 301\n"
        for p in [None] + list(masters.PREF_CODE)
    )
    # Statdb: 旧 StatsData/StatsMeta は e-Stat の統計表表示画面へ (D6 推奨案)。
    # それ以外の /Statdb/* は SPA フォールバック (実ファイルがあればそちらが優先
    # されるのが Cloudflare Pages の仕様のため、/Statdb/data/* はこの影響を受けない)
    statdb_redirects = ""
    if (PUBLIC / "Statdb" / "index.html").exists():
        statdb_redirects = (
            "/Statdb/StatsData/* https://www.e-stat.go.jp/dbview?sid=:splat 302\n"
            "/Statdb/StatsMeta/* https://www.e-stat.go.jp/dbview?sid=:splat 302\n"
            "/Statdb/* /Statdb/index.html 200\n"
            "/statdb/* /Statdb/index.html 200\n"
        )
    build_sitemap()
    write_text("_redirects", REDIRECTS + population2015_redirects + statdb_redirects)
    write_text("_headers", HEADERS)

    # スモークチェック (DESIGN.md §10)
    n_html = len(list(PUBLIC.glob("Population/City/*/index.html")))
    n_json = len(list(PUBLIC.glob("Population/CityData/*.json")))
    n_list = len(list(PUBLIC.glob("Population/CityList/*.json")))
    n_pyramid = len(list(PUBLIC.glob("Population/CityPyramid/*/index.html")))
    n_pref = len(list(PUBLIC.glob("Population/Prefecture/*/index.html")))
    n_pref_pyramid = len(list(PUBLIC.glob("Population/PrefPyramid/*/index.html")))
    n_country = len(list(PUBLIC.glob("Population/Country/*/index.html")))
    assert (PUBLIC / "Population" / "Census2010" / "index.html").exists()
    n_files = sum(1 for p in PUBLIC.rglob("*") if p.is_file())
    assert n_html == len(codes), f"HTML {n_html} != {len(codes)}"
    assert n_json == len(codes), f"JSON {n_json} != {len(codes)}"
    assert n_list == 47
    assert n_pyramid == len(codes), f"CityPyramid {n_pyramid} != {len(codes)}"
    if codes == list(masters.CITY_DIC):
        assert n_pref == 47 and n_country == 33 and n_pref_pyramid == 47
    print(f"HTML {n_html} / CityData {n_json} / CityList {n_list} / "
          f"CityPyramid {n_pyramid} / Prefecture {n_pref} / PrefPyramid {n_pref_pyramid} / "
          f"Country {n_country} / 総ファイル数 {n_files}")
    if n_files > 15000:
        print(f"警告: ファイル数 {n_files} — Cloudflare Pages の上限 20,000 に接近 (DESIGN.md §9.1)")


if __name__ == "__main__":
    main()
