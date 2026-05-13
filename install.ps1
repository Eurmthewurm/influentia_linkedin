# ─────────────────────────────────────────────────────────────────────────────
# install.ps1 — Influentia one-line installer (Windows)
# Usage: irm https://get.influentia.io/install.ps1 | iex
# ─────────────────────────────────────────────────────────────────────────────
$ErrorActionPreference = "Stop"

$INFLUENTIA_DIR = "$env:USERPROFILE\.influentia"
$INFLUENTIA_VERSION = "1.0.0"
$DOWNLOAD_URL = "https://downloads.influentia.io/Influentia-$INFLUENTIA_VERSION.tar.gz"

Write-Host ""
Write-Host "Influentia $INFLUENTIA_VERSION — Installer" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────"
Write-Host ""

# ── Python 3.11+ check ─────────────────────────────────────────────────────
Write-Host "→ Checking Python…" -ForegroundColor Cyan

$PYTHON_CMD = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $PYTHON_CMD = $cmd
                break
            }
        }
    } catch { continue }
}

if (-not $PYTHON_CMD) {
    Write-Host "→ Python 3.11+ not found. Installing via winget…" -ForegroundColor Cyan
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Python install failed." }
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    $PYTHON_CMD = "python"
}

$pyVer = & $PYTHON_CMD --version 2>&1
Write-Host "✓ $pyVer found" -ForegroundColor Green

# ── Create install directory ────────────────────────────────────────────────
Write-Host "→ Creating Influentia directory at $INFLUENTIA_DIR…" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $INFLUENTIA_DIR | Out-Null
Set-Location $INFLUENTIA_DIR

# ── Download source bundle ─────────────────────────────────────────────────
Write-Host "→ Downloading Influentia $INFLUENTIA_VERSION…" -ForegroundColor Cyan
$tarGzPath = "Influentia-$INFLUENTIA_VERSION.tar.gz"
try {
    Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $tarGzPath -UseBasicParsing
} catch {
    # Try curl as fallback
    curl.exe -fsSL $DOWNLOAD_URL -o $tarGzPath
}
Write-Host "✓ Downloaded" -ForegroundColor Green

# ── Extract ─────────────────────────────────────────────────────────────────
Write-Host "→ Extracting…" -ForegroundColor Cyan
# Windows tar (built into Windows 10+)
tar xzf $tarGzPath
Remove-Item $tarGzPath -Force
Write-Host "✓ Extracted to $INFLUENTIA_DIR" -ForegroundColor Green

# ── Create virtual environment ──────────────────────────────────────────────
Write-Host "→ Creating Python virtual environment…" -ForegroundColor Cyan
& $PYTHON_CMD -m venv venv
& .\venv\Scripts\Activate.ps1
Write-Host "✓ Virtual environment ready" -ForegroundColor Green

# ── Install Python dependencies ─────────────────────────────────────────────
Write-Host "→ Installing Python dependencies (this takes ~2 min)…" -ForegroundColor Cyan
pip install --quiet --upgrade pip
pip install --quiet anthropic playwright requests python-dotenv pytz keyring hono stripe
Write-Host "✓ Python dependencies installed" -ForegroundColor Green

# ── Install Playwright Chromium ─────────────────────────────────────────────
Write-Host "→ Installing Chromium browser (~150 MB)…" -ForegroundColor Cyan
python -m playwright install chromium
Write-Host "✓ Chromium installed" -ForegroundColor Green

# ── Create logs directory ───────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

# ── Create startup shortcut ─────────────────────────────────────────────────
Write-Host "→ Creating startup shortcut…" -ForegroundColor Cyan
$startupDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shortcutPath = "$startupDir\Influentia.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$INFLUENTIA_DIR\venv\Scripts\python.exe"
$shortcut.Arguments = "server.py"
$shortcut.WorkingDirectory = $INFLUENTIA_DIR
$shortcut.Save()
Write-Host "✓ Startup shortcut created" -ForegroundColor Green

# ── Start the server ────────────────────────────────────────────────────────
Write-Host "→ Starting Influentia server…" -ForegroundColor Cyan
$proc = Start-Process -FilePath "$INFLUENTIA_DIR\venv\Scripts\python.exe" `
    -ArgumentList "server.py" `
    -WorkingDirectory $INFLUENTIA_DIR `
    -WindowStyle Hidden `
    -PassThru
$proc.Id | Out-File "$INFLUENTIA_DIR\.server.pid"

# Wait for server
Start-Sleep -Seconds 3
try {
    $r = Invoke-WebRequest -Uri "http://localhost:5555/api/status" -UseBasicParsing -TimeoutSec 5
    Write-Host "✓ Server running (PID $($proc.Id))" -ForegroundColor Green
} catch {
    Write-Host "⚠ Server may still be starting. Check logs: $INFLUENTIA_DIR\logs\server_stderr.log" -ForegroundColor Yellow
}

# ── Open browser ─────────────────────────────────────────────────────────────
Write-Host "→ Opening Influentia in your browser…" -ForegroundColor Cyan
Start-Process "http://localhost:5555/wizard"

Write-Host ""
Write-Host "Influentia is ready." -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard:  http://localhost:5555"
Write-Host "  Wizard:     http://localhost:5555/wizard"
Write-Host "  Logs:       $INFLUENTIA_DIR\logs\"
Write-Host ""
