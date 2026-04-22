#!/bin/bash
# ─────────────────────────────────────────────
#  Influentia — one-click save & push to GitHub
#  Double-click this after Claude makes changes.
# ─────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Influentia — Save & Push         ║"
echo "╚══════════════════════════════════════╝"
echo ""

git add .
git commit -m "update $(date '+%Y-%m-%d %H:%M')" 2>&1

if git push origin main 2>&1; then
  echo ""
  echo "✅  Pushed to GitHub successfully."
  echo "    Cloudflare will auto-deploy the landing page in ~30 seconds."
else
  echo ""
  echo "⚠️  Push failed — trying force push..."
  git push --force origin main 2>&1
fi

echo ""
read -p "Press Enter to close..."
