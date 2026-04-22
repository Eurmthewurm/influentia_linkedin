#!/bin/bash
set -e

# ─────────────────────────────────────────────────────────────────────────────
# LinkedIn Outreach Autopilot — Installer
#
# Detects OS, installs Python, sets up virtualenv, and installs dependencies.
# Run with: bash install.sh  or  curl -sSL <url> | bash
# ─────────────────────────────────────────────────────────────────────────────

echo "════════════════════════════════════════════════════════════════"
echo "  LinkedIn Outreach Autopilot — Setup"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    echo "❌ Unsupported OS: $OSTYPE"
    echo "   This installer supports macOS and Linux only."
    exit 1
fi

echo "✓ Detected OS: $OS"

# ─────────────────────────────────────────────────────────────────────────────
# Check for Python 3.8+
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Checking for Python 3.8+…"

PYTHON=""
if command -v python3 &> /dev/null; then
    VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    MAJOR=$(echo $VERSION | cut -d. -f1)
    MINOR=$(echo $VERSION | cut -d. -f2)
    if [[ $MAJOR -gt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -ge 8 ]]; then
        PYTHON="python3"
        echo "✓ Found Python $VERSION"
    else
        echo "⚠ Python $VERSION is too old (need 3.8+)"
    fi
elif command -v python &> /dev/null; then
    VERSION=$(python --version 2>&1 | awk '{print $2}')
    MAJOR=$(echo $VERSION | cut -d. -f1)
    MINOR=$(echo $VERSION | cut -d. -f2)
    if [[ $MAJOR -ge 3 && $MINOR -ge 8 ]]; then
        PYTHON="python"
        echo "✓ Found Python $VERSION"
    fi
fi

# Install Python if needed
if [ -z "$PYTHON" ]; then
    echo "⚠ Python 3.8+ not found. Installing…"
    if [ "$OS" = "macOS" ]; then
        if command -v brew &> /dev/null; then
            echo "  Using Homebrew…"
            brew install python@3.11
            PYTHON="python3.11"
        else
            echo "❌ Homebrew not found. Please install Homebrew first: https://brew.sh"
            exit 1
        fi
    elif [ "$OS" = "Linux" ]; then
        if command -v apt-get &> /dev/null; then
            echo "  Using apt…"
            sudo apt-get update
            sudo apt-get install -y python3.11 python3-pip python3.11-venv
            PYTHON="python3.11"
        elif command -v yum &> /dev/null; then
            echo "  Using yum…"
            sudo yum install -y python3.11 python3-pip
            PYTHON="python3.11"
        else
            echo "❌ Could not find apt or yum. Please install Python 3.8+ manually."
            exit 1
        fi
    fi
fi

echo "✓ Python is ready: $($PYTHON --version)"

# ─────────────────────────────────────────────────────────────────────────────
# Create virtualenv
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Setting up virtual environment…"

if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "✓ Created virtual environment"
else
    echo "✓ Using existing virtual environment"
fi

# Activate virtualenv
if [ "$OS" = "macOS" ] || [ "$OS" = "Linux" ]; then
    source venv/bin/activate
fi

echo "✓ Virtual environment activated"

# ─────────────────────────────────────────────────────────────────────────────
# Upgrade pip
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Upgrading pip…"
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "✓ pip is up to date"

# ─────────────────────────────────────────────────────────────────────────────
# Install Python dependencies
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Installing dependencies…"

pip install -q \
    anthropic \
    playwright \
    requests \
    python-dotenv \
    pytz

echo "✓ Dependencies installed"

# ─────────────────────────────────────────────────────────────────────────────
# Install Playwright and browsers
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Installing Playwright browser…"
echo "  (This may take 1-2 minutes on first run)"

playwright install chromium > /dev/null 2>&1
echo "✓ Playwright and Chromium are ready"

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap .env if needed
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "Checking configuration…"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ Created .env from .env.example"
        echo "  → Open .env in a text editor and add your API keys"
    else
        echo "⚠ No .env.example found. You'll need to create .env manually."
    fi
else
    echo "✓ .env already exists"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Setup complete!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Next step: double-click start.command (macOS) or run:"
echo "   source venv/bin/activate && python server.py"
echo ""
echo "The dashboard will open at http://localhost:5555 and walk you"
echo "through the rest — API keys, your story, and connecting LinkedIn."
echo ""
echo "Questions? See TESTER_QUICKSTART.md or click Feedback in the app."
echo ""
