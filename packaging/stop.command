#!/usr/bin/env bash
# Finder-friendly stop command for the portable macOS archive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER_PATH="$SCRIPT_DIR/DDT Local Extractor.app/Contents/Resources/ddt-local-runner"

xattr -dr com.apple.quarantine "$SCRIPT_DIR" 2>/dev/null || true

if [[ -x "$RUNNER_PATH" ]]; then
    if ! "$RUNNER_PATH" --stop-scheduler; then
        osascript -e 'display alert "DDT Local Extractor" message "Non è stato possibile salvare la disattivazione dell’automazione."' >&2 || true
        exit 1
    fi
else
    # The command remains useful if the app was deleted but this ZIP folder was kept.
    PLIST_PATH="$HOME/Library/LaunchAgents/com.ddt-local-extractor.run.plist"
    launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
fi

osascript -e 'display notification "L’elaborazione automatica è stata disattivata." with title "DDT Local Extractor"'
