#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
selected.json + summaries.json + articles.json をマージして Markdown ブリーフィングを生成する。
Claude を使わない純スクリプト。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

CATEGORY_ORDER = ["tech_ai", "business", "dev_tools", "music_culture", "book_science", "other"]

CATEGORY_LABELS = {
    "tech_ai": "🤖 Tech / AI",
    "business": "💼 ビジネス / スタートアップ",
    "dev_tools": "🔧 開発・ツール",
    "music_culture": "🎵 音楽 / 機材 / カルチャー",
    "book_science": "📚 読書・サイエンス",
    "other": "🗂 その他",
}

JST = timezone(timedelta(hours=9))


def escape_pipes_in_links(markdown: str) -> str:
    """Markdownリンクのテキスト部分にある | を \\| にエスケープする（Jekyll対策）"""
    def replace_link(m: re.Match) -> str:
        text = re.sub(r"(?<!\\)\|", r"\\|", m.group(1))
        return f"[{text}]({m.group(2)})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, markdown)


def format_fetched_at(fetched_at: str) -> str:
    try:
        dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        jst = dt.astimezone(JST)
        return jst.strftime("%Y-%m-%d %H:%M (JST)")
    except Exception:
        return fetched_at


def build_item(title: str, link: str, summary: str) -> str:
    return f"- **[{title}]({link})** — {summary}"


def main() -> None:
    parser = argparse.ArgumentParser(description="selected.json + summaries.json → Markdown")
    parser.add_argument("--articles", required=True, help="articles.json のパス")
    parser.add_argument("--selected", required=True, help="selected.json のパス")
    parser.add_argument("--summaries", required=True, help="summaries.json のパス")
    parser.add_argument("--date", required=True, help="日付 YYYY-MM-DD")
    parser.add_argument("--output", required=True, help="出力 Markdown のパス")
    args = parser.parse_args()

    with open(args.articles, encoding="utf-8") as f:
        articles_data = json.load(f)
    with open(args.selected, encoding="utf-8") as f:
        selected_data = json.load(f)
    with open(args.summaries, encoding="utf-8") as f:
        summaries = json.load(f)

    articles_by_id = {a["entry_id"]: a for a in articles_data["articles"]}
    picked = selected_data.get("picked", [])
    fetched_at = selected_data.get("fetched_at", "")
    feed_count = selected_data.get("feed_count", 0)
    total_count = selected_data.get("total_count", len(articles_data["articles"]))

    starred = [p for p in picked if p.get("starred")]
    non_starred = [p for p in picked if not p.get("starred")]

    lines = []

    # Jekyll front matter
    lines.append("---")
    lines.append("---")
    lines.append("")

    # ヘッダー
    lines.append(f"# 📰 {args.date}")
    lines.append("")
    lines.append(
        f"> 取得フィード数: {feed_count} | 新着記事: {total_count}件 | ピックアップ: {len(picked)}件"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ⭐ 注目記事
    lines.append("## ⭐ 注目記事")
    lines.append("")
    if starred:
        for p in starred:
            a = articles_by_id.get(p["entry_id"])
            if not a:
                continue
            summary = summaries.get(p["entry_id"], "")
            lines.append(build_item(a["title"], a["link"], summary))
    else:
        lines.append("_今日の注目記事はありませんでした。_")
    lines.append("")
    lines.append("---")
    lines.append("")

    # starred の entry_id セット（カテゴリ別セクションで再掲しない）
    starred_ids = {p["entry_id"] for p in starred}

    # カテゴリ別セクション（starred を除外）
    by_category: dict[str, list] = {cat: [] for cat in CATEGORY_ORDER}
    for p in non_starred:
        cat = p.get("category", "other")
        if cat not in by_category:
            cat = "other"
        by_category[cat].append(p)

    for cat in CATEGORY_ORDER:
        items = by_category[cat]
        if not items:
            continue
        label = CATEGORY_LABELS[cat]
        lines.append(f"## {label}")
        lines.append("")
        for p in items:
            a = articles_by_id.get(p["entry_id"])
            if not a:
                continue
            summary = summaries.get(p["entry_id"], "")
            lines.append(build_item(a["title"], a["link"], summary))
        lines.append("")

    # フッター
    fetched_str = format_fetched_at(fetched_at)
    lines.append(f"_フィード最終取得: {fetched_str}_")
    lines.append("")

    content = "\n".join(lines)
    content = escape_pipes_in_links(content)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Rendered: {args.output}")


if __name__ == "__main__":
    main()
