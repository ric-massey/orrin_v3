#!/bin/bash
# tailscale_funnel.command — expose Orrin via Tailscale Funnel
#
# Architecture: Funnel → HTTPS:443 → backend:8800
# The backend serves the built React UI from frontend/dist/ AND handles
# WebSocket at /ws/telemetry. The built UI uses window.location.host so
# WebSocket connects to the same Tailscale domain automatically.
#
# No Vite proxy needed. No .env.local overrides needed.

cd "$(dirname "$0")"

# ── Find the Tailscale CLI ──────────────────────────────────────────────────
TS=""
for candidate in \
    /Applications/Tailscale.app/Contents/MacOS/Tailscale \
    /usr/local/bin/tailscale \
    /usr/bin/tailscale \
    "$(which tailscale 2>/dev/null)"; do
    if [ -x "$candidate" ]; then
        TS="$candidate"
        break
    fi
done

if [ -z "$TS" ]; then
    echo "ERROR: Tailscale CLI not found."
    read -r -p "Press Enter to exit..."
    exit 1
fi

echo "[funnel] Tailscale: $TS"
"$TS" status 2>&1 | head -3
echo ""

# ── Remove stale .env.local (it causes wrong WS URL in Vite dev) ──────────
if [ -f frontend/.env.local ] && grep -q VITE_TELEMETRY_WS frontend/.env.local; then
    echo "[funnel] Removing stale frontend/.env.local"
    rm -f frontend/.env.local
fi

# ── Reset any stale serve config ──────────────────────────────────────────
echo "[funnel] Resetting existing serve config..."
"$TS" serve reset 2>/dev/null || true

# ── Expose backend on port 443 ────────────────────────────────────────────
# The backend (port 8800) serves:
#   GET /*           → frontend/dist/ (built React UI)
#   GET /api/*       → REST endpoints
#   WS  /ws/telemetry → WebSocket stream
echo "[funnel] Exposing backend:8800 on HTTPS:443..."
"$TS" funnel --bg 8800 2>&1

# ── Show result ────────────────────────────────────────────────────────────
echo ""
"$TS" serve status 2>/dev/null || true
echo ""

FUNNEL_URL=$("$TS" funnel status 2>/dev/null | grep -oE 'https://[a-z0-9._:-]+\.ts\.net[^ ]*' | head -1)
if [ -z "$FUNNEL_URL" ]; then
    FUNNEL_URL="https://rics-macbook-air.tail78b69e.ts.net"
fi

echo ""
echo "========================================"
echo "  ORRIN REMOTE ACCESS"
echo "  ${FUNNEL_URL}/brain"
echo ""
echo "  /* → backend:8800 (UI + API + WebSocket)"
echo "========================================"
echo ""
echo "Funnel is running in the background."
echo "To stop: tailscale serve reset"
echo ""
read -r -p "Press Enter to exit (funnel keeps running)..."
