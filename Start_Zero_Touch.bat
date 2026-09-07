@echo off
title QuantAI — Zero-Touch Automated Trading Bot
color 0B

echo ====================================================
echo        QUANT AI — ZERO-TOUCH DAILY RUNNER
echo ====================================================
echo.
echo Mode Options:
echo   [1] Start 24/7 Daemon Mode (Runs continuously, wakes up at 08:45 AM every trading day)
echo   [2] Run Today's Session Immediately (Test / Live Now)
echo   [3] Test Auto-Login Only (Fyers Auth)
echo   [4] Test EOD Telegram Report
echo.
set /p choice="Select an option [1-4] (Default 1): "

if "%choice%"=="2" (
    echo Starting Immediate Session...
    cd /d "%~dp0trading-system"
    .\venv\Scripts\python.exe auto_daily_session.py --now
) else if "%choice%"=="3" (
    echo Testing Auto-Login...
    cd /d "%~dp0trading-system"
    .\venv\Scripts\python.exe auto_daily_session.py --test-login
) else if "%choice%"=="4" (
    echo Testing EOD Report...
    cd /d "%~dp0trading-system"
    .\venv\Scripts\python.exe auto_daily_session.py --test-eod
) else (
    echo Starting 24/7 Automated Daemon Mode...
    cd /d "%~dp0trading-system"
    .\venv\Scripts\python.exe auto_daily_session.py --daemon
)

pause
