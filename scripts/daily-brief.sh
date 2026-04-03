#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HOURS=24
for arg in "$@"; do
  HOURS="$arg"
done

DATE=$(TZ=Asia/Tokyo date +%Y-%m-%d)
OUTPUT_FILE="docs/brief-${DATE}.md"

cd "$PROJECT_DIR"

# --- 1. Sync to origin/main ---
echo "Fetching origin/main..."
git fetch origin main

LOCAL_HEAD=$(git rev-parse HEAD)
ORIGIN_HEAD=$(git rev-parse origin/main)
MERGE_BASE=$(git merge-base HEAD origin/main)

if [ "$LOCAL_HEAD" != "$ORIGIN_HEAD" ]; then
  if [ "$MERGE_BASE" = "$ORIGIN_HEAD" ]; then
    # Local is ahead of origin — cannot proceed safely
    echo ""
    echo "ERROR: Local main is ahead of origin/main."
    echo "  Local:  $(git log --oneline -1 HEAD)"
    echo "  Origin: $(git log --oneline -1 origin/main)"
    echo ""
    echo "Resolve manually:"
    echo "  git push origin main        # push local commits"
    echo "  git reset --hard origin/main # or discard local commits"
    exit 1
  elif [ "$MERGE_BASE" = "$LOCAL_HEAD" ]; then
    # Local is behind origin — fast-forward
    echo "Fast-forwarding to origin/main..."
    git merge --ff-only origin/main
  else
    # Diverged
    echo ""
    echo "ERROR: Local main has diverged from origin/main."
    echo "  Local:  $(git log --oneline -1 HEAD)"
    echo "  Origin: $(git log --oneline -1 origin/main)"
    echo ""
    echo "Resolve manually before re-running."
    exit 1
  fi
fi

# Stash uncommitted changes if any
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Stashing uncommitted changes..."
  git stash push -m "daily-brief: auto-stash before generation"
  STASHED=true
fi

cleanup() {
  if [ "$STASHED" = true ]; then
    echo ""
    echo "Restoring stashed changes..."
    git stash pop
  fi
}
trap cleanup EXIT

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
    echo ""
    echo "Pushed to main."
  fi
else
  echo "Cancelled."
fi
