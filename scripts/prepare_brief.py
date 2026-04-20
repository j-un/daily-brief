#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
デイリーブリーフ用の articles.json を pool.json から生成する。

過去N日分のブリーフMarkdownに掲載されたURLと重複する記事は除外する。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

MARKDOWN_LINK_PATTERN = re.compile(r"\[.*?\]\((https?://[^)]+)\)")


def collect_past_urls(briefs_dir: str, days: int = 7) -> set[str]:
    """過去N日分のダイジェストMarkdownからURLを収集する"""
    urls: set[str] = set()
    if not os.path.isdir(briefs_dir):
        return urls
    today = datetime.now(timezone.utc).date()
    for i in range(1, days + 1):
        date = today - timedelta(days=i)
        path = os.path.join(briefs_dir, f"brief-{date.isoformat()}.md")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for match in MARKDOWN_LINK_PATTERN.finditer(f.read()):
                urls.add(match.group(1))
    return urls


def main():
    parser = argparse.ArgumentParser(description="pool.json から articles.json を生成")
    parser.add_argument("--pool-file", default="./pool.json", help="pool.jsonのパス")
    parser.add_argument("--briefs-dir", default="./docs",
                        help="過去ブリーフMarkdownのディレクトリ（デフォルト: ./docs）")
    parser.add_argument("--days", type=int, default=7,
                        help="過去ブリーフURL参照日数（デフォルト: 7）")
    parser.add_argument("--output", default="-",
                        help="出力パス（- で標準出力、デフォルト: -）")
    args = parser.parse_args()

    if not os.path.exists(args.pool_file):
        sys.stderr.write(f"[ERROR] pool file not found: {args.pool_file}\n")
        sys.exit(1)

    with open(args.pool_file, "r", encoding="utf-8") as f:
        pool = json.load(f)

    articles = pool.get("articles", [])
    past_urls = collect_past_urls(args.briefs_dir, days=args.days)

    filtered = [a for a in articles if a.get("link") not in past_urls]

    result = {
        "articles": filtered,
        "total_count": len(filtered),
        "errors": [],
        "fetched_at": pool.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }

    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if args.output == "-":
        print(payload)
    else:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)


if __name__ == "__main__":
    main()
