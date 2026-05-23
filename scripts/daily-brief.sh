#!/usr/bin/env bash
set -euo pipefail

FORCE=false
DRY_RUN=false
LOCAL_DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --local-dry-run) LOCAL_DRY_RUN=true; DRY_RUN=true; FORCE=true; shift ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--force] [--dry-run] [--local-dry-run]

Options:
  --force          同日のブリーフが既に存在しても再生成する
  --dry-run        fetch と push をスキップして brief 生成のみ行う（動作確認用）
  --local-dry-run  ローカルのコードで動作確認する（--dry-run + main クローン不要）
EOF
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
OUTPUT_FILE="docs/brief-${DATE}.md"
REPO_URL="git@github.com:j-un/daily-brief.git"

TMPDIR=$(mktemp -d)
PUSH_SUCCESS=false
cleanup() {
  if [ "$PUSH_SUCCESS" = true ]; then
    rm -rf "$TMPDIR"
  else
    echo ""
    echo "Generated files are preserved in: $TMPDIR"
  fi
}
trap cleanup EXIT

# --- 1. Clone main (or symlink local repo) ---
if [ "$LOCAL_DRY_RUN" = true ]; then
  REPO_ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
  echo "Using local repo: $REPO_ROOT"
  ln -s "$REPO_ROOT" "$TMPDIR/main"
else
  echo "Cloning origin/main into $TMPDIR/main ..."
  git clone --depth 1 --branch main "$REPO_URL" "$TMPDIR/main"
fi

# --- 2. 同日ファイル存在チェック（Claude 呼び出し前に判定）---
if [ -f "$TMPDIR/main/$OUTPUT_FILE" ] && [ "$FORCE" != true ]; then
  echo ""
  echo "今日のブリーフは既に存在します: $OUTPUT_FILE"
  echo "再生成するには --force を指定してください。"
  PUSH_SUCCESS=true
  exit 0
fi

# --- 3. Clone data branch ---
echo "Cloning origin/data into $TMPDIR/data ..."
git clone --depth 1 --branch data "$REPO_URL" "$TMPDIR/data"

# --- 3.5. Refresh pool.json（直前までのニュースを取り込む）---
if [ "$DRY_RUN" = true ]; then
  echo ""
  echo "=== Skipping fetch (--dry-run) ==="
else
  echo ""
  echo "=== Refreshing pool (fetch feeds) ==="
  cd "$TMPDIR/main"
  uv run scripts/fetch_feeds.py \
    --config config.yaml \
    --state-file "$TMPDIR/data/state.json" \
    --pool-file "$TMPDIR/data/pool.json" \
    --retention-hours 28

  cd "$TMPDIR/data"
  git add pool.json state.json
  if git diff --cached --quiet; then
    echo "data: No new articles from fetch."
  else
    git commit -m "chore(data): fetch feeds for brief ${DATE}"
    # GHA fetch.yml と競合した場合は rebase してリトライ
    fetch_pushed=false
    for attempt in 1 2 3; do
      if git push origin data; then
        fetch_pushed=true
        break
      fi
      echo "push failed (attempt $attempt/3), rebasing..."
      git pull --rebase origin data
    done
    if [ "$fetch_pushed" != true ]; then
      echo "ERROR: Failed to push fetch result after 3 attempts."
      exit 1
    fi
  fi
fi

# --- 4. Prepare articles.json from pool ---
cd "$TMPDIR/main"
ARTICLES_JSON="$TMPDIR/articles.json"
CONSUMED_IDS="$TMPDIR/consumed_ids.txt"

echo ""
echo "=== Preparing articles from pool ==="
uv run scripts/prepare_brief.py \
  --pool-file "$TMPDIR/data/pool.json" \
  --briefs-dir "$TMPDIR/main/docs" \
  --output "$ARTICLES_JSON"

ARTICLE_COUNT=$(python3 -c "import json,sys; print(json.load(sys.stdin)['total_count'])" < "$ARTICLES_JSON")
echo "Articles to process: $ARTICLE_COUNT"

if [ "$ARTICLE_COUNT" -eq 0 ]; then
  echo "新着記事はありませんでした。"
  PUSH_SUCCESS=true
  exit 0
fi

# 消費する entry_id を記録（Claude 処理成功後に pool から除外するため）
python3 -c "
import json
with open('$ARTICLES_JSON') as f:
    data = json.load(f)
for a in data['articles']:
    print(a['entry_id'])
" > "$CONSUMED_IDS"

