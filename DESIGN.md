# eCitizenStatic 設計書

eCitizen (統計メモ帳 / ecitizen.jp) を ASP.NET Core 2.2 の動的サイトから
**静的サイト + Python によるデータ(JSON)生成** へ移行するための設計書。

WeatherCore → WeatherStatic の移行 (`../WeatherStatic/DESIGN.md`) と同じ方針を踏襲する。

---

## 1. 背景と目的

| 項目 | 現状 | 問題 |
|------|------|------|
| ランタイム | ASP.NET Core 2.2 (Kestrel, port 5011) | EOL。セキュリティ更新なし |
| データ | `App_Data/`(約11,000 JSON) + `C:\Cache\eCitizen`(外部バッチ生成) | Windows パス前提。バッチ・キャッシュ層が別管理 |
| 外部依存 | e-Stat API、気象庁 XML、GCP Datastore、SMTP | 常駐プロセスからの都度呼び出し |

**移行後の姿**: リクエスト時に行っていた計算をすべて**生成時**に行い、
HTML と JSON をファイルとして事前生成。配信は任意の静的ホスティング
(nginx / オブジェクトストレージ / CDN) で行う。

## 2. 現行システムの分析結果(要点)

- コントローラ 21 個、Razor ビュー 118 個、JSON を返すアクション約 40 個。
- データは**ほぼ全て読み取り専用**。`App_Data` のファイルと外部バッチが作る
  キャッシュを読むだけで、DB 接続なし。
- ページの動的要素は「サーバー側でモデルを計算して埋め込む」部分と、
  「クライアントの `$.getJSON` が JSON エンドポイントを叩いて Highcharts で描画する」
  部分の 2 種類。→ 前者は生成時レンダリング、後者は静的 JSON 化で置き換え可能。
- 完全に動的でないと成立しない機能は 3 つのみ(§7 参照):
  お問い合わせフォーム POST、Lg マップの動的絞り込み、Statdb の対話的 API 探索。

## 3. アーキテクチャ: 二層分離

WeatherStatic と同じ「取得層」「描画層」の分離。

```
┌─ 取得層 build_data.py ─────────────────────────────┐
│ 入力: App_Data (国勢調査等) / e-Stat API / 手動更新データ │
│ 処理: 旧 C# Model のロジック (集計・指数計算・コード変換)   │
│ 出力: data/*.json  ← DATA_CONTRACT.md で仕様固定       │
└──────────────────────────────────────────┘
                        ↓
┌─ 描画層 generate.py ──────────────────────────────┐
│ 入力: data/*.json + templates/ (Jinja2) + マスター       │
│ 出力: public/**/index.html + public/**/*.json (API 互換)  │
│       + 静的アセット (css/js/images を wwwroot からコピー)  │
└──────────────────────────────────────────┘
                        ↓
                 rsync / ストレージ同期で配信
```

設計原則(WeatherStatic から踏襲、ただしフロントエンドは刷新):

1. **表示時計算の生成時移動** — Razor/Controller にあった計算は全て Python 側で確定。
2. **データ契約の明文化** — 取得層と描画層の境界は `DATA_CONTRACT.md` の JSON
   スキーマのみ。層をまたぐ暗黙知を作らない。
3. **URL とデータの互換、UI は刷新** — URL 構造・数値の表示(丸め方向を含む)は
   現行サイトを踏襲する。一方で見た目は **Bootstrap 3 を廃止**し、
   素の CSS (Grid / Flexbox) で書き直す (§6 Phase 0)。
4. **決定性** — 同じ `data/` からは常に同じ `public/` が生成される
   (現在時刻依存はビルド引数化)。

### フロントエンド刷新の方針 (今回の見直しで決定)

- **Bootstrap 廃止**: `bootstrap-custom.min.css` / `bootstrap.min.js` / jQuery を
  使わない。レイアウト(ヘッダー・メイン・サイドバー・フッター)は CSS Grid、
  グリッド相当は Flexbox で自前実装。ナビのドロップダウン/ハンバーガーは
  CSS + 最小限の vanilla JS で実装する。
- **jQuery 廃止**: 残る動的処理 (県セレクタでの市町村リスト切替のみ) は
  `fetch()` + DOM API で実装。jquery-validation / smartmenus / DHTMLX も廃止。
- **グラフはビルド時に Python で SVG 生成** (K8): Highcharts を含む
  クライアント側チャートライブラリは全廃。生成した SVG は HTML に
  インライン埋め込みし、ホバー値表示は SVG `<title>` で行う (§8.6)。
- **お問い合わせフォーム廃止**: ContactsController 系は移植しない (§7)。
- **対話的機能は Flutter Web も選択肢**: 事前生成 JSON では成立しない
  対話的 UI (統計 API エクスプローラ等) は、静的ホスティングに同居できる
  Flutter Web アプリとして切り出してよい (§7)。

### 人口系データについての補足

人口系(国勢調査 1980–2015 + 将来推計 2015–2045)は**確定した静的データ**であり、
`App_Data/Population2015/` に完全な形で存在する。よって取得層は外部 API を呼ばず、
旧リポジトリの `App_Data` を一次ソースとしてローカル変換するだけでよい。
定期実行が必要なのは e-Stat 由来のページ(CPI、Ssds、Statdb)のみ。

## 4. ディレクトリ構成

```
eCitizenStatic/
├── DESIGN.md              # 本書
├── DATA_CONTRACT.md       # data/*.json および公開 JSON のスキーマ定義
├── README.md              # セットアップ・ビルド手順
├── build_data.py          # 取得層ドライバ
├── generate.py            # 描画層ドライバ
├── tools/
│   └── extract_masters.py # C# ソースからマスター辞書を抽出(初回/データ改定時のみ)
├── citizenlib/            # 旧 C# Model の移植 + 生成基盤
│   ├── masters.py         # マスター辞書ローダ (県コード・市町村辞書・年齢階級 等)
│   ├── population.py      # PopulationChart / PopulationClass の移植
│   ├── charts.py          # matplotlib による SVG グラフ生成 (K8/§8.6)
│   └── filters.py         # Jinja2 フィルタ ("#,##0"・"0.0" 等 .NET 書式の再現)
├── data/
│   ├── masters/           # 抽出済みマスター (コミットする)
│   └── *.json             # 取得層の出力 (人口系はコミット可、e-Stat 系は生成物)
├── templates/             # Jinja2 (旧 Razor の移植。Bootstrap 依存は除去)
│   ├── _layout.html       # 新レイアウト (旧 _LayoutBootstrap 系の構造を CSS Grid で再構成)
│   ├── partials/          # _mainnav.html, _cityinfo2015.html 等
│   └── population/city.html 等
├── assets/                # 新規フロントエンド資産 (旧 wwwroot からのコピーではないもの)
│   ├── css/site.css       # Bootstrap を置き換える自前 CSS
│   └── js/site.js         # ナビ開閉・fetch ヘルパー等の最小 vanilla JS
└── public/                # 生成物 (git 管理外)
```

## 5. URL 設計と互換性

### HTML ページ

`/Population/City/13104` → `public/Population/City/13104/index.html`

- ディレクトリ + `index.html` 方式。Web サーバー側で `/Population/City/13104`
  (末尾スラッシュなし) → `.../13104/` を解決するのは一般的な挙動のため互換性は保てる。
- 旧サイトの 301 リダイレクト(滝沢村 03305→03216、富谷町 04423→04216、
  岩舟町 09367→09203)は Cloudflare Pages の `_redirects` ファイルとして
  生成物 (`public/_redirects`) に含める (§9.1)。

### JSON エンドポイント

`/Population/CityData/13104` → `public/Population/CityData/13104.json`

- 静的配信で正しい `Content-Type` を得るため **拡張子 `.json` を付与**し、
  テンプレート内の `$.getJSON` の URL を `.json` 付きに書き換える。
- 外部から旧 URL を直接叩いているクライアントへの互換が必要になった場合は、
  `_redirects` の 200 rewrite (`/Population/CityData/:code` → `.../:code.json`)
  で対応する。
- JSON の中身は旧 ContentResult とバイト単位で同等
  (コンパクト表記・非 ASCII 生出力、`json.dumps(separators=(',',':'), ensure_ascii=False)`)。

## 6. ページ移行計画(フェーズ)

ルート棚卸しに基づく段階移行。各フェーズ完了時点で `public/` は部分公開可能。

### Phase 0: 基盤

