#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""
RSSフィード取得 & 差分抽出スクリプト

uv run で実行すると依存ライブラリ(feedparser)が自動解決される。
フィードごとに新着記事を抽出し、JSON形式で標準出力に返す。
"""

import argparse
import json
import os
import sys
import hashlib
from datetime import datetime, timedelta, timezone
import html
import re
import feedparser
import yaml


def clean_html(text: str) -> str:
    """HTMLタグを除去してプレーンテキストにする"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(date_str: str) -> datetime | None:
    """よくある日付フォーマットをパースする"""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",     # RFC 822
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",           # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def make_entry_id(entry: dict) -> str:
    """エントリの一意なIDを生成する"""
    if entry.get("link"):
        return hashlib.md5(entry["link"].encode()).hexdigest()
    if entry.get("title"):
        return hashlib.md5(entry["title"].encode()).hexdigest()
    return hashlib.md5(json.dumps(entry, sort_keys=True).encode()).hexdigest()


def fetch_feed(url: str) -> list[dict]:
    """feedparserでRSSフィードを取得・パースする"""
    feed = feedparser.parse(url)
    entries = []
    for item in feed.entries:
        entry = {
            "title": clean_html(getattr(item, "title", "")),
            "link": getattr(item, "link", ""),
            "summary": clean_html(getattr(item, "summary", getattr(item, "description", ""))),
            "published": getattr(item, "published", getattr(item, "updated", "")),
        }
        entries.append(entry)
    return entries


def load_state(state_file: str) -> dict:
    """状態ファイルを読み込む"""
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_run": None, "seen_ids": {}}


def save_state(state_file: str, state: dict):
    """状態ファイルを保存する"""
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="RSSフィード取得 & 差分抽出")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--feeds", help="フィード情報のJSON文字列")
    group.add_argument("--config", help="config.yamlのパス（feeds/interestsを含む）")
    parser.add_argument("--state-file", default=os.path.expanduser("~/.rss-digests/state.json"),
                        help="状態ファイルのパス")
    parser.add_argument("--hours", type=int, default=24, help="遡る時間数")
    args = parser.parse_args()

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        feeds = config["feeds"]
    else:
        feeds = json.loads(args.feeds)
    state = load_state(args.state_file)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    # last_runがあればそちらを優先（より新しい方を使用）
    if state.get("last_run"):
        last_run = parse_date(state["last_run"])
        if last_run and last_run > cutoff:
            cutoff = last_run

    seen_ids = state.get("seen_ids", {})
    all_new_articles = []
    errors = []

    for feed_info in feeds:
        url = feed_info["url"]
        name = feed_info.get("name", url)
        category = feed_info.get("category", "General")

        try:
            entries = fetch_feed(url)
        except Exception as e:
            errors.append({"feed": name, "url": url, "error": str(e)})
            sys.stderr.write(f"[ERROR] {name}: {e}\n")
            continue

        feed_seen = set(seen_ids.get(url, []))
        new_seen = list(feed_seen)

        for entry in entries:
            entry_id = make_entry_id(entry)

            # 既読チェック
            if entry_id in feed_seen:
                continue

            # 日付チェック
            pub_date = parse_date(entry.get("published", ""))
            if pub_date and pub_date < cutoff:
                continue

            # 概要を150文字に切り詰め（トークン節約）
            summary = entry.get("summary", "")
            if len(summary) > 150:
                summary = summary[:150] + "..."

            article = {
                "entry_id": entry_id,
                "title": entry.get("title", "(no title)"),
                "link": entry.get("link", ""),
                "summary": summary,
                "published": entry.get("published", ""),
                "feed_name": name,
                "category": category,
            }
            all_new_articles.append(article)
            new_seen.append(entry_id)

        # 直近500件のみ保持
        seen_ids[url] = new_seen[-500:]

    # 状態を保存（登録フィードに存在しないURLの残骸を除去）
    active_urls = {f["url"] for f in feeds}
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    state["seen_ids"] = {url: ids for url, ids in seen_ids.items() if url in active_urls}
    save_state(args.state_file, state)

    result = {
        "articles": all_new_articles,
        "total_count": len(all_new_articles),
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()

