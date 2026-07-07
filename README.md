# eCitizenStatic

eCitizen (統計メモ帳 / ecitizen.jp) の静的サイト版。
ASP.NET Core 2.2 の動的サイトを「静的サイト + Python によるデータ(JSON)生成」に
移行するプロジェクト。

- 日常の操作手順: **[MANUAL.md](docs/MANUAL.md)** (Zed の Run → Spawn Task にも登録済み)
- デプロイ: [DEPLOY.md](docs/DEPLOY.md)
- 設計: [DESIGN.md](docs/DESIGN.md) / JSON スキーマ: [DATA_CONTRACT.md](docs/DATA_CONTRACT.md)

## セットアップ

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

人口系の一次データ (旧 eCitizen の App_Data から移設) は `data/legacy/` に
git 管理で同梱。旧リポジトリのローカル checkout は不要。
フォントはモリサワ BIZ UD ゴシック / BIZ UD 明朝 (SIL OFL) の TTF を
`assets/fonts/` に同梱 (ビルド時の matplotlib チャート描画専用。Web フォント
配信はしない — 閲覧側はシステムフォント。ライセンスは同ディレクトリの OFL.txt)。
2020年国勢調査・将来推計は IPSS「日本の地域別将来推計人口(令和5年推計)」
(`data/raw/ipss/`、`tools/fetch_ipss.py` で1回限り取得。DESIGN.md §13)。
Country(海外)ページは Eurostat(census/EUROPOP2023) + ONS(UKのみ将来推計)
(`data/raw/eurostat/`, `data/raw/ons/`、`tools/fetch_eurostat.py`/
`tools/fetch_ons.py` で1回限り取得。DESIGN.md §14)。

## ライセンス

プログラムは **AGPL-3.0-or-later** ([LICENSE](LICENSE))。
同梱の加工済みデータは **CC BY 4.0** (© aiseed.dev。元データの出典明記も必要)、
フォントは SIL OFL 1.1。区分の詳細は [NOTICE.md](NOTICE.md) を参照。

## ビルド

```bash
python tools/extract_masters.py   # マスター抽出 (国勢調査データ改定時のみ)
python tools/fetch_ipss.py        # IPSS 令和5年推計を data/raw/ipss/ に取得 (初回のみ)
python tools/fetch_eurostat.py    # Eurostat census/projection を取得 (初回のみ)
python tools/fetch_ons.py         # ONS UK将来推計を取得 (初回のみ)
python tools/fetch_statdb.py      # Statdb カタログ取得 (243,806表。再実行で差分検出)
python tools/fetch_sac_lod.py     # 市町村廃置分合を e-Stat LOD から取得 (data/masters/ 更新時のみ)
python tools/fetch_ssds.py        # 社会・人口統計体系 都道府県26表 (Ssds。年次更新)
python build_data.py              # 取得層: data/ に中間 JSON を生成
python generate.py --clean        # 描画層: public/ に HTML/JSON/SVG を生成
```

開発時の部分ビルド:

```bash
python generate.py --codes 01100 13104   # 指定市町村のみ
python generate.py --limit 20            # 先頭 20 件のみ
```

## ローカル確認

```bash
python -m http.server 5012 --directory public
# → http://localhost:5012/Population/City/01100/
```

## Statdb (統計APIエクスプローラ) アプリ

Flet 版 (`statdb_flet/`、Android/Chromebook向け。DESIGN.md §17.8):

```bash
cd statdb_flet
python3 -m venv .venv && .venv/bin/pip install "flet[all]"
.venv/bin/python test_views.py    # 全ビュー構築テスト
.venv/bin/flet run                # デスクトップで起動
ANDROID_HOME=$HOME/Android/sdk .venv/bin/flet build apk --yes   # APK (build/apk/)
```

データは開発時はリポジトリ内 `data/statdb/`、実機は配信サイトの
`/Statdb/data/` を参照 (generate.py が public/ にコピーする)。

