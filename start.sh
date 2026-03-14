#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

if ! command -v uv &>/dev/null; then
    echo "Error: uv not found. Install with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if ! uv run python -c "import tkinter" 2>/dev/null; then
    echo "Error: tkinter not found."
    echo "  macOS:         brew install python-tk@3.14"
    echo "  Debian/RPi:    sudo apt install python3-tk"
    exit 1
fi

uv run python -m shuffle_party
