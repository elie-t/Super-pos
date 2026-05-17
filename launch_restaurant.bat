@echo off
cd /d "%~dp0"
git pull
set APP_MODE=restaurant
start "" pythonw main.py
