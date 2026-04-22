@echo off
REM ────────────────────────────────────────────────────────────────────────────
REM  Outreach Pilot — Windows launcher
REM  Double-click this file to start the dashboard.
REM ────────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo.
    echo [!] Outreach Pilot is not installed yet.
    echo     Please double-click Install.bat first.
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Open the dashboard in the default browser after a short delay
start "" /B cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5555"

echo.
echo ==========================================================
echo   Outreach Pilot is starting...
echo   Dashboard: http://localhost:5555
echo   Press Ctrl+C in this window to stop the server.
echo ==========================================================
echo.

python server.py
pause