# --- 5. Select articles (Sonnet) ---
echo ""
echo "=== Selecting articles (Sonnet) ==="
SELECTED_JSON="$TMPDIR/selected.json"
SONNET_USAGE="$TMPDIR/sonnet_usage.json"
uv run scripts/select_articles.py \
  --articles "$ARTICLES_JSON" \
  --output "$SELECTED_JSON" \
  --usage-file "$SONNET_USAGE"

# --- 6. Summarize articles (Haiku) ---
echo ""
echo "=== Summarizing articles (Haiku) ==="
SUMMARIES_JSON="$TMPDIR/summaries.json"
HAIKU_USAGE="$TMPDIR/haiku_usage.json"
uv run scripts/summarize_articles.py \
  --articles "$ARTICLES_JSON" \
  --selected "$SELECTED_JSON" \
  --output "$SUMMARIES_JSON" \
  --usage-file "$HAIKU_USAGE"

# --- 7. Render Markdown ---
echo ""
echo "=== Rendering brief ==="
uv run scripts/render_brief.py \
  --articles "$ARTICLES_JSON" \
  --selected "$SELECTED_JSON" \
  --summaries "$SUMMARIES_JSON" \
  --date "$DATE" \
  --output "$OUTPUT_FILE"

if [ ! -f "$OUTPUT_FILE" ]; then
  echo ""
  echo "ERROR: File was not generated: $OUTPUT_FILE"
  exit 1
fi

echo ""
echo "=== Claude token usage ==="
python3 - "$SONNET_USAGE" "$HAIKU_USAGE" <<'PY'
import json, sys

total_cost = 0.0
for path in sys.argv[1:]:
    try:
        with open(path) as f:
            d = json.load(f)
    except FileNotFoundError:
        continue
    label = d.get("label", path)
    cost = d.get("cost_usd") or 0.0
    u = d.get("usage", {})
    input_t = u.get("input_tokens", 0)
    cache_cr = u.get("cache_creation_input_tokens", 0)
    cache_rd = u.get("cache_read_input_tokens", 0)
    output_t = u.get("output_tokens", 0)
    total_t = input_t + cache_cr + cache_rd + output_t
    print(f"  [{label}]")
    print(f"    input={input_t:,}  cache_creation={cache_cr:,}  cache_read={cache_rd:,}  output={output_t:,}  total={total_t:,}")
    if cost:
        print(f"    cost=${cost:.4f}")
    total_cost += cost

print(f"  ----------------------------------------")
print(f"  total cost: ${total_cost:.4f}")
PY

echo ""
echo "============================================"
echo "  Generated: $OUTPUT_FILE"
echo "============================================"
echo ""
cat "$OUTPUT_FILE"
echo ""
echo "============================================"

# --- 8. Commit and push ---
echo ""
if [ "$DRY_RUN" = true ]; then
  echo "Skipping push (--dry-run mode)."
  PUSH_SUCCESS=true
  exit 0
fi
read -r -p "Push to main and data? [y/N] " REPLY
echo ""

if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  PUSH_SUCCESS=true
  exit 0
fi

# main にブリーフを push
cd "$TMPDIR/main"
git add docs/
if git diff --cached --quiet; then
  echo "main: No changes to commit."
else
  git commit -m "brief: ${DATE} daily brief"
  git push origin main
  echo "Pushed brief to main."
fi

# data から消費済み entry_id を除外して push（差分消費方式）
# fetch が並走していてもコンフリクトしないよう、毎回最新を取得して差分適用する
echo ""
echo "=== Consuming pool in data branch ==="
data_done=false
for attempt in 1 2 3; do
  cd "$TMPDIR/data"
  git fetch origin data
  git reset --hard origin/data
  cd "$TMPDIR/main"
  uv run scripts/consume_pool.py \
    --pool-file "$TMPDIR/data/pool.json" \
    --consumed-ids-file "$CONSUMED_IDS"
  cd "$TMPDIR/data"
  git add pool.json
  if git diff --cached --quiet; then
    echo "data: No articles to consume."
    data_done=true
    break
  fi
  git commit -m "chore(data): consume pool for brief ${DATE}"
  if git push origin data; then
    echo "Pushed to data."
    data_done=true
    break
  fi
  echo "push failed (attempt $attempt/3), retrying..."
done

if [ "$data_done" != true ]; then
  echo "ERROR: Failed to push data branch after 3 attempts."
  exit 1
fi

PUSH_SUCCESS=true
echo ""
echo "Done."
