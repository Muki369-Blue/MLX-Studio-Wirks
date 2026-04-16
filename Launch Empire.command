#!/bin/bash
# AI Content Empire quick launcher for macOS

set -euo pipefail

echo "🚀 Starting AI Content Empire..."

# Clear existing app ports if stale processes are hanging around
lsof -ti:8800 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

echo "✓ Ports 8800 and 3000 cleared"

# Start backend in a new Terminal window
osascript <<'EOF'
tell application "Terminal"
    do script "cd /Users/bluewirks.max/dev/apps/Empire && backend/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8800 --reload 2>&1"
    set custom title of front window to "Empire - Backend :8800"
    activate
end tell
EOF

sleep 1

# Start frontend in another Terminal window
osascript <<'EOF'
tell application "Terminal"
    do script "cd /Users/bluewirks.max/dev/apps/Empire/frontend && npm run dev 2>&1"
    set custom title of front window to "Empire - Frontend :3000"
    activate
end tell
EOF

echo "⏳ Waiting for services to warm up..."
sleep 6

open "http://localhost:3000"

echo "✅ Empire opened at http://localhost:3000"