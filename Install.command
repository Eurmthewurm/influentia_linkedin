#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Outreach Pilot — macOS installer
# Double-click this file. It will install everything needed, then you can
# double-click start.command to launch the dashboard.
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")"

if [ -f "install.sh" ]; then
    bash install.sh
    echo ""
    echo "Press any key to close this window…"
    read -n 1
else
    echo "install.sh not found. Please make sure you downloaded the full bundle."
    read -n 1
fi
