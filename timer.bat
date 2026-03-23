@echo off
cd /d "%~dp0"
start /b "" pythonw -m uv run python timer.py
