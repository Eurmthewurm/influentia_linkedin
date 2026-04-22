@echo off
REM ────────────────────────────────────────────────────────────────────────────
REM  Outreach Pilot — Windows installer
REM  Double-click this file. It will install Python if needed, create the
REM  virtual environment, install dependencies, and set up the browser.
REM ────────────────────────────────────────────────────────────────────────────
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ==========================================================
echo   Outreach Pilot — Setup
echo ==========================================================
echo.

REM 1. Check for Python
where python >nul 2>&1
if errorlevel 1 (
    echo [!] Python was not found on this computer.
    echo.
    echo     Outreach Pilot needs Python 3.10 or newer.
    echo     The easiest way to install it:
    echo       1. Open the Microsoft Store
    echo       2. Search for "Python 3.11" and click Install
    echo       3. Come back and double-click Install.bat again
    echo.
    echo     Or download the installer from https://www.python.org/downloads/
    echo     During setup, check "Add Python to PATH".
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

REM 2. Verify Python version (3.10+)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [+] Found Python %PY_VER%

REM 3. Create virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo [+] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [+] Virtual environment already exists
)

REM 4. Activate and upgrade pip
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet

REM 5. Install dependencies
echo [+] Installing dependencies (this may take a minute)...
python -m pip install --quiet anthropic playwright requests python-dotenv pytz
if errorlevel 1 (
    echo [X] Failed to install Python dependencies.
    echo     Check your internet connection and try again.
    pause
    exit /b 1
)

REM 6. Install Chromium browser for Playwright
echo [+] Installing Chromium browser for automation...
python -m playwright install chromium
if errorlevel 1 (
    echo [!] Chromium install had an issue. You can continue — if LinkedIn
    echo     Connect fails later, run "python -m playwright install chromium"
    echo     manually.
)

REM 7. Bootstrap .env from example if needed
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo [+] Created .env from template
    ) else (
        type nul > .env
        echo [+] Created empty .env
    )
) else (
    echo [+] .env already exists
)

REM 8. Done
echo.
echo ==========================================================
echo   Setup complete.
echo ==========================================================
echo.
echo   Next step: double-click Start.bat to launch Outreach Pilot.
echo   The dashboard will open in your browser at
echo   http://localhost:5555
echo.
pause
