"""
utils/lifecycle.py — telling death, stall/crash, and a normal run apart (§10.5).

These three otherwise look identical ("the process stopped"), and the wake-up screen
(§9.7) / Death Screen (§10.4) depend on distinguishing them:

  • death        — mortality recorded the deadline reached + final thoughts written.
  • interrupted  — the previous run did NOT shut down cleanly (a crash, or a reaper
                   stall-restart). We tag it from a clean-shutdown marker.
  • alive        — a clean, normal run.

A tiny `runstate.json` marker carries the clean/unclean bit across restarts: set
unclean while running, flipped to clean on graceful shutdown. If the next boot sees an
unclean marker (and Orrin isn't dead), the prior run was interrupted.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from paths import DATA_DIR

_RUNSTATE = DATA_DIR / "runstate.json"

# Captured at import-time read in mark_running(), BEFORE we overwrite the marker — so
# status() can report how the PREVIOUS run ended:
#   clean  → graceful shutdown    → "alive"
#   reaper → a watchdog stall/kill (Reaper.trigger) → "stalled" (it restarts)
#   neither → an unclean exit with no reaper trip    → "crashed"
_prev_clean: bool = True
_prev_reaper: bool = False
_prev_reason: str = ""


def _read() -> Dict[str, Any]:
    try:
        return json.loads(_RUNSTATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: Dict[str, Any]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _RUNSTATE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def mark_running() -> None:
    """Boot: remember how the previous run ended, then mark THIS run in-progress
    (unclean, no reaper) until a graceful shutdown or a reaper trip updates it."""
    global _prev_clean, _prev_reaper, _prev_reason
    prev = _read()
    # First boot ever (no marker) counts as clean — there was no prior crash.
    _prev_clean = bool(prev.get("clean", True))
    _prev_reaper = bool(prev.get("reaper", False))
    _prev_reason = str(prev.get("reason", ""))
    _write({"clean": False, "reaper": False, "started_at": time.time()})


def mark_clean_shutdown() -> None:
    """Graceful shutdown: flip the marker so the next boot reads this run as clean."""
    _write({"clean": True, "ended_at": time.time()})


def mark_stall(reason: str = "") -> None:
    """A watchdog (Reaper.trigger) is taking Orrin down to restart him — NOT death,
    NOT a crash. Tag it so the next launch shows 'restarting', not a memorial or an
    'unexpected stop'. Best-effort and reentrancy-safe."""
    cur = _read()
    cur.update({"clean": False, "reaper": True, "reason": str(reason)[:200], "stalled_at": time.time()})
    _write(cur)


def previous_run_clean() -> bool:
    return _prev_clean


def status() -> Dict[str, Any]:
    """The current lifecycle state for the UI to route on. Death takes precedence;
    then a reaper stall reads as 'stalled', any other unclean exit as 'crashed'."""
    state = "alive"
    info: Dict[str, Any] = {}
    try:
        from cognition.mortality import life_status, lifespan_rolled
        if lifespan_rolled():
            ls = life_status()
            info.update({"born_at": ls.get("born_at"), "age_days": ls.get("age_days"), "phase": ls.get("phase")})
            if ls.get("final_thoughts_written"):
                state = "dead"
    except Exception:
        pass
    if state != "dead":
        if _prev_reaper:
            state = "stalled"
            info["reason"] = _prev_reason
        elif not _prev_clean:
            state = "crashed"
    info["state"] = state
    return info
