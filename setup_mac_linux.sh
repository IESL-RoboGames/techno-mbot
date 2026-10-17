#!/usr/bin/env bash
# ======================================================
#   mBot Robot Football - Python Environment Setup
#   (macOS / Linux)
# ======================================================

set -e
cd "$(dirname "$0")"

echo "======================================================"
echo "  mBot Robot Football - Python Environment Setup"
echo "======================================================"
echo ""

# 1. Detect Python 3 executable
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    if python -c 'import sys; exit(0 if sys.version_info.major == 3 else 1)' &>/dev/null; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ [ERROR] Python 3 was not found on your system PATH!"
    echo "Please install Python 3.9 - 3.11:"
    echo "  - Linux (Ubuntu/Debian): sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "  - macOS: brew install python@3.11"
    exit 1
fi

echo "✔ Detected Python: $($PYTHON_CMD --version) at $(which $PYTHON_CMD)"

# 2. Create virtual environment if it doesn't exist
if [ ! -f "venv/bin/activate" ]; then
    echo "[*] Creating virtual environment in ./venv ..."
    $PYTHON_CMD -m venv venv
    echo "✔ [OK] Virtual environment created."
else
    echo "✔ [OK] Existing virtual environment found."
fi

# 3. Activate venv and install dependencies
source venv/bin/activate

if [ -f "requirements.txt" ]; then
    echo "[*] Upgrading pip & installing dependencies from requirements.txt..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    touch venv/.deps_installed
fi

echo ""
echo "======================================================"
echo "  Environment ready!"
echo "  To activate in your current terminal, run:"
echo "    source venv/bin/activate"
echo "======================================================"
echo ""

# 4. Spawn a new shell with active venv if run directly
if [ -n "$SHELL" ]; then
    exec "$SHELL"
fi
