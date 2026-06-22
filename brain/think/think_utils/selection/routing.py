"""Workspace → action routing for selection (Phase 4D, from select_function.py).

_workspace_routes_for() maps a conscious atomic or bound situation (the global
workspace moment) to additive action priors — goal/affect/thought/signal/user
routes, merged across facets for a bound situation. Self-contained (operates on
the moment dict only); re-exported from select_function for its external
importer (ORRIN_loop's prepare_workspace path).
"""
from __future__ import annotations

from typing import Any, Dict


def _workspace_routes_for(moment: Dict[str, Any]) -> Dict[str, float]:
    """Map a conscious atomic or bound situation to additive action priors."""
    source = str(moment.get("source", ""))
    atomic = {
        "goal":    {"attend_goal": 1.0, "plan_next_step": 0.8, "assess_goal_progress": 0.6},
        "affect":  {"reflection": 0.8, "reflect_on_self_beliefs": 0.7, "narrative_update": 0.5},
        "thought": {"reflection": 0.8, "narrative_update": 0.6},
        "signal":  {"look_outward": 0.9, "search_own_files": 0.6},
        "user":    {"attend_goal": 0.7, "narrative_update": 0.6},
    }
    if source != "binding":
        return atomic.get(source, {})

    facets = moment.get("facets") or {}
    if not isinstance(facets, dict):
        return {}
    routes: Dict[str, float] = {}

    def merge(values: Dict[str, float]) -> None:
        for name, weight in values.items():
            routes[name] = max(routes.get(name, 0.0), weight)

    if facets.get("goal"):
        merge(atomic["goal"])
    if facets.get("affect"):
        merge(atomic["affect"])
    if facets.get("memory"):
        merge(atomic["thought"])
    if facets.get("event") or facets.get("motion") or facets.get("object"):
        merge(atomic["signal"])
    if facets.get("interlocutor"):
        merge(atomic["user"])
    return routes
