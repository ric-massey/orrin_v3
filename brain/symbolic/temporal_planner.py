# brain/symbolic/temporal_planner.py
# Longer-horizon symbolic planning using causal graph + rule chains.
#
# Turns a goal into a multi-step causal plan:
#
#   goal_text → [Step 1: cause A] → [Step 2: A enables B] → [Step 3: B achieves G]
#
# Plan construction:
#   1. Seed from goal_text: extract key tokens, find causal edges that touch them.
#   2. BFS forward through the causal graph up to MAX_DEPTH steps.
#   3. At each step, annotate with a matching rule conclusion if one exists.
#   4. Estimate time horizon per step using _STEP_COSTS (symbolic, not ML).
#
# Horizons:
#   "immediate"  — single rule/action, minutes
#   "short"      — 2–4 steps, hours
#   "medium"     — 5–8 steps, up to 2 days
#   "long"       — 9+ steps, days to weeks
#
# Plans are stored in data/symbolic_plans.json (cap 100).
# integrate_goal_plan(goal) is the main external API — call it when a high-level
# goal is registered; it decomposes the goal into a causal step sequence and
# returns the plan so callers can persist or surface it.
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import DATA_DIR

PLANS_FILE  = DATA_DIR / "symbolic_plans.json"
_MAX_DEPTH  = 10
_BEAM_WIDTH = 4
_MIN_SCORE  = 0.25

_STEP_COST_HOURS: Dict[str, float] = {
    "rule":           0.1,    # rule fires → immediate
    "causal_edge":    1.0,    # causal step → ~1 hour gap
    "analogy":        0.5,
    "symbolic_search": 0.25,
}


# ─── Public API ───────────────────────────────────────────────────────────────

def integrate_goal_plan(goal: Dict, context: Optional[Dict] = None) -> Dict:
    """
    Decompose a goal into a causal multi-step plan.
    Returns the plan dict (also saved to disk).
    """
    title   = goal.get("title", "")
    desc    = goal.get("description", "")
    seed    = f"{title} {desc}"
    horizon = goal.get("horizon", "medium")

    steps  = _build_plan(seed, horizon)
    plan   = _assemble_plan(goal, steps, horizon)

    # Do not persist zero-step plans — they become permanent orphans that
    # advance_plan can never close (it requires steps). The caller falls back to
    # the real goal["plan"] execution path via pursue_goal, so nothing is lost.
    if plan["step_count"] == 0:
        plan["status"] = "unplannable"
        log_activity(
            f"[temporal_plan] No causal steps for '{title[:50]}' — "
            f"unplannable, not persisted (falling back to goal['plan'])."
        )
        return plan

    _save_plan(plan)

    log_activity(
        f"[temporal_plan] Plan for '{title[:50]}': "
        f"{len(steps)} steps, horizon={plan['estimated_horizon']}"
    )
    return plan


def plan(goal_text: str, horizon: str = "medium") -> Dict:
    """Lightweight wrapper for non-goal callers."""
    return integrate_goal_plan({"title": goal_text, "description": "", "horizon": horizon})


_ORPHAN_STATUSES = frozenset({"empty", "unplannable"})


def _is_orphan(p: Dict) -> bool:
    return p.get("status") in _ORPHAN_STATUSES and int(p.get("step_count", 0)) == 0


def get_active_plans() -> List[Dict]:
    plans = load_json(PLANS_FILE, default_type=list) or []
    return [p for p in plans if p.get("status") == "active" and not _is_orphan(p)]


def advance_plan(plan_id: str, completed_step_index: int) -> Optional[Dict]:
    """
    Mark a step complete and return the next step (or None if plan finished).
    """
    plans = load_json(PLANS_FILE, default_type=list) or []
    for plan in plans:
        if plan.get("id") != plan_id:
            continue
        steps = plan.get("steps", [])
        if completed_step_index < len(steps):
            steps[completed_step_index]["status"] = "completed"
            steps[completed_step_index]["completed_at"] = datetime.now(timezone.utc).isoformat()
        # Find next pending step
        next_step = next((s for s in steps if s.get("status") == "pending"), None)
        if not next_step:
            plan["status"] = "completed"
            plan["completed_at"] = datetime.now(timezone.utc).isoformat()
        save_json(PLANS_FILE, plans[-100:])
        return next_step
    return None


# ─── Plan construction ────────────────────────────────────────────────────────

