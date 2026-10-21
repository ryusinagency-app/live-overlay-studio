@echo off
title Live Overlay Studio
cd /d "%~dp0"
py -3 -c "import importlib.metadata as m; raise SystemExit(0 if m.version('TikTokLive') == '7.0.1' else 1)" >nul 2>nul
if errorlevel 1 (
  echo Installing the required TikTok LIVE gift receiver version...
  py -3 -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Package installation failed. The overlay will still work, but gift detection will be unavailable.
  )
)
py -3 server.py
pause
