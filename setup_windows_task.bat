@echo off
title Setup Windows Scheduled Task — QuantAI
color 0E

echo ====================================================
echo   CONFIGURING WINDOWS TASK SCHEDULER (08:45 AM)
echo ====================================================
echo.
echo This script will register a scheduled task named "QuantAI_Daily_Trader"
echo that triggers automatically every Monday to Friday at 08:45 AM IST.
echo.

set "SCRIPT_PATH=%~dp0trading-system\auto_daily_session.py"
set "PYTHON_PATH=%~dp0trading-system\venv\Scripts\python.exe"

echo Task Target: %PYTHON_PATH% "%SCRIPT_PATH%"
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$Action = New-ScheduledTaskAction -Execute '%PYTHON_PATH%' -Argument '\"%SCRIPT_PATH%\"' -WorkingDirectory '%~dp0trading-system';" ^
  "$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:45AM;" ^
  "$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8);" ^
  "Register-ScheduledTask -TaskName 'QuantAI_Daily_Trader' -Action $Action -Trigger $Trigger -Settings $Settings -Description 'QuantAI Autonomous Zero-Touch Intraday Paper Trader' -Force;"

echo.
if %ERRORLEVEL% equ 0 (
    echo ====================================================
    echo SUCCESS: Windows Task "QuantAI_Daily_Trader" registered!
    echo It will trigger every weekday at 08:45 AM IST automatically.
    echo ====================================================
) else (
    echo NOTE: To enable "Wake to Run", please run this batch file as Administrator.
)

echo.
pause
