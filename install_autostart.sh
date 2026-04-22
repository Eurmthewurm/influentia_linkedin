#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# install_autostart.sh
# Sets up the Outreach Pilot server to start automatically at login on macOS.
# Run once from inside the outreach-pilot folder:
#   bash install_autostart.sh
# ─────────────────────────────────────────────────────────────────────────────

# Get the actual folder this script lives in (works regardless of where user put it)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.outreachpilot.server"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON_PATH="$SCRIPT_DIR/venv/bin/python3"
SERVER_PATH="$SCRIPT_DIR/server.py"

echo "════════════════════════════════════════════════════════════"
echo "  Outreach Pilot — Auto-Start Installer"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check this is actually the right folder
if [ ! -f "$SERVER_PATH" ]; then
    echo "❌ Cannot find server.py in: $SCRIPT_DIR"
    echo "   Make sure you're running this from inside the outreach-pilot folder."
    exit 1
fi

# Check virtualenv exists
if [ ! -f "$PYTHON_PATH" ]; then
    echo "❌ Virtual environment not found at: $SCRIPT_DIR/venv/"
    echo "   Run install.sh first to set up dependencies."
    exit 1
fi

echo "✓ Found Outreach Pilot at: $SCRIPT_DIR"
echo ""

# Remove any previous version
if [ -f "$PLIST_DEST" ]; then
    echo "Removing previous install..."
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST_DEST"
fi

# Generate the plist dynamically with correct paths
cat > "$PLIST_DEST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SERVER_PATH}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/server_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/server_stderr.log</string>

    <!-- Start when you log in -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart automatically if it crashes -->
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
PLIST

echo "✓ LaunchAgent written to: $PLIST_DEST"

# Register it
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
if [ $? -eq 0 ]; then
    echo "✓ Auto-start registered"
else
    # Fallback for older macOS
    launchctl load "$PLIST_DEST" 2>/dev/null || true
    echo "✓ Auto-start registered (legacy method)"
fi

# Give it a moment to start
echo ""
echo "Starting server now..."
sleep 3

if curl -s --connect-timeout 5 http://localhost:5555/api/status > /dev/null 2>&1; then
    echo "✓ Server is running at http://localhost:5555"
else
    echo "⚠  Server may still be starting. Open http://localhost:5555 in a moment."
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Done! The server will now start automatically every time"
echo "  you log in to your Mac."
echo ""
echo "  Open http://localhost:5555 to use the dashboard."
echo "════════════════════════════════════════════════════════════"
echo ""
echo "To uninstall auto-start:"
echo "  launchctl bootout gui/\$(id -u) ~/Library/LaunchAgents/$LABEL.plist"
echo "  rm ~/Library/LaunchAgents/$LABEL.plist"
echo ""
