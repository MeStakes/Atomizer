#!/usr/bin/env bash
#
# Build a lightweight macOS Atomizer.app launcher and install it to /Applications
# (or ~/Applications if /Applications isn't writable).
#
# The .app is a thin launcher: it runs this repo's venv with `python -m
# atomizer.main`. It does NOT bundle Python/deps, so the repo + venv must stay in
# place (run ./setup.sh first). Re-run this script if you move the project.
#
# Usage:  ./scripts/make_app.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="Atomizer"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
ICNS="$PROJECT_DIR/assets/Atomizer.icns"

if [[ ! -x "$VENV_PY" ]]; then
  echo "!! venv not found at $VENV_PY — run ./setup.sh first." >&2
  exit 1
fi

# Choose an install location that doesn't need sudo when possible.
if [[ -w /Applications ]]; then
  DEST="/Applications"
else
  DEST="$HOME/Applications"
  mkdir -p "$DEST"
fi
APP="$DEST/$APP_NAME.app"

echo "==> Building $APP"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# --- Info.plist ---
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Atomizer</string>
    <key>CFBundleDisplayName</key><string>Atomizer</string>
    <key>CFBundleExecutable</key><string>Atomizer</string>
    <key>CFBundleIconFile</key><string>Atomizer</string>
    <key>CFBundleIdentifier</key><string>com.mestakes.atomizer</string>
    <key>CFBundleVersion</key><string>0.1.0</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSApplicationCategoryType</key><string>public.app-category.music</string>
</dict>
</plist>
PLIST

# --- launcher executable ---
# Finder-launched apps get a minimal PATH, so add Homebrew (ffmpeg lives there).
cat > "$APP/Contents/MacOS/$APP_NAME" <<LAUNCH
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
cd "$PROJECT_DIR" || exit 1
exec "$VENV_PY" -m atomizer.main
LAUNCH
chmod +x "$APP/Contents/MacOS/$APP_NAME"

# --- icon ---
if [[ -f "$ICNS" ]]; then
  cp "$ICNS" "$APP/Contents/Resources/$APP_NAME.icns"
else
  echo "!! $ICNS not found — app will use a generic icon."
fi

# Nudge Finder/LaunchServices to pick up the new bundle + icon.
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true

echo "==> Installed: $APP"
echo "    Launch it from Launchpad / Spotlight / $DEST, or:  open \"$APP\""