- **新レイアウト作成** (`_layout.html` + `assets/css/site.css`)。
  旧 `_LayoutBootstrap` + `_LayoutBootstrapA4` のページ構造
  (ヘッダーナビ / メイン / サイドバー / フッター、広告枠を含む) を
  Bootstrap なしの CSS Grid / Flexbox で再構成する。
  - ブレークポイントは旧サイト踏襲 (767px 以下 = モバイル)。
    旧 `col-xs/sm/md/lg` 相当の並び替えは Flexbox で実装。
  - ナビ (`Partials/MainNavVar.cshtml` 相当) はドロップダウンを
    CSS hover + クリック (vanilla JS 数十行) で実装。
    active 判定はリクエストパス依存 → 生成時に `nav_active` 変数で確定。
  - AdSense / Google CSE は現状のまま移植 (レイアウト用クラスのみ自前 CSS に差し替え)。
    Analytics は GA4 タグに更新 (D4)。
- アセットパイプライン: 旧 `wwwroot` からは images / favicon.ico /
  robots.txt のみコピー。**bootstrap・jQuery・HighCharts・DHTMLX・
  jquery-validation・smartmenus はコピーしない** (グラフは K8 でビルド時 SVG 化)。
  `assets/` (site.css / site.js) を `public/` へ配置。
- マスター抽出: `PopulationClass.cs` の辞書
  (PrefCode / CityDic20161010 / CodeTrans / Ages / CountryCode) を JSON 化。

### Phase 1(パイロット): 市町村の人口推移

対象ルート:

| 旧ルート | 新出力 | 件数 |
|---------|--------|------|
| `/Population/City/{id}` (HTML) | `Population/City/{id}/index.html` | 1,741 |
| `/Population/CityData/{id}` (JSON) | `Population/CityData/{id}.json` | 1,741 |
| `/Population/CityList/{pref}` (JSON) | `Population/CityList/{pref}.json` | 47 |

このページを選ぶ理由: 「サーバー側埋め込み(指数表)+ JSON API(グラフ)+
サイドバー部品(CityInfo2015)」というサイトの典型構成をすべて含み、
かつデータが App_Data で完結しているため。移植ロジックの詳細は §8。

### Phase 2: 人口系の残り

- ★実装済み `/Population/Prefecture/{id}` (47件) + `PrefData/{id}.json`
- ★実装済み `/Population/Country/{id}` (33件) + `CountryData/{id}.json`
  (日本以外は census が Ages2/kaikyu=85。当初は旧App_Data由来だったが
  K12(§14)で Eurostat/ONS に全面更新済み)
- ★実装済み `/Population/CityPyramid/{id}` (1,741件、男女別人口ピラミッド)。
  年ごとのエンドポイント分割はせず 1 市町村 1 ファイルに 15 年分を SVG として
  事前描画・埋め込み、表示切替はブラウザ側で表示/非表示を切り替えるのみ
  (§9.1 のファイル数対策と K8 のクライアント側チャートライブラリ不使用を両立)
- ★実装済み `/Population/PrefPyramid/{id}` (47件)。CityPyramid と同じ方式
  (都道府県は将来推計の欠損 = fukushima 相当のケースがないため分岐なし)
- ★実装済み `/Population/Population2015/{order}/`・`{pref}/{order}/`
  (人口順・増減数順・増減率順・コード順 × 全国+47都道府県 = 192ページ)。
  新規データ取得不要 (`data/cityinfo2015.json` を並べ替えるだけ)。
  旧URL(orderクエリ省略時)は `_redirects` で `popu/` へ301
- ★実装済み ローカルデータのみで完結するランキング系:
  `Ranking` (全国+都道府県別)、`CityAging2045`、`CityOldOld2045`、
  `ListOfCitiesByArea`、`ListOfCitiesByTfr`
  (`CityAging2045`/`CityOldOld2045` は新規データ取得不要。Phase 1/2 で
  構築済みの市町村モデルの将来推計指数から再集計するだけで再現できることが
  判明した)
- ★実装済み `/Population/CountryPyramid/{id}` (33件、JP含む)。Eurostat/ONS
  から男女別(sex=M,F)データを追加取得(`tools/fetch_eurostat.py`/
  `citizenlib/eurostat.py` に `sex` 引数を追加)。census(Ages2、90歳以上の
  データなし)と projection(Ages3的、90歳以上あり)で年齢区分の粒度が違う
  ため、census 年は 90歳以上を0埋めして19区分に揃えている。JP は旧
  `App_Data/Population2015/CountryM,CountryF` を使用(census/projection
  とも旧データのまま変更なし)
- **廃止(決定事項)**: `City3d`/`Country3d`/`Prefecture3d`。移植しない (§8.6)。
- 未着手: Population2010 系 (`Census2010`, `Ranking`, `City` ほか)
- **スコープ変更**: `Aging2015`・`Young2015`・`YoungMigration`・`Migration` は、
  調査の結果**旧実装がリクエスト時に e-Stat API を直接呼んでいる**ことが
  判明した (appId が C# ソースにハードコードされていた)。K5(データ処理は
  ローカル完結)の方針に従い、これらは Phase 3 の e-Stat 系ページとまとめて
  実装する (下記 Phase 3 に統合)

### Phase 3: e-Stat 由来ページ(定期更新が必要)

- Living (CPI): `Cpi`, `CpiJapan`, `CpiTokyoKubu`, `CpiForSelectedAreas` +
  `CpiIndex`/`CpiChange`/`CpiJapanJson` 等の JSON。
  取得層が e-Stat API から CPI を取得 → 全カテゴリ分の JSON を事前生成。
- Ssds (都道府県ランキング): `Index`, `Pref/{id}`, `Indicators` + `DataJson/{id}`。
  47 都道府県 × カテゴリで全組み合わせを事前生成。
- Sac (市区町村コード表): `Index`, `Code` — NAreaCode サービスのデータを静的化。
- Lg / Lc (市町村の統計・豆知識): `GetCity`/`GetLgInfo` は市町村ごとの JSON に静的化。
- (Phase 2 から移管) `Aging2015`・`Young2015`(高齢化率・年少人口割合ランキング)、
  `YoungMigration`・`Migration`(人口移動)。取得層バッチが e-Stat から
  スナップショットを取得し、事前生成 JSON のみを配信する (K5)。
  旧ソースにハードコードされていた appId (`22977f64c46f47314804ef3f49822e88964bdb89`)
  は Git 履歴に残るためこのまま使わず、本プロジェクト用に appId を再登録する
  ことを推奨 (要ユーザー判断)。

### Phase 4: 静的コンテンツ・その他

- Home, About, Privacy, Gdp, Io, X12Arima, ExcelVba, Search
  — ほぼ静的な Razor をそのまま Jinja2 化。
- Weather: **本移行のスコープ外** (K4)。移植・リダイレクトとも行わず、
  リンクは現状維持。扱いは別途決める。
- Statdb (統計 API エクスプローラ): 対話的探索が本質のため事前生成 JSON では
  成立しない。**Flutter Web アプリとして再実装**する(K3。詳細設計は
  Phase 4 開始時に別紙)。静的ホスティング上の `/statdb/` 配下に
  ビルド成果物 (CanvasKit/wasm + JS) を配置するだけで同居できる。
  データ供給は K5: **ローカルの取得層バッチが e-Stat から取得・加工した
  静的スナップショット JSON のみ**を読む。ライブの e-Stat 呼び出しは行わないため、
  探索できる範囲はスナップショットに含めた統計表に限る
  (旧 Statdb も実態は `C:\Cache\eCitizen` のキャッシュ前提だったので同等)。
  スナップショットは統計表単位で 1 ファイルに集約し、Pages の
  ファイル数上限 (§9.1) に収める。e-Stat API 自体の調査結果は §12。

### Phase 5: 仕上げ

- **お問い合わせフォームは廃止**(決定事項)。`/contacts/` は 410 Gone とし、
  フッター等のリンクを削除。連絡手段は Twitter リンクのみ残す。
  これに伴い SMTP 設定・EmailSender・jquery-validation は移植対象外。
- リダイレクト定義一式、sitemap.xml、404 ページ
- 本番切り替え: DNS/リバースプロキシで静的配信に向け、旧アプリ停止

## 7. 動的機能の扱い

