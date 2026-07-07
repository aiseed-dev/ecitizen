"""統計データAPI エクスプローラ — Flet 版 (DESIGN.md §17.8、K14)。

ターゲット: Android スマホ / Chromebook の Linux 環境 (Crostini) / デスクトップ。
データは配信サイトの静的スナップショット JSON (開発時はリポジトリ内 data/statdb)。
e-Stat API は呼ばない (K5)。統計表の実データは e-Stat の統計表表示画面へ
リンクする (D6 推奨案。Python なので後から表内表示を追加しやすい)。

実行: flet run statdb_flet/main.py  (または --web --port 5024)
"""
import urllib.parse

import flet as ft

from statdb_data import ESTAT_DBVIEW, StatdbData, build_tree, filter_tables

KIND_LABEL = {1: "統計", 2: "小地域・地域メッシュ"}
UPDATE_TYPE_LABEL = {0: "新規", 1: "更新", 2: "新規", 3: "更新", 4: "変更"}


FONT_CHOICES = [
    ("標準 (BIZ UDゴシック)", "BIZ UDPGothic"),
    ("教科書体 (Klee One)", "Klee One"),
    ("OS 標準", "system"),
]


def main(page: ft.Page):
    page.title = "統計データAPI エクスプローラ - 統計メモ帳"
    # フォントを同梱して全プラットフォームで使う (Android の
    # フォールバックは Noto なので、見た目を揃えるためアプリに添付。K9)
    page.fonts = {
        "BIZ UDPGothic": "/fonts/BIZUDPGothic-Regular.ttf",
        "BIZ UDPGothic Bold": "/fonts/BIZUDPGothic-Bold.ttf",
        "Klee One": "/fonts/KleeOne-Regular.ttf",
    }

    # フォント設定。key は同梱フォント名・"system" (OS標準)・または
    # インストール済みフォントの直接指定 (PC でモリサワ Fonts 等を入れた場合)
    font_state = {"key": FONT_CHOICES[0][1]}

    def set_font(key: str, save: bool = True):
        font_state["key"] = key
        page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.TEAL,
            font_family=None if key == "system" else key)
        if save:
            try:
                page.client_storage.set("font_family", key)
            except Exception:
                pass
            page.update()

    # 既定は OS 標準。同梱フォント (BIZ UD / Klee One) は既定にせず、
    # 設定画面の選択肢として提供するだけ
    saved_font = "system"
    try:
        saved_font = page.client_storage.get("font_family") or saved_font
    except Exception:
        pass
    set_font(saved_font, save=False)
    try:  # デスクトップのみ (Web/モバイルでは window が無い/効かない)
        if page.window.width and page.window.width > 1100:
            page.window.width = 1000
            page.window.height = 750
    except Exception:
        pass

    data = StatdbData()
    print(f"statdb data base: {data.base} (remote={data.is_remote})")

    def q(s: str) -> str:
        return urllib.parse.quote(s, safe="")

    def uq(s: str) -> str:
        return urllib.parse.unquote(s)

    # ---- 各ビュー ----

    def home_view() -> ft.View:
        catalog = data.catalog()
        search = ft.TextField(hint_text="統計名で検索 (例: 国勢調査)",
                              prefix_icon=ft.Icons.SEARCH, dense=True)
        listing = ft.ListView(spacing=0, expand=True)

        def stat_tiles(keyword: str = "") -> list:
            tiles = []
            for kind in (1, 2):
                stats = [e for e in catalog["stats"] if e["kind"] == kind
                         and (not keyword or keyword in e["name"])]
                if not stats:
                    continue
                tiles.append(ft.Container(
                    ft.Text(KIND_LABEL[kind], weight=ft.FontWeight.BOLD, size=16),
                    padding=ft.Padding(16, 12, 16, 4)))
                for e in stats:
                    tiles.append(ft.ListTile(
                        title=ft.Text(e["name"]),
                        subtitle=ft.Text(f"{e['id']} ({e['gov_org']})", size=12),
                        dense=True,
                        on_click=lambda _, e=e: page.push_route(
                            f"/stats/{e['kind']}/{e['id']}"),
                    ))
            return tiles

        def on_search(_):
            listing.controls = stat_tiles(search.value.strip())
            listing.update()

        search.on_change = on_search
        listing.controls = stat_tiles()

        header = [
            ft.Container(ft.Text(
                "政府統計の総合窓口 (e-Stat) の統計データAPIで提供されている"
                "統計データの一覧です。統計表は e-Stat の統計表表示画面で開きます。"
                f" (カタログ取得日: {catalog.get('fetched_at', '-')})",
                size=13), padding=ft.Padding(16, 8, 16, 0)),
            ft.Container(search, padding=ft.Padding(16, 8, 16, 0)),
        ]
        latest = data.latest()
        if latest:
            header.append(ft.Container(
                ft.TextButton(
                    f"統計データ更新情報 ({len(latest)}件)",
                    icon=ft.Icons.UPDATE,
                    on_click=lambda _: page.push_route("/latest")),
                padding=ft.Padding(8, 0, 16, 0)))

        return ft.View(
            route="/",
            appbar=ft.AppBar(
                title=ft.Text("統計データAPI エクスプローラ"),
                actions=[ft.IconButton(
                    ft.Icons.SETTINGS, tooltip="設定",
                    on_click=lambda _: page.push_route("/settings"))]),
            controls=header + [listing],
        )

    def settings_view() -> ft.View:
        builtin = [fam for _, fam in FONT_CHOICES]
        tiles: list[ft.ListTile] = []

        custom = ft.TextField(
            label="フォント名を直接指定",
            hint_text="例: UD デジタル 教科書体 N-R",
            helper="PC にインストール済みのフォント (モリサワ Fonts の"
                   "フリープラン等) を名前で指定できます。Enter で適用",
            on_submit=lambda e: choose(e.control.value.strip()))

        def refresh():
            for tile, (_, fam) in zip(tiles, FONT_CHOICES):
                tile.trailing = (ft.Icon(ft.Icons.CHECK)
                                 if font_state["key"] == fam else None)
            custom.value = ("" if font_state["key"] in builtin
                            else font_state["key"])
            page.update()

        def choose(key: str):
            if not key:
                return
            set_font(key)
            refresh()

        for label, fam in FONT_CHOICES:
            tiles.append(ft.ListTile(
                title=ft.Text(label),
                trailing=(ft.Icon(ft.Icons.CHECK)
                          if font_state["key"] == fam else None),
                on_click=lambda _, f=fam: choose(f)))

        return ft.View(
            route="/settings",
            appbar=ft.AppBar(title=ft.Text("設定")),
            controls=[ft.ListView(
                [ft.Container(ft.Text("フォント", weight=ft.FontWeight.BOLD),
                              padding=ft.Padding(16, 16, 16, 4))]
                + tiles
                + [ft.Container(custom, padding=16)],
                spacing=0, expand=True)],
        )

    def table_tile(r: dict, show_statics: bool = False) -> ft.ListTile:
        """統計表1件のタイル (タップで e-Stat の統計表表示画面を開く)。"""
        no = "" if r["no"] in ("-", "") else f"表{r['no']} "
        if show_statics:
            info = r["statics"]
        else:
            info = f"調査年月: {'-' if r['sdate'] == '0' else r['sdate']}"
            if r.get("num"):
                info += f" / {r['num']:,}件"
            info += f" / 公開: {r['open']}"
        return ft.ListTile(
            title=ft.Text(f"{no}{r['title']}", size=14),
            subtitle=ft.Text(info, size=12),
            trailing=ft.Icon(ft.Icons.OPEN_IN_NEW, size=18),
            dense=True,
            on_click=lambda _, sid=r["id"]: page.launch_url(ESTAT_DBVIEW + sid),
        )

    def tree_view(kind: int, code: str, path: str) -> ft.View:
        """statics 階層のドリルダウン。path は空白区切りの階層パス ("" = 最上位)。

        最上位では統計内の全統計表を対象にした横断検索も提供する
        (表題または統計名にキーワードを含む表を直接一覧する。旧サイトや
        e-Stat 本家の階層クリックの繰り返しより速く目的の表に着ける)。
        """
        rows = data.table_list(kind, code)
        node = build_tree(rows)
        parts = path.split(" ") if path else []
        for name in parts:
            node = node["children"].get(name, {"children": {}, "count": 0})

        def tree_tiles() -> list:
            tiles = []
            if node["count"]:
                statics = path if path else code
                tiles.append(ft.ListTile(
                    leading=ft.Icon(ft.Icons.TABLE_CHART),
                    title=ft.Text(f"この階層の統計表 ({node['count']}件)"),
                    dense=True,
                    on_click=lambda _, s=statics: page.push_route(
                        f"/tables/{kind}/{code}/{q(s)}"),
                ))
            for name, child in node["children"].items():
                n_children = len(child["children"])
                label = name + (f" ({child['count']}件)" if child["count"] else "")
                child_path = f"{path} {name}".strip()
                if n_children:  # さらに階層あり → ドリルダウン
                    tiles.append(ft.ListTile(
                        leading=ft.Icon(ft.Icons.FOLDER_OUTLINED),
                        title=ft.Text(label),
                        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                        dense=True,
                        on_click=lambda _, p=child_path: page.push_route(
                            f"/stats/{kind}/{code}/{q(p)}"),
                    ))
                else:  # 終端 → 統計表一覧へ
                    tiles.append(ft.ListTile(
                        leading=ft.Icon(ft.Icons.TABLE_CHART_OUTLINED),
                        title=ft.Text(label),
                        dense=True,
                        on_click=lambda _, p=child_path: page.push_route(
                            f"/tables/{kind}/{code}/{q(p)}"),
                    ))
            return tiles

        listing = ft.ListView(tree_tiles(), spacing=0, expand=True)
        controls = [listing]

        if not parts:  # 最上位のみ: 統計内の全表を横断検索
            search = ft.TextField(
                hint_text=f"この統計の全{len(rows):,}表から検索 (表題・統計名)",
                prefix_icon=ft.Icons.SEARCH, dense=True)

            def on_search(_):
                kw = search.value.strip()
                if len(kw) < 2:
                    listing.controls = tree_tiles()
                else:
                    hits = [r for r in rows
                            if kw in r["title"] or kw in r["statics"]]
                    hits.sort(key=lambda r: (r["statics"], r["sequence"]))
                    tiles = [ft.Container(ft.Text(
                        f"{len(hits):,}表がヒット"
                        + (" (先頭300件を表示)" if len(hits) > 300 else ""),
                        size=12), padding=ft.Padding(16, 8, 16, 0))]
                    tiles += [table_tile(r, show_statics=True)
                              for r in hits[:300]]
                    listing.controls = tiles
                listing.update()

            search.on_change = on_search
            controls = [ft.Container(search, padding=ft.Padding(16, 8, 16, 0)),
                        listing]

        title = parts[-1] if parts else data.stat_name(kind, code)
        return ft.View(
            route=page.route,
            appbar=ft.AppBar(title=ft.Text(title)),
            controls=controls,
        )

    def tables_view(kind: int, code: str, statics: str) -> ft.View:
        rows = filter_tables(data.table_list(kind, code), statics)
        tiles = [ft.Container(ft.Text(
            f"統計表をタップすると e-Stat の統計表表示画面を開きます ({len(rows)}件)",
            size=12), padding=ft.Padding(16, 8, 16, 0))]
        tiles += [table_tile(r) for r in rows]
        return ft.View(
            route=page.route,
            appbar=ft.AppBar(title=ft.Text(statics.split(" ")[-1])),
            controls=[ft.ListView(tiles, spacing=0, expand=True)],
        )

    def latest_view() -> ft.View:
        entries = list(reversed(data.latest()))
        tiles = []
        for e in entries:
            if e["update_type"] >= 4:
                continue
            tiles.append(ft.ListTile(
                title=ft.Text(e["title"]),
                subtitle=ft.Text(f"公開: {e['open']}", size=12),
                trailing=ft.Text(UPDATE_TYPE_LABEL.get(e["update_type"], "")),
                dense=True,
                on_click=lambda _, i=e["id"]: page.push_route(f"/latest/{i}"),
            ))
        if not tiles:
            tiles = [ft.Container(
                ft.Text("スナップショット取得後の更新はありません。"),
                padding=16)]
        return ft.View(
            route="/latest",
            appbar=ft.AppBar(title=ft.Text("統計データ更新情報")),
            controls=[ft.ListView(tiles, spacing=0, expand=True)],
        )

    def latest_tables_view(latest_id: str) -> ft.View:
        rows = data.latest_tables(latest_id)
        tiles = [table_tile({**r, "id": r["stats_data_id"]}, show_statics=True)
                 for r in sorted(rows, key=lambda r: (r["statics"], r["sequence"]))]
        return ft.View(
            route=page.route,
            appbar=ft.AppBar(title=ft.Text("更新された統計表")),
            controls=[ft.ListView(tiles, spacing=0, expand=True)],
        )

    # ---- ルーティング ----

    def build_view(route: str) -> ft.View:
        troute = ft.TemplateRoute(route)
        if troute.match("/stats/:kind/:code"):
            return tree_view(int(troute.kind), troute.code, "")
        if troute.match("/stats/:kind/:code/:path"):
            return tree_view(int(troute.kind), troute.code, uq(troute.path))
        if troute.match("/tables/:kind/:code/:statics"):
            return tables_view(int(troute.kind), troute.code, uq(troute.statics))
        if troute.match("/latest"):
            return latest_view()
        if troute.match("/latest/:id"):
            return latest_tables_view(troute.id)
        if troute.match("/settings"):
            return settings_view()
        return home_view()

    def route_change(_):
        route = page.route or "/"
        # 既存スタックに同じルートがあればそこまで戻る (バックナビゲーション)
        for i, v in enumerate(page.views):
            if v.route == route:
                del page.views[i + 1:]
                page.update()
                return
        try:
            if not page.views and route != "/":
                page.views.append(home_view())  # ディープリンク時もホームを底に置く
            page.views.append(build_view(route))
        except Exception as e:  # データ取得失敗等を画面に出す
            import traceback
            traceback.print_exc()
            page.views.append(ft.View(route=route, controls=[
                ft.AppBar(title=ft.Text("エラー")),
                ft.Text(f"データを読み込めませんでした: {e}"),
            ]))
        page.update()

    def view_pop(_):
        if len(page.views) > 1:
            page.views.pop()
            page.go(page.views[-1].route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop
    # 初期表示: push_route は同一ルートだと on_route_change を発火しないため直接呼ぶ
    route_change(None)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
