@echo off
rem Bear Code launcher (double-click to run)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Please create the virtual environment first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m agents.main

pause