def _build_plan(seed_text: str, requested_horizon: str) -> List[Dict]:
    """BFS through causal graph + rule engine to construct a step sequence."""
    steps: List[Dict]     = []
    visited: Set[str]     = set()
    queue: List[str]      = [seed_text]
    total_hours: float    = 0.0
    max_steps             = {"immediate": 1, "short": 4, "medium": 8, "long": _MAX_DEPTH}.get(
        requested_horizon, 8
    )

    while queue and len(steps) < max_steps:
        current_text = queue.pop(0)
        if current_text in visited:
            continue
        visited.add(current_text)

        # Try rule match first (fastest, most reliable)
        step = _step_from_rule(current_text)
        if step:
            steps.append(step)
            total_hours += _STEP_COST_HOURS["rule"]
            queue.append(step["conclusion"])
            continue

        # Try causal graph forward chaining
        causal_steps = _steps_from_causal(current_text, visited)
        if causal_steps:
            best = causal_steps[0]
            steps.append(best)
            total_hours += _STEP_COST_HOURS["causal_edge"]
            queue.append(best["conclusion"])
            # Also enqueue top alternatives as beam
            for alt in causal_steps[1:_BEAM_WIDTH]:
                queue.append(alt["conclusion"])
            continue

        # Try analogy for lateral step
        step = _step_from_analogy(current_text)
        if step:
            steps.append(step)
            total_hours += _STEP_COST_HOURS["analogy"]
            queue.append(step["conclusion"])

    return steps


def _step_from_rule(text: str) -> Optional[Dict]:
    try:
        from symbolic.rule_engine import match as _match
        rule = _match(text, threshold=0.35)
        if not rule:
            return None
        return {
            "type":       "rule",
            "source_id":  rule.get("id", ""),
            "premise":    text[:100],
            "conclusion": rule.get("conclusion", "")[:150],
            "confidence": rule.get("confidence", 0.75),
            "status":     "pending",
        }
    except Exception:
        return None


def _steps_from_causal(text: str, visited: Set[str]) -> List[Dict]:
    try:
        from symbolic.causal_graph import get_effects
        effects = get_effects(text, min_score=_MIN_SCORE)
        results = []
        for e in effects[:_BEAM_WIDTH]:
            eff = e.get("effect", "")
            if eff in visited:
                continue
            results.append({
                "type":       "causal_edge",
                "source_id":  e.get("id", ""),
                "premise":    e.get("cause", "")[:100],
                "conclusion": eff[:150],
                "confidence": e.get("causal_score", 0.5),
                "evidence":   e.get("evidence_count", 0),
                "status":     "pending",
            })
        return results
    except Exception:
        return []


def _step_from_analogy(text: str) -> Optional[Dict]:
    try:
        from symbolic.analogy_engine import best_analogue_answer
        solution = best_analogue_answer(text)
        if not solution:
            return None
        return {
            "type":       "analogy",
            "source_id":  "analogy",
            "premise":    text[:100],
            "conclusion": solution[:150],
            "confidence": 0.55,
            "status":     "pending",
        }
    except Exception:
        return None


# ─── Plan assembly ────────────────────────────────────────────────────────────

def _assemble_plan(goal: Dict, steps: List[Dict], requested_horizon: str) -> Dict:
    n = len(steps)
    if n == 0:
        estimated = "immediate"
    elif n <= 1:
        estimated = "immediate"
    elif n <= 4:
        estimated = "short"
    elif n <= 8:
        estimated = "medium"
    else:
        estimated = "long"

    total_conf = round(
        sum(s.get("confidence", 0.5) for s in steps) / max(n, 1), 3
    )

    plan_id = f"plan_{int(time.time())}_{hash(goal.get('title',''))%10000:04d}"

    return {
        "id":                plan_id,
        "goal_title":        goal.get("title", "")[:80],
        "goal_source":       goal.get("source", ""),
        "steps":             steps,
        "step_count":        n,
        "requested_horizon": requested_horizon,
        "estimated_horizon": estimated,
        "mean_confidence":   total_conf,
        "status":            "active" if steps else "empty",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "completed_at":      None,
    }


def _save_plan(plan: Dict) -> None:
    existing = load_json(PLANS_FILE, default_type=list) or []
    existing.append(plan)
    save_json(PLANS_FILE, existing[-100:])


def _sweep_orphan_plans() -> None:
    """One-time, idempotent retirement of existing empty/zero-step orphan plans.
    Re-saves only when something is actually dropped, so repeated imports are no-ops."""
    try:
        plans = load_json(PLANS_FILE, default_type=list) or []
        kept = [p for p in plans if not _is_orphan(p)]
        if len(kept) != len(plans):
            save_json(PLANS_FILE, kept[-100:])
            log_activity(
                f"[temporal_plan] Swept {len(plans) - len(kept)} empty orphan plan(s)."
            )
    except Exception:
        pass


_sweep_orphan_plans()


# ─── Progress reporting ───────────────────────────────────────────────────────

def get_plan_stats() -> Dict:
    plans = load_json(PLANS_FILE, default_type=list) or []
    plans = [p for p in plans if not _is_orphan(p)]
    if not plans:
        return {"total": 0, "active": 0, "completed": 0, "avg_steps": 0.0}
    active    = [p for p in plans if p.get("status") == "active"]
    completed = [p for p in plans if p.get("status") == "completed"]
    return {
        "total":     len(plans),
        "active":    len(active),
        "completed": len(completed),
        "avg_steps": round(sum(p.get("step_count", 0) for p in plans) / len(plans), 1),
        "horizons":  {h: sum(1 for p in plans if p.get("estimated_horizon") == h)
                      for h in ("immediate", "short", "medium", "long")},
    }
