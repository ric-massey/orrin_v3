# brain/cognition/aspiration_scoreboard.py
#
# Per-aspiration funnel scoreboard (T0.3 / WS-7 Change 5).
#
# THE PROBLEM IT SOLVES. End-of-life we could only read the final contribution
# count per aspiration (the 06-23 run: 20 / 0 / 0 / 0) and had NO way to tell
# *where* each zero-aspiration died: was it never generated? generated but never
# attempted? attempted but never progressed? The scoreboard records each stage of
# an aspiration's funnel in a rolling window, so aspiration_pressure (and a human
# reading the run) can see the DROP EDGE, not just the end state.
#
# Stages (per aspiration, rolling window):
#   generated  — a short-term goal serving this aspiration was created
#   attempted  — that goal was committed / pursued
#   progressed — it made real (effect-backed) sub-progress
#   completed  — it closed and rolled up into the aspiration
#
# Counts only; the window + a hard event cap bound memory. Failure-safe: every
# entry point swallows errors — a scoreboard must never break the goal loop.
from __future__ import annotations

import time
from typing import Dict, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.paths import DATA_DIR

_FILE = DATA_DIR / "aspiration_scoreboard.json"
_STAGES = ("generated", "attempted", "progressed", "completed")
_WINDOW_S = 24 * 3600.0      # rolling window for the live read
_MAX_EVENTS = 4000           # hard cap on stored events (bounds the file)


def _aspiration_for(driven_by: str) -> str:
    """Resolve a goal's drive to the aspiration title it serves (learned link)."""
    try:
        from brain.cognition.intrinsic_aspirations import _serves_aspiration
        return _serves_aspiration(str(driven_by or ""))
    except Exception:  # intentional: scoreboard is best-effort, never raise
        return ""


def _load() -> Dict:
    d = load_json(_FILE, default_type=dict) or {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("events", [])
    return d


def record(aspiration_title: str, stage: str) -> None:
    """Append one funnel event for an aspiration (by title)."""
    if stage not in _STAGES or not aspiration_title:
        return
    try:
        d = _load()
        events: List[dict] = d["events"]
        events.append({"ts": time.time(), "asp": str(aspiration_title), "stage": stage})
        if len(events) > _MAX_EVENTS:
            d["events"] = events[-_MAX_EVENTS:]
        save_json(_FILE, d)
    except Exception as exc:
        record_failure("aspiration_scoreboard.record", exc)


def record_by_drive(driven_by: str, stage: str) -> None:
    """Append one funnel event, resolving the aspiration from the goal's drive."""
    record(_aspiration_for(driven_by), stage)


def scoreboard(window_s: float = _WINDOW_S) -> Dict[str, Dict[str, int]]:
    """Per-aspiration {stage: count} over the rolling window."""
    out: Dict[str, Dict[str, int]] = {}
    try:
        cutoff = time.time() - max(0.0, float(window_s))
        for e in _load().get("events", []):
            if not isinstance(e, dict) or float(e.get("ts", 0) or 0) < cutoff:
                continue
            asp = str(e.get("asp", ""))
            stage = str(e.get("stage", ""))
            if not asp or stage not in _STAGES:
                continue
            out.setdefault(asp, {s: 0 for s in _STAGES})[stage] += 1
    except Exception as exc:
        record_failure("aspiration_scoreboard.scoreboard", exc)
    return out


def generation_counts(window_s: float = _WINDOW_S) -> Dict[str, int]:
    """Per-aspiration `generated` counts over the window (fed to aspiration_pressure)."""
    return {asp: stages.get("generated", 0) for asp, stages in scoreboard(window_s).items()}
