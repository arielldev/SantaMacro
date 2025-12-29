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
echo [5/5] Installing required packages...
echo Installing packages individually...
echo This may take several minutes...
echo.

set FAILED_PACKAGES=
set FAILED_COUNT=0

echo Installing mss...
python -m pip install mss==9.0.1 >nul 2>&1
if errorlevel 1 (
    echo ✗ mss failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! mss
    set /a FAILED_COUNT+=1
) else (
    echo ✓ mss installed
)

echo Installing numpy...
python -m pip install numpy==2.1.3 >nul 2>&1
if errorlevel 1 (
    echo ✗ numpy failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! numpy
    set /a FAILED_COUNT+=1
) else (
    echo ✓ numpy installed
)

echo Installing opencv-python...
python -m pip install opencv-python==4.10.0.84 >nul 2>&1
if errorlevel 1 (
    echo ✗ opencv-python failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! opencv-python
    set /a FAILED_COUNT+=1
) else (
    echo ✓ opencv-python installed
)

echo Installing Pillow...
python -m pip install Pillow==11.0.0 >nul 2>&1
if errorlevel 1 (
    echo ✗ Pillow failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! Pillow
    set /a FAILED_COUNT+=1
) else (
    echo ✓ Pillow installed
)

echo Installing pyautogui...
python -m pip install pyautogui==0.9.54 >nul 2>&1
if errorlevel 1 (
    echo ✗ pyautogui failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pyautogui
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pyautogui installed
)

echo Installing pydirectinput...
python -m pip install pydirectinput==1.0.4 >nul 2>&1
if errorlevel 1 (
    echo ✗ pydirectinput failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pydirectinput
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pydirectinput installed
)

echo Installing pynput...
python -m pip install pynput==1.7.6 >nul 2>&1
if errorlevel 1 (
    echo ✗ pynput failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pynput
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pynput installed
)

echo Installing PySide6...
python -m pip install "PySide6>=6.8.0" >nul 2>&1
if errorlevel 1 (
    echo ✗ PySide6 failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! PySide6
    set /a FAILED_COUNT+=1
) else (
    echo ✓ PySide6 installed
)

echo Installing ultralytics ^(YOLOv8 - this may take a while^)...
python -m pip install ultralytics >nul 2>&1
if errorlevel 1 (
    echo ✗ ultralytics failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! ultralytics
    set /a FAILED_COUNT+=1
) else (
    echo ✓ ultralytics installed
)

echo.
if !FAILED_COUNT! GTR 0 (
    echo ⚠️ WARNING: !FAILED_COUNT! package^(s^) failed to install
    echo.
    echo Failed packages:!FAILED_PACKAGES!
    echo.
    echo TO FIX:
    echo 1. Make sure you're using Python 3.12 or 3.13 ^(NOT 3.14+^)
    echo 2. Try running install.bat as Administrator
    echo 3. Check your internet connection
    echo 4. Install manually: python -m pip install [package_name]
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
