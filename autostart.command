#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Influentia — Autostart Setup
#
# Run this ONCE. After that the server starts automatically every time you
# log in to your Mac — no Terminal needed, no manual start.
#
# To uninstall autostart later, run: launchctl unload ~/Library/LaunchAgents/io.influentia.server.plist
# ─────────────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
PLIST_PATH="$HOME/Library/LaunchAgents/io.influentia.server.plist"
PYTHON_PATH="$APP_DIR/venv/bin/python"
LOG_DIR="$APP_DIR/logs"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Influentia — Setting up background autostart"
echo "════════════════════════════════════════════════════════"
echo ""

# ── Sanity checks ────────────────────────────────────────────────────────────
if [ ! -f "$PYTHON_PATH" ]; then
    echo "❌  Virtual environment not found."
    echo "    Please run install.sh first, then try again."
    echo ""
    read -n 1 -p "Press any key to close…"
    exit 1
fi

if [ ! -f "$APP_DIR/server.py" ]; then
    echo "❌  server.py not found in $APP_DIR"
    echo ""
    read -n 1 -p "Press any key to close…"
    exit 1
fi

# ── Create logs folder ───────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ── Stop any existing instance ───────────────────────────────────────────────
if launchctl list | grep -q "io.influentia.server" 2>/dev/null; then
    echo "↺  Stopping existing autostart service…"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Kill anything on port 5555
lsof -ti :5555 | xargs kill -9 2>/dev/null || true
sleep 1

# ── Write the LaunchAgent plist ───────────────────────────────────────────────
cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.influentia.server</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${APP_DIR}/server.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${APP_DIR}</string>

    <!-- Start automatically when you log in -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart automatically if it ever crashes -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait 10 s before restarting after a crash -->
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <!-- Log output -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/server_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/server_stderr.log</string>

    <!-- Only run when logged in (not as root) -->
    <key>SessionCreate</key>
    <true/>
</dict>
</plist>
PLIST

echo "✓  LaunchAgent written"

# ── Install daily autopilot (9 AM routine) ──────────────────────────────────
AUTOPILOT_PLIST="$HOME/Library/LaunchAgents/io.influentia.autopilot.plist"
cat > "$AUTOPILOT_PLIST" << APLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.influentia.autopilot</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${APP_DIR}/daily_autopilot.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${APP_DIR}</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/autopilot.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/autopilot.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
APLIST

launchctl unload "$AUTOPILOT_PLIST" 2>/dev/null || true
launchctl load "$AUTOPILOT_PLIST"
echo "✓  Daily routine scheduled (9 AM every day)"

# ── Load server now (no restart needed) ─────────────────────────────────────
launchctl load "$PLIST_PATH"
sleep 2

# Confirm it's running
if lsof -ti :5555 > /dev/null 2>&1; then
    echo "✓  Server is running on port 5555"
else
    echo "⚠  Server may still be starting — wait a few seconds then open"
    echo "   http://localhost:5555"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Done! Influentia now runs automatically."
echo ""
echo "  • Starts every time you log in — no Terminal needed"
echo "  • Restarts itself if it ever crashes"
echo "  • Runs outreach at 9 AM, 1 PM, and 6 PM daily"
echo "  • Dashboard: http://localhost:5555"
echo ""
echo "  To stop autostart: run remove-autostart.command"
echo "════════════════════════════════════════════════════════"
echo ""

# Open dashboard
open http://localhost:5555

read -n 1 -p "Press any key to close this window…"
