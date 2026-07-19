#!/usr/bin/env bash
# Run one local DDT extraction pass on macOS (also usable on Linux/WSL).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${DDT_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python environment not found at $PYTHON_BIN." >&2
    echo "Create it first: python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
fi

cd "$PROJECT_DIR"
exec "$PYTHON_BIN" -m ddt_local run --once "$@"
