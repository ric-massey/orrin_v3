"""
brain/behavior/speech_content.py

Typed content kernel for self-initiated speech — F19 (2026-07-08 addendum).

F7 slowed the mouth's repeats; it did not give the utterance a referent. The
07-05 run's 388 self-initiated sends were near-total `express_state` over vague
internal pressure (top exact reply 54×). Before the renderer picks words, the
mouth now chooses a TYPED intent, each requiring a concrete referent:

    answer_user           — live user input (handled upstream by speech_gate)
    share_artifact        — a credited effect produced this cycle / recently
    share_finding         — a recent research-typed long-memory finding
    state_blocker         — the committed goal is blocked on something nameable
    ask_grounded_question — an unmet milestone on the committed goal
    express_state         — raw affect: the LAST resort, not the default

The kernel is a Motive input (intent + seed + referent), so it flows through
the one expression door (express_to_user) and is reworded/sanitized there —
this module selects meaning, it never ships text to a person directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from brain.cognition.global_workspace import bound_goal
from brain.utils.failure_counter import record_failure

# Long-memory event types that count as shareable findings (mirrors
# env_snapshot's F11 research-evidence vocabulary).
_FINDING_EVENT_TYPES = frozenset({
    "world_perception", "research", "finding", "llm_tool_research",
    "web_research", "wikipedia", "dream_insight",
})
_MIN_FINDING_CHARS = 80


def _artifact_kernel(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A credited production effect from this cycle — the strongest referent."""
    rows: List[Any] = context.get("_effect_rows_this_cycle") or []
    for row in reversed(rows):
        if not isinstance(row, dict) or row.get("dedupe"):
            continue
        body = ""
        try:
            from brain.agency.effect_artifacts import load as _load_artifact
            body = _load_artifact(str(row.get("content_hash") or "")) or ""
        except Exception as exc:
            record_failure("speech_content._artifact_kernel", exc)
        seed = (body or str(row.get("kind") or "")).strip()
        if not seed:
            continue
        return {
            "intent": "share_artifact",
            "seed": f"I made something: {seed[:140]}",
            "referent": {"type": "effect", "handle": str(row.get("content_hash") or "")},
        }
    return None


def _finding_kernel(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A recent research-typed finding from long memory."""
    try:
        from brain.paths import LONG_MEMORY_FILE
        from brain.utils.json_utils import load_json
        mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    except Exception as exc:
        record_failure("speech_content._finding_kernel", exc)
        return None
    last_shared = str(context.get("_last_shared_finding_id") or "")
    for e in reversed(list(mem)[-60:]):
        if not isinstance(e, dict):
            continue
        if str(e.get("event_type") or "") not in _FINDING_EVENT_TYPES:
            continue
        text = str(e.get("content") or "").strip()
        if len(text) < _MIN_FINDING_CHARS:
            continue
        if str(e.get("id") or "") == last_shared:
            continue  # don't re-share the same finding back-to-back
        context["_last_shared_finding_id"] = str(e.get("id") or "")
        return {
            "intent": "share_finding",
            "seed": f"I learned something: {text[:140]}",
            "referent": {"type": "memory", "handle": str(e.get("id") or "")},
        }
    return None


def _blocker_kernel(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The committed goal is blocked on something concrete and nameable."""
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return None
    title = str(goal.get("title") or goal.get("name") or "").strip()
    if not title:
        return None
    needs = str(goal.get("_needs_deliberate_action") or "").strip()
    if needs:
        return {
            "intent": "state_blocker",
            "seed": f"I'm stuck on '{title[:80]}' — it needs a kind of act I "
                    f"haven't managed yet",
            "referent": {"type": "goal", "handle": str(goal.get("id") or title)},
        }
    if goal.get("_stalled"):
        return {
            "intent": "state_blocker",
            "seed": f"I keep replanning '{title[:80]}' without getting traction",
            "referent": {"type": "goal", "handle": str(goal.get("id") or title)},
        }
    return None


def _question_kernel(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """An unmet milestone on the committed goal — something real to ask about."""
    goal = bound_goal(context)
    if not isinstance(goal, dict):
        return None
    title = str(goal.get("title") or goal.get("name") or "").strip()
    for ms in (goal.get("milestones") or []):
        if not isinstance(ms, dict) or ms.get("met"):
            continue
        text = str(ms.get("text") or ms.get("milestone") or ms.get("criterion")
                   or "").strip()
        if len(text) < 12:
            continue
        return {
            "intent": "ask_grounded_question",
            "seed": f"About '{title[:60]}': I'm still working out — {text[:120]}",
            "referent": {"type": "milestone", "handle": text[:80]},
        }
    return None


def choose_content_kernel(context: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the typed intent + seed for a self-initiated utterance.

    Referent-bearing intents are tried best-first; `express_state` (raw affect,
    no referent, seed=None so the composer uses the affect meaning kernel) is
    reached only when nothing concrete exists to speak about."""
    if not isinstance(context, dict):
        return {"intent": "express_state", "seed": None, "referent": None}
    for picker in (_artifact_kernel, _finding_kernel, _blocker_kernel,
                   _question_kernel):
        try:
            kernel = picker(context)
        except Exception as exc:
            record_failure("speech_content.choose_content_kernel", exc)
            kernel = None
        if kernel:
            return kernel
    return {"intent": "express_state", "seed": None, "referent": None}
