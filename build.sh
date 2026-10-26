#!/usr/bin/env bash
set -euo pipefail

APP_PATH="dist/GestOne.app"
ZIP_PATH="dist/GestOne-macOS.zip"
DMG_PATH="dist/GestOne-macOS.dmg"
APP_NAME="GestOne"
PRIMARY_BUNDLE_ID="com.gestone.macapp"

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "error: required command not found: $1" >&2
        exit 1
    fi
}

notarize_file() {
    local path="$1"
    if [[ -z "${APPLE_NOTARY_PROFILE:-}" ]]; then
        return 0
    fi

    echo "==> Submitting for notarization: ${path}"
    xcrun notarytool submit "${path}" \
        --keychain-profile "${APPLE_NOTARY_PROFILE}" \
        --wait

    echo "==> Stapling notarization ticket to app bundle..."
    xcrun stapler staple "${APP_PATH}"
}

package_zip() {
    echo "==> Creating release zip..."
    /usr/bin/ditto -c -k --keepParent "${APP_PATH}" "${ZIP_PATH}"
}

package_dmg() {
    echo "==> Creating release dmg..."
    rm -f "${DMG_PATH}"
    hdiutil create -volname "${APP_NAME}" -srcfolder "${APP_PATH}" -ov -format UDZO "${DMG_PATH}" >/dev/null
}

if [[ -f ".venv/bin/activate" ]]; then
    # Build from the project venv so PyInstaller sees the pinned dependencies.
    source .venv/bin/activate
fi

require_cmd pyinstaller

echo "==> Cleaning previous build..."
rm -rf build dist

echo "==> Running PyInstaller..."
pyinstaller GestOne.spec --clean

if [[ -n "${APPLE_DEVELOPER_IDENTITY:-}" ]]; then
    require_cmd codesign
    echo "==> Signing with Developer ID..."
    codesign --force --deep --options runtime \
        --timestamp \
        --entitlements entitlements.plist \
        --sign "${APPLE_DEVELOPER_IDENTITY}" \
        "${APP_PATH}"
else
    echo "==> Skipping release signing"
    echo "    Local build only. For public distribution, set APPLE_DEVELOPER_IDENTITY."
fi

package_zip
package_dmg

if [[ -n "${APPLE_DEVELOPER_IDENTITY:-}" ]]; then
    if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
        require_cmd xcrun
        notarize_file "${ZIP_PATH}"
        notarize_file "${DMG_PATH}"
        echo "==> Validating Gatekeeper assessment..."
        spctl -a -vv --type exec "${APP_PATH}"
    else
        echo "==> Skipping notarization"
        echo "    For public distribution, set APPLE_NOTARY_PROFILE."
    fi
fi

echo ""
echo "✓ Build complete: ${APP_PATH}"
echo "  Zip: ${ZIP_PATH}"
echo "  Dmg: ${DMG_PATH}"
echo "  Open it with: open ${APP_PATH}"
echo ""
echo "Release env vars:"
echo "  APPLE_DEVELOPER_IDENTITY = Developer ID Application certificate name"
echo "  APPLE_NOTARY_PROFILE    = xcrun notarytool keychain profile name"
