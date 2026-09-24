@echo off
cd /d "%~dp0"
python save_diff.py
if errorlevel 1 pause
