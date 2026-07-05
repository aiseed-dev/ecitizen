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

- `/Population/Prefecture/{id}`、`/Population/Country/{id}` と各 Data JSON
- `/Population/City3d`・`CityPyramid`・`CityPyramidData/{id}/{year}`
- ランキング系 (`Ranking`, `Aging2015`, `Young2015`, `CityAging2045`,
  `CityOldOld2045`, `ListOfCitiesByArea`, `ListOfCitiesByTfr`, `Population2015`)
- `/Population/YoungMigration`, `/Population/Migration` (+ Data JSON)
- Population2010 系 (`Census2010`, `Ranking`, `City` ほか)

### Phase 3: e-Stat 由来ページ(定期更新が必要)

- Living (CPI): `Cpi`, `CpiJapan`, `CpiTokyoKubu`, `CpiForSelectedAreas` +
  `CpiIndex`/`CpiChange`/`CpiJapanJson` 等の JSON。
  取得層が e-Stat API から CPI を取得 → 全カテゴリ分の JSON を事前生成。
- Ssds (都道府県ランキング): `Index`, `Pref/{id}`, `Indicators` + `DataJson/{id}`。
  47 都道府県 × カテゴリで全組み合わせを事前生成。
- Sac (市区町村コード表): `Index`, `Code` — NAreaCode サービスのデータを静的化。
- Lg / Lc (市町村の統計・豆知識): `GetCity`/`GetLgInfo` は市町村ごとの JSON に静的化。

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
- 対象グラフ 5 種: 積み上げ縦棒 (人口推移) / 人口ピラミッド (横棒) /
  折れ線 (CPI) / 散布図 (出生率×GDP) / 3D 積み上げ棒。
  **3D (City3d) は mplot3d で静的画像化できるが見栄えは要確認** —
  Phase 2 でプロトタイプを作り、品質が不十分なら City3d ページは廃止する
  (トップからのリンクを外し、URL は City へ 301)。
- `Population/CityData/{code}.json` 等の公開 JSON は、グラフが SVG 化された後も
  **データ API 互換として生成を継続**する (§3.1 のデータ契約は不変。
  外部からの直接利用と将来の用途変更に備える)。

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
| K6 | Analytics / AdSense | **変更する**。UA タグ → GA4 (gtag.js) に差し替え。AdSense は現行推奨タグへ更新。測定 ID・クライアント ID・スロットはビルド設定 (`config.json`) で注入し、テンプレートに直書きしない |
| K7 | ホスティング先 | **Cloudflare Pages** (制約と構成は §9.1) |

| K8 | グラフ描画 | **Python によるビルド時 SVG 生成**(描画層の一部としてローカル処理)。クライアント側チャートライブラリ (Highcharts/ECharts/D3 等) は使わない。詳細は §8.6 |
| K9 | フォント | **モリサワ BIZ UD ゴシック / BIZ UD 明朝** (SIL OFL 版) をセルフホスト。本文 = BIZ UDPGothic (400/700)、見出し (h2〜h6) = BIZ UDPMincho (400)、表・グラフ SVG = BIZ UDGothic (等幅数字で桁揃え)。woff2 + OFL.txt を `/fonts/` で配信、TTF はリポジトリ同梱で matplotlib のレイアウト計算にも使用。外部フォント配信 (Google Fonts CDN / TypeSquare) は使わない。商用版 UD 新ゴへの差し替えは Morisawa Fonts 契約が必要なため不採用 |

(初版の未決事項 D1〜D5 はすべて K2〜K8 として決定済み。残る個別判断は City3d ページの扱いのみ — §8.6 参照。)

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