| 機能 | 現行実装 | 静的化方針 |
|------|---------|-----------|
| グラフ描画 | クライアントの Highcharts が JSON を取得して描画 | **ビルド時に Python で SVG 生成し HTML に埋め込み** (K8/§8.6)。JSON はデータ API 互換として事前生成を継続 (市町村1,741 / 県47 / 国33 / カテゴリ数十) |
| 市町村リスト切替 | `/Population/CityList/{pref}` | 47 ファイルを事前生成。`fetch()` + vanilla JS で描画 |
| お問い合わせ POST + SMTP | ContactsController + EmailSender | **廃止** (決定事項。410 Gone + リンク削除) |
| Lg マップ絞り込み (`GetLgMap/{coords}`) | 座標でサーバー側フィルタ | 全市町村 GeoJSON を配信しクライアント側でフィルタ。UI が複雑化する場合は Flutter Web 化も可 |
| Statdb の対話探索 | e-Stat API 中継 + キャッシュ | **Flutter Web アプリとして再実装** (決定事項。データ供給は §6 Phase 4 参照) |

方針: 「事前生成 JSON + 数十行の vanilla JS」で足りるものはそれで実装し、
状態を持つ対話的 UI (検索・多段ドリルダウン・地図操作) だけを
Flutter Web に切り出す。Flutter アプリも静的成果物なので配信構成は変わらない。

## 8. Phase 1 移植仕様(確定分)

調査済みの実装詳細。数値は現行 C# と一致させる。

### 8.1 入力データ

- `App_Data/Population2015/City/pd{code}.json` — 国勢調査。
  **21 行**(総数, 0～4歳 … 90歳以上, 年齢不詳) × **8 列**(1980–2015, 5年刻み)
- `App_Data/Population2015/City/pp{code}.json` — 将来推計。
  **20 行**(総数, 0～4歳 … 90歳以上) × **7 列**(2015–2045)。
  福島県(07)の市町村には存在しない(推計非公表)。
- コード変換: pd が無い場合 `CodeTrans20151001` (例: 04216 富谷市 = 旧 04423)、
  pp が無い場合 `CodeTrans20180401`(現在は空)に従い旧コードのファイルを
  要素ごとに合算する(旧 `PopulationChart.LoadCityData` の移植)。
- サイドバー基本情報: `App_Data/Population2015/2015/population2015.json`
  (code, name, popu2015, order2015, popu2010, area, house2015…)。

### 8.2 人口指数の計算 (`PopulationChart.SetIndex*` の移植)

行 index は総数を含む(1=0–4歳 … 19=90歳以上)。

- 国勢調査 (1980–2015 の 8 点, kaikyu=90):
  年少 = 行1+2+3 / 生産年齢 = 行4..13 / 老年 = 行14..18 **+ 行19** /
  後期老年 = 行16+17+18 **+ 行19**
- 将来推計 (2015–2045 の 7 点):
  老年 = 行14..19 / 後期老年 = 行16..19
- 割合 = 各区分 ÷ (年少+生産+老年) × 100 (年齢不詳は分母に含めない)
- 指数 = 年少/生産×100、老年/生産×100、(年少+老年)/生産×100、老年/年少×100
- ビューが参照する `人口指数` は census 8 件 + projection 7 件の連結 15 件
  (福島県は census 8 件のみ)。

### 8.3 CityData JSON (Highcharts 系列)

旧 `PopulationController.CityData` の移植。系列順は
`年齢不詳, 90歳以上, 85～89歳, …, 0～4歳`(積み上げ順)で、

- 年齢不詳: census 8 点のみ
- 各年齢階級: census 8 点 + projection の列 1..6(2020–2045)の 6 点 = 14 点
- 福島県 (`HukushimaCityData`): census 8 点 + ゼロ 5 点(現行実装のまま再現)

### 8.4 数値書式 (.NET → Python)

| .NET 書式 | 例 | Python 実装 |
|-----------|----|------------|
| `ToString("#,##0")` | 1,952,356 | 四捨五入(半分は0から遠い方向)+ 3桁区切り |
| `ToString("0.0")` / `Math.Round(x,1,AwayFromZero)` | 11.6 | `Decimal` の `ROUND_HALF_UP` 相当で 1 桁 |
| `double.ToString()` (面積) | 1121.26 / 100 | 末尾の `.0` を出さない C# 互換文字列化 |

丸め方向の差(Python 既定は銀行丸め)による 0.1 のずれを防ぐため、
フィルタは `citizenlib/filters.py` に集約し単体テストを付ける。

### 8.5 テンプレート対応表

| 旧 (Razor) | 新 (Jinja2) |
|-----------|-------------|
| `_LayoutBootstrap.cshtml` + `_LayoutBootstrapA4.cshtml` | `templates/_layout.html` (構造のみ踏襲、Bootstrap クラスは使わない) |
| `Partials/MainNavVar.cshtml` | `templates/partials/_mainnav.html` (CSS + vanilla JS ドロップダウン) |
| `Views/Population/City.cshtml` | `templates/population/city.html` |
| `Components/CityInfo2015/Default.cshtml` | `templates/partials/_cityinfo2015.html` |

Razor 側の `@section HeaderContent / rightSideUnder / AddScript` は
Jinja2 の `{% block %}` に 1:1 で対応させる。
`Copyright © 2011 - @DateTime.Now.Year` はビルド引数 `--build-year`(既定=実行時の年)。

クライアント JS の置き換え (city ページ):

- グラフ描画 JS (Highcharts 初期化・`$.getJSON('/Population/CityData/...')`) は
  **全廃**。グラフは生成時に SVG として埋め込まれる (§8.6)。
- 残るのは県セレクト変更時の `CityList` 取得・リンク再描画のみ:
  `fetch('/Population/CityList/{pref}.json')` + DOM API (vanilla JS 十数行)。

### 8.6 グラフの SVG 生成 (K8)

- 実装: `citizenlib/charts.py`。matplotlib (Agg/SVG バックエンド) で描画し、
  SVG 文字列をテンプレートに渡して **HTML にインライン埋め込み**する
  (別ファイルにしないので Pages のファイル数上限に影響しない)。
- 日本語フォント: モリサワ BIZ UDGothic (K9)。`svg.fonttype='none'` で
  テキストはテキストのまま出力し、CSS の `@font-face` (セルフホスト woff2) で解決。
  matplotlib には `assets/fonts/*.ttf` を登録してレイアウト計算に使う。
- **決定性**: `svg.hashsalt` をコード固定し、matplotlib のバージョンを
  `requirements.txt` でピン止めする (同じ data/ → 同じ public/ の原則を維持)。
- レスポンシブ: 旧サイトの `screen.width` による PC/モバイル 2 種の
  オプション出し分けは廃止し、`viewBox` + `width:100%` の SVG 1 本に統一。
- ホバー値表示: 各バー/点に SVG `<title>` (例「2015 / 65～69歳: 149,741人」) を
  付け、ブラウザ標準のツールチップで代替。凡例クリックでの系列表示切替は
  提供しない (正確な数値は直下の表が担う)。
- 色: 旧 Highcharts 設定の 15 色パレットを踏襲。
- 対象グラフ: 積み上げ縦棒 (人口推移) / 人口ピラミッド (横棒) /
  折れ線 (CPI) / 散布図 (出生率×GDP)。
  **3D (City3d/Country3d/Prefecture3d) は廃止(決定事項)**。積み上げ縦棒・
  人口ピラミッドで同じ情報を確認できるため移植の必要性が薄く、静的サイトの
  見た目・保守コストの観点からも見送る。旧サイトへの 3D グラフ用リンクは
  各ページから削除済み (`City.html`/`CityPyramid.html`/`Prefecture.html`/
  `Country.html`)。旧 URL (`/Population/City3d/{id}` 等) を踏む訪問者は
  Phase 5 で `City`/`Prefecture`/`Country` へ 301 リダイレクトする。
- `Population/CityData/{code}.json` 等の公開 JSON は、グラフが SVG 化された後も
  **データ API 互換として生成を継続**する (§3.1 のデータ契約は不変。
  外部からの直接利用と将来の用途変更に備える)。

### 8.7 Phase 2 実装で判明した実データの差異

- **都道府県**: 市町村と同じ 21行×8列(census)/20行×7列(projection) 構成。
  コード変換(市町村合併)の対象外なので `build_pref_model` は単純。
