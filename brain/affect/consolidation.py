# brain/affect/consolidation.py
#
# Affective consolidation — significant events don't just spike and pass.
# They settle into the affective substrate over several cycles, leaving a
# residual tint that colors Orrin's subsequent thinking and expression.
#
# Humans don't process a loss, a surprise, or a breakthrough in one moment.
# They return to it repeatedly. The affect is fully felt hours or days later.
# This module approximates that by spreading the affective work across cycles
# rather than applying and discarding it instantly.
#
# SCIENTIFIC BASIS:
#   Levine & Pizarro (2004) — "Emotion and memory research: A grumpy overview."
#   Social Cognition, 22(5), 530–554. Emotional activation_level extends consolidation
#   windows; high-importance events receive preferential long-term encoding.
#   McGaugh (2000) — "Memory: A century of consolidation." Science, 287, 248–251.
#   threat_detector modulation of hippocampal consolidation during affective events.
#
# How it works:
#   1. When an important event occurs (importance >= 4, dream detection, or manual
#      trigger), create a consolidation entry in data/consolidation_queue.json
#   2. Each cycle, drain_consolidations() applies a small tint toward the target
#      emotion and decrements cycles_remaining
#   3. When cycles_remaining hits 0, the entry is dropped — work is done
#
# Entry schema:
#   {
#     "id":              str (uuid)
#     "event":           str (description)
#     "emotion":         str (target emotion to tint)
#     "intensity":       float (how much to apply in total)
#     "cycles_remaining": int
#     "tint_per_cycle":  float (intensity / initial_cycles)
#     "importance":      int
#     "created_ts":      str
#   }
from __future__ import annotations
from brain.core.runtime_log import get_logger

import uuid
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import DATA_DIR
from brain.utils.timeutils import now_iso_z
_log = get_logger(__name__)

_CONSOLIDATION_FILE = DATA_DIR / "consolidation_queue.json"
_DEFAULT_CYCLES = 8      # spread across 8 cycles by default
_MAX_QUEUE      = 20     # cap queue size so it can't snowball



def _load_queue() -> List[Dict]:
    data = load_json(_CONSOLIDATION_FILE, default_type=list) or []
    return [e for e in data if isinstance(e, dict)]


def _save_queue(q: List[Dict]) -> None:
    save_json(_CONSOLIDATION_FILE, q)


# ── Queue management ──────────────────────────────────────────────────────────

def enqueue_consolidation(
    event: str,
    emotion: str,
    intensity: float,
    importance: int = 4,
    cycles: Optional[int] = None,
) -> None:
    """
    Register a significant event for gradual emotional consolidation.
    Safe to call from anywhere — dream cycle, comprehension layer, pursue_goal, etc.

    emotion:   the core emotion to tint (must be a key in affect_state.core_signals)
    intensity: total emotional delta to apply over all cycles (e.g. 0.18)
    cycles:    how many cycles to spread it over (default: 8)
    """
    n_cycles = max(1, cycles or _DEFAULT_CYCLES)
    tint = round(intensity / n_cycles, 4)

    queue = _load_queue()
    if len(queue) >= _MAX_QUEUE:
        # Evict the lowest-importance, oldest entry
        queue.sort(key=lambda e: (e.get("importance", 1), e.get("created_ts", "")))
        queue = queue[1:]

    entry = {
        "id":               str(uuid.uuid4())[:8],
        "event":            event[:200],
        "emotion":          emotion,
        "intensity":        round(float(intensity), 4),
        "cycles_remaining": n_cycles,
        "tint_per_cycle":   tint,
        "importance":       importance,
        "created_ts":       now_iso_z(),
    }
    queue.append(entry)
    _save_queue(queue)
    log_private(f"[consolidation] enqueued: {emotion}×{intensity:.2f} over {n_cycles} cycles — {event[:60]}")


# ── Per-cycle drain ───────────────────────────────────────────────────────────

def drain_consolidations(context: Dict[str, Any]) -> None:
    """
    Apply one cycle of tinting from each active consolidation entry.

    Each tint is submitted as an AffectArbiter proposal rather than written to
    AFFECT_STATE_FILE directly — so consolidation no longer races the main loop's
    update_affect_state, and the tints are subject to the same homeostatic budget
    as every other affect producer. The consolidation queue file (NOT affect_state)
    is still advanced here. Called once per cycle from the main loop.
    """
    queue = _load_queue()
    if not queue:
        return

    from brain.affect.arbiter import submit_affect

    remaining = []
    for entry in queue:
        emotion  = entry.get("emotion", "")
        tint     = float(entry.get("tint_per_cycle") or 0.0)
        cycles   = int(entry.get("cycles_remaining") or 0)

        if cycles <= 0 or not emotion or tint == 0.0:
            continue

        # Propose the tint to the convergence layer instead of writing it.
        submit_affect(context, emotion, tint, source="consolidation", ttl_cycles=2)

        entry["cycles_remaining"] = cycles - 1
        if entry["cycles_remaining"] > 0:
            remaining.append(entry)
        else:
            log_private(
                f"[consolidation] completed: {emotion} consolidation for '{entry['event'][:50]}'"
            )

    _save_queue(remaining)


# ── Trigger helpers ───────────────────────────────────────────────────────────

def maybe_trigger_from_event(event_dict: Dict[str, Any]) -> bool:
    """
    Call with any event dict that has 'importance', 'content', and optionally 'emotion'.
    Returns True if a consolidation entry was created.

    Suitable for calling from: working_memory updates, long_memory writes, dream cycle.
    """
    importance = int(event_dict.get("importance") or 0)
    if importance < 4:
        return False

    content  = str(event_dict.get("content") or "")[:200]
    emotion  = str(event_dict.get("emotion") or "").lower().strip()
    if not emotion:
        # Infer from content keywords
        _KW = {
            "exploration_drive": {"curious", "interest", "wonder", "fascinate"},
            "positive_valence":       {"positive_valence", "excit", "delight", "happy", "glad"},
            "negative_valence":   {"sad", "loss_signal", "loss", "mourn"},
            "threat_level":      {"threat_level", "afraid", "threat", "danger"},
            "impasse_signal": {"frustrat", "stuck", "fail", "can't"},
            "social_penalty":     {"social_penalty", "embarra", "disappoint"},
        }
        content_lower = content.lower()
        for emo, kws in _KW.items():
            if any(kw in content_lower for kw in kws):
                emotion = emo
                break
        if not emotion:
            return False

    intensity = min(0.25, 0.05 + (importance - 4) * 0.04)
    enqueue_consolidation(content, emotion, intensity, importance=importance)
    return True
