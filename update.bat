@echo off
echo Updating TannouryMarket POS...
git pull
echo.
echo Update complete. Press any key to launch the app.
pause >nul
python main.py
