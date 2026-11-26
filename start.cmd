@echo off
setlocal
cd /d "%~dp0"
if exist "build\python-deps\pyocd" set "PYTHONPATH=%CD%\build\python-deps"
python src\main.py
if errorlevel 1 pause
