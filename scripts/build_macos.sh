#!/usr/bin/env bash
# Build an unsigned macOS .app and DMG. Run on macOS with Tcl/Tk and PyInstaller.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="${VERSION:-1.0.0}"
BUILD_LABEL="${BUILD_LABEL:-macOS}"
DIST_DIR="$PROJECT_DIR/dist"
APP_NAME="DDT Local Extractor"
APP_PATH="$DIST_DIR/$APP_NAME.app"

cd "$PROJECT_DIR"
"$PYTHON_BIN" -c "import tkinter" || {
    echo "This build Python needs Tcl/Tk (python.org Python for macOS includes it)." >&2
    exit 1
}
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --paths src --exclude-module nltk --windowed \
    --name "$APP_NAME" src/ddt_local/desktop_gui.py
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --paths src --exclude-module nltk --onefile \
    --name ddt-local-runner src/ddt_local/desktop_runner.py

mkdir -p "$APP_PATH/Contents/Resources"
cp "$DIST_DIR/ddt-local-runner" "$APP_PATH/Contents/Resources/ddt-local-runner"
chmod +x "$APP_PATH/Contents/Resources/ddt-local-runner"

STAGING_DIR="$DIST_DIR/dmg-staging"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov \
    -format UDZO "$DIST_DIR/DDT-Local-Extractor-$VERSION-$BUILD_LABEL.dmg"

echo "Created $DIST_DIR/DDT-Local-Extractor-$VERSION-$BUILD_LABEL.dmg"
