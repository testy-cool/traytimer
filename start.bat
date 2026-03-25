@echo off
cd /d "%~dp0"

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Install uv if missing
uv --version >nul 2>&1
if errorlevel 1 (
    echo Installing uv...
    pip install uv
)

:: Sync dependencies (creates .venv if needed)
uv sync

:: Launch silently (no console window lingers)
start "" /b pythonw -m uv run python timer.py
