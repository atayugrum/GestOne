#!/usr/bin/env bash
set -euo pipefail

APP_PATH="dist/GestOne.app"

if [[ -f ".venv/bin/activate" ]]; then
    # Build from the project venv so PyInstaller sees the pinned dependencies.
    source .venv/bin/activate
fi

echo "==> Cleaning previous build..."
rm -rf build dist

echo "==> Running PyInstaller..."
pyinstaller GestOne.spec --clean

if [[ -n "${APPLE_DEVELOPER_IDENTITY:-}" ]]; then
    echo "==> Signing with Developer ID..."
    codesign --force --deep --options runtime \
        --entitlements entitlements.plist \
        --sign "${APPLE_DEVELOPER_IDENTITY}" \
        "${APP_PATH}"
else
    echo "==> Skipping release signing"
    echo "    Local build only. For public distribution, set APPLE_DEVELOPER_IDENTITY."
fi

echo ""
echo "✓ Build complete: ${APP_PATH}"
echo "  Open it with: open ${APP_PATH}"
