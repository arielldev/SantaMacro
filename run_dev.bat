@echo off
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

echo ================================================
echo  SANTAMACRO - Quick Launcher
echo ================================================
echo.
echo Controls:
echo   F1 = START/STOP tracking (toggle)
echo   ESC = EXIT
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
