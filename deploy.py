#!/usr/bin/env python3
"""Cloudflare Pages へのデプロイ (手順・事前準備は DEPLOY.md)。

cf-publish をライブラリとして使う (.venv に ../cf-publish を editable
install 済み)。デプロイはユーザー自身が実行する運用。

usage:
  ./deploy.py --dry-run          # アップロード内容の確認 (デプロイなし)
  ./deploy.py                    # 本番 (branch=main)
  ./deploy.py --branch preview   # プレビューURLへ
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = "ecitizen"

# .venv 外の python3 で起動された場合は .venv の python で実行し直す
try:
    from cf_publish import PagesError, deploy
except ImportError:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists() and Path(sys.executable) != venv_python:
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    sys.exit("cf-publish がありません: .venv/bin/pip install -e ../cf-publish")


def main() -> None:
    ap = argparse.ArgumentParser(description=f"public/ を Cloudflare Pages "
                                             f"プロジェクト {PROJECT!r} へデプロイ")
    ap.add_argument("--dry-run", action="store_true",
                    help="アップロード内容の表示のみ (デプロイしない)")
    ap.add_argument("--branch", default="main",
                    help="main=本番、それ以外はプレビューURL (default: main)")
    ap.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                    help="除外する fnmatch パターン (繰り返し指定可)")
    args = ap.parse_args()

    public = ROOT / "public"
    if not (public / "Population").is_dir():
        sys.exit("public/ が未ビルドです。先に generate.py --clean を実行してください。")

    try:
        result = deploy(public, PROJECT, branch=args.branch,
                        exclude=args.exclude, dry_run=args.dry_run,
                        on_progress=lambda msg: print(msg, file=sys.stderr))
    except PagesError as e:
        sys.exit(f"エラー: {e}")

    if result.dry_run:
        print(f"dry-run: {result.files} ファイル (ユニーク {result.unique}、"
              f"アップロード対象 {result.uploaded})")
    else:
        print(f"デプロイ完了 ({result.files} ファイル、新規アップロード "
              f"{result.uploaded}、{result.duration:.1f}秒)")
        print(result.url)


if __name__ == "__main__":
    main()
