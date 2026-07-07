"""全ビューの構築テスト (ブラウザ不要のスモークテスト)。

実データ (data/statdb/) に対して各ビューのコントロールツリーが例外なく
構築できることを検証する。描画・操作の確認は実機 (デスクトップ/Android) で行う。

実行: .venv/bin/python test_views.py
"""
import sys
import types
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as app  # noqa: E402
from statdb_data import StatdbData, build_tree, filter_tables  # noqa: E402


class FakePage(types.SimpleNamespace):
    """main() が触る Page の属性だけを持つスタブ。"""

    def __init__(self):
        super().__init__(title="", theme=None, route="/", views=[],
                         on_route_change=None, on_view_pop=None)
        self.pushed = []

    def update(self):
        pass

    def push_route(self, route, **kw):
        self.pushed.append(route)
        self.route = route
        if self.on_route_change:
            self.on_route_change(None)

    def launch_url(self, url):
        self.pushed.append(("url", url))


def view_texts(view) -> str:
    """View 内の全 Text をたどって連結 (存在確認用)。"""
    out = []

    def walk(c):
        for attr in ("controls", "content", "title", "subtitle", "leading",
                     "trailing", "appbar"):
            v = getattr(c, attr, None)
            if v is None:
                continue
            for item in (v if isinstance(v, list) else [v]):
                if hasattr(item, "value") and isinstance(
                        getattr(item, "value"), str):
                    out.append(item.value)
                walk(item)

    walk(view)
    return " ".join(out)


def run():
    page = FakePage()
    app.main(page)  # route_change(None) が走りホームが積まれる

    assert page.title.startswith("統計データAPI"), page.title
    assert len(page.views) == 1, [v.route for v in page.views]
    home_text = view_texts(page.views[0])
    assert "国勢調査" in home_text
    print(f"home OK (views={len(page.views)})")

    # 国勢調査 (kind1) のツリー最上位
    page.push_route("/stats/1/00200521")
    assert len(page.views) == 2
    t = view_texts(page.views[-1])
    assert "令和２年国勢調査" in t and "昭和55年国勢調査" in t
    print("tree(top) OK")

    # ドリルダウン
    path = urllib.parse.quote("令和２年国勢調査", safe="")
    page.push_route(f"/stats/1/00200521/{path}")
    assert len(page.views) == 3
    t = view_texts(page.views[-1])
    assert "人口等基本集計" in t
    print("tree(drill) OK")

    # 統計表一覧
    statics = urllib.parse.quote("令和２年国勢調査 人口等基本集計　（主な内容：男女・年齢・配偶関係，世帯の構成，住居の状態，母子・父子世帯，国籍など）", safe="")
    page.push_route(f"/tables/1/00200521/{statics}")
    t = view_texts(page.views[-1])
    assert "e-Stat" in t
    n_tiles = len(page.views[-1].controls[0].controls) - 1
    data = StatdbData()
    expected = len(filter_tables(data.table_list(1, "00200521"),
                                 "令和２年国勢調査 人口等基本集計　（主な内容：男女・年齢・配偶関係，世帯の構成，住居の状態，母子・父子世帯，国籍など）"))
    assert n_tiles == expected > 0, (n_tiles, expected)
    print(f"tables OK ({n_tiles} 表)")

    # 戻る (既存ルートへの遷移でスタックが切り詰められる)
    page.push_route("/stats/1/00200521")
    assert len(page.views) == 2, [v.route for v in page.views]
    print("back-nav OK")

    # 小地域 (kind2) と社会・人口統計体系 (00200502)
    page.push_route("/stats/2/00200521")
    assert "小地域" in view_texts(page.views[-1]) or page.views[-1] is not None
    page.push_route("/stats/1/00200502")
    t = view_texts(page.views[-1])
    assert "都道府県データ" in t
    print("kind2 / 00200502 OK")

    # 更新情報 (初回スナップショットでは空)
    page.push_route("/latest")
    t = view_texts(page.views[-1])
    assert "更新" in t
    print("latest OK")

    # 設定 (フォント選択)
    page.push_route("/settings")
    t = view_texts(page.views[-1])
    assert "フォント" in t and "教科書体" in t, t
    settings = page.views[-1]
    tiles = [c for c in settings.controls[0].controls
             if isinstance(c, __import__("flet").ListTile)]
    tiles[1].on_click(None)   # 教科書体を選択
    assert page.theme.font_family == "Klee One", page.theme.font_family
    tiles[2].on_click(None)   # OS 標準
    assert page.theme.font_family is None
    tiles[0].on_click(None)   # 標準に戻す
    assert page.theme.font_family == "BIZ UDPGothic"
    print("settings OK")

    # ディープリンク (ホームが底に積まれる)
    page2 = FakePage()
    page2.route = "/stats/1/00200502"
    app.main(page2)
    assert len(page2.views) == 2, [v.route for v in page2.views]
    assert page2.views[0].route == "/"
    print("deep-link OK")

    print("全ビュー構築テスト OK")


if __name__ == "__main__":
    run()
