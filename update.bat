@echo off
echo Checking for updates...
git fetch origin
git checkout -- .
git clean -fd
git pull
echo.
echo Update complete. Press any key to launch the app.
pause >nul
python main.py
