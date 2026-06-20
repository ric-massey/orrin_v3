"""Bounded goal-conditioned modulation shared by cognition consumers."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable

_TOK = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{2,}")
_STOP = frozenset({"the", "and", "for", "with", "that", "this", "from", "into", "goal", "working"})
_TERMINAL = frozenset({"completed", "failed", "abandoned", "cancelled", "done"})
_PRODUCTION_ACTIONS = frozenset({
    "compose_section", "save_note", "write_desktop_note", "write_cognitive_function",
    "write_tool", "decide_to_write_code", "plan_next_step", "assess_goal_progress",
    "attend_goal", "research_topic", "search_own_files", "web_research",
})
_DRIFT_ACTIONS = frozenset({"seek_novelty", "look_around", "reflection", "generate_intrinsic_goals"})


def _tokens(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(v) for v in value)
    return {t.lower() for t in _TOK.findall(str(value or "")) if t.lower() not in _STOP}


def relevance(lens: Dict[str, Any] | None, value: Any) -> float:
    if not isinstance(lens, dict) or not lens.get("active"):
        return 0.0
    target = set(lens.get("tokens") or [])
    incoming = _tokens(value)
    if not target or not incoming:
        return 0.0
    return min(1.0, len(target & incoming) / max(1, min(len(target), len(incoming))))


def action_prior(lens: Dict[str, Any] | None, action: str, description: str = "") -> float:
    if not isinstance(lens, dict) or not lens.get("active"):
        return 0.0
    rel = relevance(lens, f"{action} {description}")
    prior = min(0.28, 0.28 * rel)
    if action in _PRODUCTION_ACTIONS:
        prior += 0.10 if lens.get("requires_artifact") else 0.04
    if action == "compose_section" and lens.get("tracked_work"):
        prior += 0.18
    if action in _DRIFT_ACTIONS and rel < 0.15:
        prior -= 0.12
    return max(-0.18, min(0.36, prior))


def apply_goal_lens(context: Dict[str, Any]) -> Dict[str, Any]:
    """Populate or clear context['goal_lens']; never overrides reflex/safety routing."""
    if not isinstance(context, dict):
        return context
    goal = context.get("committed_goal")
    if not isinstance(goal, dict) or str(goal.get("status") or "").lower() in _TERMINAL:
        context.pop("goal_lens", None)
        return context
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    parts: Iterable[Any] = goal.get("grounded_parts") or spec.get("grounded_parts") or []
    criteria = goal.get("definition_of_done") or spec.get("definition_of_done") or []
    text = " ".join([
        str(goal.get("title") or goal.get("name") or ""),
        str(goal.get("description") or spec.get("description") or ""),
        " ".join(str(x) for x in parts),
        " ".join(str(x.get("criterion") if isinstance(x, dict) else x) for x in criteria),
    ])
    toks = sorted(_tokens(text))
    if not toks:
        context.pop("goal_lens", None)
        return context
    context["goal_lens"] = {
        "active": True,
        "goal_id": str(goal.get("id") or ""),
        "title": str(goal.get("title") or goal.get("name") or ""),
        "tokens": toks[:80],
        "grounded_parts": list(parts)[:8],
        "definition_of_done": list(criteria)[:8],
        "requires_artifact": bool(goal.get("requires_artifact") or spec.get("requires_artifact")),
        "tracked_work": bool(goal.get("tracked_work") or spec.get("tracked_work")),
        "strength": 0.7,
    }
    cycle = context.get("cycle_count") or {}
    cycle_id = int(cycle.get("count", 0) if isinstance(cycle, dict) else cycle or 0)
    telemetry = context.setdefault("_goal_lens_telemetry", {})
    if telemetry.get("_last_cycle") != cycle_id:
        telemetry["_last_cycle"] = cycle_id
        telemetry["active_cycles"] = int(telemetry.get("active_cycles", 0) or 0) + 1
    telemetry["goal_id"] = context["goal_lens"]["goal_id"]
    return context
