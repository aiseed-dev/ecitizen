# デプロイマニュアル (Cloudflare Pages + cf-publish)

eCitizenStatic の `public/` を [cf-publish](https://github.com/aiseed-dev/cf-publish)
で Cloudflare Pages にデプロイする手順。wrangler (Node.js) は不要。

## 1. 事前準備 (最初の1回だけ)

### 1.1 API トークンの作成

1. [dash.cloudflare.com](https://dash.cloudflare.com/) にログイン
2. 右上のアイコン → **My Profile** → **API Tokens** → **Create Token**
3. **Create Custom Token** で以下を設定
   - Token name: `cf-publish` など任意
   - Permissions: **Account / Cloudflare Pages / Edit** (これ1つだけでよい)
4. 作成されたトークンをコピー (この画面でしか表示されない)

### 1.2 アカウント ID の確認

ダッシュボードで任意のドメインを開いた右下、または
**Workers & Pages** の Overview 右側に **Account ID** が表示される。

### 1.3 認証情報の保存

`~/.config/cloudflare/pages.env` に保存する (git 管理外の場所なので安全):

```bash
mkdir -p ~/.config/cloudflare
cat > ~/.config/cloudflare/pages.env <<'EOF'
CLOUDFLARE_API_TOKEN=ここにトークン
CLOUDFLARE_ACCOUNT_ID=ここにアカウントID
EOF
chmod 600 ~/.config/cloudflare/pages.env
```

環境変数 `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` を直接設定してもよい
(環境変数が優先される)。

### 1.4 cf-publish のインストール確認

このリポジトリの `.venv` にはローカルの `../cf-publish` が editable install
済み (`pip install -e ../cf-publish`)。cf-publish 側のコードを修正すると
そのまま反映される。確認:

```bash
.venv/bin/cf-publish --version
```

## 2. デプロイ手順

### 2.1 サイトのビルド (未ビルドまたはデータ更新時)

```bash
. .venv/bin/activate
python build_data.py         # 取得層 (data/ 更新時のみ)
python generate.py --clean   # 描画層 → public/ (フルビルド 5〜15分)
```

Statdb の Flutter Web 版を含める場合は先に
`cd statdb_app && flutter build web --base-href /Statdb/`
(generate.py が `statdb_app/build/web` を public/Statdb/ に取り込む)。

### 2.2 ドライラン (アップロード内容の確認。デプロイはされない)

```bash
./deploy.py --dry-run
```

- ファイル数・ユニーク数と「would upload ...」の一覧が表示される
- プロジェクト未作成の場合は「would create」と表示される
- 2回目以降は変更ファイルだけが対象になる (コンテンツハッシュ方式)

### 2.3 本番デプロイ

```bash
./deploy.py
```

- プロジェクト名は `ecitizen` (deploy.py 内で指定)。初回は自動作成される
- 完了すると `https://<デプロイID>.ecitizen.pages.dev` の URL が表示される
- 本番 URL は `https://ecitizen.pages.dev` (branch=main のため)

### 2.4 プレビューデプロイ (本番に影響しない確認用)

```bash
./deploy.py --branch preview
```

`main` 以外のブランチ名を指定するとプレビュー URL
(`https://preview.ecitizen.pages.dev`) に配信される。

### 2.5 その他のオプション

deploy.py のオプション:

| オプション | 意味 |
|-----------|------|
| `--dry-run` | アップロード内容の表示のみ (デプロイしない) |
| `--branch BRANCH` | main=本番、それ以外はプレビューURL |
| `--exclude 'パターン'` | fnmatch でファイルを除外 (繰り返し指定可) |

cf-publish の CLI を直接使うと `--no-create` / `--quiet` / `--json` も使える:

```bash
.venv/bin/cf-publish public --project ecitizen --json
```

## 3. デプロイ後の確認

```bash
# トップと主要ページ
curl -sI https://ecitizen.pages.dev/ | head -1
curl -sI https://ecitizen.pages.dev/Population/City/01100/ | head -1

# _redirects の動作 (旧X-12記事 → アーカイブ 301)
curl -sI https://ecitizen.pages.dev/x-12-arima/win-x-12/ | grep -i location

# Statdb SPA フォールバックとデータ
curl -sI https://ecitizen.pages.dev/Statdb/ | head -1
curl -sI https://ecitizen.pages.dev/Statdb/data/catalog.json | head -1
```

ブラウザでの確認ポイント:
- `/Population/City/01100/` — グラフ (SVG) とフォント (BIZ UD) の表示
- `/Statdb/` — Flutter Web 版統計APIエクスプローラの起動とカタログ表示
- `/x-12-arima/` — 季節調整セクション
- `/Population/Census2010/` — セル色分け

Statdb がデプロイされると、ネイティブアプリ (Flet 版 APK 等) も
`https://ecitizen.jp/Statdb/data/` からデータを取得できるようになる
(カスタムドメイン設定後。それまでは pages.dev ドメイン)。

## 4. カスタムドメイン (ecitizen.jp) の割り当て

本番切替 (Phase 5) の時に実施:

1. ダッシュボード → **Workers & Pages** → `ecitizen` プロジェクト →
   **Custom domains** → **Set up a custom domain**
2. `ecitizen.jp` (と `www.ecitizen.jp`) を追加
3. DNS が Cloudflare 管理なら CNAME が自動設定される

## 5. トラブルシューティング

| 症状 | 対処 |
|------|------|
| `set CLOUDFLARE_API_TOKEN ...` エラー | §1.3 の認証情報ファイルを確認。環境変数が空文字で設定されていると上書きされるので `env \| grep CLOUDFLARE` も確認 |
| 401/403 エラー | トークンの権限が「Cloudflare Pages: Edit」になっているか、Account ID が正しいか確認 |
| 429 (rate limit) | cf-publish が自動リトライする。頻発する場合は時間を置く |
| ファイル数・サイズ超過 | プリフライトで検出される。上限は 20,000ファイル / 25MiB per file。現状は約6,200ファイル・最大11MBで余裕あり |
| デプロイされたのに反映されない | Pages の CDN キャッシュ。`_headers` の Cache-Control (人口系JSON=1日) を確認。強制リロード (Ctrl+Shift+R) で確認 |

## 6. 運用メモ

- デプロイは**ユーザー自身が実行する** (このプロジェクトの運用ルール)
- `public/` は git 管理外。デプロイ前に必ずローカルでフルビルドする
- コンテンツハッシュのキャッシュは wrangler と共有されるため、
  wrangler (`wrangler pages deploy public/`) に切り替えても再アップロードは
  発生しない
