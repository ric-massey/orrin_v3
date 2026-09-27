# brain/cognition/default_mode.py
#
# Default-mode stage: runs ambient thought (mind-wandering) and rumination once
# per cycle and OFFERS what surfaced to the Global Workspace.
#
# Before this stage existed, think() generated ambient fragments and ruminative
# loops and wrote them onto context keys nothing read — the DMN produced content
# that never reached awareness or the action pick. Now the surfaced content
# competes in the pre-think workspace like any other candidate (I7: bias, never
# preempt). When it wins, the workspace prior routes it to cheap inward work
# (selection/routing.py: "ambient", "rumination"); when it loses, habituation and
# attention load keep it in the background. No LLM is involved at any step.
#
# Salience ceilings sit below a present user (0.95) and near a pursued goal
# (0.55), so default-mode content wins on quiet cycles and loses under demand.
# Disable the workspace offers with ORRIN_DMN_WORKSPACE=0 (generation still runs).
from __future__ import annotations

import os
from typing import Any, Dict

from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

AMBIENT_SAL_BASE    = 0.15
AMBIENT_SAL_GAIN    = 0.35   # intensity 1.0 → 0.50
RUMINATION_SAL_BASE = 0.25
RUMINATION_SAL_GAIN = 0.45   # rumination charge caps at 0.70 → 0.565
BROOD_RESOLVE_RETURNS = 8


def _offers_enabled() -> bool:
    return os.environ.get("ORRIN_DMN_WORKSPACE", "1") != "0"


def _already_ran(context: Dict[str, Any]) -> bool:
    idx = context.get("_cycle_index")
    return idx is not None and context.get("_dmn_cycle") == idx


def run_default_mode(context: Dict[str, Any]) -> Dict[str, Any]:
    """Update ambient thought + rumination, set their context keys, and offer the
    surfaced content to the workspace. Idempotent per cycle (keyed on
    context['_cycle_index']). Fail-safe: every key is always set."""
    if _already_ran(context):
        return context
    context["_dmn_cycle"] = context.get("_cycle_index")

    try:
        from brain.cognition.ambient_thought import update_ambient
        context["ambient_texture"] = update_ambient(context).get("surfaced", []) or []
    except Exception as e:
        record_failure("default_mode.ambient", e)
        context["ambient_texture"] = []

    try:
        from brain.cognition.rumination import update_rumination, mark_resolved
        loop = update_rumination(context).get("surfaced")
        context["ruminative_loop"] = loop
        # Treynor et al. (2003): a brood that keeps returning without resolution is
        # shifted toward reflective mode so it can decay (charge ×0.25).
        if (loop and loop.get("mode") == "brooding"
                and int(loop.get("return_count", 0)) >= BROOD_RESOLVE_RETURNS):
            mark_resolved(loop["id"])
    except Exception as e:
        record_failure("default_mode.rumination", e)
        context["ruminative_loop"] = None

    if _offers_enabled():
        _offer(context)
    return context


def _offer(context: Dict[str, Any]) -> None:
    try:
        from brain.cognition.global_workspace import offer_to_workspace
        surfaced = context.get("ambient_texture") or []
        if surfaced:
            top = max(surfaced, key=lambda f: float(f.get("intensity", 0.0) or 0.0))
            content = str(top.get("content") or "").strip()
            if content:
                intensity = max(0.0, min(1.0, float(top.get("intensity", 0.0) or 0.0)))
                sal = round(AMBIENT_SAL_BASE + AMBIENT_SAL_GAIN * intensity, 3)
                offer_to_workspace(context, {
                    "content": content, "salience": sal,
                    "source": "ambient", "kind": str(top.get("fragment_type") or "ambient"),
                })
                log_activity(f"[dmn] offered ambient ({top.get('fragment_type')}, sal={sal}): {content[:80]}")

        loop = context.get("ruminative_loop")
        if isinstance(loop, dict) and loop.get("content"):
            charge = max(0.0, min(1.0, float(loop.get("charge", 0.0) or 0.0)))
            sal = round(RUMINATION_SAL_BASE + RUMINATION_SAL_GAIN * charge, 3)
            content = str(loop["content"]).strip()
            offer_to_workspace(context, {
                "content": f"it keeps coming back: {content}", "salience": sal,
                "source": "rumination", "kind": str(loop.get("mode") or "rumination"),
            })
            log_activity(f"[dmn] offered rumination ({loop.get('mode')}, sal={sal}): {content[:80]}")
    except Exception as e:
        record_failure("default_mode.offer", e)
