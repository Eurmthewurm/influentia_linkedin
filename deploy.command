#!/bin/bash
# ─────────────────────────────────────────────
#  Influentia — one-click deploy
#  Double-click this file to push everything live.
# ─────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║       Influentia — Deploy Tool       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. Make sure wrangler is available ──────
if ! command -v npx &>/dev/null; then
  echo "❌  Node / npx not found. Install Node.js from https://nodejs.org and try again."
  echo ""; read -p "Press Enter to close..."; exit 1
fi

# ── 2. Re-install node_modules if needed (macOS native) ─
echo "▶  Checking worker dependencies..."
cd "$DIR/worker"
if [ ! -d node_modules ] || [ ! -f node_modules/.install-platform ]; then
  echo "   Installing (first time or platform changed)..."
  rm -rf node_modules
  npm install --silent
  uname > node_modules/.install-platform
  echo "   ✓ Done"
else
  echo "   ✓ Already up to date"
fi

# ── 3. Deploy Worker ─────────────────────────
echo ""
echo "▶  Deploying backend (Cloudflare Worker)..."
if npx wrangler deploy --env production 2>&1; then
  echo "   ✓ Worker deployed"
else
  echo ""
  echo "❌  Worker deploy failed. Make sure you're logged in:"
  echo "   Open Terminal and run:  npx wrangler login"
  echo ""; read -p "Press Enter to close..."; exit 1
fi

# ── 4. Deploy Landing Page ───────────────────
echo ""
echo "▶  Deploying landing page (Cloudflare Pages)..."
if npx wrangler pages deploy "$DIR/landing" --project-name influentia 2>&1; then
  echo "   ✓ Landing page deployed"
else
  echo "❌  Pages deploy failed. Check the output above."
  echo ""; read -p "Press Enter to close..."; exit 1
fi

# ── Done ─────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  ✅  Everything is live!"
echo ""
echo "  Landing:  https://influentia.io"
echo "  Account:  https://influentia.io/account.html"
echo "  Worker:   https://outreach-pilot-api-production.plain-king-ead0.workers.dev"
echo "════════════════════════════════════════"
echo ""
read -p "Press Enter to close..."
