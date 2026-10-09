@echo off
REM =============================================================
REM FloraScheme Daily Scraper Task Runner for Windows
REM =============================================================
cd /d "D:\florascheme"
"C:\Users\shiva\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe" "D:\florascheme\run_scheduler.py" --now >> "D:\florascheme\data\daily_task.log" 2>&1
