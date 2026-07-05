#!/usr/bin/env python3
"""Statdb カタログの取得 (旧 statdbcron の移植。DESIGN.md §17.3、DATA_CONTRACT.md §2.9)。

e-Stat getStatsList から統計名一覧と統計コード別の統計表一覧を取得し、
data/statdb/ にスナップショットを生成する。前回スナップショットがあれば
差分検出 (旧 ChangeInfo 相当) を行い latest.json に追記する。

usage:
  python tools/fetch_statdb.py                 # 全統計コード
  python tools/fetch_statdb.py --codes 00200521 00200502   # 指定コードのみ (開発用)
  python tools/fetch_statdb.py --use-raw       # data/raw/statdb/ のキャッシュを使う (API を呼ばない)

K5: ローカルバッチ専用。appId は secrets.json から読む。
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from citizenlib.estat import EstatClient  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "statdb"
OUT_DIR = ROOT / "data" / "statdb"

# kind → list ファイル名の接頭辞 (旧 statsList ディレクトリの命名)。
# 旧 API 2.0 の kind3 (社会・人口統計体系、C プレフィックス) は API 3.0 で
# kind1 に統合された (00200502 が kind1 の統計名一覧に含まれる) ため廃止。
KIND_PREFIX = {1: "", 2: "T"}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.rename(path)


def sequence(no: str) -> str:
    """旧 StatsList.Sequence(): 表番号を桁揃えして並べ替えキーにする。
    先頭要素は3桁、'-' 区切りの後続要素は2桁にゼロ埋め。"""
    if "-" in no:
        parts = no.split("-")
        out = [parts[0].zfill(3)]
        out += [p.zfill(2) for p in parts[1:]]
        return "-".join(out)
    return no.zfill(3)


def fetch_catalog(client: EstatClient | None, use_raw: bool) -> list:
    """統計名一覧 (statsNameList=Y、searchKind 1..3)。旧 JStats.GetStatsNameList()。"""
    entries = []
    for kind in (1, 2):
        raw_path = RAW_DIR / f"namelist_{kind}.json"
        if use_raw and raw_path.exists():
            body = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            body = client.get_stats_list(statsNameList="Y", searchKind=kind)
            write_json(raw_path, body)
        infs = body["DATALIST_INF"]["LIST_INF"]
        if isinstance(infs, dict):
            infs = [infs]
        for e in infs:
            entries.append({
                "kind": kind,
                "id": e["@id"],
                "name": e["STAT_NAME"]["$"],
                "gov_org": e["GOV_ORG"]["$"],
            })
    entries.sort(key=lambda e: (e["kind"], e["id"]))
    return entries


def fetch_table_list(client: EstatClient | None, entry: dict, use_raw: bool) -> list | None:
    """統計コード1件分の統計表一覧。旧 StatsList.GetStatsList()。

    status 1 (0件) は空リスト。取得失敗は None (既存スナップショットを残す)。
    """
    kind, code = entry["kind"], entry["id"]
    raw_path = RAW_DIR / f"list_{KIND_PREFIX[kind]}{code}.json"
    if use_raw and raw_path.exists():
        body = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        try:
            body = client.get_stats_list_body(statsCode=code, searchKind=kind)
        except Exception as e:  # ネットワーク断等。1コードの失敗で全体を止めない
            print(f"  取得失敗 {code} (kind{kind}): {e}", file=sys.stderr)
            return None
        write_json(raw_path, body)

    status = body["RESULT"]["STATUS"]
    if status == 1:  # 該当データなし
        return []
    if status != 0:
        print(f"  API エラー {code} (kind{kind}): {body['RESULT']}", file=sys.stderr)
        return None

    infs = body["DATALIST_INF"]["TABLE_INF"]
    if isinstance(infs, dict):
        infs = [infs]
    rows = []
    for t in infs:
        title = t.get("TITLE", "")
        if isinstance(title, dict):
            no = str(title.get("@no", "-"))
            title_text = title.get("$", "")
        else:  # TITLE が文字列のみの表 (表番号なし)
            no = "-"
            title_text = str(title)
        rows.append({
            "id": t["@id"],
            "statics": t["STATISTICS_NAME"],
            "no": no,
            "title": title_text,
            "cycle": t.get("CYCLE", "-"),
            "sdate": str(t.get("SURVEY_DATE", "0")),
            "open": t.get("OPEN_DATE", "-"),
            "num": t.get("OVERALL_TOTAL_NUMBER"),
            "update": t.get("UPDATED_DATE", "-"),
            "sequence": sequence(no),
        })
    return rows


def title_split(statics: str) -> str:
    """旧 ChangeInfo.TitleSplit(): 統計名の先頭2階層。"""
    parts = statics.split(" ")
    return " ".join(parts[:2]) if len(parts) > 1 else statics


def detect_changes(entry: dict, new_rows: list, old_rows: list,
                   latest: list, latest_tables_dir: Path,
                   now_id_base: str, today: str, counter: list) -> None:
    """旧 ChangeInfo.GetChangeInfo() の移植。latest への追記と latest_tables の生成。

    update_type: 0=新規(公開日=取得日)/2=新規、1=公開日変更(取得日)/3=公開日変更、
    4=属性変更。旧実装の datetimetype と同じ。
    """
    old_by_id = {r["id"]: r for r in old_rows}
    pending: dict[str, dict] = {}  # latest id → {"stat": latest行, "tables": [...]}

    def update_latest(update_type: int, row: dict) -> None:
        dtype = update_type + 2
        if update_type < 3 and row.get("open") == today:
            dtype = update_type
        key = f"{entry['id']}|{title_split(row['statics'])}|{dtype}"
        # 既存の latest 行 (今回実行分) を探す
        found = None
        for p in pending.values():
            s = p["stat"]
            if (s["stat_code"] == entry["id"]
                    and s["title"] == title_split(row["statics"])
                    and s["update_type"] == dtype):
                found = p
                break
        if found is None:
            if counter[0] > 999:
                return
            latest_id = now_id_base + f"{counter[0]:03d}"
            counter[0] += 1
            found = {"stat": {"id": latest_id, "stat_code": entry["id"],
                              "title": title_split(row["statics"]),
                              "open": row.get("open"), "update_type": dtype},
                     "tables": []}
            pending[key] = found
        found["tables"].append({
            "stats_data_id": row["id"], "statics": row["statics"],
            "title": row["title"], "no": row["no"],
            "sequence": row["sequence"], "update_type": dtype,
        })

    for row in new_rows:
        old = old_by_id.get(row["id"])
        if old is None:
            update_latest(0, row)
        elif row.get("open") != old.get("open"):
            update_latest(1, row)
        elif any(row.get(k) != old.get(k)
                 for k in ("statics", "no", "title", "cycle", "sdate", "update")):
            update_latest(2, row)

    for p in pending.values():
        latest.append(p["stat"])
        write_json(latest_tables_dir / f"{p['stat']['id']}.json", p["tables"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", nargs="*", help="対象統計コードを限定 (開発用)")
    ap.add_argument("--use-raw", action="store_true",
                    help="data/raw/statdb/ のキャッシュから再生成 (API を呼ばない)")
    args = ap.parse_args()

    client = None if args.use_raw else EstatClient.from_secrets()
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")

    catalog = fetch_catalog(client, args.use_raw)
    print(f"統計名一覧 {len(catalog)} 件 "
          f"(統計 {sum(1 for e in catalog if e['kind'] == 1)} / "
          f"小地域 {sum(1 for e in catalog if e['kind'] == 2)})")

    targets = catalog
    if args.codes:
        targets = [e for e in catalog if e["id"] in args.codes]
        print(f"対象を {len(targets)} 件に限定")

    list_dir = OUT_DIR / "list"
    latest_path = OUT_DIR / "latest.json"
    latest = (json.loads(latest_path.read_text(encoding="utf-8"))
              if latest_path.exists() else [])
    n_before = len(latest)
    now_id_base = now.strftime("%Y%m%d%H%M")
    counter = [0]

    fetched = empty = failed = 0
    for i, entry in enumerate(targets, 1):
        rows = fetch_table_list(client, entry, args.use_raw)
        if rows is None:
            failed += 1
            continue
        list_path = list_dir / f"{KIND_PREFIX[entry['kind']]}{entry['id']}.json"
        if list_path.exists():
            old_rows = json.loads(list_path.read_text(encoding="utf-8"))
            detect_changes(entry, rows, old_rows, latest,
                           OUT_DIR / "latest_tables", now_id_base, today, counter)
        # 初回 (旧ファイルなし) は差分なし扱い (旧 statdbcron と同じ)
        write_json(list_path, rows)
        fetched += 1
        if not rows:
            empty += 1
        if i % 50 == 0:
            print(f"  {i}/{len(targets)}")

    write_json(OUT_DIR / "catalog.json", {"fetched_at": today, "stats": catalog})
    write_json(latest_path, latest)
    n_tables = sum(
        len(json.loads(p.read_text(encoding="utf-8")))
        for p in list_dir.glob("*.json"))
    print(f"統計表一覧 {fetched} コード (うち0件 {empty}、失敗 {failed}) / "
          f"統計表 合計 {n_tables:,} 件 / 更新情報 +{len(latest) - n_before} 件")


if __name__ == "__main__":
    main()
