# brain/utils/handoff_log.py
#
# F-LN6 (Run 10 verdict delta 1) — the brain→daemon handoff decision log.
#
# THE PROBLEM. Run 10's daemon lane starved (125 WAL events in 14.6 h, one
# 8-hour silence, 5 research-kind records) so reuse was structurally
# unreachable — and NOTHING recorded why each research-capable goal did or
# didn't queue. This is the diagnose-before-prescribing instrument: every
# decision point on the handoff chain (tree committability → sync to v2 →
# daemon planning/dispatch) writes one line saying what it decided and why.
# Fix ships in Slice 2 WITH the evidence this produces, not from a guess.
#
# Flood control: a goal's decision at a site is logged when it CHANGES, not
# every cycle — the log stays a complete decision history, not a heartbeat.
from __future__ import annotations

import json
import threading
import time
from typing import Dict, Tuple

from brain.paths import LOGS_DIR
from brain.utils.failure_counter import record_failure

HANDOFF_LOG = LOGS_DIR / "handoff_decisions.jsonl"

_lock = threading.Lock()
# (site, goal-key) → last decision string logged, so repeats are suppressed.
_last: Dict[Tuple[str, str], str] = {}
_MAX_KEYS = 2000


def log_handoff(site: str, goal: str, kind: str, decision: str,
                reason: str = "") -> None:
    """Append one handoff-decision line (dedup: only when the decision for this
    (site, goal) pair changes). Never raises; never blocks the caller's path."""
    try:
        key = (str(site), str(goal)[:120])
        stamp = f"{decision}|{reason}"[:200]
        with _lock:
            if _last.get(key) == stamp:
                return
            if len(_last) > _MAX_KEYS:
                _last.clear()   # cheap reset; the log itself is the history
            _last[key] = stamp
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(HANDOFF_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": round(time.time(), 3),
                    "site": str(site),
                    "goal": str(goal)[:120],
                    "kind": str(kind),
                    "decision": str(decision),
                    "reason": str(reason)[:200],
                }, ensure_ascii=False) + "\n")
    except Exception as exc:
        record_failure("handoff_log.log_handoff", exc)