- **国**: 日本は市町村と同じ Ages3/kaikyu=90 構成(21行)。日本以外は
  Ages2/kaikyu=85 (20行、85歳以上を1行に合算)。**将来推計(ep)は国によらず
  常に90歳以上まで分離済みの20行**だが、**列数(何年まで推計があるか)は
  国ごとに異なり**、スイス(CH)・アイスランド(IS)のみ2045年分がなく6列
  (他は7列)。旧 C# の `SetIndexProjectionAll` も列数固定ではなく実データ依存
  だったため、`build_country_model` も列数を動的に検出する (固定の
  `PROJECTION_YEARS` を使わない)。
  また非日本国の `CountryData` 系列生成は、census(粒度が粗い)と
  projection(粒度が細かい)の年齢階級がずれるため専用の分岐が必要
  (`countrydata_series`。DATA_CONTRACT §3.4)。
- **人口ピラミッド**: 旧サイトはクライアントが年ごとに JSON を取得して
  Highcharts で再描画していたが、K8(クライアント側チャートライブラリ不使用)
  に従い **14年分の SVG をビルド時に全て生成して1ページに埋め込み**、
  年の切替は表示/非表示の切り替えのみで実現する(fetch なし)。
  実装時に、matplotlib は `svg.hashsalt` を固定しているため**同一レイアウトの
  図を複数回描画すると内部 id (clip-path 等) が完全一致し、1ページに
  複数 SVG を埋め込むと id 衝突でブラウザの `url(#id)` 解決が壊れる**ことが
  判明した。`citizenlib/charts.py` の `_inline_svg` に `id_prefix` 引数を追加し、
  id とその参照(`url(#..)`・`xlink:href="#.."`)を呼び出しごとに一意化して解決した。
  1ページに14枚の SVG を埋め込むため `CityPyramid` の HTML は 1 ページ平均
  約500KB(全体では旧 City ページの約2倍のサイズ)になる。許容範囲だが、
  将来的に SVG の軽量化(パス簡略化・精度削減)の余地はある。
- **CityAging2045/CityOldOld2045**: 旧実装は `App_Data/.../City/Project.json`
  という専用ファイルを読んでいたが、その中身は Phase 1 で構築済みの
  市町村モデルの将来推計 index と同一データだったため、**新規のソース読込は
  不要**で `data/population/city/*.json` から再集計するだけで再現できた。
- **Ranking2045**: 全国ランキングは元データ (`CityRanking2045.json`) に
  順位が既に計算済みで、そのまま配信するだけで良い。都道府県別ランキングのみ
  リクエスト時計算(`PrefRanking`)だったため、47都道府県分を事前生成する。

## 9. ビルドと運用

```bash
# 初回のみ
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # jinja2, matplotlib (バージョンピン止め)
python tools/extract_masters.py          # マスター抽出(データ改定時のみ)

# ビルド
python build_data.py                     # 取得層: data/*.json 生成
python generate.py --clean               # 描画層: public/ 生成
python -m http.server 5012 --directory public   # ローカル確認
```

- **人口系は再ビルド不要**(データ確定済み)。cron が必要なのは Phase 3 以降の
  e-Stat 系のみ(WeatherStatic と同じく「fetch 失敗時は前回値でビルド継続」)。
- 原子性: Cloudflare Pages はデプロイ単位が原子的(ビルド成功時のみ切替)なので、
  生成途中の状態が公開されることはない。
- 検証: ビルド後にスモークチェック
  (ページ数・JSON 件数、代表都市の数値スポットチェック)を generate.py に内蔵。

### 9.1 Cloudflare Pages 構成 (K7)

デプロイ: `wrangler pages deploy public/`(ローカル/cron から)または
Git 連携ビルド。定期更新(Phase 3 の e-Stat 系)は cron で
`build_data.py && generate.py && wrangler pages deploy` を実行する。

| Pages の機能/制約 | 本設計での扱い |
|------------------|---------------|
| **1 デプロイ 20,000 ファイル上限** | Phase 1 は約 3,600 ファイルで問題なし。Phase 2 の `CityPyramidData/{id}/{year}` を素直に展開すると 1,741×15年 ≒ 26,000 ファイルで**超過**する。→ ピラミッドデータは**市町村ごとに全年を 1 ファイルに束ねる** (`CityPyramidData/{id}.json` に year キー) 等、エンドポイント設計時にファイル数を抑える。フェーズごとに合計ファイル数を generate.py が報告し、15,000 超で警告 |
| 1 ファイル 25 MiB 上限 | 対象なし (最大でも数百 KB) |
| `_redirects` ファイル | 旧 URL の 301 (滝沢村ほか §5) を生成物に含める。ただし 410 は表現できない |
| `_headers` ファイル | `/Population/CityData/*` 等に `Cache-Control` を付与 (人口系は immutable 長期、e-Stat 系は短め) |
| Pages Functions | **データ処理には使わない** (K5: 処理はローカル完結)。唯一の例外は `/contacts/*` に 410 Gone を返す数行の関数 (これも不要なら静的 404 で代用可) |
| Content-Type | 拡張子から自動判定。`.json` 出力方針 (§5) とそのまま整合 |

## 10. 検証方針

1. **数値一致**: 代表市町村(札幌 01100・大阪 27100・富谷 04216=コード変換例・
   福島市 07201=推計なし例・千代田区 13101)について、旧サイト(または旧コードの
   手計算)と指数表・JSON 系列を突き合わせる。
2. **構造検証**: 全 1,741 ページ生成済みであること、全 JSON が
   `DATA_CONTRACT.md` のスキーマに適合することをビルド時に assert。
3. **表示検証**: ローカル http.server + ブラウザでグラフ描画・県切替・
   リンク遷移を確認。

## 11. 決定事項と未決事項

### 決定事項

| # | 事項 | 決定 |
|---|------|------|
| K1 | UI フレームワーク | **Bootstrap 3 を廃止**。自前 CSS (Grid/Flexbox) + 最小 vanilla JS。jQuery / DHTMLX / smartmenus / jquery-validation も廃止 |
| K2 | お問い合わせフォーム | **廃止**。410 Gone + リンク削除。SMTP/EmailSender は移植しない |
| K3 | 対話的機能 | 事前生成 JSON で足りないものは **Flutter Web アプリ**として実装可 (第一候補: Statdb。必要に応じて Lg マップ) |
| K4 | Weather ページ | **本移行のスコープ外(別途対応)**。移植もリダイレクトも本プロジェクトでは行わず、ナビ・フッターからのリンクは現状維持。扱いは別途決める |
| K5 | データ供給 | **データ処理はすべてローカルの取得層バッチで行う**。Statdb を含む全ページ・全アプリは、ローカルで事前生成した静的スナップショット JSON のみを参照する。Cloudflare 側での処理(Pages Functions プロキシ等)や、クライアントからの e-Stat API 直接呼び出しは**行わない**。appId を使うのはローカルバッチのみ(クライアント露出なし) |
| K6 | Analytics / AdSense | **変更する**。UA タグ → GA4 (gtag.js) に差し替え。AdSense は現行推奨タグへ更新。測定 ID・クライアント ID・スロットはビルド設定 (`config.json`) で注入し、テンプレートに直書きしない。**自動広告 (Auto ads) は使わない** — ページ遷移毎の全画面インタースティシャル (vignette) が過剰広告・不快なUXの原因になっていたため。手動配置のバナー1枠+レクタングル1枠のみ (`templates/_layout.html` 実装済み)。本番で旧 AdSense アカウントを引き継ぐ際は、アカウント側の自動広告設定を明示的にオフにする |
| K7 | ホスティング先 | **Cloudflare Pages** (制約と構成は §9.1) |
| K8 | グラフ描画 | **Python によるビルド時 SVG 生成**(描画層の一部としてローカル処理)。クライアント側チャートライブラリ (Highcharts/ECharts/D3 等) は使わない。詳細は §8.6 |
| K9 | フォント | **モリサワ BIZ UD ゴシック / BIZ UD 明朝** (SIL OFL 版) をセルフホスト。本文 = BIZ UDPGothic (400/700)、見出し (h2〜h6) = BIZ UDPMincho (400)、表・グラフ SVG = BIZ UDGothic (等幅数字で桁揃え)。woff2 + OFL.txt を `/fonts/` で配信、TTF はリポジトリ同梱で matplotlib のレイアウト計算にも使用。外部フォント配信 (Google Fonts CDN / TypeSquare) は使わない。商用版 UD 新ゴへの差し替えは Morisawa Fonts 契約が必要なため不採用 |
| K10 | 3D グラフ | **廃止**。`City3d`/`Country3d`/`Prefecture3d` は移植しない。積み上げ縦棒・人口ピラミッドで代替できるため必要性が薄く、保守コストも避ける (§8.6) |
| K11 | 2020年国勢調査・将来推計の更新 | City/Pref の census に2020年列(実績値)を追加(8→9列)、projection を IPSS「日本の地域別将来推計人口(令和5(2023)年推計)」(2020-2050) に全面差し替え。取得は e-Stat API ではなく **IPSS公式サイトの都道府県別 Excel を1回限りダウンロード**(§13)。旧C#にハードコードされていた e-Stat appId (`22977f64c46f47314804ef3f49822e88964bdb89`) はユーザー判断で今回のみ他用途(統計表検索)に再利用したが、恒久的な組み込みは行っていない。Country(海外)は対象外、旧データ(2015年国勢調査+平成30年推計)のまま |
| K12 | Country(海外)のデータ更新 | census を **Eurostat `demo_pjangroup`**(1980-2020、appId不要のオープンAPI)に、projection を **Eurostat `proj_23np`(EUROPOP2023、基準シナリオ)**(2025-2050)に全面差し替え。**UKのみEUROPOP2023対象外(EU離脱国)のため英国統計局(ONS)「National population projections: 2024-based」を使用**、その旨をUKページに脚注表示。表示年はUKも含め全国で5年刻み(2025,2030,...,2050)に統一。JPはCountryとしては対象外(旧データのまま)。詳細は §14 |
| K13 | Statdb (統計APIエクスプローラ) | **Flutter アプリとして再実装** (K3 の適用を確定)。**Web 版に加えて PC(デスクトップ)版・スマホ版も公開する** (同一コードベースのマルチプラットフォーム。2026-07-06 ユーザー決定「いいものができれば、Webよりも便利」)。アプリID/パッケージ名は **`dev.aiseed.ecitizen`**。データ供給は K5 準拠のローカルバッチ + 静的スナップショット JSON。仕様書は §17 |
| K14 | Statdb Flet 版 | Flutter 版と並行して **Flet (Python) 版も作る** (2026-07-06 ユーザー決定)。ターゲットは **Android スマホと Chromebook の Linux 環境 (Crostini)**。Python なので**利用者・運用者がコードを自由に追加・改造できる**ことが価値 (統計処理の実験場)。**実装は Flet 版から先に着手する**。詳細は §17.8 |

