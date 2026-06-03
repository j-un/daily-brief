#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
selected.json + articles.json を受け取り、Claude Haiku でピックアップ記事を要約し summaries.json を出力する。
"""

import argparse
import json
import os
import re
import subprocess
import sys

SYSTEM_PROMPT = """\
あなたは技術・音楽・ビジネス分野の記事キュレーターです。
与えられた記事タイトルと概要をもとに、各記事の内容を日本語で簡潔に要約してください。

## 要約ルール
- 1記事につき 30〜100文字程度で要約する
- title や summary のコピーでなく、自分の言葉で内容を説明する
- 「誰に影響するか」「何が変わるか」「従来との違い」など、事実として述べられる情報は積極的に含めてよい
- 「注目すべき」「要チェック」「検討したい」「期待される」などの主観的な推奨表現は使わない
- title が空欄の場合は summary や link をもとにベストエフォートで要約する
- 入力された全件について必ず summary_jp を返すこと。1件でも省略してはならない

## 良い要約の例
- upstream keep-aliveがデフォルト有効に変更。nginx本番環境の接続設定に影響する。
- CNCFプロジェクトのDaprがAIエージェントオーケストレーション機能を正式リリース。
- PostgreSQLのupsertが予想外の書き込みを発生させるケースのデバッグ事例。

## 出力形式
以下のJSON形式のみで出力してください。コードブロックや説明文は不要です。
id は記事リストの id フィールドの値をそのまま使ってください（整数）。

{"summaries":[{"id":0,"summary_jp":"30〜100文字の日本語要約"},...]}
"""


def call_claude(prompt: str) -> tuple[str, dict, float | None]:
    cmd = [
        "claude",
        "--model", "claude-haiku-4-5-20251001",
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
    # コードフェンスを除去し、前後に説明文があっても最外の JSON オブジェクトを取り出す
    text = re.sub(r"```(?:json)?\s*\n?(.*?)\n?```", r"\1", text, flags=re.DOTALL)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
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
    parser = argparse.ArgumentParser(description="Claude Haiku で選定済み記事を要約し summaries.json を生成")
    parser.add_argument("--articles", required=True, help="articles.json のパス")
    parser.add_argument("--selected", required=True, help="selected.json のパス")
    parser.add_argument("--output", required=True, help="summaries.json の出力先パス")
    parser.add_argument("--usage-file", help="トークン使用量・コストの出力先 JSON")
    args = parser.parse_args()

    with open(args.articles, encoding="utf-8") as f:
        articles_data = json.load(f)
    with open(args.selected, encoding="utf-8") as f:
        selected_data = json.load(f)

    articles_by_id = {a["entry_id"]: a for a in articles_data["articles"]}
    picked = selected_data.get("picked", [])

    if not picked:
        print("No picked articles to summarize.", file=sys.stderr)
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False)
        if args.usage_file:
            os.makedirs(os.path.dirname(args.usage_file) or ".", exist_ok=True)
            with open(args.usage_file, "w", encoding="utf-8") as f:
                json.dump({"label": "Haiku Summarize", "cost_usd": 0.0, "usage": {}}, f)
        return

    # id(連番) / title / summary のみ渡す（entry_id の転記ミスを防ぐため連番を使用）
    # selected.json が title/summary を含む場合はそれを使用、含まない場合は articles.json から取得
    payload: list[dict] = []
    idx_to_eid: dict[int, str] = {}
    for p in picked:
        entry_id = p.get("entry_id") or p.get("id")  # entry_id または id を使用
        a = articles_by_id.get(entry_id)
        if a:
            idx = len(payload)
            idx_to_eid[idx] = entry_id
            payload.append({
                "id": idx,
                "title": a["title"],
                "summary": a.get("summary", ""),
            })
    sent_eids = set(idx_to_eid.values())

    prompt = (
        SYSTEM_PROMPT
        + f"\n## 記事リスト（{len(payload)}件）\n\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + f"\n\n上記 {len(payload)} 件すべてに対して summary_jp を返すこと。"
    )

    print("Calling Claude Haiku for summarization...", file=sys.stderr)
    result_text, usage, cost = call_claude(prompt)
    print_usage("Haiku Summarize", usage, cost)

    try:
        result_json = extract_json(result_text)
        summaries_list = result_json["summaries"]
    except Exception as e:
        print(f"ERROR: JSON parse failed: {e}", file=sys.stderr)
        print(f"Raw output: {result_text[:500]}", file=sys.stderr)
        sys.exit(1)

    errors = []
    summaries: dict[str, str] = {}
    for s in summaries_list:
        try:
            idx = int(s["id"])
        except (TypeError, ValueError, KeyError):
            errors.append(f"invalid id in summaries: {s.get('id')!r}")
            continue
        if idx not in idx_to_eid:
            errors.append(f"id out of range in summaries: {idx}")
            continue
        eid = idx_to_eid[idx]
        if s.get("summary_jp", "").strip():
            summaries[eid] = s["summary_jp"]
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 空の summary_jp も欠落扱いにする
    missing = sent_eids - summaries.keys()

    if missing:
        for attempt in range(1, 3):
            print(f"要約欠落 {len(missing)} 件をリトライ ({attempt}/2)...", file=sys.stderr)
            retry_idx_to_eid: dict[int, str] = {}
            retry_payload: list[dict] = []
            for eid in missing:
                if eid in articles_by_id:
                    ridx = len(retry_payload)
                    retry_idx_to_eid[ridx] = eid
                    retry_payload.append({
                        "id": ridx,
                        "title": articles_by_id[eid]["title"],
                        "summary": articles_by_id[eid].get("summary", ""),
                    })
            if not retry_payload:
                break
            retry_prompt = (
                SYSTEM_PROMPT
                + f"\n## 記事リスト（{len(retry_payload)}件） ※リトライ {attempt}/2\n\n"
                + json.dumps(retry_payload, ensure_ascii=False, separators=(",", ":"))
                + f"\n\n上記 {len(retry_payload)} 件すべてに対して summary_jp を返すこと。"
            )
            try:
                retry_text, retry_usage, retry_cost = call_claude(retry_prompt)
                print_usage("Haiku Summarize (retry)", retry_usage, retry_cost)
                retry_list = extract_json(retry_text)["summaries"]
            except Exception as e:
                print(f"ERROR: リトライ {attempt} 失敗: {e}", file=sys.stderr)
                break
            for s in retry_list:
                try:
                    ridx = int(s["id"])
                except (TypeError, ValueError, KeyError):
                    continue
                if ridx in retry_idx_to_eid and s.get("summary_jp", "").strip():
                    summaries[retry_idx_to_eid[ridx]] = s["summary_jp"]
            missing = sent_eids - summaries.keys()
            if not missing:
                break

    if missing:
        print(f"ERROR: リトライ後も要約が得られなかった記事: {len(missing)}件", file=sys.stderr)
        for eid in sorted(missing):
            print(f"  - {eid}", file=sys.stderr)
        sys.exit(1)

    print(f"Summarized {len(summaries)} articles")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False)

    if args.usage_file:
        os.makedirs(os.path.dirname(args.usage_file) or ".", exist_ok=True)
        with open(args.usage_file, "w", encoding="utf-8") as f:
            json.dump({"label": "Haiku Summarize", "cost_usd": cost, "usage": usage}, f)


if __name__ == "__main__":
    main()
