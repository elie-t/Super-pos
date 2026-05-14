@echo off
cd /d "%~dp0"
echo Checking for updates...
git pull
echo Starting Restaurant POS...
set APP_MODE=restaurant
python main.py
