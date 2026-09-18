@echo off
title AI Trading Bot Launcher
color 0A

echo ====================================================
echo          QUANT AI TRADING SYSTEM LAUNCHER
echo ====================================================
echo.

rem -- Refuse to hijack a session that is already running -----------------
rem The port cleanup below force-kills whatever owns 8000/3000. While the
rem zero-touch orchestrator is running that is ITS api_bridge and dashboard:
rem on 2026-09-18 this killed a healthy bridge at 10:16, the supervisor's
rem five restarts were all refused by the new instance's singleton lock, and
rem the session ran the rest of the day orphaned on stale code. The main.py
rem started below also adopted the paper observer's open position and then
rem warned "has not ticked in never" because it streams a different symbol.
rem One session, one set of books.
rem Name -eq 'python.exe' matters: without it the powershell process running
rem this very check matches its own command line and the launcher refuses
rem every time.
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and ($_.CommandLine -like '*auto_daily_session.py*' -or $_.CommandLine -like '*paper_observer.py*') }) { exit 1 }"
if errorlevel 1 (
    color 0C
    echo.
    echo  !! A TRADING SESSION IS ALREADY RUNNING.
    echo.
    echo  Starting a second copy would kill its API bridge and dashboard,
    echo  and run two trading books against the same positions file.
    echo  NOTHING has been started.
    echo.
    echo  The dashboard is already up: http://localhost:3000
    echo.
    pause
    exit /b 1
)

echo -^> Cleaning up old ports (8000, 3000) to prevent errors...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    if not "%%a"=="0" taskkill /PID %%a /F 2>nul
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do (
    if not "%%a"=="0" taskkill /PID %%a /F 2>nul
)
echo.

echo [1/3] Starting API Bridge (Backend)...
start "API Bridge" cmd /k "cd /d "%~dp0trading-system" && .\venv\Scripts\python.exe api_bridge.py"

echo [2/3] Starting Live/Paper Trading Bot Engine...
start "Trading Engine" cmd /k "cd /d "%~dp0trading-system" && .\venv\Scripts\python.exe trading_bot\main.py"

echo [3/3] Starting Next.js Dashboard (Frontend)...
start "Frontend UI" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Waiting 10 seconds for all services to initialize...
timeout /t 10 /nobreak >nul

echo Opening Dashboard in your browser...
start http://localhost:3000

echo.
echo ====================================================
echo ALL SYSTEMS ARE LIVE! 
echo Keep the 3 black command windows open while trading.
echo ====================================================
pause
