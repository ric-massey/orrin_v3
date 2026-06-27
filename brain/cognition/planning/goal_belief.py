# brain/cognition/planning/goal_belief.py
# Self-belief falsification on goal success (Phase 4.5C, from goals.py): when a
# goal succeeds in a domain Orrin believes he is weak at, weaken that weak-area
# belief (and drop it once confidence falls below 0.2), recording the revision in
# a persistent ledger so a dream-cycle rebuild doesn't snap it back. Called by
# mark_goal_completed; self-contained (operates on the self-model + revisions
# files, not the goal store).
from __future__ import annotations

from typing import Any, List, Dict

from brain.utils.log import log_activity
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
from brain.paths import SELF_BELIEF_REVISIONS_FILE


# Domain keyword map for self-belief falsification — mirrors symbolic_self_model._DOMAIN_KW.
# When a goal succeeds in an area Orrin believes he's weak at, the belief weakens.
_BELIEF_DOMAIN_KW: Dict[str, List[str]] = {
    "SOCIAL":    ["user", "ric", "person", "conversation", "relationship", "social"],
    "TECHNICAL": ["code", "error", "system", "build", "function", "import", "bug", "fix"],
    "EMOTIONAL": ["emotion", "mood", "exploration_drive", "risk_estimate", "resource_deficit", "feel", "feeling"],
    "PLANNING":  ["goal", "plan", "step", "decision", "strategy", "milestone", "schedule"],
    "COGNITIVE": ["rule", "memory", "learn", "pattern", "concept", "reason", "think"],
}


def _domains_for_goal(goal: Dict[str, Any]) -> List[str]:
    """Return the domain tags (e.g. 'EMOTIONAL') that a goal's text touches."""
    text_parts = [
        str(goal.get("title") or ""),
        str(goal.get("name") or ""),
        str(goal.get("description") or ""),
    ]
    tags = goal.get("tags")
    if isinstance(tags, list):
        text_parts.extend(str(t) for t in tags)
    blob = " ".join(text_parts).lower()
    out: List[str] = []
    for dom, kws in _BELIEF_DOMAIN_KW.items():
        if any(kw in blob for kw in kws):
            out.append(dom)
    # Also accept explicit uppercase domain tags from the goal directly
    if isinstance(tags, list):
        for t in tags:
            up = str(t).upper()
            if up in _BELIEF_DOMAIN_KW and up not in out:
                out.append(up)
    return out


def _revise_weak_area_beliefs(goal: Dict[str, Any]) -> None:
    """
    Self-belief falsification: when a goal succeeds in an area Orrin believes he's
    weak at, reduce the confidence of that weakness belief (or remove it entirely
    if confidence falls below 0.2).
    """
    try:
        from brain.paths import DATA_DIR
        from brain.utils.json_utils import load_json as _load, save_json as _save

        sym_path = DATA_DIR / "symbolic_self_model.json"
        revisions_path = SELF_BELIEF_REVISIONS_FILE

        model: Dict[str, Any] = _load(sym_path, default_type=dict) or {}
        weak_areas = model.get("weak_areas") or []
        if not weak_areas:
            return

        domains = _domains_for_goal(goal)
        if not domains:
            return

        overlap = [d for d in domains if d in weak_areas]
        if not overlap:
            return

        # Persistent revision ledger so the belief doesn't simply snap back on
        # the next dream-cycle rebuild.
        revisions: Dict[str, Any] = _load(revisions_path, default_type=dict) or {}
        if not isinstance(revisions, dict):
            revisions = {}

        goal_title = goal.get("title") or goal.get("name") or "unknown"
        now = now_iso_z()
        changed_weak_areas = list(weak_areas)

        for dom in overlap:
            entry = revisions.get(dom) or {
                "domain": dom,
                "confidence": 1.0,   # starting strength of the weakness belief
                "events": [],
            }
            old_conf = float(entry.get("confidence", 1.0))
            new_conf = max(0.0, round(old_conf - 0.15, 3))
            entry["confidence"] = new_conf
            entry["events"].append({
                "timestamp": now,
                "goal": goal_title,
                "delta": -0.15,
                "new_confidence": new_conf,
            })
            # Keep the event log bounded
            entry["events"] = entry["events"][-50:]
            revisions[dom] = entry

            if new_conf < 0.2 and dom in changed_weak_areas:
                changed_weak_areas.remove(dom)
                log_activity(
                    f"[self_state] Removed weak-area belief '{dom}' "
                    f"(confidence dropped to {new_conf:.2f}) after success in "
                    f"'{goal_title[:60]}'"
                )
            else:
                log_activity(
                    f"[self_state] Revised weak-area belief '{dom}' "
                    f"(confidence {old_conf:.2f}→{new_conf:.2f}) after success in "
                    f"'{goal_title[:60]}'"
                )

        _save(revisions_path, revisions)

        # Also reflect the removals in the live model so downstream code sees
        # the updated weak_areas immediately (dream cycle can rebuild later).
        if changed_weak_areas != weak_areas:
            model["weak_areas"] = changed_weak_areas
            _save(sym_path, model)
    except Exception as _e:
        try:
            log_activity(f"[self_state] Weak-area belief revision error: {_e}")
        except Exception as _e:
            record_failure("goals._revise_weak_area_beliefs", _e)
