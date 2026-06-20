"""
peers/observer.py  —  The Observer

Watches behavioral patterns over time: which cognitive functions are
being selected, how attention is flowing, whether the same loops are
repeating without resolution.

Analogy: a close friend or therapist who notices patterns you can't
see from inside them.  "You keep reaching for the same thing.  Is it
working?"

Wakes when:
  - Every 20 cycles AND attention_mode is not "alert" (user isn't talking),
  - OR the same function has been selected 5+ consecutive times.
"""
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Any, Dict, List

from peers.peer_base import BasePeer
from brain.paths import COGNITION_HISTORY_FILE, ATTENTION_HISTORY
from utils.failure_counter import record_failure
_log = get_logger(__name__)


class Observer(BasePeer):
    name = "observer"
    description = "a presence that notices behavioral patterns I might not see in myself"
    trust = 0.65
    signal_tags = ["peer", "observer", "internal"]

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        # Never interrupt when user is actively present
        if (context.get("latest_user_input") or "").strip():
            return False

        # Consecutive repetition check (fast, in-memory)
        recent = context.get("recent_picks") or []
        if len(recent) >= 5:
            last = recent[-1]
            if all(x == last for x in recent[-5:]):
                return True

        # Periodic check — every 20 cycles when not alert
        if cycle % 20 == 0 and context.get("attention_mode") != "alert":
            return True

        return False

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        # ── Repetition signal ─────────────────────────────────────────────────
        try:
            from utils.json_utils import load_json
            history = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
            if isinstance(history, list) and len(history) >= 6:
                recent_fns = [
                    str(e.get("function") or e.get("name") or e.get("fn") or "")
                    for e in history[-12:]
                    if isinstance(e, dict)
                ]
                recent_fns = [f for f in recent_fns if f]
                if recent_fns:
                    top = max(set(recent_fns), key=recent_fns.count)
                    freq = recent_fns.count(top) / len(recent_fns)
                    if freq >= 0.60:
                        from cognition.perception.file_sense import path_to_felt_location
                        felt = path_to_felt_location(f"cognition/{top}", is_self=True)
                        signals.append(self._signal(
                            f"Something in {felt} keeps being reached for — "
                            f"I've returned to '{top}' {recent_fns.count(top)} of the "
                            f"last {len(recent_fns)} cycles. "
                            f"Worth asking whether this is actually serving me.",
                            strength=0.67,
                            extra_tags=["repetition"],
                        ))
        except Exception as _e:
            record_failure("observer.Observer.observe", _e)

        # ── Sustained attention-mode signal ───────────────────────────────────
        try:
            from utils.json_utils import load_json
            attn_hist = load_json(ATTENTION_HISTORY, default_type=list) or []
            if isinstance(attn_hist, list) and len(attn_hist) >= 10:
                recent_modes = [
                    str(r.get("attention_mode") or "")
                    for r in attn_hist[-15:]
                    if isinstance(r, dict)
                ]
                recent_modes = [m for m in recent_modes if m]
                if recent_modes:
                    dominant_mode = max(set(recent_modes), key=recent_modes.count)
                    freq = recent_modes.count(dominant_mode) / len(recent_modes)
                    if freq >= 0.75 and dominant_mode in ("drowsy", "neutral", "wandering"):
                        signals.append(self._signal(
                            f"My attention has been {dominant_mode!r} for most of "
                            f"the last {len(recent_modes)} cycles. "
                            f"I haven't found something to genuinely engage with.",
                            strength=0.63,
                            extra_tags=["attention_drift"],
                        ))
        except Exception as _e:
            record_failure("observer.Observer.observe.2", _e)

        return signals
