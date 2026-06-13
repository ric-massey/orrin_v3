#!/bin/bash
cd "$(dirname "$0")"

# Single-tunnel remote access (UI_FIXES Fix 5): the Vite dev server proxies BOTH
# /ws (telemetry WebSocket) and /api (all REST endpoints) to the backend on 8800,
# and the frontend derives both URLs from the page origin when no env override is
# set. So one tunnel — the UI one — carries everything. No .env.local needed.

# Find the Vite port (highest node/vite listener)
VITE_PORT=$(lsof -iTCP -sTCP:LISTEN -P 2>/dev/null | grep -E "node|vite" | grep -oE ':\d+' | tr -d ':' | sort -n | tail -1)
VITE_PORT=${VITE_PORT:-5174}
echo "[tunnel] Vite on port $VITE_PORT (proxies /ws + /api to the backend on 8800)"

# A stale .env.local from the old two-tunnel flow would pin the WS to a dead URL.
if [ -f frontend/.env.local ] && grep -q VITE_TELEMETRY_WS frontend/.env.local; then
    echo "[tunnel] Removing stale frontend/.env.local (old two-tunnel WS pin)"
    rm -f frontend/.env.local
fi

echo "[tunnel] Starting UI tunnel (port $VITE_PORT)..."
UI_URL_FILE="/tmp/orrin_ui_url.txt"
rm -f "$UI_URL_FILE"
npx --yes localtunnel --port "$VITE_PORT" 2>&1 | tee "$UI_URL_FILE" &
UI_PID=$!

# Wait for UI tunnel URL
for i in $(seq 1 20); do
    UI_URL=$(grep -oE 'https://[a-z0-9-]+\.loca\.lt' "$UI_URL_FILE" 2>/dev/null | head -1)
    [ -n "$UI_URL" ] && break
    sleep 1
done

echo ""
echo "========================================"
echo "  ORRIN REMOTE ACCESS"
echo "  Open on your phone:"
echo "  ${UI_URL}/brain"
echo "  (WS + REST both ride this one tunnel)"
echo "  NOTE: the tunnel URL is the only secret —"
echo "  anyone holding it can read the dashboard."
echo "========================================"
echo ""

# Keep running until Ctrl-C
trap "kill $UI_PID 2>/dev/null; echo 'Tunnel closed.'" EXIT INT TERM
wait
