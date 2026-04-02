#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RETRY=false
HOURS=24
for arg in "$@"; do
  case "$arg" in
    --retry) RETRY=true ;;
    *)       HOURS="$arg" ;;
  esac
done

DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
OUTPUT_FILE="docs/brief-${DATE}.md"
WORKTREE_DIR="${PROJECT_DIR}/.worktree-brief"

# --- 1. Fetch origin/main ---
echo "Fetching origin/main..."
git -C "$PROJECT_DIR" fetch origin main

# --- 2. Create worktree from origin/main ---
if [ "$RETRY" = true ] && [ -d "$WORKTREE_DIR" ]; then
  echo "Reusing existing worktree (--retry mode)..."
else
  if [ -d "$WORKTREE_DIR" ]; then
    git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
  fi
  echo "Creating worktree (origin/main)..."
  git -C "$PROJECT_DIR" worktree add --detach "$WORKTREE_DIR" origin/main
fi

PUSH_SUCCESS=false

cleanup() {
  if [ "$PUSH_SUCCESS" = true ]; then
    echo ""
    echo "Removing worktree..."
    git -C "$PROJECT_DIR" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
  else
    echo ""
    echo "Worktree preserved at: $WORKTREE_DIR"
    echo "Re-run with --retry to skip generation and retry push."
  fi
}
trap cleanup EXIT

cd "$WORKTREE_DIR"

# --- 3. Generate brief ---
if [ "$RETRY" = true ] && [ -f "$OUTPUT_FILE" ]; then
  echo ""
  echo "Skipping generation (--retry mode, file exists: $OUTPUT_FILE)"
else
  echo ""
  echo "=== Generating daily brief (--hours $HOURS) ==="
  echo ""

  claude \
    --model claude-sonnet-4-6 \
    --dangerously-skip-permissions \
    --max-budget-usd 1.00 \
    -p "RSSフィードチェックして。出力先は ${OUTPUT_FILE}、--hours ${HOURS} を使うこと。日付は ${DATE} を使うこと"
fi

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
    PUSH_SUCCESS=true
  else
    git commit -m "brief: ${DATE} daily brief"
    git push origin HEAD:main
    echo ""
    echo "Pushed to main."
    PUSH_SUCCESS=true
  fi
else
  echo "Cancelled."
  PUSH_SUCCESS=true
fi
