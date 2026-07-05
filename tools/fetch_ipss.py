#!/usr/bin/env python3
"""IPSS「日本の地域別将来推計人口(令和5(2023)年推計)」都道府県別 Excel を
data/raw/ipss/ に1回限りダウンロードする (再生成可能。git 管理外)。

出典: https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities.asp

usage: python tools/fetch_ipss.py [--force]
"""
import argparse
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "ipss"
BASE_URL = "https://www.ipss.go.jp/pp-shicyoson/j/shicyoson23/3kekka/Municipalities/{pref}.xlsx"
USER_AGENT = "Mozilla/5.0 (eCitizenStatic build; https://github.com/aiseed-dev/ecitizen)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="既存ファイルも再ダウンロード")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for n in range(1, 48):
        pref = f"{n:02d}"
        dest = OUT_DIR / f"{pref}.xlsx"
        if dest.exists() and not args.force:
            continue
        req = urllib.request.Request(BASE_URL.format(pref=pref), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        print(f"{pref}.xlsx 取得完了")
        time.sleep(0.3)  # 常識的なアクセス間隔


if __name__ == "__main__":
    main()
