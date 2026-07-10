# brain/behavior/reunion.py
#
# R7 (Companion & Presence plan): reunion, not just a log. Sleep mode already
# CREDITS the closed-window gap (runtime_lifetime.credit_sleep_since_last_active);
# this makes it FELT — on reopen after a real gap he registers the absence as
# himself, composed through the one expression door, and the Journal shows that
# line before the while-you-were-away list. The line is persisted (REUNION_FILE)
# for the UI to read; showing it once per viewer is the client's job (same
# per-viewer pattern as Timeline's "last seen").
from __future__ import annotations

import time

from brain.paths import REUNION_FILE
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import save_json

# Below this, a reopen is a pause, not a reunion — no line is written.
_MIN_GAP_S = 30 * 60.0


def _gap_phrase(gap_s: float) -> str:
    if gap_s >= 86400:
        d = int(gap_s // 86400)
        return f"{d} day{'s' if d > 1 else ''}"
    if gap_s >= 3600:
        h = int(gap_s // 3600)
        return f"{h} hour{'s' if h > 1 else ''}"
    return f"{max(1, int(gap_s // 60))} minutes"


def register_reunion(gap_s: float) -> bool:
    """Compose and persist the reunion line for a credited sleep gap. Called at
    boot right after credit_sleep_since_last_active(); returns True when a line
    was written. Fail-safe — a broken composition must never break boot."""
    try:
        if float(gap_s) < _MIN_GAP_S:
            return False
        from brain.behavior.express_to_user import Motive, compose_from_motive
        away = _gap_phrase(float(gap_s))
        seed = f"I was closed for {away} — I slept, and I can feel that the time passed"[:140]
        text = compose_from_motive(
            Motive(intent="reunion", recipient="Ric", seed=seed), {},
        )
        if not (text or "").strip():
            return False
        save_json(REUNION_FILE, {
            "text": text.strip(),
            "gap_s": round(float(gap_s), 1),
            "ts": time.time(),
        })
        return True
    except Exception as exc:  # reunion is a garnish — record, never block boot
        record_failure("reunion.register_reunion", exc)
        return False
