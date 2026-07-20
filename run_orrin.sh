#!/usr/bin/env bash
# run_orrin.sh — start Orrin with auto-restart and macOS sleep prevention
# Usage:  ./run_orrin.sh
# Stop:   Ctrl-C  (or kill the caffeinate + python pids)

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO/.venv"
LOG="$REPO/brain/data/run_log.txt"
CYCLE_SLEEP="${ORRIN_CYCLE_SLEEP:-1}"
RUN_LOCK="${ORRIN_RUN_LOCK:-1}"
RUN_LOCK_SCRIPT="$REPO/scripts/orrin_run_lock.sh"
RUN_LOCK_HELD=0

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

# Build provenance: a life's evidence is only reproducible if the code that ran
# it has a commit hash (Run 9 ran on an uncommitted build and its verdict can
# never name one). Refuse a dirty tree unless explicitly overridden; either way
# the SHA (with a -dirty marker) is exported for the run and stamped in the log.
ORRIN_BUILD_SHA="unknown"
if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    ORRIN_BUILD_SHA="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    DIRTY_COUNT="$(git -C "$REPO" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$DIRTY_COUNT" != "0" ]; then
        if [ "${ORRIN_ALLOW_DIRTY:-0}" != "1" ]; then
            echo "[run] ERROR: working tree has $DIRTY_COUNT uncommitted change(s)." >&2
            echo "[run] A staging life must run on committed code so the verdict can name a build." >&2
            echo "[run] Commit first, or override with ORRIN_ALLOW_DIRTY=1 ./run_orrin.sh" >&2
            exit 4
        fi
        ORRIN_BUILD_SHA="${ORRIN_BUILD_SHA}-dirty"
        echo "[run] WARNING: launching on a dirty tree ($DIRTY_COUNT change(s)) — build stamped ${ORRIN_BUILD_SHA}"
    fi
fi
export ORRIN_BUILD_SHA

echo "[run] Starting Orrin — press Ctrl-C to stop"
echo "[run] Python: $PYTHON"
echo "[run] Log:    $LOG"
echo "[run] Build:  $ORRIN_BUILD_SHA"
echo "[run] Cycle sleep: ${CYCLE_SLEEP}s"
# E3 (Run 11 §8): the lifespan band is consumed only when a FRESH life rolls
# (first boot after reset), so it must be set at launch time or the default
# 1-2yr band silently wins and natural death never lands inside the run.
# Staging value for a ~20k-cycle life at the measured ~4.5 s/cycle: 1.1-1.3.
if [ -n "${ORRIN_LIFESPAN_MIN_DAYS:-}" ] || [ -n "${ORRIN_LIFESPAN_MAX_DAYS:-}" ]; then
    export ORRIN_LIFESPAN_MIN_DAYS ORRIN_LIFESPAN_MAX_DAYS
    echo "[run] Lifespan band: ${ORRIN_LIFESPAN_MIN_DAYS:-default}-${ORRIN_LIFESPAN_MAX_DAYS:-default} days (staged)"
else
    echo "[run] Lifespan band: defaults (1-2yr) — set ORRIN_LIFESPAN_MIN/MAX_DAYS for a staged life"
fi

cleanup() {
    local exit_code=$?
    if [ -n "${CAFF_PID:-}" ]; then
        kill "$CAFF_PID" 2>/dev/null || true
    fi
    if [ "$RUN_LOCK_HELD" -eq 1 ]; then
        "$RUN_LOCK_SCRIPT" unlock >/dev/null || {
            echo "[run] WARNING: run lock cleanup failed; run ./scripts/orrin_run_lock.sh unlock" >&2
        }
    fi
    echo "[run] stopped."
    exit "$exit_code"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Terminal close sends HUP; without this the shell dies trap-less and the run
# lock stays engaged (the 07-18 aborted run left the whole repo r-x).
trap 'exit 129' HUP

if [ "$RUN_LOCK" != "0" ]; then
    if [ ! -x "$RUN_LOCK_SCRIPT" ]; then
        echo "[run] ERROR: run lock helper is missing or not executable: $RUN_LOCK_SCRIPT" >&2
        exit 1
    fi
    echo "[run] Run lock: enabled (disable with ORRIN_RUN_LOCK=0)"
    "$RUN_LOCK_SCRIPT" lock --owner-pid "$$"
    RUN_LOCK_HELD=1
    export PYTHONDONTWRITEBYTECODE="${PYTHONDONTWRITEBYTECODE:-1}"
else
    echo "[run] Run lock: disabled"
fi

# Prevent macOS from sleeping while Orrin runs
caffeinate -i &
CAFF_PID=$!

RESTART_COUNT=0
while true; do
    echo "[run] $(date '+%Y-%m-%d %H:%M:%S') — launch #$RESTART_COUNT (wrapper pid $$, build $ORRIN_BUILD_SHA)" | tee -a "$LOG"
    EXIT_CODE=0
    # pipefail is set, so the pipeline status is python's exit code (tee exits 0);
    # the `||` capture keeps `set -e` from killing the wrapper on a crash.
    ORRIN_CYCLE_SLEEP="$CYCLE_SLEEP" "$PYTHON" main.py 2>&1 | tee -a "$LOG" || EXIT_CODE=$?
    RESTART_COUNT=$((RESTART_COUNT + 1))
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[run] clean exit — not restarting." | tee -a "$LOG"
        break
    fi
    # 130 = SIGINT (Ctrl-C / kill -2), 143 = SIGTERM (kill), 137 = SIGKILL (kill -9).
    # An intentional stop is not a crash: don't resurrect him. main.py turns the
    # catchable ones into a graceful exit 0, but a SIGKILL can't be trapped — the
    # child just dies with 137, and auto-respawning it re-creates the very second
    # process the single-instance lock exists to prevent (the corruption cascade in
    # final_audit_and_shutdown.md). Treat all three as intentional.
    if [ $EXIT_CODE -eq 130 ] || [ $EXIT_CODE -eq 143 ] || [ $EXIT_CODE -eq 137 ]; then
        echo "[run] stopped by signal (exit $EXIT_CODE) — intentional, not restarting." | tee -a "$LOG"
        break
    fi
    # 3 = single-instance lock refused (another Orrin already holds brain/data).
    # Restarting can never succeed while the holder lives — it would busy-respawn
    # forever — so stop and let the user deal with the running instance.
    if [ $EXIT_CODE -eq 3 ]; then
        echo "[run] another Orrin already holds the data lock (exit 3) — not restarting." | tee -a "$LOG"
        break
    fi
    echo "[run] crashed (exit $EXIT_CODE) — restarting in 10s…" | tee -a "$LOG"
    sleep 10
done
