#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
pool.json からブリーフで消費した entry_id の記事を除外する（差分消費方式）。

ブリーフ処理中に fetch が走って pool へ追記された記事は、
消費対象に含まれないためそのまま残る。
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="pool.json から消費済み記事を除外する")
    parser.add_argument("--pool-file", required=True, help="pool.jsonのパス")
    parser.add_argument("--consumed-ids-file", required=True,
                        help="改行区切りの entry_id ファイル")
    args = parser.parse_args()

    with open(args.pool_file, "r", encoding="utf-8") as f:
        pool = json.load(f)

    with open(args.consumed_ids_file, "r", encoding="utf-8") as f:
        consumed_ids = {line.strip() for line in f if line.strip()}

    articles = pool.get("articles", [])
    before = len(articles)
    pool["articles"] = [a for a in articles if a.get("entry_id") not in consumed_ids]
    after = len(pool["articles"])

    with open(args.pool_file, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

    sys.stderr.write(f"Consumed {before - after} articles from pool (was {before}, now {after}).\n")


if __name__ == "__main__":
    main()
