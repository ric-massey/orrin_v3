"""
cognition/introspection/router.py

Single dispatch table for all cognition-level reflection triggers.

Design contract:
  - Callers use introspect(trigger, context) — never import handlers directly.
  - Each trigger has a minimum cooldown (seconds). Duplicate calls within the
    window are skipped and logged, not silently ignored.
  - Handlers are lazy-loaded to avoid circular imports at module init.
  - meta_reflect uses force=True so its full sweep always runs.
  - All other callers use the default (force=False) to get dedup protection.

Trigger taxonomy:
  "cognition"          — recent cognition-history patterns
  "cognition_schedule" — rebalance schedule weights
  "conversation"       — conversation tone / pattern analysis
  "effectiveness"      — goal/decision effectiveness review
  "internal_agents"    — critique by internal peer voices
  "missed_goals"       — goals that slipped
  "outcome"            — outcome/result review
  "planning"           — introspective goal planning (may use LLM)
  "repair"             — cognition rhythm + contradiction detection
  "rules"              — symbolic rule health + proposals
  "self_belief"        — self-model consistency + value evolution
  "think"              — structural analysis of think_module.py
  "world_model"        — rebuild symbolic world model
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from core.runtime_log import get_logger
from utils.log import log_private, log_error

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Cooldowns (seconds between allowed runs for a given trigger)
# ---------------------------------------------------------------------------
COOLDOWNS: dict[str, float] = {
    "cognition":           300.0,   # 5 min
    "cognition_schedule":  600.0,   # 10 min
    "conversation":        300.0,   # 5 min
    "effectiveness":       900.0,   # 15 min
    "internal_agents":     600.0,   # 10 min
    "missed_goals":        900.0,   # 15 min
    "outcome":             300.0,   # 5 min
    "planning":            900.0,   # 15 min
    "repair":              600.0,   # 10 min
    "rules":               600.0,   # 10 min
    "self_belief":         900.0,   # 15 min
    "think":              3600.0,   # 1 hour
    "world_model":         600.0,   # 10 min
}

TRIGGER_TYPES: frozenset[str] = frozenset(COOLDOWNS)

_last_run: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Lazy handler loader (prevents circular imports at module level)
# ---------------------------------------------------------------------------
def _load_handlers() -> dict[str, Callable[[], Any]]:
    from cognition.reflection.reflect_on_cognition import reflect_on_cognition_patterns
    from cognition.reflection.reflect_on_cognition_schedule import reflect_on_cognition_schedule
    from cognition.reflection.reflect_on_conversation import reflect_on_conversation_patterns
    from cognition.reflection.reflect_on_internal_agents import reflect_on_internal_agents
    from cognition.reflection.reflect_on_outcome import reflect_on_outcomes
    from cognition.reflection.reflect_on_self_belief import reflect_on_self_beliefs
    from cognition.reflection.rule_reflection import reflect_on_rules_used
    from cognition.reflection.self_reflection import reflect_on_think
    from cognition.planning.reflection import reflect_on_missed_goals, reflect_on_effectiveness
    from cognition.planning.introspection import introspective_planning
    from cognition.repair.repair import reflect_on_cognition_rhythm
    from cognition.world_model import update_world_model

    return {
        "cognition":          reflect_on_cognition_patterns,
        "cognition_schedule": reflect_on_cognition_schedule,
        "conversation":       reflect_on_conversation_patterns,
        "effectiveness":      reflect_on_effectiveness,
        "internal_agents":    reflect_on_internal_agents,
        "missed_goals":       reflect_on_missed_goals,
        "outcome":            reflect_on_outcomes,
        "planning":           introspective_planning,
        "repair":             reflect_on_cognition_rhythm,
        "rules":              reflect_on_rules_used,
        "self_belief":        reflect_on_self_beliefs,
        "think":              reflect_on_think,
        "world_model":        update_world_model,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def introspect(
    trigger: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Route a reflection trigger to its canonical handler.

    Returns:
      {
        "trigger":  str,
        "result":   Any,       # handler return value, or None if skipped
        "skipped":  bool,
        "reason":   str | None # skip reason, or error message
      }
    """
    if trigger not in TRIGGER_TYPES:
        log_error(f"[introspect] Unknown trigger {trigger!r}. Valid: {sorted(TRIGGER_TYPES)}")
        return {"trigger": trigger, "result": None, "skipped": True,
                "reason": f"unknown trigger {trigger!r}"}

    now = time.monotonic()
    cooldown = COOLDOWNS[trigger]
    last = _last_run.get(trigger, 0.0)
    elapsed = now - last

    if not force and elapsed < cooldown:
        remaining = int(cooldown - elapsed)
        log_private(f"[introspect] {trigger}: cooldown {remaining}s remaining — skipped")
        return {"trigger": trigger, "result": None, "skipped": True,
                "reason": f"cooldown {remaining}s remaining"}

    handlers = _load_handlers()
    handler = handlers[trigger]

    _last_run[trigger] = now
    log_private(f"[introspect] → {trigger}")

    try:
        result = handler()
        return {"trigger": trigger, "result": result, "skipped": False, "reason": None}
    except Exception as e:
        log_error(f"[introspect] {trigger} raised: {e}")
        return {"trigger": trigger, "result": None, "skipped": False, "reason": f"error: {e}"}


def reset_cooldown(trigger: str) -> None:
    """Force-expire a trigger's cooldown (useful in tests)."""
    _last_run.pop(trigger, None)


def cooldown_status() -> Dict[str, Any]:
    """Return seconds-remaining for each trigger (0 = ready)."""
    now = time.monotonic()
    return {
        t: max(0.0, round(COOLDOWNS[t] - (now - _last_run.get(t, 0.0)), 1))
        for t in sorted(TRIGGER_TYPES)
    }
