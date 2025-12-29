@echo off
setlocal enabledelayedexpansion
echo ========================================
echo   SantaMacro - Easy Installation
echo ========================================
echo.

echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.12 or 3.13 from https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python %PYTHON_VERSION% found

echo.
echo [2/5] Creating virtual environment...
if exist ".venv" (
    echo ✓ Virtual environment already exists
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment
        pause
        exit /b 1
    )
    echo ✓ Virtual environment created
)

echo.
echo [3/5] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate virtual environment
    pause
    exit /b 1
)
echo ✓ Virtual environment activated

echo.
echo [4/5] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
if errorlevel 1 (
    echo WARNING: Could not upgrade pip, continuing anyway...
) else (
    echo ✓ Pip upgraded successfully
)

echo.
echo [5/5] Installing required packages from requirements.txt...
if not exist "requirements.txt" (
    echo ERROR: requirements.txt not found
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ⚠️ WARNING: Some packages may have failed to install
    echo.
    echo TO FIX:
    echo 1. Make sure you're using Python 3.12 or 3.13 ^(NOT 3.14+^)
    echo 2. Try running install.bat as Administrator
    echo 3. Check your internet connection
    echo.
) else (
    echo ✓ All packages installed successfully!
)

echo.
echo [Verification] Testing core imports...
python -c "import numpy, cv2, ultralytics, pydirectinput, keyboard, mss; print('✓ Core modules verified')" 2>nul
if errorlevel 1 (
    echo WARNING: Some core modules may not be properly installed
    echo The program may still work, but some features might be limited
)

python -c "from PySide6.QtWidgets import QApplication; print('✓ UI modules verified')" 2>nul
if errorlevel 1 (
    echo WARNING: PySide6 UI modules may have issues
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo To run SantaMacro:
echo   • Double-click "run_dev.bat" for development with terminal
echo   • Double-click "run.bat" for silent background mode
echo   • Or run ".venv\Scripts\python.exe src\main.py"
echo.
echo Press any key to exit...
pause >nul
