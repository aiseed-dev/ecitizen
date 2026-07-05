"""Statdb カタログのデータ層 (DATA_CONTRACT.md §2.9)。

ベースはローカルディレクトリ (開発時: ../data/statdb) または
配信サイトの URL (https://ecitizen.jp/Statdb/data)。K5: e-Stat API は呼ばない。
URL の場合は ~/.cache/ecitizen-statdb/ にローカルキャッシュする
(オフラインでもカタログ閲覧できるようにする。Web版との差別化ポイント)。
"""
import json
import os
import urllib.request
from pathlib import Path

DEFAULT_SITE = "https://ecitizen.jp/Statdb/data"
_REPO_LOCAL = Path(__file__).resolve().parent.parent / "data" / "statdb"

KIND_PREFIX = {1: "", 2: "T"}
ESTAT_DBVIEW = "https://www.e-stat.go.jp/dbview?sid="


def default_base() -> str:
    """開発時はリポジトリ内の data/statdb、なければ配信サイト。"""
    env = os.environ.get("ECITIZEN_STATDB_DATA")
    if env:
        return env
    if (_REPO_LOCAL / "catalog.json").exists():
        return str(_REPO_LOCAL)
    return DEFAULT_SITE


class StatdbData:
    def __init__(self, base: str | None = None):
        self.base = base or default_base()
        self.is_remote = self.base.startswith("http")
        self.cache_dir = Path.home() / ".cache" / "ecitizen-statdb"
        self._mem: dict[str, object] = {}

    def _load(self, rel: str):
        """rel 例: "catalog.json", "list/00200521.json"。"""
        if rel in self._mem:
            return self._mem[rel]
        if self.is_remote:
            cache = self.cache_dir / rel
            try:
                req = urllib.request.Request(
                    f"{self.base}/{rel}",
                    headers={"User-Agent": "ecitizen-statdb-app/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(raw)
            except OSError:
                if not cache.exists():  # オフラインかつキャッシュなし
                    raise
                raw = cache.read_bytes()
            obj = json.loads(raw.decode("utf-8"))
        else:
            obj = json.loads((Path(self.base) / rel).read_text(encoding="utf-8"))
        self._mem[rel] = obj
        return obj

    def catalog(self) -> dict:
        return self._load("catalog.json")

    def stats(self, kind: int) -> list:
        return [e for e in self.catalog()["stats"] if e["kind"] == kind]

    def stat_name(self, kind: int, code: str) -> str:
        for e in self.catalog()["stats"]:
            if e["kind"] == kind and e["id"] == code:
                return e["name"]
        return code

    def table_list(self, kind: int, code: str) -> list:
        return self._load(f"list/{KIND_PREFIX[kind]}{code}.json")

    def latest(self) -> list:
        return self._load("latest.json")

    def latest_tables(self, latest_id: str) -> list:
        return self._load(f"latest_tables/{latest_id}.json")


def build_tree(rows: list) -> dict:
    """統計表一覧から statics の空白区切り階層ツリーを構築する
    (旧 StatsClass.GetStatsClass の移植)。

    返り値: {"children": {名前: 同型ノード}, "count": 直下の表数}
    count はそのノード名で statics が終端する表の数 (旧 Count と同じ)。
    """
    root = {"children": {}, "count": 0}
    for row in sorted(rows, key=lambda r: r["id"]):
        parts = [p for p in row["statics"].split(" ") if p]
        node = root
        for depth, name in enumerate(parts):
            node = node["children"].setdefault(name, {"children": {}, "count": 0})
            if depth == len(parts) - 1:
                node["count"] += 1
    return root


def filter_tables(rows: list, statics: str) -> list:
    """statics 完全一致の統計表を表番号順に返す (旧 StatsTitleList 相当)。"""
    hits = [r for r in rows if r["statics"] == statics]
    hits.sort(key=lambda r: r["sequence"])
    return hits
