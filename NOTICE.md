# ライセンス構成 (NOTICE)

このリポジトリはプログラムとデータでライセンスが異なる。

## プログラム — AGPL-3.0-or-later

Copyright (C) 2011-2026 ecitizen.jp

ビルドスクリプト (`build_data.py`, `generate.py`, `citizenlib/`, `tools/`)、
テンプレート (`templates/`)、CSS/JS (`assets/css/`, `assets/js/`)、
Statdb アプリ (`statdb_app/`, `statdb_flet/`) は
GNU Affero General Public License v3.0 またはそれ以降 ([LICENSE](LICENSE))。

## データ — 各出典の利用条件に従う (AGPL の対象外)

| パス | 内容 | 出典・条件 |
|------|------|-----------|
| `data/legacy/App_Data/` | 国勢調査 1980-2015・将来推計・面積・TFR 等の加工済み統計データ | 政府統計の総合窓口 (e-Stat)・総務省統計局。政府標準利用規約 (CC BY 4.0 互換)。出典明記の上で利用可 |
| `data/legacy/wwwroot/` | 旧サイトの図版・アイコン | Copyright ecitizen.jp |
| `data/masters/` | 市町村名・廃置分合等のマスター | e-Stat 統計LOD 由来 + 自作 (同上) |
| `data/raw/` (git 管理外) | IPSS 将来推計・Eurostat・ONS の取得キャッシュ | IPSS 利用規約 / Eurostat (CC BY 4.0) / ONS (Open Government Licence v3.0) |

生成サイト (ecitizen.jp) 上の統計データを利用する場合も、
各ページに記載の出典 (総務省統計局等) を明記すること。

## フォント — SIL Open Font License 1.1

`assets/fonts/` のモリサワ BIZ UDゴシック / BIZ UD明朝は
SIL OFL 1.1 ([assets/fonts/OFL.txt](assets/fonts/OFL.txt))。
