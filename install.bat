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

for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if %PYTHON_MAJOR% GTR 3 (
    echo.
    echo ========================================
    echo   ERROR: Unsupported Python Version!
    echo ========================================
    echo.
    echo You are using Python %PYTHON_VERSION%
    echo.
    echo SantaMacro requires Python 3.12 or 3.13
    echo Python 3.14+ is NOT supported due to package compatibility
    echo.
    echo Please install Python 3.13 or 3.12:
    echo   • Python 3.13: https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe
    echo   • Python 3.12: https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
    echo.
    pause
    exit /b 1
)

if %PYTHON_MAJOR% EQU 3 if %PYTHON_MINOR% GEQ 14 (
    echo.
    echo ========================================
    echo   ERROR: Unsupported Python Version!
    echo ========================================
    echo.
    echo You are using Python %PYTHON_VERSION%
    echo.
    echo SantaMacro requires Python 3.12 or 3.13
    echo Python 3.14+ is NOT supported due to package compatibility
    echo.
    echo Please install Python 3.13 or 3.12:
    echo   • Python 3.13: https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe
    echo   • Python 3.12: https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
    echo.
    pause
    exit /b 1
)

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
python -m pip install --upgrade pip --quiet
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
echo NOTE: If you see errors, don't worry - we'll verify at the end.
echo.

set FAILED_PACKAGES=
set FAILED_COUNT=0

echo Installing mss...
python -m pip install mss==9.0.1 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ mss failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! mss
    set /a FAILED_COUNT+=1
) else (
    echo ✓ mss installed
)

echo Installing numpy...
python -m pip install numpy==2.1.3 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ numpy failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! numpy
    set /a FAILED_COUNT+=1
) else (
    echo ✓ numpy installed
)

echo Installing opencv-python...
python -m pip install opencv-python==4.10.0.84 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ opencv-python failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! opencv-python
    set /a FAILED_COUNT+=1
) else (
    echo ✓ opencv-python installed
)

echo Installing Pillow...
python -m pip install Pillow==11.0.0 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ Pillow failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! Pillow
    set /a FAILED_COUNT+=1
) else (
    echo ✓ Pillow installed
)

echo Installing pyautogui...
python -m pip install pyautogui==0.9.54 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ pyautogui failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pyautogui
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pyautogui installed
)

echo Installing pydirectinput...
python -m pip install pydirectinput==1.0.4 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ pydirectinput failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pydirectinput
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pydirectinput installed
)

echo Installing pynput...
python -m pip install pynput==1.7.6 --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ pynput failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! pynput
    set /a FAILED_COUNT+=1
) else (
    echo ✓ pynput installed
)

echo Installing PySide6...
python -m pip install "PySide6>=6.8.0" --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ PySide6 failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! PySide6
    set /a FAILED_COUNT+=1
) else (
    echo ✓ PySide6 installed
)

echo Installing requests ^(for Discord webhooks^)...
python -m pip install requests --disable-pip-version-check --no-warn-script-location
if errorlevel 1 (
    echo ✗ requests failed
    set FAILED_PACKAGES=!FAILED_PACKAGES! requests
    set /a FAILED_COUNT+=1
) else (
    echo ✓ requests installed
)

echo Installing ultralytics ^(YOLOv8 - this may take a while^)...
python -m pip install ultralytics --disable-pip-version-check --no-warn-script-location
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
    echo 4. Install manually with: .venv\Scripts\python.exe -m pip install [package_name]
    echo.
    echo IMPORTANT: Do not close this window - scroll up to see actual error messages!
    echo.
    pause
) else (
    echo ✓ All packages installed successfully!
)

echo.
echo [Verification] Testing package imports in virtual environment...
echo This tests if packages work correctly in your venv...
echo.

set VERIFY_FAILED=0

.venv\Scripts\python.exe -c "import mss; print(f'mss v{mss.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ mss import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ mss working
)

.venv\Scripts\python.exe -c "import numpy; print(f'numpy v{numpy.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ numpy import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ numpy working
)

.venv\Scripts\python.exe -c "import cv2; print(f'opencv v{cv2.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ opencv-python import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ opencv-python working
)

.venv\Scripts\python.exe -c "import PIL; print(f'Pillow v{PIL.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ Pillow import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ Pillow working
)

.venv\Scripts\python.exe -c "import pyautogui; print(f'pyautogui v{pyautogui.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ pyautogui import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ pyautogui working
)

.venv\Scripts\python.exe -c "import pydirectinput; print(f'pydirectinput v{pydirectinput.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ pydirectinput import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ pydirectinput working
)

.venv\Scripts\python.exe -c "import pynput; print(f'pynput v{pynput.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ pynput import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ pynput working
)

.venv\Scripts\python.exe -c "from PySide6 import __version__; print(f'PySide6 v{__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ PySide6 import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ PySide6 working
)

.venv\Scripts\python.exe -c "import requests; print(f'requests v{requests.__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ requests import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ requests working
)

.venv\Scripts\python.exe -c "from ultralytics import __version__; print(f'ultralytics v{__version__}')" 2>nul
if errorlevel 1 (
    echo ✗ ultralytics import failed - Package not properly installed in venv
    set VERIFY_FAILED=1
) else (
    echo ✓ ultralytics working
)

echo.
if !VERIFY_FAILED! EQU 1 (
    echo ========================================
    echo   ⚠️ INSTALLATION INCOMPLETE!
    echo ========================================
    echo.
    echo Some packages failed to install or import properly.
    echo SantaMacro will NOT work correctly!
    echo.
    echo CRITICAL: Scroll up in this window to see the actual error messages!
    echo.
    echo Common fixes:
    echo 1. Delete the .venv folder and run install.bat again
    echo 2. Run install.bat as Administrator ^(right-click ^> Run as administrator^)
    echo 3. Make sure you're using Python 3.12 or 3.13 ^(not 3.14+^)
    echo 4. Check your internet connection
    echo 5. Try manually: .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    echo If still failing, save this window output and ask for help in Discord!
    echo.
    pause
    exit /b 1
) else (
    echo ========================================
    echo   ✓ ALL PACKAGES VERIFIED!
    echo ========================================
    echo.
    echo All packages installed and working correctly in your virtual environment.
)

echo.
echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo To run SantaMacro:
echo   • Double-click "run.bat" for silent background mode
echo   • Double-click "run_dev.bat" for development with terminal
echo.
echo NEW FEATURES:
echo   • Settings button in overlay for custom attacks
echo   • Discord webhook notifications
echo   • Record your own attack sequences
echo.
echo Press any key to exit...
pause >nul
