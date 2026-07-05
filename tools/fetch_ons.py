#!/usr/bin/env python3
"""UK 統計局(ONS)「National population projections: 2024-based」の
Principal projection (機械可読 Excel 一式) をダウンロードし、
data/raw/ons/ に展開する (再生成可能。git 管理外)。

出典: https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/
      populationprojections/datasets/z1zippedpopulationprojectionsdatafilesuk

usage: python tools/fetch_ons.py
"""
import io
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "ons"
URL = ("https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/populationandmigration/"
       "populationprojections/datasets/z1zippedpopulationprojectionsdatafilesuk/2024based/uk1.zip")
USER_AGENT = "Mozilla/5.0 (eCitizenStatic build; https://github.com/aiseed-dev/ecitizen)"
# Principal projection (基準シナリオ) のみ使用。他は感度分析用のため取得しない。
KEEP_FILE = "uk_ppp_machine_readable.xlsx"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / KEEP_FILE
    if dest.exists():
        print(f"{dest} は既に存在します (再取得するには削除してから実行)")
        return
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open(KEEP_FILE) as src, open(dest, "wb") as dst:
            dst.write(src.read())
    print(f"{dest} を取得しました")


if __name__ == "__main__":
    main()
