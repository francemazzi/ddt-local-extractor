#!/usr/bin/env bash
# Finder-friendly launcher for the portable macOS archive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/DDT Local Extractor.app"

if [[ ! -d "$APP_PATH" ]]; then
    osascript -e 'display alert "DDT Local Extractor" message "L’app non è presente accanto a start.command. Estrai completamente lo ZIP e riprova."' >&2 || true
    exit 1
fi

open "$APP_PATH"
