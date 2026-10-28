#!/bin/bash
# Build dist/DupeSort-<version>-macOS.dmg: a disk image with DupeSort.app and a
# shortcut to Applications, so users install by dragging the app across.
#
#   packaging/build_macos.sh            # from the project root
#
# Signing: without a certificate the app is ad-hoc signed and users must
# right-click > Open the first time. Set DEVELOPER_ID="Developer ID Application:
# Your Name (TEAMID)" to sign properly, and also NOTARY_PROFILE=<keychain profile
# made with `xcrun notarytool store-credentials`> to notarize, so it opens with
# no warning.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
VERSION=$("$PY" -c "import dupesort; print(dupesort.__version__)")
ARCH=$(uname -m)
DMG="dist/DupeSort-${VERSION}-macOS-${ARCH}.dmg"

[ -f packaging/icon.icns ] || "$PY" packaging/make_icons.py
"$PY" -m PyInstaller --noconfirm --log-level WARN dupesort.spec

APP=dist/DupeSort.app
if [ -n "${DEVELOPER_ID:-}" ]; then
  codesign --force --deep --options runtime --timestamp --sign "$DEVELOPER_ID" "$APP"
else
  codesign --force --deep --sign - "$APP"
fi
codesign --verify --deep --strict "$APP"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "DupeSort $VERSION" -srcfolder "$STAGE" -fs HFS+ \
  -format UDZO -imagekey zlib-level=9 -ov "$DMG" >/dev/null

if [ -n "${DEVELOPER_ID:-}" ]; then
  codesign --force --sign "$DEVELOPER_ID" --timestamp "$DMG"
  if [ -n "${NOTARY_PROFILE:-}" ]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
  fi
fi
echo "Built $DMG ($(du -h "$DMG" | cut -f1))"
