@echo off
cd /d "%~dp0"
git pull
start "" pythonw main.py
