#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Influentia — Remove Autostart
# Run this if you want to stop the server from starting automatically.
# ─────────────────────────────────────────────────────────────────────────────
PLIST_PATH="$HOME/Library/LaunchAgents/io.influentia.server.plist"

echo ""
echo "Removing Influentia autostart…"

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "✓  Autostart removed"
else
    echo "⚠  Autostart was not installed"
fi

lsof -ti :5555 | xargs kill -9 2>/dev/null || true
echo "✓  Server stopped"
echo ""
echo "Done. Run autostart.command again to re-enable it."
echo ""
read -n 1 -p "Press any key to close…"
