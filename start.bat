@echo off
title Live Overlay Studio
cd /d "%~dp0"
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo Python 3 was not found. Install Python 3, then run this file again.
  pause
  exit /b 1
)
%PYTHON_CMD% -c "import importlib.metadata as m; raise SystemExit(0 if m.version('TikTokLive') == '7.0.1' else 1)" >nul 2>nul
if errorlevel 1 (
  echo Installing the required TikTok LIVE gift receiver version...
  %PYTHON_CMD% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Package installation failed. The overlay will still work, but gift detection will be unavailable.
  )
)
%PYTHON_CMD% server.py
pause
