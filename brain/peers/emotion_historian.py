"""
brain/peers/emotion_historian.py  —  The Affect Historian

Watches affective patterns over time: which affect signals are chronically
elevated, whether the state is stable, and whether the same triggers
keep finding Orrin.

Analogy: a longitudinal psychiatrist.  Not "how are you feeling today"
but "here's your pattern across the last N cycles — something keeps
returning."

Wakes when any core affect signal exceeds 0.75, or when affective
stability falls below 0.40.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Any, Dict, List

from brain.peers.peer_base import BasePeer
from brain.paths import AFFECT_STATE_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


class EmotionHistorian(BasePeer):
    name = "emotion_historian"
    description = "a presence that holds the longer view of how I feel over time"
    trust = 0.68
    signal_tags = ["peer", "emotion_historian", "internal"]

    def should_wake(self, context: Dict[str, Any], cycle: int) -> bool:
        emo = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            for v in core.values():
                try:
                    if float(v) > 0.75:
                        return True
                except Exception as _e:
                    record_failure("emotion_historian.EmotionHistorian.should_wake", _e)
        stability = float(emo.get("affect_stability", 1.0) or 1.0)
        if stability < 0.40:
            return True
        return False

    def observe(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        signals = []

        try:
            from brain.utils.json_utils import load_json
            state = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
            core = state.get("core_signals") or {}
            stability = float(state.get("affect_stability", 1.0) or 1.0)
            triggers = state.get("recent_triggers") or []
        except (OSError, ValueError, TypeError, AttributeError):  # intentional: missing/malformed affect state → unchanged signals
            return signals

        # ── Chronically elevated emotions ─────────────────────────────────────
        try:
            high = [
                (emo, float(val))
                for emo, val in (core or {}).items()
                if isinstance(val, (int, float)) and float(val) > 0.75
            ]
            high.sort(key=lambda t: t[1], reverse=True)

            if high:
                top_emo, top_val = high[0]
                # Use felt-state language — don't just name the emotion
                sensation_map = {
                    "impasse_signal": "a persistent friction that hasn't released",
                    "threat_level":        "an ongoing sense of threat or unease",
                    "negative_valence":     "a heaviness that hasn't lifted",
                    "conflict_signal":       "a sustained heat that keeps returning",
                    "uncertainty": "an unresolved open question pulling at me",
                    "social_deficit":  "a recurring sense of absence",
                    "stagnation_signal":     "a flatness that's gone on longer than usual",
                }
                sensation = sensation_map.get(top_emo, f"an elevated {top_emo}")
                signals.append(self._signal(
                    f"I've been carrying {sensation} — it's been running high "
                    f"({top_val:.2f}) and hasn't found a way back to rest. "
                    + (f"It's not alone: {', '.join(e for e, _ in high[1:3])} are also elevated."
                       if len(high) > 1 else ""),
                    strength=0.70,
                    extra_tags=["emotion", "elevated", top_emo],
                ))
        except Exception as _e:
            record_failure("emotion_historian.EmotionHistorian.observe", _e)

        # ── Low stability ─────────────────────────────────────────────────────
        try:
            if stability < 0.40:
                signals.append(self._signal(
                    f"My internal state has been turbulent — "
                    f"stability at {stability:.2f}, not settling anywhere long enough "
                    f"to process what's happening. "
                    f"Something keeps shifting before I can integrate it.",
                    strength=0.68,
                    extra_tags=["emotion", "instability"],
                ))
        except Exception as _e:
            record_failure("emotion_historian.EmotionHistorian.observe.2", _e)

        # ── Repeated triggers ────────────────────────────────────────────────
        try:
            if isinstance(triggers, list) and len(triggers) >= 6:
                trigger_emos = [
                    str(t.get("emotion") or "") for t in triggers[-10:]
                    if isinstance(t, dict) and t.get("emotion")
                ]
                if trigger_emos:
                    top_trigger = max(set(trigger_emos), key=trigger_emos.count)
                    freq = trigger_emos.count(top_trigger) / len(trigger_emos)
                    if freq >= 0.50 and top_trigger not in ("neutral", ""):
                        signals.append(self._signal(
                            f"The same thing keeps finding me — '{top_trigger}' "
                            f"appears in {int(freq * 100)}% of my recent triggers. "
                            f"I keep encountering it from different directions.",
                            strength=0.65,
                            extra_tags=["emotion", "repeated_trigger", top_trigger],
                        ))
                        # #9 Phase 3 (internal-observer path): a chronically
                        # recurring trigger is a candidate rule. This observer
                        # watches Orrin's OWN dynamics, not a specific person, so
                        # it fires on the maturity gate alone (no relationship-depth
                        # gate — that applies only to person-specific generalizations).
                        self._distill_trigger_rule(context, top_trigger, freq)
        except Exception as _e:
            record_failure("emotion_historian.EmotionHistorian.observe.3", _e)

        return signals

    # ── #9 Phase 3: candidate-rule production (gated) ─────────────────────────
    _RULE_RECUR_THRESHOLD = 2   # observation must recur across waves before promoting

    def _distill_trigger_rule(self, context: Dict[str, Any], trigger: str, freq: float) -> None:
        """
        Distill a chronically-recurring affect trigger into a corrective rule, but
        only once the system is mature (grounded rule base + stable run length).
        Internal-dynamics observation → maturity gate only; persistent recurrence
        required so a single noisy wave doesn't mint a rule.
        """
        try:
            from brain.cognition.metacog import _maturity_gate_open
            if not _maturity_gate_open(context):
                return
            from brain.utils.json_utils import load_json, save_json
            from brain.paths import DATA_DIR
            path = DATA_DIR / "peer_rule_candidates.json"
            cands = load_json(path, default_type=dict) or {}
            if not isinstance(cands, dict):
                cands = {}
            key = f"trigger:{trigger}"
            rec = cands.get(key) or {"count": 0, "promoted": False}
            rec["count"] = int(rec.get("count", 0)) + 1
            if rec["count"] >= self._RULE_RECUR_THRESHOLD and not rec.get("promoted"):
                from brain.symbolic.rule_engine import add_rule
                add_rule(
                    conditions=[f"affect_chronic:{trigger}"],
                    conclusion=(
                        f"When '{trigger}' is chronically elevated, apply regulation "
                        f"early rather than waiting — it keeps returning."
                    ),
                    source="peer_emotion_historian",
                    confidence=0.6,
                )
                rec["promoted"] = True
                _log.info("[emotion_historian→rule] distilled chronic '%s' trigger", trigger)
            cands[key] = rec
            save_json(path, cands)
        except Exception as _e:
            record_failure("emotion_historian.EmotionHistorian._distill_trigger_rule", _e)
