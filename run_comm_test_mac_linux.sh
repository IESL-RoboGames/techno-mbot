#!/usr/bin/env bash
# ======================================================
#   mBot Robot Football - Communication Test Tool
#   (macOS / Linux)
# ======================================================

set -e
cd "$(dirname "$0")"

echo "======================================================"
echo "  mBot Robot Football - Communication Test Tool"
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
    echo "Please install Python 3.9 - 3.11."
    exit 1
fi

# 2. Create virtual environment if it doesn't exist
if [ ! -f "venv/bin/activate" ]; then
    echo "[*] Virtual environment not found. Creating ./venv ..."
    $PYTHON_CMD -m venv venv
    echo "✔ [OK] Virtual environment created."
fi

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install dependencies if needed
if [ ! -f "venv/.deps_installed" ]; then
    if [ -f "requirements.txt" ]; then
        echo "[*] Installing dependencies from requirements.txt..."
        python -m pip install --upgrade pip
        python -m pip install -r requirements.txt
        touch venv/.deps_installed
    fi
fi

echo ""
echo "======================================================"
echo "  Starting Communication Test Tool..."
echo "======================================================"
echo ""

python communication/comm_test_tool.py
