#!/usr/bin/env bash
set -euo pipefail

HOURS="${1:-24}"
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

# --- 2. Generate brief ---
echo ""
echo "=== Generating daily brief (--hours $HOURS) ==="
echo ""

PROMPT="RSSフィードチェックして。日付は ${DATE} を使うこと。git commitはしないこと。"
if [ "$HOURS" -ne 24 ]; then
  PROMPT="RSSフィードチェックして。日付は ${DATE}、--hours ${HOURS} を使うこと。git commitはしないこと。"
fi

claude \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  --max-budget-usd 1.00 \
  -p "$PROMPT"

# --- 3. Show result and confirm ---
if [ ! -f "$OUTPUT_FILE" ]; then
  echo ""
  echo "ERROR: File was not generated: $OUTPUT_FILE"
  exit 1
fi

echo ""
echo "============================================"
echo "  Generated: $OUTPUT_FILE"
echo "============================================"
echo ""
cat "$OUTPUT_FILE"
echo ""
echo "============================================"

# --- 4. Commit and push ---
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
