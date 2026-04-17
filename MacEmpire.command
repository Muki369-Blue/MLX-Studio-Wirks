#!/bin/bash
# AI Content Empire quick launcher for macOS
# Starts backend (:8800) + frontend (:3000) with Shadow-Wirk connection to Windows PC

set -euo pipefail

EMPIRE_DIR="$(cd "$(dirname "$0")" && pwd)"
SHADOW_WIRKS_URL="http://100.119.54.18:8800"

echo "🚀 Starting AI Content Empire..."
echo "   Project dir : $EMPIRE_DIR"
echo "   Shadow-Wirk : $SHADOW_WIRKS_URL"

# Clear existing app ports if stale processes are hanging around
lsof -ti:8800 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

echo "✓ Ports 8800 and 3000 cleared"

# Start backend in a new Terminal window
osascript <<EOF
tell application "Terminal"
    do script "cd '$EMPIRE_DIR' && source .venv/bin/activate && SHADOW_WIRKS_URL='$SHADOW_WIRKS_URL' python -m uvicorn backend.main:app --host 0.0.0.0 --port 8800 --reload 2>&1"
    set custom title of front window to "Empire - Backend :8800"
    activate
end tell
EOF

sleep 1

# Start frontend in another Terminal window (points at local backend)
osascript <<EOF
tell application "Terminal"
    do script "cd '$EMPIRE_DIR/frontend' && NEXT_PUBLIC_API_URL=http://localhost:8800 npm run dev 2>&1"
    set custom title of front window to "Empire - Frontend :3000"
    activate
end tell
EOF

echo "⏳ Waiting for services to warm up..."
sleep 6

open "http://localhost:3000"

echo "✅ Empire opened at http://localhost:3000"
echo "   Shadow-Wirk (Windows PC) → $SHADOW_WIRKS_URL"