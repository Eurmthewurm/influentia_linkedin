#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# install.sh — Influentia one-line installer
# Usage: curl -fsSL https://get.influentia.io/install.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

INFLUENTIA_DIR="$HOME/.influentia"
INFLUENTIA_VERSION="1.0.0"
DOWNLOAD_URL="https://downloads.influentia.io/Influentia-${INFLUENTIA_VERSION}.tar.gz"

# ── colours ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
fail()  { echo -e "${RED}✕${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}Influentia ${INFLUENTIA_VERSION} — Installer${NC}"
echo "─────────────────────────────────────────"
echo ""

# ── OS detection ────────────────────────────────────────────────────────────
OS="unknown"
case "$(uname -s)" in
  Darwin*)  OS="macos" ;;
  Linux*)   OS="linux" ;;
  MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
esac

if [[ "$OS" == "windows" ]]; then
  fail "Windows detected. Please use the PowerShell installer:\n  irm https://get.influentia.io/install.ps1 | iex"
fi

if [[ "$OS" == "linux" ]]; then
  warn "Linux is not officially supported yet. Proceeding with best-effort install."
fi

# ── Python 3.11+ check ─────────────────────────────────────────────────────
info "Checking Python…"

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3; do
  if command -v "$cmd" &>/dev/null; then
    PY_VERSION=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0")
    MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [[ "$MAJOR" -ge 3 && "$MINOR" -ge 11 ]]; then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done

if [[ -z "$PYTHON_CMD" ]]; then
  info "Python 3.11+ not found. Installing…"
  if [[ "$OS" == "macos" ]]; then
    if ! command -v brew &>/dev/null; then
      info "Installing Homebrew…"
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || fail "Homebrew install failed."
    fi
    brew install python@3.11 || fail "Python install failed."
    PYTHON_CMD="python3.11"
  else
    if command -v apt-get &>/dev/null; then
      sudo apt-get update -qq
      sudo apt-get install -y -qq python3.11 python3.11-venv || fail "Python install failed."
      PYTHON_CMD="python3.11"
    else
      fail "Cannot auto-install Python. Please install Python 3.11+ manually."
    fi
  fi
fi

ok "Python $($PYTHON_CMD --version 2>&1 | cut -d' ' -f2) found"

# ── Create install directory ────────────────────────────────────────────────
info "Creating Influentia directory at ${INFLUENTIA_DIR}…"
mkdir -p "$INFLUENTIA_DIR"
cd "$INFLUENTIA_DIR"

# ── Download source bundle ─────────────────────────────────────────────────
info "Downloading Influentia ${INFLUENTIA_VERSION}…"

# Remove old download if partial
rm -f "Influentia-${INFLUENTIA_VERSION}.tar.gz"

if command -v curl &>/dev/null; then
  curl -fsSL "$DOWNLOAD_URL" -o "Influentia-${INFLUENTIA_VERSION}.tar.gz" || fail "Download failed. Check your internet connection."
elif command -v wget &>/dev/null; then
  wget -q "$DOWNLOAD_URL" -O "Influentia-${INFLUENTIA_VERSION}.tar.gz" || fail "Download failed. Check your internet connection."
else
  fail "Neither curl nor wget found. Please install one and retry."
fi

ok "Downloaded $(du -h "Influentia-${INFLUENTIA_VERSION}.tar.gz" | cut -f1)"

# ── Extract ─────────────────────────────────────────────────────────────────
info "Extracting…"
tar xzf "Influentia-${INFLUENTIA_VERSION}.tar.gz" || fail "Extraction failed."
rm -f "Influentia-${INFLUENTIA_VERSION}.tar.gz"
ok "Extracted to ${INFLUENTIA_DIR}"

# ── Create virtual environment ──────────────────────────────────────────────
info "Creating Python virtual environment…"
"$PYTHON_CMD" -m venv venv || fail "Failed to create virtual environment."
source venv/bin/activate
ok "Virtual environment ready"

# ── Install Python dependencies ─────────────────────────────────────────────
info "Installing Python dependencies (this takes ~2 min)…"
pip install --quiet --upgrade pip
pip install --quiet \
  anthropic \
  playwright \
  requests \
  python-dotenv \
  pytz \
  keyring \
  hono \
  stripe \
  || fail "Dependency install failed."
ok "Python dependencies installed"

# ── Install Playwright Chromium ─────────────────────────────────────────────
info "Installing Chromium browser (~150 MB, takes ~1 min)…"
python -m playwright install chromium --with-deps 2>/dev/null || {
  # --with-deps may fail without sudo; try without
  python -m playwright install chromium || fail "Playwright Chromium install failed."
}
ok "Chromium installed"

# ── Create logs directory ───────────────────────────────────────────────────
mkdir -p logs

# ── Register LaunchAgent (macOS) ────────────────────────────────────────────
if [[ "$OS" == "macos" ]]; then
  info "Registering LaunchAgent (auto-start on login)…"
  PLIST_PATH="$HOME/Library/LaunchAgents/io.influentia.server.plist"

  cat > "$PLIST_PATH" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>io.influentia.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>${INFLUENTIA_DIR}/venv/bin/python</string>
    <string>${INFLUENTIA_DIR}/server.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${INFLUENTIA_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${INFLUENTIA_DIR}/logs/server_stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${INFLUENTIA_DIR}/logs/server_stderr.log</string>
</dict>
</plist>
PLIST_EOF

  # Unload old version if running, then load new
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
  sleep 1
  launchctl load "$PLIST_PATH" || warn "LaunchAgent load failed — you may need to start manually."
  ok "LaunchAgent registered"
fi

# ── Start the server ────────────────────────────────────────────────────────
info "Starting Influentia server…"
nohup "$INFLUENTIA_DIR/venv/bin/python" "$INFLUENTIA_DIR/server.py" \
  > "$INFLUENTIA_DIR/logs/server_stdout.log" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$INFLUENTIA_DIR/.server.pid"

# Wait for server to bind
for i in $(seq 1 15); do
  if curl -s http://localhost:5555/api/status >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# ── Open browser ─────────────────────────────────────────────────────────────
sleep 1
if curl -s http://localhost:5555/api/status >/dev/null 2>&1; then
  ok "Server running (PID ${SERVER_PID})"
  info "Opening Influentia in your browser…"
  if [[ "$OS" == "macos" ]]; then
    open "http://localhost:5555/wizard"
  else
    xdg-open "http://localhost:5555/wizard" 2>/dev/null || true
  fi
else
  warn "Server may still be starting. Check logs: ${INFLUENTIA_DIR}/logs/server_stderr.log"
fi

echo ""
echo -e "${GREEN}${BOLD}Influentia is ready.${NC}"
echo ""
echo "  Dashboard:  http://localhost:5555"
echo "  Wizard:     http://localhost:5555/wizard"
echo "  Logs:       ${INFLUENTIA_DIR}/logs/"
echo ""
echo "  Restart:    launchctl kickstart -k gui/$(id -u)/io.influentia.server"
echo "  Stop:       launchctl unload ~/Library/LaunchAgents/io.influentia.server.plist"
echo ""
