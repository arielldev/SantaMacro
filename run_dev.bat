@echo off
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo ================================================
echo  SANTAMACRO - Quick Launcher
echo ================================================
echo.

echo [Checking] Verifying installation...

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERROR: Virtual environment not found!
    echo Please run install.bat first.
    echo.
    pause
    exit /b 1
)

echo Checking required packages...
.venv\Scripts\python.exe -c "import mss, numpy, cv2, PIL, pyautogui, pydirectinput, pynput, PySide6, ultralytics, requests" 2>nul
if errorlevel 1 (
    echo.
    echo ========================================
    echo   ERROR: Missing Required Packages!
    echo ========================================
    echo.
    echo One or more required packages are not installed.
    echo This will cause the macro to spin endlessly or crash.
    echo.
    echo Please run install.bat to install all packages.
    echo.
    pause
    exit /b 1
)

if not exist "Model.pt" (
    echo.
    echo ========================================
    echo   WARNING: Model.pt not found!
    echo ========================================
    echo.
    echo The YOLO detection model is missing.
    echo Santa detection will NOT work without it.
    echo.
    echo Please ensure Model.pt is in the root folder.
    echo.
    pause
)

echo ✓ All checks passed!
echo.
echo Controls:
echo   F1 = START/STOP tracking (toggle)
echo   ESC = EXIT
echo   Settings button in overlay = Open settings GUI
echo.
echo ================================================

.venv\Scripts\python.exe src\main.py

echo.
echo ================================================
echo Macro exited normally
echo ================================================
echo.
echo Press any key to continue . . .
pause > nul
