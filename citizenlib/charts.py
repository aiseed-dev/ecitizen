"""ビルド時 SVG グラフ生成 (DESIGN.md §8.6 / K8)。

matplotlib で描画し、インライン埋め込み用の SVG 文字列を返す。
- 決定性: svg.hashsalt 固定・メタデータの日付を除去
- ホバー値: 各バーに SVG <title> を後注入 (JS 不要のネイティブツールチップ)
- レスポンシブ: width/height 属性を落とし viewBox のみ残す (CSS 側で width:100%)
"""
import io
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# モリサワ BIZ UD ゴシック (assets/fonts/ にリポジトリ同梱、SIL OFL)。
# SVG は svg.fonttype='none' でテキスト出力し、CSS 側の @font-face と同じ
# ファミリ名で解決される。matplotlib にはレイアウト計算用に登録する。
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
for _ttf in sorted(_FONTS_DIR.glob("*.ttf")):
    font_manager.fontManager.addfont(str(_ttf))

# 旧 Highcharts オプションの 15 色パレット (系列 index 順に循環適用)
PALETTE = [
    "#f45b5b", "#8085e9", "#8d4654", "#7798BF", "#aaeeee", "#ff0066", "#eeaaee",
    "#55BF3B", "#DF5353", "#666666", "#00DDDD", "#ff9326", "#0DB88F", "#3625DF",
    "#DDDD33",
]
# City/Pref (IPSS令和5年推計): 1980..2050 の15カテゴリ。Country(旧データのまま)は
# 呼び出し側 (generate.py) が 1980..2045 の14カテゴリを別途渡す。

matplotlib.rcParams.update({
    "svg.fonttype": "none",
    "svg.hashsalt": "ecitizenstatic",
    "font.family": ["BIZ UDGothic", "Noto Sans CJK JP", "sans-serif"],
    "axes.unicode_minus": False,
})

_SVG_TAG_RE = re.compile(r'<svg([^>]*?) width="[^"]*" height="[^"]*"')


def _inline_svg(fig, tooltips: dict, id_prefix: str = "") -> str:
    """matplotlib Figure を静的サイト埋め込み用 SVG 文字列に変換する。

    id_prefix: 同一 HTML ページに複数の SVG を埋め込むときは必須。
    matplotlib は svg.hashsalt を固定しているため、同じレイアウトの図を
    複数回描画すると clip-path 等の内部 id (例 "p2cb465e343") が完全に
    一致してしまい、ブラウザ側で先勝ちの id 解決により意図しない図が
    参照される。呼び出しごとに一意な prefix を渡し、id とその参照
    (url(#..)・xlink:href="#..") をまとめてリネームして衝突を防ぐ。
    """
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    svg = buf.getvalue()
    svg = svg[svg.index("<svg"):]  # XML 宣言・DOCTYPE を除去
    svg = _SVG_TAG_RE.sub(r'<svg\1', svg, count=1)  # 固定サイズを外し viewBox に任せる

    if id_prefix:
        svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{id_prefix}{m.group(1)}"', svg)
        svg = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{id_prefix}{m.group(1)})', svg)
        svg = re.sub(r'xlink:href="#([^"]+)"', lambda m: f'xlink:href="#{id_prefix}{m.group(1)}"', svg)
        tooltips = {f"{id_prefix}{k}": v for k, v in tooltips.items()}

    # gid を振った <g id="..."> の直後に <title> を注入 (tooltips になければ何もしない)
    def add_title(m):
        tip = tooltips.get(m.group(1))
        return m.group(0) + (f"<title>{tip}</title>" if tip else "")
    svg = re.sub(r'<g id="([^"]+)">', add_title, svg)
    return svg


SOURCE_NOTE_IPSS = ("出典: 国勢調査を独自集計、"
                    "「日本の地域別将来推計人口(令和5(2023)年推計)」(国立社会保障・人口問題研究所)")
SOURCE_NOTE_EUROSTAT = "出典: Eurostat「Population on 1 January」・EUROPOP2023(基準シナリオ)、UKのみONS推計"


