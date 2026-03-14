#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import pygame, pythonosc" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install pygame-ce python-osc xair-api
fi

python main.py
