# brain/utils/heartbeat.py
#
# Liveness heartbeat + silent-death detection — F8 (2026-07-05 findings).
#
# THE PROBLEM IT SOLVES. Segment 1 of the 2026-07-05 life died mid-run (lid
# close under `caffeinate -i`, SIGKILL — no shutdown lines) and nothing noticed
# for ~10 hours. The heartbeat stamps `last_alive` roughly once a minute while
# the loop runs; a clean shutdown marks itself; at the next boot,
# check_silent_death() compares the gap and, when the last life ended without a
# shutdown record, writes a first-class `silent_death` event to
# lifecycle_events.jsonl — unexplained deaths become data, not a mystery in the
# run log.
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

HEARTBEAT_FILE = DATA_DIR / "heartbeat.json"
LIFECYCLE_EVENTS_FILE = DATA_DIR / "lifecycle_events.jsonl"

# Stamp cadence and the gap past which an unmarked death counts as silent.
_BEAT_INTERVAL_S = 60.0
SILENT_DEATH_GAP_S = 300.0

_last_beat: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def beat(cycle: Optional[int] = None) -> None:
    """Stamp liveness (throttled to ~1/min — safe to call every cycle)."""
    global _last_beat
    now = time.time()
    if now - _last_beat < _BEAT_INTERVAL_S:
        return
    _last_beat = now
    try:
        save_json(HEARTBEAT_FILE, {
            "ts": now,
            "iso": _now_iso(),
            "cycle": cycle,
            "clean_shutdown": False,
        })
    except Exception as exc:
        record_failure("heartbeat.beat", exc)


def mark_clean_shutdown() -> None:
    """Record that this run is ending on purpose (SIGTERM/KeyboardInterrupt/
    lifespan end) — the next boot must not read the gap as a silent death."""
    try:
        d = load_json(HEARTBEAT_FILE, default_type=dict) or {}
        d.update({"ts": time.time(), "iso": _now_iso(), "clean_shutdown": True})
        save_json(HEARTBEAT_FILE, d)
    except Exception as exc:
        record_failure("heartbeat.mark_clean_shutdown", exc)


def _append_event(event: Dict[str, Any]) -> None:
    try:
        LIFECYCLE_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LIFECYCLE_EVENTS_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError as exc:
        record_failure("heartbeat._append_event", exc)


def check_silent_death() -> Optional[Dict[str, Any]]:
    """Boot-time check: did the previous run end without a shutdown record?
    Returns the recorded event (or None). Resets the heartbeat either way so
    one gap is never reported twice."""
    try:
        d = load_json(HEARTBEAT_FILE, default_type=dict) or {}
    except Exception as exc:
        record_failure("heartbeat.check_silent_death", exc)
        return None
    last_ts = float(d.get("ts") or 0.0)
    event: Optional[Dict[str, Any]] = None
    gap = time.time() - last_ts if last_ts else 0.0
    if last_ts and not d.get("clean_shutdown") and gap > SILENT_DEATH_GAP_S:
        event = {
            "event": "silent_death",
            "gap_s": round(gap, 1),
            "last_alive": d.get("iso"),
            "last_cycle": d.get("cycle"),
            "detected_at": _now_iso(),
        }
        _append_event(event)
        log_activity(
            f"[lifecycle] SILENT DEATH detected: last alive {d.get('iso')} "
            f"(~{gap / 3600.0:.1f} h ago, cycle {d.get('cycle')}), no shutdown record."
        )
    # Fresh run starts with a fresh heartbeat regardless.
    try:
        save_json(HEARTBEAT_FILE, {
            "ts": time.time(), "iso": _now_iso(), "cycle": None,
            "clean_shutdown": False,
        })
    except Exception as exc:
        record_failure("heartbeat.check_silent_death.reset", exc)
    return event
