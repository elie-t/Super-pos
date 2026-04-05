@echo off
echo Installing Tannoury POS dependencies...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Installation failed. Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)
echo.
echo Installation complete! Run launch.bat to start the app.
pause
