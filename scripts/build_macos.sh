#!/usr/bin/env bash
# Build a portable macOS ZIP. Run on macOS with Tcl/Tk and PyInstaller.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="${VERSION:-1.0.0}"
BUILD_LABEL="${BUILD_LABEL:-macOS}"
DIST_DIR="$PROJECT_DIR/dist"
APP_NAME="DDT Local Extractor"
APP_PATH="$DIST_DIR/$APP_NAME.app"
PACKAGE_NAME="DDT-Local-Extractor-$VERSION-$BUILD_LABEL"
PACKAGE_DIR="$DIST_DIR/$PACKAGE_NAME"
ARCHIVE_PATH="$DIST_DIR/$PACKAGE_NAME.zip"

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

# PyInstaller seals the app before the invisible scheduler runner is copied into
# Resources. Seal it again so macOS sees a coherent application bundle.
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"
cp -R "$APP_PATH" "$PACKAGE_DIR/"
cp "$PROJECT_DIR/packaging/start.command" "$PACKAGE_DIR/start.command"
cp "$PROJECT_DIR/packaging/start.sh" "$PACKAGE_DIR/start.sh"
cp "$PROJECT_DIR/packaging/stop.command" "$PACKAGE_DIR/stop.command"
cp "$PROJECT_DIR/packaging/LEGGIMI.txt" "$PACKAGE_DIR/LEGGIMI.txt"
chmod +x "$PACKAGE_DIR/start.command" "$PACKAGE_DIR/start.sh" "$PACKAGE_DIR/stop.command"

rm -f "$ARCHIVE_PATH"
ditto -c -k --sequesterRsrc --keepParent "$PACKAGE_DIR" "$ARCHIVE_PATH"

echo "Created $ARCHIVE_PATH"
