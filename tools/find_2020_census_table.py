#!/usr/bin/env python3
"""令和2年国勢調査(人口等基本集計)の統計表IDを探す (1回限りの調査用スクリプト)。

見つかった statsDataId は citizenlib/estat.py 経由で build_data.py に
組み込む。appId は secrets.json (git 管理外) に置く (estat.py 参照)。

usage: python tools/find_2020_census_table.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citizenlib.estat import EstatClient  # noqa: E402


def main() -> None:
    client = EstatClient.from_secrets()
    result = client.get_stats_list(
        surveyYears="202010",           # 令和2(2020)年10月調査
        statsField="02",                # 人口・世帯
        searchWord="国勢調査 人口等基本集計 男女 年齢 5歳階級",
    )
    tables = result.get("DATALIST_INF", {}).get("TABLE_INF", [])
    if isinstance(tables, dict):
        tables = [tables]
    print(f"{len(tables)} 件ヒット\n")
    for t in tables:
        stat_name = t.get("STATISTICS_NAME", "")
        title = t.get("TITLE", "")
        title_text = title.get("$", title) if isinstance(title, dict) else title
        print(f"[{t['@id']}] {stat_name} / {title_text}")


if __name__ == "__main__":
    main()
