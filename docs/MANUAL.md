# 運用マニュアル

ecitizen (統計メモ帳 / ecitizen.jp) の日常運用の手順書。
設計は [DESIGN.md](DESIGN.md)、スキーマは [DATA_CONTRACT.md](DATA_CONTRACT.md)、
デプロイの詳細は [DEPLOY.md](DEPLOY.md) を参照。

**Zed を使っている場合**: 主要な操作は Run → Spawn Task に登録済み
(`.zed/tasks.json`)。コマンドを覚えなくてもタスク名で実行できる。

## 0. 全体の流れ

```
外部データ取得 (tools/fetch_*.py、必要な時だけ)
      ↓
build_data.py    … 取得層: data/ に中間JSONを生成 (約1分)
      ↓
generate.py --clean … 描画層: public/ にサイト一式を生成 (5〜15分)
      ↓
ローカル確認 (http.server) → ./deploy.py --dry-run → ./deploy.py
```

## 1. 環境セットアップ (新しいマシンでの初回のみ)

```bash
cd ~/dev/ecitizen
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pip install -e ../cf-publish        # デプロイ用 (ローカルの cf-publish)

# e-Stat appId (Statdb カタログ取得に必要)
mkdir -p ~/.config/ecitizen && chmod 700 ~/.config/ecitizen
cp secrets.json.example ~/.config/ecitizen/secrets.json   # → estat_app_id を書き込む
chmod 600 ~/.config/ecitizen/secrets.json
# appId の取得 (無料): https://www.e-stat.go.jp/api/
# リポジトリ直下の secrets.json も可 (開発用の上書き。git 管理外)
```

人口系の一次データは `data/legacy/` に同梱 (git 管理) なので checkout だけで
ビルドできる。旧 eCitizen リポジトリは不要。Statdb アプリの開発環境は §5 を参照。

## 2. データ取得 (tools/) — いつ何を実行するか

詳細は [tools/README.md](../tools/README.md)。

| ツール | 取得元 | 実行タイミング |
|--------|--------|---------------|
| `fetch_statdb.py` | e-Stat API | **随時** (統計表カタログの更新。再実行すると前回との差分が「更新情報」に載る) |
| `fetch_sac_lod.py` | e-Stat 統計LOD | 廃置分合があった時 (年数回。data/masters/municipal_changes.json を更新→コミット) |
| `fetch_ssds.py` | e-Stat API | 社会・人口統計体系の年次更新時 (26表・約500万値、初回10分程度。--use-raw でキャッシュから再加工) |
| `fetch_ipss.py` | IPSS | 将来推計人口の改定時のみ (5年に1回程度) |
| `fetch_eurostat.py` | Eurostat | EUROPOP改定・census更新時 (年1回確認で十分) |
| `fetch_ons.py` | 英国ONS | UK将来推計の改定時のみ |
| `extract_masters.py` | 旧C#ソース | 実行不要 (マスター改定の時だけ) |

```bash
. .venv/bin/activate
python tools/fetch_statdb.py            # 例: Statdbカタログの更新
python tools/fetch_statdb.py --use-raw  # data/raw/ のキャッシュから再生成 (API を呼ばない)
```

`data/raw/` は取得キャッシュ (git 管理外)。消しても再取得できるが、
IPSS/statdb は取得に時間がかかるので基本は残しておく。

## 3. ビルド

```bash
. .venv/bin/activate
python build_data.py           # 取得層。data/ 更新後は必ず実行
python generate.py --clean     # 描画層フルビルド (5〜15分、CPU全コア使用)

# 開発時の部分ビルド (public/ を消さずに一部だけ更新)
python generate.py --codes 01100 13104   # 指定市町村のみ
python generate.py --limit 20            # 先頭20市町村のみ
```

ビルド末尾のスモークチェック (ファイル数の assert と Cloudflare 上限警告)
がエラーなく出れば成功。現在の規模: 約6,200ファイル (上限 20,000)。

## 4. ローカル確認

```bash
python -m http.server 5012 --directory public
# → http://localhost:5012/
```

