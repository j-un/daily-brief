#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["feedparser", "pyyaml", "httpx"]
# ///
"""
RSSフィード取得 & プール追記スクリプト

pool.json に新着記事を追記し、指定時間内の記事のみを保持する。
state.json で既読IDを管理して重複取得を防ぐ。
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
import httpx
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


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")


def is_bluesky_feed(url: str) -> bool:
    """BlueskyのRSSフィードかどうか判定する"""
    return "bsky.app/" in url


def extract_external_url(description: str, post_link: str) -> tuple[str, str]:
    """descriptionから外部URLを抽出し、(external_url, remaining_text) を返す。
    外部URLがなければ (post_link, description) を返す。"""
    urls = URL_PATTERN.findall(description)
    external_urls = [u for u in urls if "bsky.app/" not in u]
    if external_urls:
        external_url = external_urls[0]
        remaining = description.replace(external_url, "").strip()
        return external_url, remaining
    return post_link, description


TITLE_TAG_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
BLUESKY_SHORT_SUMMARY_THRESHOLD = 30


def fetch_page_title(url: str, timeout: float = 5.0) -> str:
    """URLから<title>タグだけを軽量取得する。先頭4KBのみ読み込む。"""
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": "daily-brief/1.0"}) as resp:
            chunk = b""
            for data in resp.iter_bytes():
                chunk += data
                if len(chunk) >= 4096:
                    break
        text = chunk.decode("utf-8", errors="replace")
        m = TITLE_TAG_PATTERN.search(text)
        if m:
            return clean_html(m.group(1))
    except Exception:
        pass
    return ""


def fetch_feed(url: str) -> list[dict]:
    """feedparserでRSSフィードを取得・パースする"""
    feed = feedparser.parse(url)
    is_bluesky = is_bluesky_feed(url)
    entries = []
    for item in feed.entries:
        link = getattr(item, "link", "")
        content = getattr(item, "content", None)
        content_value = content[0].value if content else ""
        summary = clean_html(getattr(item, "summary", getattr(item, "description", content_value)))
        title = clean_html(getattr(item, "title", ""))

        if is_bluesky and summary:
            link, summary = extract_external_url(summary, link)
            # summaryが短く内容不明な場合、リンク先の<title>を取得して補完
            if len(summary) < BLUESKY_SHORT_SUMMARY_THRESHOLD and link.startswith("http"):
                page_title = fetch_page_title(link)
                if page_title:
                    title = page_title

        entry = {
            "title": title,
            "link": link,
            "summary": summary,
            "published": getattr(item, "published", getattr(item, "updated", "")),
        }
        entries.append(entry)
    return entries


def load_json(path: str, default):
    """JSONファイルを読み込む。存在しなければ default を返す"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: str, data):
    """JSONファイルを保存する"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def trim_pool(articles: list[dict], hours: int) -> list[dict]:
    """fetched_at（初回取得時刻）基準で直近N時間以内の記事のみを残す"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = []
    for a in articles:
        ts = parse_date(a.get("fetched_at") or "")
        if ts and ts >= cutoff:
            result.append(a)
    return result


def main():
    parser = argparse.ArgumentParser(description="RSSフィード取得 & プール追記")
    parser.add_argument("--config", required=True, help="config.yamlのパス")
    parser.add_argument("--state-file", default="./state.json",
                        help="状態ファイルのパス（デフォルト: ./state.json）")
    parser.add_argument("--pool-file", default="./pool.json",
                        help="プールファイルのパス（デフォルト: ./pool.json）")
    parser.add_argument("--retention-hours", type=int, default=28,
                        help="プール内の記事保持時間（デフォルト: 28）")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    feeds = config["feeds"]
    exclude_keywords = [k.lower() for k in config.get("interests", {}).get("exclude_keywords", [])]

    state = load_json(args.state_file, {"last_run": None, "seen_ids": {}})
    pool = load_json(args.pool_file, {"articles": []})

    seen_ids = state.get("seen_ids", {})
    existing_ids = {a["entry_id"] for a in pool.get("articles", []) if "entry_id" in a}

    fetched_at = datetime.now(timezone.utc).isoformat()

    added_articles = []
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

            if entry_id in feed_seen:
                continue

            summary = entry.get("summary", "")
            if len(summary) > 150:
                summary = summary[:150] + "..."

            if exclude_keywords:
                text_lower = f"{entry.get('title', '')} {summary}".lower()
                if any(kw in text_lower for kw in exclude_keywords):
                    continue

            # pool 内重複チェック（複数フィードで同じ記事の取りこぼし時など）
            if entry_id in existing_ids:
                new_seen.append(entry_id)
                continue

            article = {
                "entry_id": entry_id,
                "title": entry.get("title", "(no title)"),
                "link": entry.get("link", ""),
                "summary": summary,
                "published": entry.get("published", ""),
                "fetched_at": fetched_at,
                "feed_name": name,
                "category": category,
            }
            added_articles.append(article)
            existing_ids.add(entry_id)
            new_seen.append(entry_id)

        seen_ids[url] = new_seen[-500:]

    # プール更新 + 保持期間トリム
    pool_articles = pool.get("articles", []) + added_articles
    pool_articles = trim_pool(pool_articles, args.retention_hours)

    # state 更新（登録フィードに存在しないURLの残骸を除去）
    active_urls = {f["url"] for f in feeds}
    state["last_run"] = fetched_at
    state["seen_ids"] = {url: ids for url, ids in seen_ids.items() if url in active_urls}

    # pool 更新
    pool["articles"] = pool_articles
    pool["updated_at"] = fetched_at

    save_json(args.state_file, state)
    save_json(args.pool_file, pool)

    summary = {
        "added": len(added_articles),
        "pool_total": len(pool_articles),
        "errors": errors,
        "fetched_at": fetched_at,
    }
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
