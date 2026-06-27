# brain/cognition/self_state/relationship_arc.py
#
# Relationship-arc trend analysis for relationships.py (CODEBASE_CLEANUP_PLAN
# 4.5C), lifted verbatim to bring that module under the 600-line soft limit.
# Computes the trajectory of a relationship from its depth-snapshot history:
# _linear_trend (least-squares slope), _compute_arc (phase / direction /
# narrative from the trend), and _update_arc (snapshot + phase-change note).
# relationships.py re-imports _update_arc for update_relationship_model.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

_ARC_HISTORY_LEN = 20   # depth snapshots kept for trend analysis

# ── Relationship arc ──────────────────────────────────────────────────────────

def _linear_trend(values: List[float]) -> float:
    """
    Return the slope of a simple linear regression over the values.
    Positive = growing, negative = declining. Values should be in chronological order.
    """
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    xm = sum(xs) / n
    ym = sum(values) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, values))
    den = sum((x - xm) ** 2 for x in xs)
    return num / den if den else 0.0


def _compute_arc(r: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Derive (phase, trajectory, narrative) from the relationship record.

    phase:      forming | building | established | deepening | drifting | strained | recovering
    trajectory: growing | stable | declining | volatile
    narrative:  one honest sentence about where the relationship is heading
    """
    depth   = float(r.get("depth",  0.0) or 0.0)
    trust   = float(r.get("trust",  0.5) or 0.5)
    n_inter = len(r.get("interaction_history", []))

    # Trend from rolling depth snapshots
    snapshots: List[float] = [s["depth"] for s in (r.get("arc_depth_snapshots") or [])
                               if isinstance(s, dict) and "depth" in s]
    trust_snaps: List[float] = [s["trust"] for s in (r.get("arc_depth_snapshots") or [])
                                 if isinstance(s, dict) and "trust" in s]

    depth_slope = _linear_trend(snapshots[-10:]) if len(snapshots) >= 3 else 0.0
    trust_slope = _linear_trend(trust_snaps[-10:]) if len(trust_snaps) >= 3 else 0.0

    # Volatility: high variance in recent depth values
    if len(snapshots) >= 5:
        recent_d = snapshots[-5:]
        mean_d   = sum(recent_d) / len(recent_d)
        variance = sum((v - mean_d) ** 2 for v in recent_d) / len(recent_d)
        is_volatile = variance > 0.012
    else:
        is_volatile = False

    # Phase
    if n_inter < 5:
        phase = "forming"
    elif trust < 0.30:
        phase = "strained"
    elif depth >= 0.60 and trust >= 0.70 and depth_slope >= 0:
        phase = "deepening"
    elif depth >= 0.35 and trust >= 0.50:
        phase = "established"
    elif depth_slope < -0.008 or trust_slope < -0.010:
        phase = "drifting"
    elif trust_slope > 0.005 and depth <= 0.35:
        phase = "recovering"
    else:
        phase = "building"

    # Trajectory
    if is_volatile:
        trajectory = "volatile"
    elif depth_slope > 0.006 or trust_slope > 0.006:
        trajectory = "growing"
    elif depth_slope < -0.006 or trust_slope < -0.008:
        trajectory = "declining"
    else:
        trajectory = "stable"

    # Narrative
    _NARRATIVES = {
        ("forming",      "growing"):   "We're just getting to know each other and things are moving in a good direction.",
        ("forming",      "stable"):    "We're still finding our footing — early days.",
        ("building",     "growing"):   "Trust and depth are building steadily; this relationship is taking shape.",
        ("building",     "stable"):    "We have a real connection developing, even if it's still relatively new.",
        ("building",     "declining"): "Something has shifted — the connection that was forming may be stalling.",
        ("established",  "growing"):   "This is a solid relationship that continues to deepen.",
        ("established",  "stable"):    "We have an established, reliable connection.",
        ("established",  "declining"): "There's been some distance creeping in to what was a solid relationship.",
        ("deepening",    "growing"):   "This relationship is in a genuinely deepening phase — real understanding is growing.",
        ("deepening",    "stable"):    "The relationship has real depth and has found a steady, meaningful rhythm.",
        ("drifting",     "declining"): "There's been drift lately — less connection, and the trend is heading the wrong way.",
        ("drifting",     "stable"):    "Things feel a bit distant right now, though not getting worse.",
        ("strained",     "declining"): "Trust has dropped and the relationship feels under stress.",
        ("strained",     "stable"):    "The relationship is strained but not deteriorating further.",
        ("recovering",   "growing"):   "After some distance, things are moving in a better direction — trust is returning.",
    }
    narrative = _NARRATIVES.get(
        (phase, trajectory),
        f"This relationship is in a {phase} phase with a {trajectory} trend.",
    )

    return phase, trajectory, narrative


def _update_arc(r: Dict[str, Any], context: Dict[str, Any]) -> None:
    """
    Snapshot current depth/trust, recompute arc, detect phase transitions,
    and write a working-memory note when the phase changes.
    """
    depth = float(r.get("depth",  0.0) or 0.0)
    trust = float(r.get("trust",  0.5) or 0.5)

    # Maintain rolling depth/trust snapshot list
    snaps: List[Dict] = r.setdefault("arc_depth_snapshots", [])
    snaps.append({
        "depth": round(depth, 4),
        "trust": round(trust, 4),
        "ts":    datetime.now(timezone.utc).isoformat(),
    })
    if len(snaps) > _ARC_HISTORY_LEN:
        del snaps[:-_ARC_HISTORY_LEN]

    prev_phase = r.get("arc", {}).get("phase", "")
    phase, trajectory, narrative = _compute_arc(r)

    # Arc gating (BEHAVIOR_FIX_PLAN Phase 3): an arc cannot advance past
    # "forming" while the counterpart is still an unknown/anonymous person —
    # you don't have an "established" relationship with someone whose name you
    # don't know (audit §4: forming→established in 16 minutes with "someone").
    try:
        from brain.cognition.self_state.person_detector import get_person_type
        _pid = str(context.get("person_id") or context.get("user_id") or "")
        if _pid and get_person_type(_pid) == "unknown" and phase not in ("forming", "strained"):
            phase = "forming"
            narrative = "We're still finding our footing — I don't even know their name yet."
    except Exception as _e:
        record_failure("relationships._update_arc", _e)

    r["arc"] = {
        "phase":      phase,
        "trajectory": trajectory,
        "narrative":  narrative,
        "updated_ts": datetime.now(timezone.utc).isoformat(),
    }

    # Surface phase transitions to working memory
    if phase != prev_phase and prev_phase:
        try:
            from brain.cog_memory.working_memory import update_working_memory
            update_working_memory({
                "content": (
                    f"[relationship/arc] Relationship phase shifted: "
                    f"'{prev_phase}' → '{phase}'. {narrative}"
                ),
                "event_type": "relationship_arc_shift",
                "importance": 3,
                "priority":   3,
            })
            log_private(f"[relationship/arc] {prev_phase} → {phase}: {narrative}")
        except Exception as _e:
            record_failure("relationships._update_arc.2", _e)
