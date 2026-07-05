# eCitizenStatic

eCitizen (統計メモ帳 / ecitizen.jp) の静的サイト版。
ASP.NET Core 2.2 の動的サイトを「静的サイト + Python によるデータ(JSON)生成」に
移行するプロジェクト。設計は [DESIGN.md](DESIGN.md)、JSON スキーマは
[DATA_CONTRACT.md](DATA_CONTRACT.md) を参照。

## セットアップ

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

前提: 旧リポジトリ `../eCitizen/eCitizen` (App_Data がデータの一次ソース)。
フォントはモリサワ BIZ UD ゴシック / BIZ UD 明朝 (SIL OFL) を `assets/fonts/` に同梱
(サイト配信用 woff2 + matplotlib 用 TTF。ライセンスは同ディレクトリの OFL.txt)。
2020年国勢調査・将来推計は IPSS「日本の地域別将来推計人口(令和5年推計)」
(`data/raw/ipss/`、`tools/fetch_ipss.py` で1回限り取得。DESIGN.md §13)。
Country(海外)ページは Eurostat(census/EUROPOP2023) + ONS(UKのみ将来推計)
(`data/raw/eurostat/`, `data/raw/ons/`、`tools/fetch_eurostat.py`/
`tools/fetch_ons.py` で1回限り取得。DESIGN.md §14)。

## ビルド

```bash
python tools/extract_masters.py   # マスター抽出 (国勢調査データ改定時のみ)
python tools/fetch_ipss.py        # IPSS 令和5年推計を data/raw/ipss/ に取得 (初回のみ)
python tools/fetch_eurostat.py    # Eurostat census/projection を取得 (初回のみ)
python tools/fetch_ons.py         # ONS UK将来推計を取得 (初回のみ)
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

## デプロイ (Cloudflare Pages)

```bash
wrangler pages deploy public/
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
- [ ] Phase 3: e-Stat 由来 (CPI / Ssds / Sac / Lg / Aging2015 / Young2015 / Migration 系)
- [ ] Phase 4: 静的コンテンツ・Statdb (**Flutter Web に決定 K13、仕様書 = DESIGN.md §17**。
      未決 D6: 統計表実データの扱い。データ契約 = DATA_CONTRACT.md §2.9)
- [ ] Phase 5: 仕上げ (sitemap / 404 / 本番切替)
