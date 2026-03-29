#!/usr/bin/env python3
"""
キーワードベースの記事フィルタリングスクリプト

標準入力からJSON形式の記事リストを受け取り、
キーワードマッチで粗くフィルタリングした結果を標準出力にJSON形式で返す。
"""

import argparse
import json
import sys
import re


def normalize(text: str) -> str:
    """マッチング用にテキストを正規化する"""
    return text.lower().strip()


def matches_any(text: str, keywords: list[str]) -> list[str]:
    """テキストにマッチするキーワードのリストを返す"""
    text_lower = normalize(text)
    matched = []
    for kw in keywords:
        kw_lower = normalize(kw)
        if kw_lower in text_lower:
            matched.append(kw)
    return matched


def main():
    parser = argparse.ArgumentParser(description="キーワードで記事をフィルタリング")
    parser.add_argument("--keywords", required=True,
                        help="カンマ区切りの関心キーワード")
    parser.add_argument("--exclude", default="",
                        help="カンマ区切りの除外キーワード")
    parser.add_argument("--fallback-limit", type=int, default=20,
                        help="キーワードマッチが0件の場合に返す記事数")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    exclude = [k.strip() for k in args.exclude.split(",") if k.strip()]

    # 標準入力からJSON読み取り
    input_data = json.load(sys.stdin)

    # 入力形式に対応: {"articles": [...]} or [...]
    if isinstance(input_data, dict):
        articles = input_data.get("articles", [])
        meta = {k: v for k, v in input_data.items() if k != "articles"}
    else:
        articles = input_data
        meta = {}

    filtered = []
    excluded_count = 0

    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}"

        # 除外チェック
        if exclude and matches_any(text, exclude):
            excluded_count += 1
            continue

        # キーワードマッチ
        matched = matches_any(text, keywords)
        if matched:
            article["matched_keywords"] = matched
            filtered.append(article)

    # マッチが0件の場合はフォールバック（上位N件をそのまま返す）
    used_fallback = False
    if not filtered and articles:
        used_fallback = True
        filtered = articles[:args.fallback_limit]
        for a in filtered:
            a["matched_keywords"] = ["(fallback — no keyword match)"]

    result = {
        **meta,
        "articles": filtered,
        "filter_stats": {
            "input_count": len(articles),
            "matched_count": len(filtered),
            "excluded_count": excluded_count,
            "used_fallback": used_fallback,
            "keywords_used": keywords,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
