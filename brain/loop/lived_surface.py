"""The lived surface (P7 / A1): a curated projection of what it is like to be
Orrin right now — attending-to, pressured-by, what-changed, what-he's-avoiding,
what-he's-trying-to-resolve.

NOT a state dump. Every field is sourced from the same projections consciousness
itself uses, so the surface shows the lived view, never the plumbing:
  - attending_to      — the Global Workspace winner's content (felt by
                        construction; membrane-tested)
  - pressured_by      — top PERCEIVED signals via introspection.felt_affect
                        (the P6 veil door), rendered in felt language
  - what_changed      — the run's most recent durable effect (ledger tail)
  - avoiding          — goals degraded/disengaged away from (Wrosch), i.e. what
                        pursuit is currently steering around
  - trying_to_resolve — the top active tension, else the directional long-term
                        driver's frontier (P4's cross-session gap)

Assembled once per cycle by telemetry (fail-safe) and shipped in the `lived`
frame field to the UI.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from brain.utils.failure_counter import record_failure
from brain.utils.felt_lexicon import felt_label

_PRESSURE_FLOOR = 0.45   # a signal must be at least this loud to count as pressure
_MAX_PRESSURES = 3


def _attending_to(context: Dict[str, Any]) -> str:
    moment = context.get("global_workspace")
    if isinstance(moment, dict):
        return str(moment.get("content") or "").strip()
    return ""


def _pressured_by(context: Dict[str, Any]) -> List[str]:
    try:
        from brain.control_signals.introspection import felt_affect
        perceived = felt_affect(context) or {}
    except Exception:  # intentional: the lived surface degrades to empty, never raises
        return []
    core = perceived.get("core_signals") or {}
    loud = sorted(
        ((k, float(v)) for k, v in core.items()
         if isinstance(v, (int, float)) and float(v) >= _PRESSURE_FLOOR),
        key=lambda kv: kv[1], reverse=True,
    )
    return [felt_label(k) for k, _ in loud[:_MAX_PRESSURES]]


def _what_changed() -> str:
    """The most recent durable effect this run left on the world (ledger tail)."""
    try:
        from brain.agency.effect_ledger import EFFECT_LEDGER_FILE
        if not EFFECT_LEDGER_FILE.exists():
            return ""
        tail = EFFECT_LEDGER_FILE.read_text("utf-8").strip().splitlines()[-8:]
        for line in reversed(tail):
            try:
                row = json.loads(line)
            except Exception:  # intentional: skip a malformed ledger line, keep scanning
                continue
            if row.get("dedupe") or row.get("kind") == "reuse":
                continue
            kind = str(row.get("kind") or "")
            gid = str(row.get("goal_id") or "")
            if kind:
                return f"{kind.replace('_', ' ')}" + (f" — for '{gid[:60]}'" if gid else "")
    except Exception as e:
        record_failure("lived_surface.what_changed", e)
    return ""


def _avoiding(context: Dict[str, Any]) -> str:
    """What pursuit is steering around: a degraded goal's original aim, or the
    most recent degrade/disengage event in working memory."""
    for g in (context.get("committed_goals") or []):
        if isinstance(g, dict) and g.get("_degraded"):
            orig = str(g.get("_original_title") or "").strip()
            if orig:
                return orig
    wm = context.get("working_memory")
    if isinstance(wm, list):
        for item in reversed(wm[-30:]):
            if isinstance(item, dict) and str(item.get("event_type") or "") in (
                    "goal_degraded", "goal_disengaged", "goal_abandoned"):
                return str(item.get("content") or "").strip()[:120]
    return ""


def _trying_to_resolve(context: Dict[str, Any]) -> str:
    tensions = context.get("active_tensions")
    if isinstance(tensions, list) and tensions:
        top = tensions[0]
        if isinstance(top, dict):
            title = str(top.get("title") or "").strip()
            if title:
                return title
    # No open tension → the long-term driver's frontier is the standing gap.
    for g in (context.get("committed_goals") or []):
        if isinstance(g, dict) and (g.get("directional") or g.get("never_complete")):
            frontier = str(g.get("frontier") or "").strip()
            if frontier:
                return frontier
    return ""


def assemble_lived_surface(context: Dict[str, Any]) -> Dict[str, Any]:
    """One curated lived-view dict per cycle. Every field degrades to ''/[] —
    the surface never raises and never shows raw keys."""
    try:
        return {
            "attending_to": _attending_to(context),
            "pressured_by": _pressured_by(context),
            "what_changed": _what_changed(),
            "avoiding": _avoiding(context),
            "trying_to_resolve": _trying_to_resolve(context),
        }
    except Exception as e:
        record_failure("lived_surface.assemble", e)
        return {"attending_to": "", "pressured_by": [], "what_changed": "",
                "avoiding": "", "trying_to_resolve": ""}
