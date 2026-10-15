Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Projects\AI trading Bot\trading-system"
WshShell.Run """D:\Projects\AI trading Bot\trading-system\venv\Scripts\python.exe"" auto_daily_session.py --daemon", 0, False
