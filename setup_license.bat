@echo off
cd /d "%~dp0"
echo Registering this machine...
python main.py --register
if %errorlevel%==0 (
    echo.
    echo Done! This machine is now licenced.
) else (
    echo.
    echo ERROR: Run this file as Administrator.
)
pause
