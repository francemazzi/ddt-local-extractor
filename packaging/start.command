#!/usr/bin/env bash
# Finder-friendly launcher for the portable macOS archive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/DDT Local Extractor.app"

if [[ ! -d "$APP_PATH" ]]; then
    osascript -e 'display alert "DDT Local Extractor" message "L’app non è presente accanto a start.command. Estrai completamente lo ZIP e riprova."' >&2 || true
    exit 1
fi

# macOS marks every executable extracted from an internet ZIP as quarantined.
# The user explicitly authorises this launcher once via Finder → ctrl-click →
# Apri; after that, clear that download marker from this self-contained package
# so later launches are plain double-clicks and the bundled app can open too.
xattr -dr com.apple.quarantine "$SCRIPT_DIR" 2>/dev/null || true

open "$APP_PATH"
