@echo off
cls
color 0A
title KYC Validator Startup

echo.
echo ============================================
echo   KYC VALIDATOR - STARTUP SCRIPT
echo ============================================
echo.

REM Check Python
echo Checking if Python is installed...
python --version
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo ERROR: Python not found!
    echo.
    echo Download Python from: https://www.python.org/downloads/
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    echo Press any key to close...
    pause >nul
    exit /b 1
)

echo Python found!
echo.

REM Create venv
if not exist "venv" (
    echo Creating Python environment...
    python -m venv venv
)

echo Activating environment...
call venv\Scripts\activate.bat

echo.
echo Installing packages (first time: 2-3 minutes)...
pip install -q streamlit pandas openpyxl

echo.
echo ============================================
echo Starting KYC Validator...
echo ============================================
echo.
echo Opening browser in 3 seconds...
echo Go to: http://localhost:8501
echo.
timeout /t 3 /nobreak

streamlit run streamlit_app.py

echo.
echo Application closed.
pause