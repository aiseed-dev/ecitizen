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

## ビルド

```bash
python tools/extract_masters.py   # マスター抽出 (国勢調査データ改定時のみ)
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
- [x] Phase 2 (一部): Prefecture (47) / Country (33) / CityPyramid (1,741) /
      Ranking2045 (全国+都道府県別) / ListOfCitiesByArea / ListOfCitiesByTfr /
      CityAging2045 / CityOldOld2045
- [ ] Phase 2 (残り): City3d (品質プロトタイプ判断待ち)、Population2015 ランキング
      (ソート順の静的化方針が未定)、Population2010 系
- [ ] Phase 3: e-Stat 由来 (CPI / Ssds / Sac / Lg / Aging2015 / Young2015 / Migration 系)
- [ ] Phase 4: 静的コンテンツ・Statdb (Flutter)
- [ ] Phase 5: 仕上げ (sitemap / 404 / 本番切替)