### 未決事項

| # | 論点 | 状態 |
|---|------|------|
| D6 | Statdb の統計表実データ表示の扱い | **未決**。推奨案 = 統計表一覧までを SPA で提供し各表は e-Stat `dbview` へ外部リンク (§17.2)。ネイティブ版限定で「ユーザー自身の appId による直接取得」案もあり (§17.6)。Phase 4 実装開始時に決定する |
| D7 | Statdb ネイティブ版の配布方法 | **未決**。Google Play / App Store / バイナリ直接配布の選択 (§17.6)。iOS は Apple Developer Program のコストがあるため優先度を相談 |

(初版の未決事項 D1〜D5 はすべて K2〜K12 として決定済み。)

## 12. e-Stat API 調査メモ (2026-07-05 時点)

Statdb・CPI・Ssds の取得層/プロキシ設計の前提。出典は文末のリンク。

### 機能 (API バージョン 3.0、2019-07 提供開始)

| 機能 | エンドポイント | 用途 (旧 eCitizen での対応物) |
|------|---------------|------------------------------|
| 統計表情報取得 | `getStatsList` | 統計表の検索・一覧 (Statdb の StatsIndex / StatsTitleList) |
| メタ情報取得 | `getMetaInfo` | 統計表の分類事項・地域事項 (MetaInfo) |
| 統計データ取得 | `getStatsData` | 実データ (StatsData、CPI、Ssds の元データ) |
| 簡易データ取得 | `getSimpleStatsData` | CSV での軽量取得 (取得層バッチ向き) |
| データカタログ取得 | `getDataCatalog` | 統計ファイル(Excel等)のカタログ |
| 一括取得 | `getStatsDatas` (POST) | 複数統計表のまとめ取り (取得層バッチ向き) |

- リクエスト形式: `https://api.e-stat.go.jp/rest/3.0/app/{format}/{機能}?appId=...&...`
  (format = XML / `json/` / `csv/`)。gzip 圧縮対応。
- 1 リクエストの取得上限 100,000 レコード。超過分は `NEXT_KEY` でページング。

### 制約・規約

- **appId 必須** (利用登録は無料、アプリ単位で発行。登録 URL はローカルでも可)。
- **リクエスト回数制限: 現在なし** (公式 FAQ)。ただし取得層バッチは
  WeatherStatic と同じく常識的な間隔 (≥0.2 秒) でアクセスする。
- **CORS 対応** — ブラウザからの直接呼び出しも公式にはサポートされているが、
  appId がクライアントコードに露出するため**採用しない**。
  K5 のとおり e-Stat へのアクセスはローカルの取得層バッチに限定し、
  クライアント(Flutter 含む)は事前生成スナップショットのみを読む。
  この構成では appId はローカルにしか存在せず、露出の問題自体が消える。
- **商用利用可・クレジット表示義務あり**。公開アプリには
  「このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、
  サービスの内容は国によって保証されたものではありません」旨の表示が必要。
  → Statdb / CPI / Ssds 各ページに表示 (旧サイトの文言を踏襲)。

