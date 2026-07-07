# tools/ — 外部データ取得ツール

取得層 ([../build_data.py](../build_data.py)) の上流にあたる、外部一次データの
取得スクリプト群。取得結果は `data/raw/` (キャッシュ、git 管理外) と
`data/masters/`・`data/ssds/` 等 (加工済み、一部コミット対象) に保存される。
運用タイミングの一覧は [docs/MANUAL.md §2](../docs/MANUAL.md)、
設計の背景は [docs/DESIGN.md](../docs/DESIGN.md) を参照。

## 一覧

| ツール | 取得元 | appId | 出力 | 実行タイミング |
|--------|--------|:-----:|------|---------------|
| `fetch_statdb.py` | e-Stat API (getStatsList) | 要 | `data/statdb/` (スナップショット+差分) | 随時 (カタログ更新) |
| `fetch_ssds.py` | e-Stat API (getStatsData) | 要 | `data/raw/ssds/` → `data/ssds/` | 社会・人口統計体系の年次更新時 |
| `fetch_cpi.py` | e-Stat API (getStatsData) | 要 | `data/cpi.json` | CPI の月次更新時 |
| `fetch_sac_lod.py` | e-Stat 統計LOD (SPARQL) | 不要 | `data/masters/municipal_changes.json` (コミット) | 市町村の廃置分合があった時 (年数回) |
| `fetch_ipss.py` | 国立社会保障・人口問題研究所 | 不要 | `data/raw/ipss/` | 将来推計人口の改定時のみ (5年に1回程度) |
| `fetch_eurostat.py` | Eurostat API | 不要 | `data/raw/eurostat/` | EUROPOP 改定・census 更新時 (年1回確認) |
| `fetch_ons.py` | 英国 ONS | 不要 | `data/raw/ons/` | UK 将来推計の改定時のみ |
| `extract_masters.py` | 旧 eCitizen の C# ソース | — | `data/masters/*.json` (コミット済み) | 再実行不要 (要: 旧リポジトリの checkout) |
| `find_2020_census_table.py` | e-Stat API | 要 | (標準出力のみ) | 1回限りの調査用。再実行不要 |

各ツールの詳細な usage は先頭 docstring に記載。

## 前提

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

e-Stat API を使うツール (上表で「appId 要」) は、リポジトリ直下に
`secrets.json` が必要 (git 管理外):

```bash
cp secrets.json.example secrets.json   # estat_app_id を書き込む
```

appId は [e-Stat API 機能](https://www.e-stat.go.jp/api/) の
利用登録 (無料) で取得できる。

## 設計上の約束 (K5)

- 外部 API を呼ぶのは**ローカルバッチだけ**。生成サイトや配布アプリは
  一切外部 API を呼ばない (スナップショット方式)
- 取得キャッシュは `data/raw/` に置き、`--use-raw` で API を呼ばずに
  再加工できるようにする (レートリミット節約・オフライン開発)
- 加工結果のうち再取得不能なもの・マスターはコミット、再生成可能な
  中間データは git 管理外

## e-Stat API 利用上の注意

e-Stat API の利用規約により、取得データを用いたサービスを公開する場合は
次の注記が必要 (本サイトはフッターに表示済み):

> このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、
> サービスの内容は国によって保証されたものではありません。
