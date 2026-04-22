#!/bin/bash
# ─────────────────────────────────────────────────────
#  Influentia — Worker Secrets Setup
#  Run this ONCE to push your API keys into the Worker.
#  Keys are stored securely in Cloudflare — never in code.
#  Double-click this file to run it.
# ─────────────────────────────────────────────────────

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/worker"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Influentia — Secrets Setup             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "This sets your Anthropic and Brave API keys as"
echo "secure secrets in the Cloudflare Worker."
echo "You only need to do this once (or when keys change)."
echo ""

# ── Anthropic API key ────────────────────────────────
echo "Step 1 of 2: Anthropic API key"
echo "Get yours at: https://console.anthropic.com"
echo ""
read -p "Paste your Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
if [ -z "$ANTHROPIC_KEY" ]; then
  echo "⚠️  Skipped Anthropic key."
else
  echo "$ANTHROPIC_KEY" | npx wrangler secret put ANTHROPIC_API_KEY --env production
  echo ""
fi

# ── Brave Search API key ─────────────────────────────
echo "Step 2 of 2: Brave Search API key"
echo "Get yours free (2000 searches/month) at: https://api.search.brave.com"
echo ""
read -p "Paste your Brave Search API key (BSA...): " BRAVE_KEY
if [ -z "$BRAVE_KEY" ]; then
  echo "⚠️  Skipped Brave key."
else
  echo "$BRAVE_KEY" | npx wrangler secret put BRAVE_API_KEY --env production
  echo ""
fi

echo ""
echo "════════════════════════════════════════════"
echo "  ✅  Secrets saved to Cloudflare Worker!"
echo "  Users no longer need their own API keys."
echo "════════════════════════════════════════════"
echo ""
read -p "Press Enter to close..."