def city_stack_svg(name: str, series: list, years: list, source_note: str = SOURCE_NOTE_IPSS) -> str:
    """市町村/都道府県/国ページの積み上げ縦棒 (旧 Highcharts stacking:normal 相当)。

    series は DATA_CONTRACT §3.1/3.3/3.4 の配列 (先頭=年齢不詳=スタック最上段)。
    旧チャートの reversedStacks 相当: 末尾の系列 (0～4歳) を最下段に積む。
    years はカテゴリ (x軸) ラベル。City/Pref は15個(1980-2050、IPSS令和5年推計)、
    Country-JP も City/Pref と同じ15個 (IPSS令和5年推計。2026-07-06 更新)、非JP は15個(1980-2020+2025-2050)。
    """
    years = [str(y) for y in years]
    n = len(years)
    fig, ax = plt.subplots(figsize=(9.2, 7.0), dpi=100)
    x = list(range(n))
    bottoms = [0.0] * n
    tooltips = {}

    for si in range(len(series) - 1, -1, -1):
        s = series[si]
        data = (list(s["data"]) + [0] * n)[:n]
        bars = ax.bar(x, data, 0.72, bottom=bottoms,
                      color=PALETTE[si % len(PALETTE)], label=s["name"], linewidth=0)
        for xi, rect in enumerate(bars):
            if data[xi]:
                gid = f"b{si}x{xi}"
                rect.set_gid(gid)
                tooltips[gid] = f"{years[xi]}年 {s['name']}: {data[xi]:,}人"
        bottoms = [b + d for b, d in zip(bottoms, data)]

    # 合計ラベル (旧 stackLabels 相当)
    ymax = max(bottoms)
    for xi, total in enumerate(bottoms):
        if total:
            ax.text(xi, total + ymax * 0.01, f"{int(total):,}", ha="center",
                    va="bottom", fontsize=7, fontweight="bold", color="#555555")

    ax.set_title(f"{name} の年齢別人口の推移", fontsize=13)
    ax.set_ylabel("人口(人)")
    ax.set_xticks(x, years, fontsize=9)
    ax.set_ylim(0, ymax * 1.08)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)

    # 凡例は下部・描画順 (0～4歳が先頭。旧 legend.reversed 相当)
    fig.legend(loc="lower center", ncol=5, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 0.155, source_note, ha="center", fontsize=7, color="#888888")
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.24)
    return _inline_svg(fig, tooltips)


# 旧 CityPyramid.cshtml の Highcharts categories (総数・年齢不詳を除く19階級)
PYRAMID_CATEGORIES = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44",
    "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85-89", "90+",
]


def city_pyramid_svg(name: str, year: int, male: list, female: list, max_value: int) -> str:
    """人口ピラミッド (1年分)。男性=左(負)・女性=右(正)の水平積み上げ棒。

    DESIGN.md §8.6/K8 の通りクライアント側チャートライブラリを使わないため、
    年ごとに1枚ずつ事前生成し、テンプレート側で表示/非表示を切り替える
    (DATA_CONTRACT §2.5)。軸スケールは全年共通 (max_value) にして
    アニメーション的な年送り時にガクつかないようにする。
    """
    n = len(PYRAMID_CATEGORIES)
    fig, ax = plt.subplots(figsize=(7.6, 6.4), dpi=100)
    y = list(range(n))
    tooltips = {}

    male_bars = ax.barh(y, [-v for v in male], 0.82, color="#997fff", label="男性", linewidth=0)
    female_bars = ax.barh(y, female, 0.82, color="#ff99ff", label="女性", linewidth=0)
    for i, rect in enumerate(male_bars):
        gid = f"m{i}"
        rect.set_gid(gid)
        tooltips[gid] = f"男性 {PYRAMID_CATEGORIES[i]}歳: {male[i]:,}人"
    for i, rect in enumerate(female_bars):
        gid = f"f{i}"
        rect.set_gid(gid)
        tooltips[gid] = f"女性 {PYRAMID_CATEGORIES[i]}歳: {female[i]:,}人"

    ax.set_title(f"{name} の人口ピラミッド {year}年", fontsize=13)
    ax.set_yticks(y, PYRAMID_CATEGORIES, fontsize=9)
    ax.set_xlim(-max_value * 1.05, max_value * 1.05)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{abs(int(v)):,}"))
    ax.tick_params(axis="x", labelsize=8)
    ax.axvline(0, color="#999999", linewidth=0.8)
    ax.grid(axis="x", color="#DDDDDD", linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.legend(loc="lower center", ncol=2, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.14))
    fig.text(0.5, 0.02, SOURCE_NOTE_IPSS, ha="center", fontsize=7, color="#888888")
    fig.subplots_adjust(left=0.12, right=0.96, top=0.93, bottom=0.14)
    # 1ページに15年分を埋め込むため、id_prefix で id 衝突を回避する (_inline_svg 参照)
    return _inline_svg(fig, tooltips, id_prefix=f"y{year}_")


