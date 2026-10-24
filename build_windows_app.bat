@echo off
setlocal
cd /d "%~dp0"
title Live Overlay Studio - EXE Builder

echo ==============================================
echo   Live Overlay Studio Windows App Builder
echo ==============================================
echo.

set "PYTHON_CMD=python"
python --version >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3 was not found.
    echo Install Python 3, enable "Add Python to PATH", then run this file again.
    if not defined CI pause
    exit /b 1
  )
  set "PYTHON_CMD=py -3"
)

%PYTHON_CMD% -m pip install --upgrade pyinstaller "TikTokLive==7.0.1"
if errorlevel 1 (
  echo Required packages could not be installed.
  if not defined CI pause
  exit /b 1
)

%PYTHON_CMD% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "Live_Overlay_Studio_Windows_x64" ^
  --icon "app_icon.ico" ^
  --collect-all TikTokLive ^
  --add-data "control.html;." ^
  --add-data "overlay.html;." ^
  --add-data "overlay_comp.html;." ^
  --add-data "overlay_counters.html;." ^
  --add-data "overlay_gacha.html;." ^
  --add-data "overlay_other_gacha.html;." ^
  --add-data "overlay_gacha_history.html;." ^
  --add-data "overlay_gacha_ranking.html;." ^
  --add-data "overlay_gacha_set_ranking.html;." ^
  --add-data "overlay_gacha_win_ranking.html;." ^
  --add-data "overlay_gacha_rankings.html;." ^
  --add-data "overlay_gift_history.html;." ^
  --add-data "overlay_gift_media.html;." ^
  --add-data "overlay_pachinko.html;." ^
  --add-data "overlay_missions.html;." ^
  --add-data "overlay_smoking.html;." ^
  --add-data "overlay_smoking_gacha.html;." ^
  --add-data "overlay_timer.html;." ^
  --add-data "overlay_win.html;." ^
  --add-data "v6608.js;." ^
  --add-data "README.txt;." ^
  --add-data "update_config.json;." ^
  --add-data "app_icon.ico;." ^
  server.py

if errorlevel 1 (
  echo.
  echo EXE build failed. Check the messages above.
  if not defined CI pause
  exit /b 1
)

echo.
echo Build complete:
echo   dist\Live_Overlay_Studio_Windows_x64.exe
echo.
echo Distribute that EXE file. Users do not need to install Python.
echo Each user's settings are saved in %%LOCALAPPDATA%%\LiveOverlayStudio.
if not defined CI (
  explorer "%~dp0dist"
  pause
)