## デプロイ (Cloudflare Pages)

[cf-publish](https://github.com/aiseed-dev/cf-publish) を使う。手順は [DEPLOY.md](docs/DEPLOY.md)。

```bash
./deploy.py --dry-run   # 確認
./deploy.py             # 本番 (プロジェクト名: ecitizen)
```

## 設定 (config.json、任意)

```json
{
  "ga4_id": "G-XXXXXXXXXX",
  "adsense_client": "ca-pub-XXXXXXXXXXXXXXXX",
  "adsense_slot_banner": "0000000000",
  "adsense_slot_rect": "0000000000"
}
```

未設定 (ファイルなし) の場合、GA4/AdSense タグは出力されない。

## 実装状況

- [x] Phase 0: 基盤 (レイアウト・自前 CSS・マスター抽出・アセット)
- [x] Phase 1: `/Population/City/{code}` 1,741 市町村 + `CityData/{code}.json` + `CityList/{pref}.json`
- [x] Phase 2: Prefecture (47) / Country (33) / CityPyramid (1,741) /
      Ranking2045 (全国+都道府県別) / ListOfCitiesByArea / ListOfCitiesByTfr /
      CityAging2045 / CityOldOld2045
- [x] Population2020統合(K11): City/Pref の census に2020年実績値を追加、
      projection を IPSS令和5年推計(2020-2050)に全面更新 (DESIGN.md §13)
- [x] Country(海外)データ更新(K12): census を Eurostat、projection を
      EUROPOP2023(UKのみONS 2024年基準)に全面更新 (DESIGN.md §14)
- [x] PrefPyramid (47件、都道府県版人口ピラミッド)
- [x] CountryPyramid (33件、JP含む。Eurostat/ONSから男女別データを追加取得。DESIGN.md §15.2)
- [x] Population2015 ランキング (人口順/増減数順/増減率順/コード順 × 全国+47都道府県 = 192ページ)
- [x] Census2010 (2010年国勢調査人口と2008年推計の比較。DESIGN.md §16。
      旧Population2010Controllerの他ルートはPhase2既存機能の重複ルート、
      またはe-Stat直叩き系のためPhase3へ整理・移動)
      (City3d/Country3d/Prefecture3d は廃止・移植しない。K10)
- [x] Phase 3 (一部): Ssds 都道府県ランキング (社会・人口統計体系26表、
      5,356項目×47都道府県。トップ+分野別カタログ26+県別1,222+項目別5,356ページ。
      DESIGN.md §21)
- [ ] Phase 3 (残り): CPI / Sac / Lg / Aging2015 / Young2015 / Migration 系
- [ ] Phase 4: 静的コンテンツ・Statdb (**Flutter に決定 K13、Web + PC + スマホの
      マルチプラットフォーム展開。仕様書 = DESIGN.md §17**。
      未決 D6: 統計表実データの扱い / D7: ネイティブ版の配布方法。
      データ契約 = DATA_CONTRACT.md §2.9)
- [x] 季節調整セクション刷新 (X-13ARIMA-SEATS 中心・Linux中心の新3ページ、
      旧X-12-ARIMA記事4本は /x-12-arima/archive/ へ301+バナー。DESIGN.md §19)
- [x] ホーム (/) と人口トップ (/Population/)。JP/EUの4区分チャートは
      ビルド時SVG (旧CountryBy4AgeGroupの置き換え)
- [x] 静的コンテンツ: /about/ /privacy/ /gdp/ /gdp/fertility-rate-and-gdp/
      /io/ /excel-vba/ (旧Razorから本文抽出して移植。/Search は廃止APIのため
      移植せず、ヘッダーの検索フォームで代替)
- [x] Phase 5 (一部): 404.html、sitemap.xml (全ページ自動生成)
- [ ] Phase 5 (残り): 本番切替 (カスタムドメイン割り当て。DEPLOY.md §4)
