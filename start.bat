@echo off
chcp 65001 >nul
echo ============================================
echo   Case Library - FastAPI Startup
echo ============================================
echo.

cd /d "%~dp0backend"

echo [1/3] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python was not found. Please install Python first.
    pause
    exit /b 1
)
echo Python is available.
echo.

echo [2/3] Checking startup prerequisites...
echo This script does not run demo data initialization.
echo This script does not run SQLite to MongoDB migration.
echo.
echo First-time setup:
echo   1. Start MongoDB.
echo   2. Install dependencies if needed: pip install -r requirements.txt
echo   3. Optional one-time migration: python migrate_sqlite_to_mongo.py
echo.

echo [3/3] Starting FastAPI at http://localhost:8001 ...
echo Press Ctrl+C to stop.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8001

pause
