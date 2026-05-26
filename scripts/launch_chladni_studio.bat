@echo off
setlocal

rem Double-click launcher for Chladni Studio.
set "PROJECT_DIR=%~dp0.."
set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"

cd /d "%PROJECT_DIR%"

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -m src.main target-ui --port 8765 %*
) else (
    python -m src.main target-ui --port 8765 %*
)

if errorlevel 1 pause