出典:
[API仕様](https://www.e-stat.go.jp/api/api-info/api-spec) /
[仕様3.0版](https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0) /
[利用ガイド](https://www.e-stat.go.jp/api/api-info/api-guide) /
[FAQ](https://www.e-stat.go.jp/api/api-dev/faq) /
[利用規約](https://www.e-stat.go.jp/api/en/terms-of-use)

## 13. Population2020 統合 (K11、2026-07-05)

市町村・都道府県ページに2020年国勢調査(census最終列)と、より新しい将来推計
(2020-2050年)を反映した。データソース調査の経緯と実装の要点をまとめる。

### 13.1 データソースの選定

当初 e-Stat API での取得を検討したが(統計表 `0003445162`「男女，年齢（5歳階級），
国籍総数か日本人別人口－全国，都道府県，市区町村」で市区町村別2020年国勢調査
実績値を取得可能なところまで確認した)、国立社会保障・人口問題研究所(IPSS)の
「日本の地域別将来推計人口(令和5(2023)年推計)」に**2020年の国勢調査実績値と
2050年までの将来推計が同じファイルに同梱されている**ことが判明したため、
こちらを一次ソースとして採用した(e-Stat への追加アクセスは不要になった)。

- 出典: <https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities.asp>
- 47都道府県別 Excel (`Municipalities/{01..47}.xlsx`)。1シート=1自治体
  (都道府県計は各ファイル先頭シート)。`tools/fetch_ipss.py` で1回限り取得し
  `data/raw/ipss/` にキャッシュ (git管理外。DESIGN.md 全体の「取得層はローカル
  完結」の原則(K5)通り、ビルド時にネットワークアクセスするのはこの取得層のみ)。
- 対象: 2023年12月時点で1,883地域(福島県浜通り13市町村を除く769市・736町・
  180村、東京23特別区、政令市175区)。本サイトの `CITY_DIC`(2016-10-10時点、
  1,741件)とはコード体系が完全一致するわけではないため §13.2 で対応。

### 13.2 マスターコードとの突合

47都道府県すべてで突合した結果、`CITY_DIC` にあって IPSS に無いコードは
**福島県浜通り13町村 + 那珂川町(40305)の計14件**のみだった。那珂川町は
2018-10-01 に那珂川市(40231)へ市制施行しており、`CITY_DIC` が2016-10-10
時点のマスターであるためコードが一致しない。`masters.IPSS_CODE_TRANS`
(1件のみ)で吸収し、実質的な対象外は福島県浜通り13町村のみに絞れた
(citizenlib/ipss.py の `city()`)。

### 13.3 スキーマへの反映

- census: 8列→9列(1980-2020)。2020列は「国勢調査による実績値」(IPSS表記)。
  ただし福島県浜通り13町村は IPSS 側にも実績値が無く、8列のまま(`fukushima: true`)。
- projection: 20行×7列(2015-2045、年齢不詳行なし)→**21行×7列(2020-2050、
  年齢不詳=0の行を追加)**。この変更で census と projection が完全に同じ
  行構成(Ages3準拠)になり、`_index_of` の計算式が census/projection で
  共通化された(旧仕様は include90_in_old フラグで作り分けが必要だった)。
- 90～94歳・95歳以上の2区分(IPSS)は合算して「90歳以上」1区分(Ages3)に
  正規化 (`citizenlib/ipss.py` の `_parse_sheet`)。
- Country(海外)は IPSS の対象外のため**変更なし**(2015年国勢調査 + 平成30年
  推計のまま)。`stacked_series`/`city_stack_svg` は City/Pref(新15点構成)と
  Country(旧14点構成)の両方を行数・列数から自動判別して描画する。
- CityAging2045/CityOldOld2045 ランキングは Phase 1/2 で構築済みの市町村
  モデルから再計算しているため、データの中身は自動的に「2020→2050年」に
  切り替わった(URL・ファイル名の "2045" は据え置き、表示文言のみ更新)。
  Ranking2045(全国+都道府県別)は別ソース(`CityRanking2045.json`、旧
  平成30年推計のまま)なので今回の変更の影響を受けていない。

### 13.4 検証

東京都2020年人口 1,404万人・大阪市2020年人口 275万人など既知の実際の値と
一致することを確認。コード変換対象の富谷市・那珂川市も正しく2020年実績値・
将来推計を持つことを確認。福島県浜通り13町村は census 8列・projection なし
のまま(2015年の人口が原発事故避難により0という実データも従来通り反映)。

## 14. Country(海外)データ更新 (K12、2026-07-05)

Population2020統合(§13)に続き、Country(海外)ページのデータソースも
Eurostat/ONSへ切替した。旧データ(App_Data由来、census 2015年まで・
projection 平成30年ベースの2045年まで)は情報として古くなっていたため。

### 14.1 データソースの選定

- census: **Eurostat `demo_pjangroup`**(男女，年齢(5歳階級)別人口)。
  年齢区分が既存の Ages2(20区分: 総数,0-4,...,80-84,85歳以上,不詳)と
  完全に一致しており変換不要。**appId不要のオープンAPI**で、1960-2025年を
  カバー。EU離脱後のUKについても過去データは継続提供されていることを確認。
- projection: 当初 EUROPOP2023(`proj_23np`)のみを想定していたが、
  この統計表はEU加盟27カ国+EFTA3カ国(アイスランド・ノルウェー・スイス)の
  **30カ国のみが対象**で、UKはEU離脱により対象外と判明。ユーザー指示
  「UKの統計は充実している、UKの統計局から」を受け、UKのみ
  **英国統計局(ONS)「National population projections: 2024-based」**
  (Principal projection、基準シナリオ)を採用。ONSのデータはEUROPOP2023
  より新しい版(2024年基準)で、5歳階級・年次データが2024-2124年の100年分、
  無料でダウンロード可能だった。

### 14.2 実装の要点

- `proj_23np` は**1歳刻み**(0歳～100歳以上の110区分)のため、
  0-4歳,5-9歳,...,85-89歳,90歳以上(19区分)に合算する処理が必要
  (`citizenlib/eurostat.py` の `load_projection_eurostat()`)。
  ONSの数値は元々5歳階級(0-4,...,100-104,105以上)で提供されているため、
  90歳以上は90-94/95-99/100-104/105以上の4区分を合算するだけで済んだ。
- 将来推計の表示年を **全32カ国で5年刻み(2025,2030,2035,2040,2045,2050)に
  統一**。EUROPOP2023は2022年始まり、ONSは2024年始まりで、どちらも
  City/Pref/JPの基準年(2020年)と一致しないため、census最終年と
  projection開始年が重複しない(旧データは両方2015年で重複していた)。
  `stacked_series`/`countrydata_series` はこの非重複ケースに対応し、
  census・projectionの列を単純連結するよう修正した(旧実装は
  projection先頭列を「census最終年と同じ」とみなして捨てていたため、
  非JP国では捨ててはいけない実装ミスがあり、検証時に発見・修正した)。
- 全32カ国+EU集計を1回のAPIリクエストで一括取得できることを確認
  (Eurostatは同一パラメータキーの繰り返し `&geo=A&geo=B&...` で複数地域を
  指定可能。カンマ区切りでは機能しない)。"EU"は集計コード `EU27_2020` を使用。
- ダウンロード・取得は `tools/fetch_eurostat.py`(census 9回・projection 6回の
  APIコール、`data/raw/eurostat/` にキャッシュ)と `tools/fetch_ons.py`
  (ONSのzipから Principal projection のExcelのみ展開、`data/raw/ons/`)。
  どちらも1回限りの取得で、以降は再ビルドのたびに叩き直さない(K5準拠)。
- JP(日本)はCountryとしては対象外(旧来通り2015年国勢調査+平成30年推計の
  まま)。日本国内のデータは City/Pref 側で既にIPSS令和5年推計に統合済み
  (§13)のため、Country/JP ページの位置づけは「参考」に留める。

### 14.3 検証

ドイツ8,317万人・フランス6,747万人・UK6,703万人・EU全体4億4,703万人
(いずれも2020年census)など既知の実際の人口と一致することを確認。
スイス・アイスランド(旧データでは将来推計が2045年までの6列しかなかった)も
新データでは他国と同じ2050年までの6列で統一されていることを確認。

## 15. PrefPyramid・CountryPyramid・Population2015ランキング (2026-07-05)

Phase 2 の残りタスクのうち、新規の外部データソース調査が不要なものを実装した。

### 15.1 PrefPyramid

CityPyramid と同じ方式(15年分の男女別人口ピラミッドSVGを1ページに事前埋め込み)。
都道府県は市町村と違い将来推計の欠損(福島県浜通りの fukushima 相当)が無いため、
分岐なしでシンプルに実装できた。男女別の census(1980-2015)は旧
`App_Data/Population2015/PrefM,PrefF`、2020年census実績値と将来推計は
IPSS(`IpssData.prefecture()` が既に male/female を返す実装だったため
追加の取得は不要だった)。

### 15.2 CountryPyramid

Country の census/projection は当初 `sex=T`(男女計)のみ取得していたため、
実装には Eurostat/ONS から男女別データを追加取得する必要があった。

- Eurostat API は `sex` 次元を `&sex=T&sex=M&sex=F` のように複数指定でき、
  1回のリクエストで男女計・男・女を同時に取得できることを確認。
  `tools/fetch_eurostat.py`・`citizenlib/eurostat.py`(`load_census`/
  `load_projection_eurostat`/`load_projection_uk`)に `sex` 引数を追加。
- census(Eurostat, Ages2, 90歳以上のデータなし)と projection(Ages3的、
  90歳以上あり)で年齢区分の粒度が異なるため、census 年のピラミッドは
  90歳以上を0埋めして19区分に揃えた(`countrydata_series` と同じ扱い)。
- JP(日本)は旧 `App_Data/Population2015/CountryM,CountryF` を使用
  (census/projectionとも旧データのまま)。census最終年(2015)とprojection
  開始年(2015)が重複するため1点スキップする点も City/Pref の JP-Country
  パターンと同じ。
- 検証: ドイツ・UKとも男女合計が総数(census/projectionそれぞれ)と完全一致
  することを確認。

### 15.3 Population2015ランキング

旧 `PopulationController.Population2015(id, order)` の移植。新規データ取得は
不要で、既存の `data/cityinfo2015.json` を並べ替えるだけで再現できる
(順位列は都道府県フィルタ時も全国順位のまま表示。旧実装と同じ)。

- `order`: 人口順・増減数順・増減率順・コード順の4種
- 出力: `Population/Population2015/{order}/index.html`(全国)、
  `Population/Population2015/{pref}/{order}/index.html`(都道府県別)。
  4種 × 48地域(全国+47県) = 192ページ
- 旧URL(`order` クエリ省略時の既定値 `popu`)は `_redirects` で301

### 15.4 結果

全1,741市町村 + 47都道府県 + 33カ国 + 192ランキングページの
フルビルドで5,766ファイル(Cloudflare Pages の上限20,000に対して余裕あり)。

## 16. Census2010 (2026-07-05)

Phase 2の残り「Population2010系」を調査した結果、旧 `Population2010Controller`
のルートの大半は既に実装済みの機能の**旧バージョン(重複ルート)**だと判明した:

- `Ranking`/`CityAging2040`/`ListOfCitiesByArea`/`ListOfCitiesByTfr` は、
  旧コードで `Models.Population2010.*` を使う旧実装だが、実際に
  `PopulationController`(`Models.Population2015.*`、Ranking2045・
  CityAging2045・ListOfCitiesByArea・ListOfCitiesByTfr として既に移植済み)
  に置き換えられた後も残っていたデッドルート。新規実装は不要。
- `Aging2010`/`Young2010` は `Population2010.cs` 内で `HttpClient` により
  e-Stat APIを**リクエスト時に直接呼んでいた**(Aging2015/Young2015と同じ
  パターン)。K5(データ処理は完全ローカル)によりPhase 3のe-Stat系に
  まとめて移動する(新規実装ではない、既存の方針の適用)。

新規実装が必要だったのは **`Census2010`** のみ:
2010年国勢調査人口と、国立社会保障・人口問題研究所「市区町村別将来推計人口
(2008年12月推計)」の2010年推計値との比較表。旧実装(`Census2010.cshtml`)を
読むと、都道府県ごとに表を分けた**1枚の静的ページ**(ページ内アンカーで
47都道府県にジャンプ)であり、ランキングやページ分割ではなかった
(想定より遥かに小規模)。

- 一次データは旧 `App_Data/Population2010/2010/census2010List.json`
  (1,878件、2010年時点の団体コード。国勢調査人口3年分+推計2種)。
  データ処理は完全ローカル(K5)、追加の外部取得は不要。
- 市区町村・行政区の名称解決には旧 `App_Data/NAreaCode/
  StandardAreaCodeList.json`(4,588件、団体コードごとの施行/廃止年月日
  付き名称履歴)が必要だった。現行の市町村マスタ(2016年時点、1,741件)は
  2010年時点の団体コード体系と直接対応しない(合併等により差異があるため)
  ので使えず、旧実装同様「2010-10-01時点で有効な名称」を履歴から引く方式
  (`citizenlib.census2010._area_index()`)を移植した。
- 政令指定都市の行政区(区。種別コード8)は都道府県合計に含めない
  (親の市の行が既に集計済みのため、旧実装の分岐をそのまま踏襲)。
- 着色は他ページと統一して `rate_class`(5%刻み)を使用。旧実装は6項目
  それぞれ独自の連続グラデーション色だったが、人数セルも対応する増減率と
  同じ色クラスで着色する簡略化を行った(符号は常に一致するため実質的な
  情報量の低下はない)。詳細は DATA_CONTRACT.md §2.8。
- 旧実装にあった団体名へのハイパーリンクは存在しない(元々テキスト表示
  のみ)ため、静的版でもリンクは付けない。

以上でPhase 2は完了。残るはPhase 3(e-Stat由来)・Phase 4(Statdb)・
Phase 5(仕上げ)のみ。

## 17. Statdb(統計APIエクスプローラ)仕様書 (K13、2026-07-05 設計・実装は別日)

Phase 4 の中心。K3 の方針どおり **Flutter Web アプリとして再実装する**
(2026-07-05 ユーザー決定)。データ供給は K5 のとおり完全ローカル
(取得層バッチ + 静的スナップショット JSON)。

### 17.1 旧実装の構造(調査結果)

旧 Statdb は2つのコンポーネントから成っていた:

1. **statdbcron** (eCitizenToolsCore、cron で毎日実行):
   - e-Stat `getStatsList?statsNameList=Y&searchKind={1,2,3}` で統計名一覧
     (`JStatsName.json`) を維持 (kind 1=統計、2=小地域・地域メッシュ、
     3=社会・人口統計体系)
   - 統計コードごとに `getStatsList?statsCode={code}&searchKind={kind}` で
     統計表一覧を取得し `statsList/{code}.json` (kind2は `T{code}.json`、
     kind3は `C{code}.json`) を更新
   - 前回スナップショットとの差分検出 (ChangeInfo): 新規/更新の統計表を
     `latestStats.json` (統計単位、ID=取得時刻+連番) と
     `latestTables/{id}.json` (統計表単位) に追記
   - 変更のあった統計表のデータ/メタキャッシュを削除 (CacheUpdate)
2. **StatdbController** (eCitizen):
   - カタログ系ページ (Index / StatsIndex / StatsTitleList / LatestInfo 等) は
     statdbcron が維持する JSON を読んで描画するだけ
   - 統計表詳細 (StatsData/StatsMeta) は**リクエスト時に e-Stat API を呼び**
     (ファイルキャッシュ付き)、先頭2000件を表として表示

### 17.2 決定事項と論点

| # | 論点 | 決定/提案 |
|---|------|----------|
| K13 | UI 実装方式 | **Flutter Web** (ユーザー決定 2026-07-05)。`/Statdb/` 配下に SPA を配置 |
| K13-a | カタログのデータ供給 | statdbcron 相当を Python 移植 (`tools/fetch_statdb.py`)。ローカルバッチで取得・差分検出し、静的 JSON を配信 (K5準拠) |
| **D6** | **統計表の実データ表示** | **未決 (要ユーザー判断)**。全表 (数十万件) の静的化は不可能。**推奨案**: 統計表一覧までを SPA 内で提供し、各表は e-Stat の統計表表示画面 `https://www.e-stat.go.jp/dbview?sid={statsDataId}` へ外部リンク。代替案: 主要統計に限り実データもスナップショット化し SPA 内で表表示 (データ契約は両対応の設計とし、初期リリースは外部リンクのみでも後から追加可能) |

### 17.3 データ設計 (取得層)

`tools/fetch_statdb.py` (statdbcron の Python 移植):

```
data/raw/statdb/          # e-Stat 生レスポンスのキャッシュ (git管理外)
data/statdb/              # 整形済みスナップショット (git管理外、再生成可能)
├── catalog.json          # 統計名一覧 (旧 JStatsName.json 相当)
├── list/{code}.json      # kind1 統計表一覧 (統計コード別、フラット)
├── list/T{code}.json     # kind2 小地域・地域メッシュ
├── list/C00200502.json   # kind3 社会・人口統計体系
├── latest.json           # 更新情報 (旧 latestStats.json 相当、差分検出で追記)
└── latest_tables/{id}.json  # 更新ID別の統計表リスト
```

- 差分検出は旧 ChangeInfo の移植: 前回の `list/*.json` と比較し、
  新規 (UpdateType=0/2)・公開日変更 (1/3)・属性変更 (2/4) を判定して
  `latest.json` に追記。初回実行時は差分なし (全件新規扱いにしない)
- appId は `secrets.json` から読む (citizenlib/estat.py と同じ)
- e-Stat 呼び出し回数: 統計名一覧3回 + 統計コード数 (数百) 回。
  1回限り/随時の手動実行 (cron 常駐はしない。更新したいときに再実行)
- スキーマの詳細は DATA_CONTRACT.md §2.9

### 17.4 画面仕様 (Flutter SPA)

旧 URL をそのまま SPA のルートとして踏襲する (ブックマーク互換):

| ルート | 画面 | データ |
|--------|------|--------|
| `/Statdb/` | トップ: 統計名一覧 (統計/小地域/社会・人口統計体系の3節) + 更新情報最新5件 | catalog.json + latest.json |
| `/Statdb/StatsIndex/{code}` | 統計の階層ツリー (「統計名 (N件)」リンク付き)。旧実装はサーバー側で `Statics` フィールドを空白分割して木を構築していた → Flutter 側で同じロジックを実装 | list/{code}.json |
| `/Statdb/SaStatsIndex/{code}` | 小地域版の階層ツリー | list/T{code}.json |
| `/Statdb/StatsTitleList/{code}?statsname={名}` | 統計表一覧 (表番号+タイトル)。各表は D6 の決定に従い e-Stat へ外部リンク (または SPA 内表示) | list/{code}.json をクライアントでフィルタ |
| `/Statdb/SaStatsTitleList/{code}?statsname={名}` | 同上 (小地域) | list/T{code}.json |
| `/Statdb/StatsTitleList3/00200502` | 社会・人口統計体系の統計表一覧 | list/C00200502.json |
| `/Statdb/LatestInfo` | 更新情報一覧 (スナップショット時点) | latest.json |
| `/Statdb/LatestInfoSets/{id}` | 更新ID別の統計表一覧 | latest_tables/{id}.json |
| `/Statdb/StatsData/{id}` `/Statdb/StatsMeta/{id}` | (D6) 推奨案では e-Stat `dbview?sid={id}` へリダイレクト | — |

- 統計表一覧は1コード=1JSON をクライアントで読み込み・フィルタする方式。
  旧実装のようにページを統計名グルーピング単位で分けない
  (ページ数爆発の回避、K5 のファイル数上限対策)
- 検索/絞り込み (統計名のインクリメンタル検索等) は Flutter 側で追加
  実装してよい (旧実装にはない付加価値)

### 17.5 ルーティング・配置・ビルド

- Flutter プロジェクトは同一リポジトリの `statdb_app/` に置く
- ルーティングは go_router の **path URL 方式** (hash 方式は使わない。
  旧URL互換のため)。`--base-href /Statdb/`
- Cloudflare Pages の `_redirects` (generate.py が生成):
  ```
  # D6 推奨案採用時: 統計表詳細は e-Stat へ (動的プレースホルダ)
  /Statdb/StatsData/* https://www.e-stat.go.jp/dbview?sid=:splat 302
  /Statdb/StatsMeta/* https://www.e-stat.go.jp/dbview?sid=:splat 302
  # SPA フォールバック (上記以外の /Statdb/* は index.html を返す)
  /Statdb/* /Statdb/index.html 200
  ```
  注: Pages の動的リダイレクト (プレースホルダ付き) は100件まで、
  静的リダイレクトは2000件まで。スナップショット済みの表を SPA 内表示に
  切り替える場合は、その表IDの静的 200 ルールを外部リンクルールより
  前に置く
- ビルド: `flutter build web --base-href /Statdb/`。生成物 `build/web/` を
  `public/Statdb/` にコピーし、`data/statdb/` を `public/Statdb/data/` に
  コピーする (generate.py に組み込む。Flutter ビルド自体は generate.py の
  外で実行し、成果物ディレクトリを引数/規約で渡す — Python 環境に
  Flutter SDK を要求しないため)
- フォント: BIZ UDPGothic TTF を Flutter アセットに同梱 (assets/fonts/ の
  ものを再利用)。ナビゲーション等の外枠は SPA 内で再現するか、
  トップページのみ静的 HTML でラップするかは実装時に判断
- ファイル数見積: catalog 1 + list ~600 + latest_tables 数百 +
  Flutter 成果物 ~50 = +1,300 程度。現在 5,767 + 1,300 ≪ 20,000 で問題なし
- SEO: SPA 化により Statdb 配下は検索エンジンに載りにくくなるが、
  カタログページは元々検索流入がほぼないため許容 (トレードオフとして記録)

### 17.6 マルチプラットフォーム展開 (2026-07-06 ユーザー決定)

Web 版に加えて **PC(デスクトップ)版・スマホ版も公開する**。
方向性は「統計局(e-Stat本家)との競争」— カタログの見やすさ・速さで
本家より快適な統計探索体験を目指す。ネイティブ版は Web より便利に
できる余地が大きい (起動の速さ、オフラインキャッシュ、履歴・お気に入り等)。

- **同一コードベース** (`statdb_app/`) から全ターゲットをビルドする。
  ターゲット: Web / Android / iOS / Windows / Linux (macOS は保留)
- **データ層の設計**: データ取得は抽象化し、ベース URL を設定可能にする
  - Web 版: 同一オリジンの相対パス `/Statdb/data/`
  - ネイティブ版: `https://ecitizen.jp/Statdb/data/` から fetch
    (配信するのは静的スナップショット JSON のみなので K5 と整合。
    クライアントが e-Stat API を直接呼ばない原則は全プラットフォーム共通)
  - ネイティブ版はローカルキャッシュ (取得済み JSON の保存) を持ち、
    オフラインでもカタログ閲覧可能にする (Web版との差別化ポイント)
- **UI**: レスポンシブ/アダプティブ設計を最初から前提にする
  (スマホ=縦1カラム+ドロワー、PC/タブレット=マスター・ディテール2ペイン)。
  Web 版もこの恩恵を受ける
- ネイティブ版がカタログ表示だけでは価値が薄いため、**D6 (統計表実データ
  の扱い) はネイティブ版の企画と合わせて判断する**。ネイティブ限定の
  選択肢として「ユーザー自身の e-Stat appId を設定画面で入力してもらい、
  端末から直接 e-Stat API を呼ぶ」方式もあり得る (配布物に appId を
  同梱しないため K5 の趣旨=自前 appId の非露出とは矛盾しない。要判断)

| # | 論点 | 状態 |
|---|------|------|
| D7 | ネイティブ版の配布方法 | **未決**。Android: Google Play / APK直接配布、iOS: App Store (Apple Developer Program 年会費が必要)、Windows/Linux: サイトからのバイナリ直接配布 or ストア (Microsoft Store 等)。iOS はコストがかかるため優先度をユーザーと相談 |

### 17.7 Flutter 版の構成

- アプリID/パッケージ名: **`dev.aiseed.ecitizen`** (Android の
  applicationId、iOS/デスクトップの bundle id も同一系列)
- Flutter SDK: stable チャネルを `~/development/flutter` にインストール
  (2026-07-06 実施)

### 17.8 Flet (Python) 版 (K14)

Flutter 版と並行して **Flet 版**を作る。Flet は Flutter の UI を Python から
使うフレームワークで、UI 品質は Flutter 相当のまま**ロジックを Python で
自由に書き足せる**のが特長。

- **位置づけ**: Flutter 版 = 配布用の本命 (Web/ストア)。
  Flet 版 = **コードを自由に追加・改造できる実験場**。取得層
  (citizenlib/tools) と同じ Python なので、統計処理・分析コードを
  そのままアプリに持ち込める (例: pandas での集計、matplotlib 図の表示)
- **ターゲット**: Android スマホ (`flet build apk`) と
  **Chromebook の Linux 環境 (Crostini)** (Python 直接実行
  `flet run` / `python main.py`。Chromebook では Linux アプリとして起動)
- **実装順**: **Flet 版から先に作る** (ユーザー決定)。Python でカタログの
  データモデル・画面フローを固めてから Flutter 版に移植する
  (データ契約 §2.9 は共通なので二重実装のコストは UI 層のみ)
- **ディレクトリ**: `statdb_flet/` (同一リポジトリ)。`main.py` +
  `statdb_data.py` (データ層) + `test_views.py` (FakePage による全ビュー
  構築テスト) + `pyproject.toml` (flet build 用。org=dev.aiseed、
  name=ecitizen → applicationId **dev.aiseed.ecitizen**)
- **データ取得**: Flutter 版と同じ (ecitizen.jp の静的スナップショット
  JSON を fetch + `~/.cache/ecitizen-statdb/` にローカルキャッシュ。
  開発時はリポジトリ内 `data/statdb/` を直接読む。e-Stat 直叩きはしない。
  ただし D6 で「ユーザー自身の appId」案を採用する場合、Flet 版は
  Python なので最も自然に実装できる)
- 画面仕様は §17.4 と共通 (ルート構造は Flet のビュー遷移に読み替え)。
  追加機能: 統計ツリー最上位に**統計内全表の横断検索** (表題・統計名の
  部分一致。本家 e-Stat の階層クリック繰り返しより速い)
- **ビルド環境** (2026-07-06 構築済み):
  - Flet 0.85.3 (`statdb_flet/.venv`、`flet[all]`)。flet build は専用の
    Flutter SDK 3.41.7 を `~/.flet/` に自動インストールする
    (手動インストールした `~/development/flutter` の 3.44.4 は
    Flutter 版 statdb_app 用で別物)
  - Android SDK: `~/Android/sdk` (commandline-tools + platform-tools、
    ライセンス承諾済み)。JDK は システムの OpenJDK 21
  - APK ビルド: `ANDROID_HOME=$HOME/Android/sdk .venv/bin/flet build apk
    --yes` (成果物 `build/apk/`)
- **既知の注意**: `flet run --web` の開発サーバーはページリロードで
  セッションが復元されない (初回ロードのみ描画確認可)。動作確認は
  デスクトップ (`flet run`) または実機で行う

### 17.9 実装ステップ (次回作業)

1. D6 (統計表実データの扱い。§17.6 のネイティブ版企画と合わせて) の
   ユーザー決定
2. `tools/fetch_statdb.py` 実装 → `data/statdb/` 生成・検証
3. **`statdb_flet/` Flet 版の実装 (先行)**: データ層 (fetch+キャッシュ) →
   カタログ画面 (トップ/階層ツリー/統計表一覧/更新情報) →
   Chromebook Linux で動作確認 → `flet build apk` で Android 確認
4. `statdb_app/` Flutter プロジェクト作成 (`dev.aiseed.ecitizen`、
   Web/Android/Windows/Linux ターゲット)、Flet 版で固めた画面フローを移植
5. `generate.py` に public/Statdb/ 組み込み + `_redirects` 追記
6. ローカル確認 (`flutter run -d chrome` / `-d linux` →
   ビルド成果物での結合確認)
7. 検証: 旧サイトの主要ページとカタログ内容を突合
8. (D7 決定後) ネイティブ版のビルド・配布パイプライン整備
