#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
articles.json を受け取り Claude Sonnet で関連度判定・カテゴリ分類・注目選定を行い selected.json を出力する。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

CATEGORY_ENUM = ["tech_ai", "business", "dev_tools", "music_culture", "book_science", "other"]

SYSTEM_PROMPT = """\
あなたは技術・音楽・ビジネス分野に精通したキュレーターです。
記事リストを受け取り、ユーザーの関心テーマに照らして関連度の高い記事を選定してください。

## ユーザーの関心テーマ
- 生成AIの最新動向と実用事例
- AIを活用したシステム開発やシステム運用
- SREやDevOpsのノウハウ
- 開発者ツール・DXの改善
- テック企業の戦略
- AWSの新サービス・アップデート
- クラウドインフラとアーキテクチャ設計
- デスク周り・物理的な作業環境
- 電子音楽・シンセサイザー・音楽制作ツール
- 読書・書評・知的好奇心を刺激する本
- 宇宙・サイエンス

## 選定ルール
- title と summary のみで関連度を判断する
- 関連度が低い記事は除外する（通常は全体の 20〜40% 程度を選定）
- 特に注目すべき記事（インパクトが大きい・トレンドを捉えている）を最大 5件、starred=true にする

## カテゴリ（必ず以下のいずれかを選ぶ）
- tech_ai: AI・機械学習・LLM・モデル関連
- business: テック企業戦略・スタートアップ・市場動向・資金調達
- dev_tools: 開発ツール・DX・SRE・DevOps・クラウドインフラ・AWS・セキュリティ
- music_culture: 音楽・シンセ・音楽制作・機材・カルチャー
- book_science: 読書・書評・宇宙・サイエンス・研究
- other: 上記いずれにも当てはまらないもの

## 出力形式
以下のJSON形式のみで出力してください。コードブロックや説明文は不要です。

{"picked":[{"entry_id":"...","category":"tech_ai","starred":false},...]}
"""


def call_claude(prompt: str) -> tuple[str, dict, float | None]:
    cmd = [
        "claude",
        "--model", "claude-sonnet-4-6",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "-p", prompt,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"claude exited with {result.returncode}")

    data = json.loads(result.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude error: {data.get('result')}")

    cost = data.get("total_cost_usd") or data.get("cost_usd")
    return data["result"], data.get("usage", {}), cost


def extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*\n?(.*?)\n?```", r"\1", text, flags=re.DOTALL).strip()
    return json.loads(text)


def print_usage(label: str, usage: dict, cost: float | None) -> None:
    input_t = usage.get("input_tokens", 0)
    cache_cr = usage.get("cache_creation_input_tokens", 0)
    cache_rd = usage.get("cache_read_input_tokens", 0)
    output_t = usage.get("output_tokens", 0)
    total = input_t + cache_cr + cache_rd + output_t
    cost_str = f" / cost=${cost:.4f}" if cost is not None else ""
    print(
        f"  [{label}] input={input_t:,} cache_creation={cache_cr:,} cache_read={cache_rd:,} output={output_t:,} total={total:,}{cost_str}",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude Sonnet で記事を選定し selected.json を生成")
    parser.add_argument("--articles", required=True, help="articles.json のパス")
    parser.add_argument("--output", required=True, help="selected.json の出力先パス")
    parser.add_argument("--usage-file", help="トークン使用量・コストの出力先 JSON")
    args = parser.parse_args()

    with open(args.articles, encoding="utf-8") as f:
        data = json.load(f)

    articles = data["articles"]
    if not articles:
        print("No articles to select.", file=sys.stderr)
        result = {
            "fetched_at": data.get("fetched_at", datetime.now(timezone.utc).isoformat()),
            "feed_count": data.get("feed_count", 0),
            "total_count": 0,
            "picked": [],
        }
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        if args.usage_file:
            os.makedirs(os.path.dirname(args.usage_file) or ".", exist_ok=True)
            with open(args.usage_file, "w", encoding="utf-8") as f:
                json.dump({"label": "Sonnet Selection", "cost_usd": 0.0, "usage": {}}, f)
        return

    # Sonnet には entry_id / title / summary のみを渡す
    payload = [
        {"entry_id": a["entry_id"], "title": a["title"], "summary": a.get("summary", "")}
        for a in articles
    ]

    prompt = (
        SYSTEM_PROMPT
        + f"\n## 記事リスト（{len(articles)}件）\n\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )

    print("Calling Claude Sonnet for selection...", file=sys.stderr)
    result_text, usage, cost = call_claude(prompt)
    print_usage("Sonnet Selection", usage, cost)

    try:
        result_json = extract_json(result_text)
        picked = result_json["picked"]
    except Exception as e:
        print(f"ERROR: JSON parse failed: {e}", file=sys.stderr)
        print(f"Raw output: {result_text[:500]}", file=sys.stderr)
        sys.exit(1)

    valid_ids = {a["entry_id"] for a in articles}
    errors = [
        f"unknown entry_id: {p['entry_id']}" for p in picked if p["entry_id"] not in valid_ids
    ] + [
        f"invalid category '{p['category']}' for {p['entry_id']}"
        for p in picked
        if p.get("category") not in CATEGORY_ENUM
    ]
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    starred_count = sum(1 for p in picked if p.get("starred"))
    print(f"Selected {len(picked)} / {len(articles)} articles (starred: {starred_count})")

    output = {
        "fetched_at": data.get("fetched_at", datetime.now(timezone.utc).isoformat()),
        "feed_count": data.get("feed_count", 0),
        "total_count": data.get("total_count", len(articles)),
        "picked": picked,
    }

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    if args.usage_file:
        os.makedirs(os.path.dirname(args.usage_file) or ".", exist_ok=True)
        with open(args.usage_file, "w", encoding="utf-8") as f:
            json.dump({"label": "Sonnet Selection", "cost_usd": cost, "usage": usage}, f)


if __name__ == "__main__":
    main()
