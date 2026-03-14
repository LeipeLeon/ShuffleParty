#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import shuffle_party" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -e .
fi

python -m shuffle_party
