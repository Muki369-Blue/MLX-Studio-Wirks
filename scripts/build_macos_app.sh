#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS_DIR="$ROOT_DIR/assets"
ICONSET_DIR="$ASSETS_DIR/MLX-Moxy-Wirks.iconset"
ICNS_PATH="$ASSETS_DIR/MLX-Moxy-Wirks.icns"
HELPER_SPEC_PATH="$ROOT_DIR/MLX-Moxy-Wirks-Backend.spec"
MACOS_DIR="$ROOT_DIR/macos"
APP_PATH="$ROOT_DIR/dist/MLX-Moxy-Wirks.app"
PYINSTALLER_VERSION="${PYINSTALLER_VERSION:-6.20.0}"

cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  echo "Missing .venv in project root."
  exit 1
fi

source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
python -m pip install "pyinstaller==$PYINSTALLER_VERSION" >/dev/null

mkdir -p "$ASSETS_DIR"

node scripts/generate_macos_icon.mjs

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

if [[ ! -f "$HELPER_SPEC_PATH" ]]; then
  echo "Missing PyInstaller helper spec: $HELPER_SPEC_PATH"
  exit 1
fi

rm -rf build
mkdir -p dist
chmod -R u+w dist 2>/dev/null || true
find dist -mindepth 1 -maxdepth 1 -exec rm -rf {} +

pyinstaller "$HELPER_SPEC_PATH"

swift build --package-path "$MACOS_DIR" -c release

mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"
cp "$MACOS_DIR/.build/release/MLX-Moxy-Wirks" "$APP_PATH/Contents/MacOS/MLX-Moxy-Wirks"
cp "$MACOS_DIR/Info.plist" "$APP_PATH/Contents/Info.plist"
cp "$ICNS_PATH" "$APP_PATH/Contents/Resources/MLX-Moxy-Wirks.icns"
cp -R "$ROOT_DIR/dist/MLX-Moxy-Wirks-Backend" "$APP_PATH/Contents/Resources/Backend"

chmod +x "$APP_PATH/Contents/MacOS/MLX-Moxy-Wirks"
chmod +x "$APP_PATH/Contents/Resources/Backend/MLX-Moxy-Wirks-Backend"

echo "Built app: $APP_PATH"
