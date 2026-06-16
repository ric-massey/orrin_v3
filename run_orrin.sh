#!/usr/bin/env bash
# run_orrin.sh — start Orrin with auto-restart and macOS sleep prevention
# Usage:  ./run_orrin.sh
# Stop:   Ctrl-C  (or kill the caffeinate + python pids)

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO/.venv"
LOG="$REPO/brain/data/run_log.txt"
CYCLE_SLEEP="${ORRIN_CYCLE_SLEEP:-1}"

# Dual-process (dual_process_loop.md Phase 5): run the Executive as a continuous
# background daemon by default — goal steps advance every ~7s, decoupled from the
# cognitive cycle, freeing the conscious slot. It's LLM-free (symbolic planning),
# procedural-only (no code-writing/speech/deletion off-thread), and affect-complete.
# Disable with: ORRIN_EXECUTIVE_DAEMON=0 ./run_orrin.sh
export ORRIN_EXECUTIVE_DAEMON="${ORRIN_EXECUTIVE_DAEMON:-1}"

cd "$REPO"

if [ -f "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo "[run] ERROR: no python found" >&2
    exit 1
fi

echo "[run] Starting Orrin — press Ctrl-C to stop"
echo "[run] Python: $PYTHON"
echo "[run] Log:    $LOG"
echo "[run] Cycle sleep: ${CYCLE_SLEEP}s"

# Prevent macOS from sleeping while Orrin runs
caffeinate -i &
CAFF_PID=$!
trap "kill $CAFF_PID 2>/dev/null; echo '[run] stopped.'" EXIT INT TERM

RESTART_COUNT=0
while true; do
    echo "[run] $(date '+%Y-%m-%d %H:%M:%S') — launch #$RESTART_COUNT (wrapper pid $$)" | tee -a "$LOG"
    EXIT_CODE=0
    # pipefail is set, so the pipeline status is python's exit code (tee exits 0);
    # the `||` capture keeps `set -e` from killing the wrapper on a crash.
    ORRIN_CYCLE_SLEEP="$CYCLE_SLEEP" "$PYTHON" main.py 2>&1 | tee -a "$LOG" || EXIT_CODE=$?
    RESTART_COUNT=$((RESTART_COUNT + 1))
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[run] clean exit — not restarting." | tee -a "$LOG"
        break
    fi
    # 130 = SIGINT (Ctrl-C / kill -2), 143 = SIGTERM (kill). An intentional stop is
    # not a crash: don't resurrect him. main.py now turns these into a graceful
    # exit 0, but if one ever escapes ungracefully we still must not auto-restart.
    if [ $EXIT_CODE -eq 130 ] || [ $EXIT_CODE -eq 143 ]; then
        echo "[run] stopped by signal (exit $EXIT_CODE) — intentional, not restarting." | tee -a "$LOG"
        break
    fi
    echo "[run] crashed (exit $EXIT_CODE) — restarting in 10s…" | tee -a "$LOG"
    sleep 10
done
