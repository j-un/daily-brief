#!/usr/bin/env bash
set -euo pipefail

RESET_STATE=false
HOURS=24
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset-state) RESET_STATE=true; shift ;;
    *) HOURS="$1"; shift ;;
  esac
done
DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
OUTPUT_FILE="docs/brief-${DATE}.md"
REPO_URL="git@github.com:j-un/daily-brief.git"

# --- 1. Clone origin/main into temp directory ---
TMPDIR=$(mktemp -d)
PUSH_SUCCESS=false
cleanup() {
  if [ "$PUSH_SUCCESS" = true ]; then
    rm -rf "$TMPDIR"
  else
    echo ""
    echo "Generated files are preserved in: $TMPDIR"
    echo "  $TMPDIR/$OUTPUT_FILE"
    echo "  $TMPDIR/state.json"
  fi
}
trap cleanup EXIT

echo "Cloning origin/main into $TMPDIR ..."
git clone --depth 1 "$REPO_URL" "$TMPDIR"
cd "$TMPDIR"

if [ "$RESET_STATE" = true ]; then
  echo "Resetting state.json ..."
  rm -f state.json
fi

# --- 2. Fetch feeds (deterministic) ---
echo ""
echo "=== Fetching feeds (--hours $HOURS) ==="
ARTICLES_JSON="$TMPDIR/articles.json"
uv run scripts/fetch_feeds.py \
  --config config.yaml \
  --hours "$HOURS" \
  > "$ARTICLES_JSON"

ARTICLE_COUNT=$(python3 -c "import json,sys; print(json.load(sys.stdin)['total_count'])" < "$ARTICLES_JSON")
echo "Fetched $ARTICLE_COUNT articles."

if [ "$ARTICLE_COUNT" -eq 0 ]; then
  echo "新着記事はありませんでした。"
  PUSH_SUCCESS=true
  exit 0
fi

# --- 3. Generate brief with Claude (LLM) ---
echo ""
echo "=== Generating daily brief ==="
echo ""

CLAUDE_RESULT_JSON="$TMPDIR/claude_result.json"
claude \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  --max-budget-usd 1.00 \
  --output-format json \
  -p "$(cat <<EOF
${ARTICLES_JSON} の記事JSONを読み取り、日次ブリーフィングを生成して ${OUTPUT_FILE} に書き出してください。
日付は ${DATE} です。git commitはしないこと。
EOF
)" > "$CLAUDE_RESULT_JSON"

echo ""
echo "=== Claude token usage ==="
python3 - "$CLAUDE_RESULT_JSON" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
usage = data.get("usage", {})
cost = data.get("total_cost_usd", data.get("cost_usd"))
input_tokens = usage.get("input_tokens", 0)
cache_creation = usage.get("cache_creation_input_tokens", 0)
cache_read = usage.get("cache_read_input_tokens", 0)
output_tokens = usage.get("output_tokens", 0)
total = input_tokens + cache_creation + cache_read + output_tokens
print(f"  input_tokens:         {input_tokens:>10,}")
print(f"  cache_creation:       {cache_creation:>10,}")
print(f"  cache_read:           {cache_read:>10,}")
print(f"  output_tokens:        {output_tokens:>10,}")
print(f"  total:                {total:>10,}")
if cost is not None:
    print(f"  cost_usd:             ${cost:.4f}")
PY

# --- 4. Postprocess (deterministic) ---
if [ ! -f "$OUTPUT_FILE" ]; then
  echo ""
  echo "ERROR: File was not generated: $OUTPUT_FILE"
  exit 1
fi

uv run scripts/postprocess_brief.py "$OUTPUT_FILE"

echo ""
echo "============================================"
echo "  Generated: $OUTPUT_FILE"
echo "============================================"
echo ""
cat "$OUTPUT_FILE"
echo ""
echo "============================================"

# --- 5. Commit and push ---
echo ""
read -r -p "Push to main? [y/N] " REPLY
echo ""

if [[ "$REPLY" =~ ^[Yy]$ ]]; then
  git add state.json docs/
  if git diff --cached --quiet; then
    echo "No changes to commit."
  else
    git commit -m "brief: ${DATE} daily brief"
    git push origin main
    PUSH_SUCCESS=true
    echo ""
    echo "Pushed to main."
  fi
else
  echo "Cancelled."
  PUSH_SUCCESS=true
fi
