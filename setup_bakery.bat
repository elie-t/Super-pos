@echo off
echo ====================================
echo   Super POS - Bakery Setup
echo ====================================
echo.

echo [1/3] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python is installed and in PATH.
    pause
    exit /b 1
)

echo.
echo [2/3] Creating bakery configuration...
(
echo APP_MODE=restaurant
echo IS_MAIN_BRANCH=false
) > .env
echo .env created with restaurant mode.

echo.
echo [3/3] Initialising database and seeding admin user...
python -c "from database.engine import init_db; init_db(); print('Database ready.')"
if %errorlevel% neq 0 (
    echo ERROR: Database init failed.
    pause
    exit /b 1
)

echo.
echo ====================================
echo   Setup complete!
echo   Login: admin  /  admin123
echo ====================================
echo.
pause
