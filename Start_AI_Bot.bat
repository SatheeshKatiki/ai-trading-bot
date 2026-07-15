@echo off
title AI Trading Bot Launcher
color 0A

echo ====================================================
echo          QUANT AI TRADING SYSTEM LAUNCHER
echo ====================================================
echo.

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
