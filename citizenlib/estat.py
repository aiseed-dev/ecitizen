"""e-Stat API 3.0 クライアント (DESIGN.md K5: ローカルバッチ専用、ライブ呼び出しはしない)。

appId は `secrets.json` から読む (形式: {"estat_app_id": "xxxx..."})。
探索順: リポジトリ直下 (開発用の上書き) → ~/.config/ecitizen/secrets.json (推奨)。

使い方:
    from citizenlib.estat import EstatClient
    client = EstatClient.from_secrets()
    tables = client.get_stats_list(searchWord="国勢調査 令和2年 人口等基本集計")
    data = client.get_stats_data(statsDataId="0003xxxxxx")
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "eCitizenStatic-build/1.0 (+https://github.com/aiseed-dev/ecitizen; local batch, not live)"


def _secrets_paths() -> list[Path]:
    """secrets.json の探索順: リポジトリ直下 (開発用の上書き) → XDG config。"""
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [ROOT / "secrets.json", xdg / "ecitizen" / "secrets.json"]


class EstatError(RuntimeError):
    pass


class EstatClient:
    def __init__(self, app_id: str, min_interval: float = 0.3):
        self.app_id = app_id
        self.min_interval = min_interval
        self._last_request = 0.0

    @classmethod
    def from_secrets(cls, path: Path | None = None) -> "EstatClient":
        candidates = [path] if path else _secrets_paths()
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            locations = " または ".join(str(p) for p in candidates)
            raise EstatError(
                f"secrets.json が見つかりません ({locations})。"
                "secrets.json.example をコピーして appId を書き込んでください "
                "(取得: https://www.e-stat.go.jp/api/ の利用登録)。"
                "推奨の置き場所は ~/.config/ecitizen/secrets.json。")
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

    def get_stats_list_body(self, **params) -> dict:
        """getStatsList の GET_STATS_LIST をステータス検査なしで返す。

        「該当データなし」(STATUS=1) を正常系として扱いたい呼び出し側
        (tools/fetch_statdb.py) 用。
        """
        return self._get("getStatsList", params)["GET_STATS_LIST"]

    def get_stats_data(self, statsDataId: str, **params) -> dict:
        """統計データ取得 (getStatsData)。100,000件超は NEXT_KEY でページング。"""
        params = {"statsDataId": statsDataId, **params}
        body = self._get("getStatsData", params)
        result = body.get("GET_STATS_DATA", {}).get("RESULT", {})
        if result.get("STATUS") != 0:
            raise EstatError(f"getStatsData エラー ({statsDataId}): {result}")
        return body["GET_STATS_DATA"]
