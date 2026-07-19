#!/usr/bin/env bash
# Advanced developer helper. Desktop users activate scheduling in the graphical wizard.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${DDT_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python environment not found at $PYTHON_BIN." >&2
    exit 1
fi

case "${1:-}" in
    "")
        exec "$PYTHON_BIN" -m ddt_local scheduler install
        ;;
    --uninstall)
        exec "$PYTHON_BIN" -m ddt_local scheduler remove
        ;;
    --dry-run)
        echo "The desktop scheduler will run: $PYTHON_BIN -m ddt_local.desktop_runner --run-once"
        echo "The selected folder is read from the desktop configuration (or DDT_HOME if set)."
        ;;
    -h|--help)
        echo "Usage: $0 [--dry-run | --uninstall]"
        ;;
    *)
        echo "Usage: $0 [--dry-run | --uninstall]" >&2
        exit 2
        ;;
esac
