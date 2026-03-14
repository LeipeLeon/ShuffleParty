#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import tkinter" 2>/dev/null; then
    echo "Error: tkinter not found."
    echo "  macOS:         brew install python-tk@3.14"
    echo "  Debian/RPi:    sudo apt install python3-tk"
    exit 1
fi

if ! python -c "import shuffle_party" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -e .
fi

python -m shuffle_party
