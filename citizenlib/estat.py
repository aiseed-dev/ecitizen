"""e-Stat API 3.0 クライアント (DESIGN.md K5: ローカルバッチ専用、ライブ呼び出しはしない)。

appId は `secrets.json` (git 管理外。リポジトリ直下) から読む:
    {"estat_app_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}

使い方:
    from citizenlib.estat import EstatClient
    client = EstatClient.from_secrets()
    tables = client.get_stats_list(searchWord="国勢調査 令和2年 人口等基本集計")
    data = client.get_stats_data(statsDataId="0003xxxxxx")
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SECRETS = ROOT / "secrets.json"
USER_AGENT = "eCitizenStatic-build/1.0 (+https://github.com/aiseed-dev/ecitizen; local batch, not live)"


class EstatError(RuntimeError):
    pass


class EstatClient:
    def __init__(self, app_id: str, min_interval: float = 0.3):
        self.app_id = app_id
        self.min_interval = min_interval
        self._last_request = 0.0

    @classmethod
    def from_secrets(cls, path: Path = DEFAULT_SECRETS) -> "EstatClient":
        if not path.exists():
            raise EstatError(
                f"{path} が見つかりません。"
                '{"estat_app_id": "..."} の形式で appId を保存してください '
                "(git 管理外。.gitignore 済み)。")
        secrets = json.loads(path.read_text(encoding="utf-8"))
        app_id = secrets.get("estat_app_id")
        if not app_id:
            raise EstatError(f"{path} に estat_app_id がありません。")
        return cls(app_id)

    def _get(self, endpoint: str, params: dict) -> dict:
        # WeatherStatic/旧サイト踏襲: 常識的な間隔でアクセスする (§12)
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        query = dict(params)
        query["appId"] = self.app_id
        url = f"{API_BASE}/{endpoint}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise EstatError(f"e-Stat API 呼び出し失敗 ({endpoint}): {e}") from e
        finally:
            self._last_request = time.monotonic()
        return body

    def get_stats_list(self, **params) -> dict:
        """統計表情報取得 (getStatsList)。統計表IDの検索に使う。"""
        body = self._get("getStatsList", params)
        result = body.get("GET_STATS_LIST", {}).get("RESULT", {})
        if result.get("STATUS") != 0:
            raise EstatError(f"getStatsList エラー: {result}")
        return body["GET_STATS_LIST"]

    def get_stats_data(self, statsDataId: str, **params) -> dict:
        """統計データ取得 (getStatsData)。100,000件超は NEXT_KEY でページング。"""
        params = {"statsDataId": statsDataId, **params}
        body = self._get("getStatsData", params)
        result = body.get("GET_STATS_DATA", {}).get("RESULT", {})
        if result.get("STATUS") != 0:
            raise EstatError(f"getStatsData エラー ({statsDataId}): {result}")
        return body["GET_STATS_DATA"]
