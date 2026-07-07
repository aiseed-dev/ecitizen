# ecitizen — 統計メモ帳

[ecitizen.jp](https://ecitizen.jp) のソース一式。人口・GDP など日本と世界の
公的統計をグラフで見やすく提供するサイトと、約24万の統計表カタログを
高速に探せる**統計APIエクスプローラ** (Web / PC / スマホアプリ)。

15年運営した ASP.NET の動的サイトを「**静的サイト + Python による
ビルド時生成**」に移行したもので、実行時にはサーバーもデータベースも
外部 API も使わない。

## 特徴

- **完全静的**: 1,741市町村 × 35年分の人口ページ約13,000ファイルを
  ビルド時に生成。チャートは matplotlib の SVG (テキスト保持)
- **データ同梱**: 確定した歴史統計 (国勢調査 1980–2015 等) は
  `data/legacy/` に git 管理で同梱 — clone するだけでビルドできる
- **外部 API はローカルバッチだけ**: e-Stat 等の取得は `tools/` の
  スクリプトで行い、成果物をスナップショットとして凍結する
- **アプリも同じスナップショットを参照**: Flutter 版 (Web/PC/スマホ) と
  Flet 版 (Python) の統計APIエクスプローラが、サイトと同一の静的 JSON で動く

## クイックスタート

```bash
git clone https://github.com/aiseed-dev/ecitizen.git && cd ecitizen
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python build_data.py            # data/ に中間 JSON を生成 (約1分)
python generate.py --clean      # public/ にサイト一式を生成 (5〜15分)
python -m http.server 5012 --directory public
# → http://localhost:5012/
```

開発時の部分ビルド: `python generate.py --codes 01100` (指定市町村のみ)。
外部データの再取得 (通常は不要) は [tools/README.md](tools/README.md)。

## ドキュメント

| 文書 | 内容 |
|------|------|
| [docs/MANUAL.md](docs/MANUAL.md) | 運用マニュアル (セットアップ・ビルド・デプロイ・トラブル対応) |
| [docs/DESIGN.md](docs/DESIGN.md) | 設計書 (設計方針と各機能の設計) |
| [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) | データ契約 (中間 JSON のスキーマ) |
| [docs/DEPLOY.md](docs/DEPLOY.md) | デプロイ手順 (Cloudflare Pages + cf-publish) |
| [docs/STATUS.md](docs/STATUS.md) | 実装状況 (フェーズ別チェックリスト) |
| [tools/README.md](tools/README.md) | 外部データ取得ツール一覧 |

## Statdb (統計APIエクスプローラ) アプリ

- `statdb_app/` — **Flutter 版**。ブラウザで今すぐ使える
  ([ecitizen.jp/Statdb/](https://ecitizen.jp/Statdb/))。同じコードから
  PC・Android アプリも作れる
- `statdb_flet/` — **Python (Flet) 版**。デスクトップや Android、
  Chromebook の Linux 環境で動く。Python が読めれば自分好みに
  改造しやすい

e-Stat の全統計表カタログ (約24万表) を検索・閲覧して目的の統計表に
たどり着くためのツール。カタログはビルド時に取得した静的スナップショットを
参照するので、検索は常に一瞬で、オフラインでも動き、統計局のサーバーに
負荷をかけない (実行時の API アクセスはゼロ)。開発手順は
[docs/MANUAL.md §5](docs/MANUAL.md)。

## ライセンス

- プログラム: **AGPL-3.0-or-later** ([LICENSE](LICENSE))
- 同梱の加工済みデータ: **CC BY 4.0** (© aiseed.dev。元データの出典明記も必要)
- フォント (ビルド用 TTF): SIL OFL 1.1

区分の詳細は [NOTICE.md](NOTICE.md)。