確認ポイント:
- `/Population/City/01100/` — 市町村ページ (グラフ・フォント)
- `/Population/Census2010/` — 2010年国勢調査比較 (セル色分け)
- `/x-12-arima/` — 季節調整セクション
- `/Statdb/` — 統計APIエクスプローラ (Flutter Web。ビルド済みの場合)

## 5. Statdb アプリ (統計APIエクスプローラ)

### 5.1 Flet 版 (Python。実験場・Android/Chromebook向け)

```bash
cd statdb_flet
python3 -m venv .venv && .venv/bin/pip install "flet[all]"   # 初回のみ

.venv/bin/python test_views.py    # 全ビュー構築テスト (実データで検証)
.venv/bin/flet run                # デスクトップで起動
ANDROID_HOME=$HOME/Android/sdk .venv/bin/flet build apk --yes   # APK (→ build/apk/ecitizen.apk)
```

- データ参照先: 開発時はリポジトリ内 `data/statdb/`、実機は配信サイトの
  `/Statdb/data/` (環境変数 `ECITIZEN_STATDB_DATA` で上書き可)
- 既知の癖: `flet run --web` はページリロードでセッションが切れる。
  動作確認はデスクトップ (`flet run`) で行う

### 5.2 Flutter 版 (配布本命。Web/ストア向け)

```bash
cd statdb_app
~/development/flutter/bin/flutter analyze
~/development/flutter/bin/flutter build web --base-href /Statdb/
# → generate.py が build/web を public/Statdb/ に取り込む
```

- アプリID: `dev.aiseed.ecitizen`
- Web のデータ参照先は同一オリジン `/Statdb/data` を自動解決。
  開発時は `--dart-define=STATDB_DATA_BASE=http://localhost:5012/Statdb/data`

## 6. テスト・検証

```bash
.venv/bin/python -m citizenlib.municipal        # 廃置分合データの自己チェック
(cd statdb_flet && .venv/bin/python test_views.py)  # Flet版 全ビュー構築テスト
```

数値の検証はビルド時 assert (build_data.py / generate.py 内) が兼ねる。

## 7. デプロイ

→ [DEPLOY.md](DEPLOY.md)。要点だけ:

```bash
./deploy.py --dry-run    # アップロード内容の確認
./deploy.py              # 本番 (プロジェクト: ecitizen、本番URLは https://ecitizen.jp)
./deploy.py --branch preview   # プレビューURLで確認
```

デプロイは**ユーザー自身が実行する** (運用ルール)。

## 8. サイト設定 (config.json、任意)

```json
{
  "ga4_id": "G-XXXXXXXXXX",
  "adsense_client": "ca-pub-XXXXXXXXXXXXXXXX",
  "adsense_slot_banner": "0000000000",
  "adsense_slot_rect": "0000000000"
}
```

未設定 (ファイルなし) の場合、GA4/AdSense タグは出力されない。

## 9. git 運用

- 機能単位でローカルコミット (日本語の説明的メッセージ)
- **push はユーザー自身が行う** (settings で `git push` はブロック済み)
- コミット対象: ソース・テンプレート・`data/masters/`・ドキュメント。
  生成物 (`public/`、`data/population/` 等) と `secrets.json` は管理外

## 10. よくあるトラブル

| 症状 | 対処 |
|------|------|
| generate.py の assert で停止 | data/ が古い。`build_data.py` を先に実行 |
| fetch_statdb.py で `secrets.json が見つかりません` | §1 の secrets.json を作成 |
| チャートの日本語が豆腐 | `assets/fonts/` の TTF が無い (リポジトリ同梱。checkout し直す) |
| Flet デスクトップが起動しない | `pip install "flet[all]"` (flet だけでは desktop/web が入らない) |
| Statdb 実機でデータ読込エラー | サイト未デプロイ。§7 でデプロイするか `ECITIZEN_STATDB_DATA` をローカルに向ける |
| デプロイが 401/403 | DEPLOY.md §5 (トークン権限・アカウントID) |
