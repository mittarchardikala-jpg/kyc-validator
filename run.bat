@echo off
setlocal enabledelayedexpansion

echo Starting KYC Validator...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo ERROR: Python is not installed!
    echo ============================================
    echo.
    echo Please download and install Python from:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, CHECK the box:
    echo "Add Python to PATH"
    echo.
    echo ============================================
    pause
    exit /b 1
)

echo Python found!
echo.

REM Check if venv exists, if not create it
if not exist "venv" (
    echo Creating virtual environment (this takes 1-2 minutes)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Error creating virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created!
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

if %errorlevel% neq 0 (
    echo Error activating virtual environment
    pause
    exit /b 1
)

echo.
echo Installing dependencies (this takes 2-3 minutes on first run)...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Error installing dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo KYC Validator is starting...
echo ========================================
echo.
echo Your browser will open automatically in 5 seconds...
echo If not, go to: http://localhost:8501
echo.
timeout /t 5

streamlit run streamlit_app.py

pause