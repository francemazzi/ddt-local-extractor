#!/usr/bin/env bash
# Install a per-user launchd agent that runs the queue job every five minutes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.ddt-local-extractor.run"
PLIST_PATH="${DDT_LAUNCHD_PLIST:-$HOME/Library/LaunchAgents/$LABEL.plist}"
DDT_HOME_PATH="${DDT_HOME:-$HOME/DDT}"
RUN_SCRIPT="$SCRIPT_DIR/run_macos.sh"

usage() {
    echo "Usage: $0 [--dry-run | --uninstall]"
}

write_plist() {
    PLIST_PATH="$1" PROJECT_DIR="$PROJECT_DIR" LABEL="$LABEL" DDT_HOME_PATH="$DDT_HOME_PATH" \
        RUN_SCRIPT="$RUN_SCRIPT" python3 - <<'PY'
import os
import plistlib
import sys

payload = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": [os.environ["RUN_SCRIPT"]],
    "WorkingDirectory": os.environ["PROJECT_DIR"],
    "RunAtLoad": True,
    "StartInterval": 300,
    "EnvironmentVariables": {"DDT_HOME": os.environ["DDT_HOME_PATH"]},
    "StandardOutPath": os.path.join(os.environ["DDT_HOME_PATH"], "logs", "launchd.out.log"),
    "StandardErrorPath": os.path.join(os.environ["DDT_HOME_PATH"], "logs", "launchd.err.log"),
}
plistlib.dump(payload, sys.stdout.buffer, sort_keys=False)
PY
}

case "${1:-}" in
    "")
        ;;
    --dry-run)
        write_plist -
        exit 0
        ;;
    --uninstall)
        launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
        rm -f "$PLIST_PATH"
        echo "Removed launchd agent $LABEL"
        exit 0
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

mkdir -p "$(dirname "$PLIST_PATH")" "$DDT_HOME_PATH/logs"
write_plist "$PLIST_PATH" > "$PLIST_PATH"
plutil -lint "$PLIST_PATH" >/dev/null

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL. It runs every 5 minutes and at login."
echo "Plist: $PLIST_PATH"
