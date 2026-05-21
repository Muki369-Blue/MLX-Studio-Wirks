#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS_DIR="$ROOT_DIR/assets"
ICONSET_DIR="$ASSETS_DIR/MLX-Moxy-Wirks.iconset"
ICNS_PATH="$ASSETS_DIR/MLX-Moxy-Wirks.icns"
SPEC_PATH="$ROOT_DIR/MLX-Moxy-Wirks.spec"

cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  echo "Missing .venv in project root."
  exit 1
fi

source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
python -m pip install pyinstaller >/dev/null

mkdir -p "$ASSETS_DIR"

node scripts/generate_macos_icon.mjs

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

if [[ ! -f "$SPEC_PATH" ]]; then
  echo "Missing PyInstaller spec: $SPEC_PATH"
  exit 1
fi

rm -rf build dist

pyinstaller "$SPEC_PATH"

echo "Built app: $ROOT_DIR/dist/MLX-Moxy-Wirks.app"
