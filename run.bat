@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [error] Virtual environment not found.
    echo Run these once from this folder:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py %*
echo.
echo App exited.
pause
