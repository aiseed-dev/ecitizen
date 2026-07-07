# ライセンス構成 (NOTICE)

このリポジトリはプログラムとデータでライセンスが異なる。

## プログラム — AGPL-3.0-or-later

Copyright (C) 2011-2026 ecitizen.jp

ビルドスクリプト (`build_data.py`, `generate.py`, `citizenlib/`, `tools/`)、
テンプレート (`templates/`)、CSS/JS (`assets/css/`, `assets/js/`)、
Statdb アプリ (`statdb_app/`, `statdb_flet/`) は
GNU Affero General Public License v3.0 またはそれ以降 ([LICENSE](LICENSE))。

## データ — CC BY 4.0 (AGPL の対象外)

Copyright (C) aiseed.dev

このリポジトリに同梱する加工済みデータは
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/deed.ja)。
クレジットは「aiseed.dev (統計メモ帳)」を表示すること。
あわせて、元データの出典 (総務省統計局等、下表) も明記すること。

| パス | 内容 | 元データの出典 |
|------|------|---------------|
| `data/legacy/App_Data/` | 国勢調査 1980-2015・将来推計・面積・TFR 等の加工済み統計データ | 政府統計の総合窓口 (e-Stat)・総務省統計局。政府標準利用規約 (CC BY 4.0 互換) |
| `data/legacy/wwwroot/` | 旧サイトの図版・アイコン | aiseed.dev 自作 |
| `data/masters/` | 市町村名・廃置分合等のマスター | e-Stat 統計LOD + 自作 |
| `data/raw/` (git 管理外、加工前の取得キャッシュ) | IPSS 将来推計・Eurostat・ONS | IPSS 利用規約 / Eurostat (CC BY 4.0) / ONS (Open Government Licence v3.0) — 各出典の条件のまま |

生成サイト (ecitizen.jp) 上の統計データの利用も同条件
(CC BY 4.0 + 各ページ記載の出典明記)。

## フォント — SIL Open Font License 1.1

`assets/fonts/` のモリサワ BIZ UDゴシック / BIZ UD明朝は
SIL OFL 1.1 ([assets/fonts/OFL.txt](assets/fonts/OFL.txt))。
