@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller
py build_windows_app.py
echo.
echo Build complete: dist\Live_Minecraft_Studio_Windows_x64.exe
pause
