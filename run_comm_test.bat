@echo off
setlocal
cd /d "%~dp0"

REM Ensure UTF-8 console output and Python runtime encoding
chcp 65001 >nul 2>&1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

title mBot - Communication Test Tool

echo ======================================================
echo   mBot Robot Football - Communication Test Tool
echo ======================================================
echo.

REM Check for Administrator privileges (recommended for keyboard hook)
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [NOTE] Not running as Administrator.
    echo The 'keyboard' library usually requires Administrator privileges on Windows.
    echo If keys are not detected, close this window and right-click -^> "Run as administrator".
    echo.
)

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
    echo Make sure "Add Python to PATH" is checked during installation.
    echo.
    pause
    exit /b 1
)

REM 2. Create virtual environment if it doesn't exist
if not exist "venv\Scripts\activate.bat" (
    echo [*] Virtual environment not found. Creating .\venv ...
    %PYTHON_CMD% -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

REM 3. Activate virtual environment
call venv\Scripts\activate.bat

REM 4. Install / verify dependencies if needed
if not exist "venv\.deps_installed" (
    if exist "requirements.txt" (
        echo [*] Installing dependencies from requirements.txt...
        python -m pip install --upgrade pip
        python -m pip install -r requirements.txt
        if %ERRORLEVEL% EQU 0 (
            echo Dependencies installed > "venv\.deps_installed"
        ) else (
            echo [WARNING] Some dependencies failed to install.
        )
    )
)

echo.
echo ======================================================
echo   Starting Communication Test Tool...
echo ======================================================
echo.

python communication\comm_test_tool.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Program exited with an error code: %ERRORLEVEL%
    pause
)