# ホーム/人口トップの4区分チャート (旧 CountryBy4AgeGroup + Highcharts の置き換え)
AGE4_COLORS = {"15歳未満": "#55BF3B", "15～64歳": "#7798BF",
               "65～74歳": "#f4a259", "75歳以上": "#DF5353"}


def age4_stack_svg(title: str, groups: list, years: list, source_note: str,
                   id_prefix: str = "") -> str:
    """4区分 (15歳未満/15～64歳/65～74歳/75歳以上) の積み上げ縦棒。

    groups は [{"name":..., "data":[...]}] (下から積む順)。単位は百万人表示。
    1ページに2枚 (日本+EU) 並べるため id_prefix 必須 (SVG内部IDの衝突回避)。
    """
    years = [str(y) for y in years]
    n = len(years)
    fig, ax = plt.subplots(figsize=(6.4, 4.6), dpi=100)
    x = list(range(n))
    bottoms = [0.0] * n
    tooltips = {}

    for gi, g in enumerate(groups):
        data = (list(g["data"]) + [0] * n)[:n]
        bars = ax.bar(x, data, 0.72, bottom=bottoms,
                      color=AGE4_COLORS.get(g["name"], "#CCCCCC"),
                      label=g["name"], linewidth=0)
        for xi, rect in enumerate(bars):
            if data[xi]:
                gid = f"a{gi}x{xi}"
                rect.set_gid(gid)
                tooltips[gid] = f"{years[xi]}年 {g['name']}: {data[xi]:,}人"
        bottoms = [b + d for b, d in zip(bottoms, data)]

    ymax = max(bottoms)
    for xi, total in enumerate(bottoms):
        if total:
            ax.text(xi, total + ymax * 0.012, f"{total / 1e6:.0f}", ha="center",
                    va="bottom", fontsize=7, fontweight="bold", color="#555555")

    ax.set_title(title, fontsize=12)
    ax.set_ylabel("人口(百万人)", fontsize=9)
    ax.set_xticks(x, years, fontsize=7.5, rotation=45)
    ax.set_ylim(0, ymax * 1.09)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e6:.0f}"))
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)

    fig.legend(loc="lower center", ncol=4, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    fig.text(0.5, 0.13, source_note, ha="center", fontsize=6.5, color="#888888")
    fig.subplots_adjust(left=0.08, right=0.98, top=0.92, bottom=0.26)
    return _inline_svg(fig, tooltips, id_prefix=id_prefix)


def cpi_line_svg(title: str, series: dict, ylabel: str, id_prefix: str) -> str:
    """CPI等の月次折れ線 (DESIGN.md §22)。series = {ラベル: {"YYYY-MM": 値文字列}}。"""
    fig, ax = plt.subplots(figsize=(9.2, 4.6), dpi=100)
    months = sorted({m for d in series.values() for m in d})
    x = {m: i for i, m in enumerate(months)}
    for label, d in series.items():
        pts = [(x[m], float(v)) for m, v in sorted(d.items()) if v not in ("-", "…", "***")]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], linewidth=1.1, label=label)
    ticks = [i for i, m in enumerate(months) if m.endswith("-01") and int(m[:4]) % 5 == 0]
    ax.set_xticks(ticks, [months[i][:4] for i in ticks], fontsize=8)
    ax.set_title(title, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(color="#DDDDDD", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    fig.text(0.99, 0.01, "出典: 総務省統計局「消費者物価指数(2020年基準)」",
             ha="right", fontsize=6.5, color="#888888")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.92, bottom=0.09)
    return _inline_svg(fig, {}, id_prefix=id_prefix)
