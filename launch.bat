@echo off
cd /d "%~dp0"
git pull --quiet
python main.py
if errorlevel 1 (
    echo.
    echo ERROR: App crashed. See message above.
    pause
)
