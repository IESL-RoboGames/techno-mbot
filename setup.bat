@echo off
setlocal

REM Ensure UTF-8 console output and Python runtime encoding
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"

echo ======================================================
echo   mBot Robot Football - Python Environment Setup
echo ======================================================
echo.

REM 1. Detect Python executable
set "PYTHON_CMD="
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 set "PYTHON_CMD=python"
if "%PYTHON_CMD%"=="" (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_CMD=py"
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found on your system PATH!
    echo Please install Python 3.9 - 3.11 from https://www.python.org/downloads/
    echo Make sure Add Python to PATH is checked during installation.
    echo.
    pause
    exit /b 1
)

REM 2. Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment in .\venv ...
    %PYTHON_CMD% -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Existing virtual environment found.
)

REM 3. Activate venv and install dependencies
call venv\Scripts\activate.bat

if exist "requirements.txt" (
    echo [*] Installing / verifying dependencies from requirements.txt...
    python -m pip install -r requirements.txt
)

echo.
echo ======================================================
echo   Environment ready! Terminal is now open in (venv).
echo ======================================================
echo.

REM 4. Keep terminal open with activated venv
cmd /k
