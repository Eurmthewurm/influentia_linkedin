#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Outreach Pilot — macOS launcher
# Double-click this file to start the dashboard.
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")"

echo ""
echo "=========================================================="
echo "  Outreach Pilot"
echo "=========================================================="
echo ""

# If the virtualenv doesn't exist, the user hasn't installed yet.
if [ ! -f "venv/bin/activate" ]; then
    echo "[!] Outreach Pilot is not installed yet."
    echo ""
    echo "    Please double-click Install.command first."
    echo ""
    echo "    Press any key to close..."
    read -n 1
    exit 1
fi

# Activate virtualenv
source venv/bin/activate

# Open the dashboard in the default browser after a short delay
( sleep 3 && open http://localhost:5555 ) &

echo "  Dashboard: http://localhost:5555"
echo "  Press Ctrl+C in this window to stop the server."
echo ""

python server.py
