@echo off
REM One-click MC3 Archipelago installer (Windows).
REM Double-click this file. Requires Python 3.10+ on PATH.
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.10+ from python.org and re-run.
  pause
  exit /b 1
)
python install.py %*
echo.
pause
