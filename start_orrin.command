#!/bin/bash
cd "$(dirname "$0")"

LOCK="brain/data/.orrin.instance.lock"

# If the lock exists but no Python process owns it, it's stale — clear it.
if [ -f "$LOCK" ]; then
    LOCK_PID=$(cat "$LOCK" 2>/dev/null)
    if [ -z "$LOCK_PID" ] || ! kill -0 "$LOCK_PID" 2>/dev/null; then
        echo "[start] Stale lock detected (PID ${LOCK_PID:-empty}) — clearing it."
        rm -f "$LOCK"
    fi
fi

# Allow the Tailscale Funnel origin for REST API CORS
ORRIN_UI_DEV=1 \
ORRIN_EXTRA_ORIGINS="https://rics-macbook-air.tail78b69e.ts.net" \
./run_orrin.sh
