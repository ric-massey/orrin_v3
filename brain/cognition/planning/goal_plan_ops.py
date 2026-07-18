# brain/cognition/planning/goal_plan_ops.py
# Goal plan / step operations, extracted from goals.py (Phase 4.5C). Pure,
# symbolic (no-LLM) primitives that read and adapt the ordered step list on a
# goal dict: read/advance the plan, set/dedupe it, detect drift, and the dynamic
# subgoal-adaptation operations (insert / skip / reprioritize the pending tail,
# milestone token matching, prune already-satisfied steps). They mutate the
# in-memory goal dict; callers persist it. No dependency on the rest of goals.py,
# which re-exports these names.
from __future__ import annotations

from typing import Any, Callable, List, Dict, Optional

from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure


# ── Goal plan helpers ────────────────────────────────────────────────────────
# A "plan" on a committed goal is an ordered list of step dicts:
#   [{"step": str, "status": "pending"|"completed"|"skipped", "generated_at": iso_str}, ...]
#
# These helpers operate on the in-memory goal dict. Callers are responsible
# for persisting the goal back to context["committed_goal"] or GOALS_FILE.

def get_goal_plan(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the plan list on a goal, or empty list if none."""
    plan = goal.get("plan")
    return plan if isinstance(plan, list) else []


def get_next_pending_step(goal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the first step with status='pending', or None if plan exhausted."""
    for step in get_goal_plan(goal):
        if isinstance(step, dict) and step.get("status") == "pending":
            return step
    return None


def advance_goal_plan(goal: Dict[str, Any], step: Dict[str, Any]) -> None:
    """Mark a plan step as completed in-place."""
    step["status"] = "completed"
    step["completed_at"] = now_iso_z()
    # Metric hook (Phase 4 / audit §9): a completed concrete step credits the
    # matching knowledge domain so domain scores respond to action.
    try:
        from brain.symbolic.symbolic_self_model import credit_domain_action
        credit_domain_action(str(step.get("step", "")))
    except Exception as _e:
        record_failure("goals.advance_goal_plan", _e)


def _normalize_step_text(s: str) -> str:
    """Canonical form for plan-step uniqueness: lowercase, collapsed whitespace,
    stripped trailing punctuation."""
    return " ".join(str(s).lower().split()).rstrip(".!?")


# Placeholder steps that pretend to be plans (BEHAVIOR_FIX_PLAN 2.2): when the
# adapter can't produce something concrete it must say "blocked", not emit
# filler that completes trivially and fakes progress.
_PLACEHOLDER_STEPS = frozenset({
    "do the thing", "continue as planned", "reflect", "gather context",
    "think about it", "keep going", "continue", "proceed", "work on it",
    "make progress", "next step",
})


def is_placeholder_step(s: str) -> bool:
    return _normalize_step_text(s) in _PLACEHOLDER_STEPS


def set_goal_plan(goal: Dict[str, Any], steps: List[Any]) -> None:
    """
    Attach a fresh plan to a goal from a list of step description strings.
    Overwrites any existing plan.

    Steps are de-duplicated by normalized text (a duplicate is never appended,
    regardless of status — audit §7 found the same step 5× in one plan) and
    placeholder steps are rejected outright.
    """
    ts = now_iso_z()
    plan: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in steps:
        source = dict(raw) if isinstance(raw, dict) else {}
        s = source.get("step") if source else raw
        if not isinstance(s, str) or not s.strip():
            continue
        key = _normalize_step_text(s)
        if not key or key in seen or is_placeholder_step(s):
            continue
        seen.add(key)
        item: Dict[str, Any] = {"step": str(s)[:200], "status": "pending", "generated_at": ts}
        action = source.get("action")
        if isinstance(action, dict) and action.get("function"):
            item["action"] = dict(action)
        plan.append(item)
    goal["plan"] = plan
    goal["last_updated"] = ts


def plan_drift_detected(assessment_text: str) -> bool:
    """
    Heuristic: does the assessment signal that the current plan is off-track?
    Returns True when the text mentions divergence, failure, or stagnation.
    """
    lower = (assessment_text or "").lower()
    drift_signals = {
        "off track", "stalled", "not converging", "drift", "wrong direction",
        "not working", "reconsi", "replanning", "blocked", "failed", "pivot",
    }
    return any(sig in lower for sig in drift_signals)


# ── Dynamic subgoal / plan adaptation ─────────────────────────────────────────
# Primitives that let Orrin surgically adjust a goal's breakdown *while* pursuing
# it — inserting, skipping, or reordering steps in response to changing
# conditions — instead of being locked into the initial decomposition or forced
# into a wholesale replan (which pursue_goal.py owns for genuine drift).
#
# Design rules:
#   • Pure and symbolic (no LLM) so they work with the LLM gate closed.
#   • Progress-preserving: completed steps are never removed or reordered; only
#     the *pending* tail of the plan is ever adapted.
#   • A pruned/obsolete step becomes status="skipped" (a terminal status,
#     alongside "completed") rather than being deleted, so history is auditable.

# Statuses that mean a plan step needs no further work.
TERMINAL_STEP_STATUSES = frozenset({"completed", "skipped"})

_PLAN_STEP_STOPWORDS = frozenset({
    "a", "an", "the", "is", "to", "for", "in", "of", "and", "or", "my", "that",
    "this", "with", "from", "its", "by", "at", "it", "i", "me", "about", "into",
    "on", "be", "was", "are", "will", "have", "has",
})


def _plan_step_tokens(text: object) -> set[str]:
    """Non-trivial lowercase tokens of a step/milestone, for overlap matching."""
    out = set()
    for w in str(text or "").split():
        tok = w.strip(".,;:!?\"'()[]").lower()
        if len(tok) >= 3 and tok not in _PLAN_STEP_STOPWORDS:
            out.add(tok)
    return out


def insert_plan_step(
    goal: Dict[str, Any], step: str, position: Optional[int] = None, reason: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Insert a new pending step into the goal's plan.

    By default the step is placed at the head of the *pending* region (right
    after the last completed/skipped step) so it runs before the remaining work.
    Returns the inserted step dict, or None if `step` is empty or duplicates an
    already-pending step.
    """
    text = str(step or "").strip()
    if not text or is_placeholder_step(text):
        return None
    plan = goal.get("plan")
    if not isinstance(plan, list):
        plan = []
        goal["plan"] = plan

    # Refuse a step that already exists in ANY status (BEHAVIOR_FIX_PLAN 2.2):
    # re-adding a completed step is how plans accumulated the same line 5×.
    tokens = _plan_step_tokens(text)
    norm = _normalize_step_text(text)
    for s in plan:
        if not isinstance(s, dict):
            continue
        if _normalize_step_text(s.get("step", "")) == norm:
            return None
        if tokens and _plan_step_tokens(s.get("step")) == tokens:
            return None

    new_step = {"step": text[:200], "status": "pending", "generated_at": now_iso_z()}
    if reason:
        new_step["inserted_reason"] = reason[:120]

    if position is None:
        idx = 0
        for i, s in enumerate(plan):
            if isinstance(s, dict) and s.get("status") in TERMINAL_STEP_STATUSES:
                idx = i + 1
        plan.insert(idx, new_step)
    else:
        plan.insert(max(0, min(int(position), len(plan))), new_step)

    goal["last_updated"] = now_iso_z()
    return new_step


def skip_pending_steps(goal: Dict[str, Any], predicate: Callable[[Dict[str, Any]], bool], reason: str = "") -> int:
    """
    Mark every pending step for which `predicate(step_dict)` is True as
    'skipped' (a terminal status). Completed steps are never touched.
    Returns the number of steps changed.
    """
    plan = goal.get("plan")
    if not isinstance(plan, list):
        return 0
    n = 0
    for s in plan:
        if isinstance(s, dict) and s.get("status") == "pending":
            try:
                hit = bool(predicate(s))
            except Exception:
                hit = False
            if hit:
                s["status"] = "skipped"
                s["closed_at"] = now_iso_z()
                if reason:
                    s["closed_reason"] = reason[:120]
                n += 1
    if n:
        goal["last_updated"] = now_iso_z()
    return n


def reprioritize_pending_steps(goal: Dict[str, Any], score_fn: Callable[[Dict[str, Any]], float]) -> bool:
    """
    Stable-sort the *pending tail* of the plan by `score_fn(step) -> float`
    (descending), leaving completed/skipped steps fixed in place. Ties keep
    their original order. Returns True if the order actually changed.
    """
    plan = goal.get("plan")
    if not isinstance(plan, list) or not plan:
        return False
    head, pending = [], []
    for s in plan:
        if isinstance(s, dict) and s.get("status") in TERMINAL_STEP_STATUSES:
            head.append(s)
        else:
            pending.append(s)
    if len(pending) < 2:
        return False
    ordered = sorted(pending, key=lambda s: -float(score_fn(s) or 0.0))
    if ordered == pending:
        return False
    goal["plan"] = head + ordered
    goal["last_updated"] = now_iso_z()
    return True


def met_milestone_tokens(goal: Dict[str, Any]) -> set[str]:
    """Union of tokens across all already-met milestones on the goal."""
    out: set[str] = set()
    for ms in (goal.get("milestones") or []):
        if isinstance(ms, dict) and ms.get("met"):
            out |= _plan_step_tokens(ms.get("text"))
    return out


def milestone_text(ms: Dict[str, Any]) -> str:
    """The criterion text of a milestone, whichever key its writer used.

    R10-4: milestones arrive keyed differently by writer — evolution uses
    `text`, goal_comprehension writes `milestone`, others use label/desc/
    criterion/description/name. A single-key read (`ms.get("text")`) silently
    dropped comprehension-built milestones: it rendered failure reasons as
    ['?', '?'] AND derived empty plans from them. Resolve them all here."""
    if not isinstance(ms, dict):
        return ""
    return str(
        ms.get("text") or ms.get("milestone") or ms.get("label")
        or ms.get("desc") or ms.get("criterion") or ms.get("description")
        or ms.get("name") or ""
    ).strip()


def unmet_milestone_texts(goal: Dict[str, Any]) -> List[str]:
    """Text of milestones that are not yet met."""
    return [
        milestone_text(ms)
        for ms in (goal.get("milestones") or [])
        if isinstance(ms, dict) and not ms.get("met") and milestone_text(ms)
    ]


def prune_satisfied_steps(goal: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> int:
    """
    Skip pending steps whose work is already done — i.e. their keywords are
    largely covered by an already-met milestone. This stops Orrin from
    redundantly re-executing a step when the underlying outcome happened as a
    side effect of earlier work. Milestone-only (not raw working memory) so the
    pursuit loop's own bookkeeping can't trigger a false positive.
    Returns the number of steps skipped.
    """
    met = met_milestone_tokens(goal)
    if not met:
        return 0

    def _satisfied(step: Dict[str, Any]) -> bool:
        toks = _plan_step_tokens(step.get("step"))
        if len(toks) < 2:
            return False
        return len(toks & met) >= max(2, len(toks) // 2)

    return skip_pending_steps(goal, _satisfied, reason="milestone_already_met")

