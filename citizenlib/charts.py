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
YEARS = [str(y) for y in range(1980, 2050, 5)]  # 14 カテゴリ (1980..2045)

matplotlib.rcParams.update({
    "svg.fonttype": "none",
    "svg.hashsalt": "ecitizenstatic",
    "font.family": ["BIZ UDGothic", "Noto Sans CJK JP", "sans-serif"],
    "axes.unicode_minus": False,
})

_SVG_TAG_RE = re.compile(r'<svg([^>]*?) width="[^"]*" height="[^"]*"')


def _inline_svg(fig, tooltips: dict) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    svg = buf.getvalue()
    svg = svg[svg.index("<svg"):]  # XML 宣言・DOCTYPE を除去
    svg = _SVG_TAG_RE.sub(r'<svg\1', svg, count=1)  # 固定サイズを外し viewBox に任せる
    # gid を振った <g id="..."> の直後に <title> を注入
    def add_title(m):
        gid = m.group(1)
        tip = tooltips.get(gid)
        return m.group(0) + (f"<title>{tip}</title>" if tip else "")
    svg = re.sub(r'<g id="(b\d+x\d+)">', add_title, svg)
    return svg


def city_stack_svg(name: str, series: list) -> str:
    """市町村ページの積み上げ縦棒 (旧 Highcharts stacking:normal 相当)。

    series は DATA_CONTRACT §3.1 の配列 (先頭=年齢不詳=スタック最上段)。
    旧チャートの reversedStacks 相当: 末尾の系列 (0～4歳) を最下段に積む。
    """
    n = len(YEARS)
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
                tooltips[gid] = f"{YEARS[xi]}年 {s['name']}: {data[xi]:,}人"
        bottoms = [b + d for b, d in zip(bottoms, data)]

    # 合計ラベル (旧 stackLabels 相当)
    ymax = max(bottoms)
    for xi, total in enumerate(bottoms):
        if total:
            ax.text(xi, total + ymax * 0.01, f"{int(total):,}", ha="center",
                    va="bottom", fontsize=7, fontweight="bold", color="#555555")

    ax.set_title(f"{name} の年齢別人口の推移", fontsize=13)
    ax.set_ylabel("人口(人)")
    ax.set_xticks(x, YEARS, fontsize=9)
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
    fig.text(0.5, 0.155,
             "出典: 国勢調査を独自集計、「日本の地域別将来推計人口(平成30(2018)年3月推計)」"
             "(国立社会保障・人口問題研究所)",
             ha="center", fontsize=7, color="#888888")
    fig.subplots_adjust(left=0.09, right=0.98, top=0.94, bottom=0.24)
    return _inline_svg(fig, tooltips)
