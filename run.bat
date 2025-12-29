@echo off
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

start "" /B .venv\Scripts\pythonw.exe src\main.py
