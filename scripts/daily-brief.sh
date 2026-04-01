#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HOURS="${1:-24}"
DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
OUTPUT_FILE="docs/brief-${DATE}.md"
WORKTREE_DIR="${PROJECT_DIR}/.worktree-brief"

# --- 1. Fetch origin/main ---
echo "Fetching origin/main..."
git -C "$PROJECT_DIR" fetch origin main

# --- 2. Create worktree from origin/main ---
if [ -d "$WORKTREE_DIR" ]; then
  git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
fi

echo "Creating worktree (origin/main)..."
git -C "$PROJECT_DIR" worktree add --detach "$WORKTREE_DIR" origin/main

cleanup() {
  echo ""
  echo "Removing worktree..."
  git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
}
trap cleanup EXIT

cd "$WORKTREE_DIR"

# --- 3. Generate brief ---
echo ""
echo "=== Generating daily brief (--hours $HOURS) ==="
echo ""

claude \
  --model claude-sonnet-4-6 \
  --dangerously-skip-permissions \
  --max-budget-usd 1.00 \
  -p "RSSフィードチェックして。出力先は ${OUTPUT_FILE}、--hours ${HOURS} を使うこと。日付は ${DATE} を使うこと"

# --- 4. Show result and confirm ---
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

# --- 5. Push to main ---
echo ""
read -r -p "Push to main? [y/N] " REPLY
echo ""

if [[ "$REPLY" =~ ^[Yy]$ ]]; then
  git add state.json docs/
  if git diff --cached --quiet; then
    echo "No changes to commit."
  else
    # Switch from detached HEAD to main branch before committing
    git checkout -B main origin/main
    git add state.json docs/
    git commit -m "brief: ${DATE} daily brief"
    git push origin main
    echo ""
    echo "Pushed to main."
  fi
else
  echo "Cancelled."
fi
