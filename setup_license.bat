@echo off
cd /d "%~dp0"
echo ===============================
echo   SuperPOS Licence Setup
echo ===============================
echo.
python main.py --register
if %errorlevel%==0 (
    echo.
    echo Licence saved successfully.
) else (
    echo.
    echo Registration failed. Make sure you run as Administrator.
)
pause
