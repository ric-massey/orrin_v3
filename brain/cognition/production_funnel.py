# brain/cognition/production_funnel.py
#
# Production funnel instrument (T0.3 — "so '0 output' is never again a mystery").
#
# The 06-23 run produced 0 real works and we could not say WHERE the making path
# dropped: was a producing candidate never generated? generated but never
# committed? committed but the selector never routed to the producer? the producer
# ran but wrote nothing? wrote something but it was never credited? This records a
# count at each stage of the making path so the drop EDGE is nameable — it is the
# instrument T1.G's throughput kill-criterion reads to pinpoint the failure.
#
# Stages (ordered; iterate, no per-stage special-casing):
#   candidate    — an output_producing / requires_artifact goal was generated
#   committed    — that goal was committed (selected for pursuit)
#   handoff      — execution reached the explicit compose/produce handoff
#   producer_ran — the producer (compose_section / decide_to_write_code) executed
#   artifact     — a real artifact was written to disk
#   credited     — the artifact earned effect-ledger credit (novelty/significance)
#
# Counts only; failure-safe — a funnel must never break the production loop.
from __future__ import annotations

import time
from typing import Dict, List

from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.paths import DATA_DIR

_FILE = DATA_DIR / "production_funnel.json"
# Ordered so a reader can scan left→right and find the first stage whose count
# collapses relative to the one before it — that is the drop edge.
STAGES = ("candidate", "committed", "handoff", "producer_ran", "artifact", "credited")
_WINDOW_S = 24 * 3600.0
_MAX_EVENTS = 4000


def _load() -> Dict:
    d = load_json(_FILE, default_type=dict) or {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("events", [])
    return d


def record(stage: str, goal_id: str = "") -> None:
    """Append one funnel event for a making-path stage."""
    if stage not in STAGES:
        return
    try:
        d = _load()
        events: List[dict] = d["events"]
        events.append({"ts": time.time(), "stage": stage, "goal": str(goal_id or "")})
        if len(events) > _MAX_EVENTS:
            d["events"] = events[-_MAX_EVENTS:]
        save_json(_FILE, d)
    except Exception as exc:
        record_failure("production_funnel.record", exc)


def funnel(window_s: float = _WINDOW_S) -> Dict[str, int]:
    """{stage: count} over the rolling window, in canonical stage order."""
    out: Dict[str, int] = {s: 0 for s in STAGES}
    try:
        cutoff = time.time() - max(0.0, float(window_s))
        for e in _load().get("events", []):
            if not isinstance(e, dict) or float(e.get("ts", 0) or 0) < cutoff:
                continue
            stage = str(e.get("stage", ""))
            if stage in out:
                out[stage] += 1
    except Exception as exc:
        record_failure("production_funnel.funnel", exc)
    return out


def drop_edge(window_s: float = _WINDOW_S) -> str:
    """The first stage whose count falls to 0 while a prior stage was non-zero —
    i.e. where the making path died. Returns "" if production flowed end-to-end
    (credited > 0) or nothing was generated at all."""
    counts = funnel(window_s)
    prev_nonzero = False
    for stage in STAGES:
        c = counts[stage]
        if prev_nonzero and c == 0:
            return stage
        if c > 0:
            prev_nonzero = True
    return ""
