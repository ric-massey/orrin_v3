# brain/cognition/planning/step_attempts.py
#
# Durable per-(goal, step) attempt counters — F1b (2026-07-05 findings).
#
# THE PROBLEM IT SOLVES. `_step_attempts` lived only on the goal dict, but the
# executive queue re-pulls goal dicts from the v2 store every tick, so the
# counter reset before it could reach _STEP_MAX_ATTEMPTS — the 2026-07-05 run
# retried one compose_section step 146 times over ~20 h while `_step_attempts`
# sat empty. This store keys attempts by (goal_id, step) on disk, so the count
# survives the v1/v2 round-trip AND restarts, and it tracks per-goal GIVE-UPS
# (steps advanced past after the cap) so a goal whose plan keeps regenerating
# unreachable steps escalates to a real failure instead of retrying forever.
from __future__ import annotations

import threading
from typing import Dict, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure

STEP_ATTEMPTS_FILE = DATA_DIR / "step_attempts.json"

# Give-up advances (a step abandoned at the attempt cap) a single goal may
# accumulate before the goal itself is failed — the F1b escalation.
GOAL_GIVE_UP_MAX = 3
_MAX_GOALS = 200          # bound the file; oldest goal records evicted
_MAX_STEPS_PER_GOAL = 40  # bound one goal's step map

_lock = threading.Lock()


def _load() -> Dict:
    try:
        d = load_json(STEP_ATTEMPTS_FILE, default_type=dict) or {}
        return d if isinstance(d, dict) else {}
    except Exception as exc:
        record_failure("step_attempts._load", exc)
        return {}


def _save(d: Dict) -> None:
    try:
        if len(d) > _MAX_GOALS:
            # Evict the goals with the lowest write serial (oldest activity).
            ordered = sorted(d.items(), key=lambda kv: int((kv[1] or {}).get("serial", 0)))
            for gid, _ in ordered[: len(d) - _MAX_GOALS]:
                d.pop(gid, None)
        save_json(STEP_ATTEMPTS_FILE, d)
    except Exception as exc:
        record_failure("step_attempts._save", exc)


def _rec(d: Dict, goal_id: str) -> Dict:
    rec = d.setdefault(str(goal_id), {})
    rec.setdefault("steps", {})
    rec.setdefault("give_ups", 0)
    rec["serial"] = int(rec.get("serial", 0)) + 1
    return rec


def bump_attempt(goal_id: str, step_key: str) -> int:
    """Count one more failed attempt at this step; returns the new count."""
    if not goal_id or not step_key:
        return 1
    with _lock:
        d = _load()
        rec = _rec(d, goal_id)
        steps: Dict[str, int] = rec["steps"]
        n = int(steps.get(step_key, 0) or 0) + 1
        steps[step_key] = n
        if len(steps) > _MAX_STEPS_PER_GOAL:
            for k in list(steps)[: len(steps) - _MAX_STEPS_PER_GOAL]:
                steps.pop(k, None)
        _save(d)
        return n


def clear_attempt(goal_id: str, step_key: Optional[str] = None) -> None:
    """Forget attempts for one step (real progress), or the whole goal."""
    if not goal_id:
        return
    with _lock:
        d = _load()
        if str(goal_id) not in d:
            return
        if step_key is None:
            d.pop(str(goal_id), None)
        else:
            (d[str(goal_id)].get("steps") or {}).pop(step_key, None)
        _save(d)


def record_give_up(goal_id: str) -> int:
    """Count a step advanced past at the attempt cap; returns the goal's total.
    The caller escalates to mark_goal_failed at GOAL_GIVE_UP_MAX."""
    if not goal_id:
        return 0
    with _lock:
        d = _load()
        rec = _rec(d, goal_id)
        rec["give_ups"] = int(rec.get("give_ups", 0) or 0) + 1
        _save(d)
        return rec["give_ups"]


def attempts_for(goal_id: str) -> Dict[str, int]:
    """Read-only view of a goal's per-step attempt counts."""
    d = _load()
    rec = d.get(str(goal_id)) or {}
    steps = rec.get("steps")
    return dict(steps) if isinstance(steps, dict) else {}


def handle_unexecuted_step(goal: Dict, goal_title: str, next_step: str,
                           context: Dict, max_attempts: int) -> Optional[Dict]:
    """The retry/give-up policy for a recognised step whose act produced no
    effect (pursue_committed_goal's blocked branch, extracted next to its
    counters). Returns a result dict the caller must return (retry, or the F1b
    goal-failure escalation), or None to advance past the step (give-up under
    the escalation threshold)."""
    from brain.utils.log import log_activity
    from brain.cog_memory.working_memory import update_working_memory

    step_key = str(next_step)[:120]
    gid = str(goal.get("id") or goal_title)
    n = bump_attempt(gid, step_key)
    goal.setdefault("_step_attempts", {})[step_key] = n   # mirror for readers
    context["committed_goal"] = goal
    if n < max_attempts:
        update_working_memory(
            f"[goal_blocked] '{goal_title}': step did not take hold "
            f"(attempt {n}/{max_attempts}) — {next_step[:80]}"
        )
        try:
            from brain.cognition.planning.goals import merge_updated_goal_into_tree
            from brain.cognition.planning import goal_arbiter
            # Atomic load→merge→save through the GoalArbiter (no uncoordinated
            # load_goals/save_goals race; daemon-ready). dual_process_loop.md Phase 1.
            goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, goal),
                               source="pursue_goal.blocked_retry")
        except Exception as _e:
            record_failure("step_attempts.blocked_retry_persist", _e)
        return {"status": "retry", "goal": goal_title, "next_step": next_step, "attempt": n}
    update_working_memory(
        f"[goal_blocked] '{goal_title}': could not execute after {n} "
        f"attempts — {next_step[:80]}. Moving on."
    )
    # F1b escalation: a goal that keeps producing unreachable steps (plans
    # regenerating the same dead end) fails for real instead of cycling
    # retry-cap → advance → replan forever.
    gave_up = record_give_up(gid)
    if gave_up >= GOAL_GIVE_UP_MAX:
        from brain.cognition.planning.goals import mark_goal_failed
        clear_attempt(gid)
        mark_goal_failed(
            goal,
            reason=f"steps_unreachable: {gave_up} steps abandoned at the "
                   f"{max_attempts}-attempt cap",
            context=context,
        )
        context["committed_goal"] = None
        context["_last_bootstrap_ts"] = 0.0
        log_activity(f"[pursue_goal] '{goal_title[:60]}': {gave_up} capped step "
                     f"give-ups — FAILED (feeds self-repair).")
        return {"status": "failed", "goal": goal_title, "give_ups": gave_up}
    return None
