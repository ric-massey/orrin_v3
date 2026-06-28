# brain/cognition/planning/problem_refocus.py
#
# Reactive problem handling — the human "drop everything and fix the blocker"
# reflex, applied to Orrin's goal pursuit.
#
# When something Orrin relies on fails mid-pursuit (the motivating example: he
# tries the LLM and it's down), he should not just keep failing and eventually
# abandon the goal. Like a person, he should:
#
#   1. NOTICE the problem (a real, recurring failure while pursuing a goal),
#   2. INTERRUPT — park the current goal and refocus on a high-priority micro
#      goal: "figure out why <capability> isn't working",
#   3. DIAGNOSE it over a small attempt budget,
#   4a. RESUME the original goal once the problem clears, OR
#   4b. WORK AROUND it when he finds he can't fix it — resume the original goal
#       re-planned WITHOUT the broken capability (LLM down → research via
#       Wikipedia / symbolic path instead).
#
# This is a deliberate, single-source-of-truth override of context["committed_goal"]
# run once per cycle from ORRIN_loop, AFTER the goal slot has been resolved from
# the GoalsAPI. It complements (does not duplicate) the surgical plan reshaping
# in adapt_subgoals() and the wholesale drift→replan in pursue_goal.py.
#
# Detection reads cumulative failure counters and diffs them against a per-cycle
# baseline, so only NEW failures trigger a refocus — old accumulated failures at
# boot do not. Only one problem is handled at a time, and a fix micro-goal can
# never itself trigger another refocus (no nesting).
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

from brain.core.runtime_log import get_logger
from typing import Any, Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json
from brain.utils.log import log_activity
from brain.utils.timeutils import now_iso_z
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

# ── Tunables ──────────────────────────────────────────────────────────────────
MAX_FIX_ATTEMPTS = 3            # diagnosing cycles before declaring "can't fix it"
_MIN_LLM_FAILS_TO_TRIGGER = 1   # any new LLM failure is worth noticing
_MIN_SITE_FAILS_TO_TRIGGER = 2  # a generic site must recur before it counts

_LLM_FAIL_FILE = DATA_DIR / "llm_failure_counts.json"

# Human-readable labels for known capabilities.
_CAP_LABELS = {"llm": "the language model"}

# Registry tools (LLM, Wikipedia, web search, …): their outage is a normal
# fact, not a crisis. The fix goal for a tool runs in the BACKGROUND — an
# ordinary curiosity goal with a capped motivational weight — instead of
# parking the committed goal and seizing the focus slot every cycle.
_TOOL_CAPABILITIES = frozenset({"llm"})

# Curiosity about a broken tool may never outrank actual goals (plan §0.3).
_FIX_GOAL_WEIGHT_CAP = 0.4


def _cap_label(capability: str) -> str:
    return _CAP_LABELS.get(capability, capability)


def _cycle(context: Dict[str, Any]) -> int:
    cc = context.get("cycle_count") or {}
    if isinstance(cc, dict):
        return int(cc.get("count", 0) or 0)
    try:
        return int(cc or 0)
    except (TypeError, ValueError):  # intentional: non-int cycle → 0
        return 0


# ── Failure fingerprints (cumulative counters → diffable totals) ───────────────

def _llm_fail_total() -> int:
    counts: Dict[str, Any] = load_json(_LLM_FAIL_FILE, default_type=dict) or {}
    if not isinstance(counts, dict):
        return 0
    return sum(int(v or 0) for v in counts.values() if isinstance(v, (int, float)))


def _site_fail_totals() -> Dict[str, int]:
    """Per-site cumulative failure counts from the live in-memory counter."""
    try:
        from brain.utils.failure_counter import get_summary
        summary = get_summary() or {}
        return {site: int(data.get("count", 0) or 0) for site, data in summary.items()}
    except ImportError:  # intentional: failure counter unavailable → no site totals
        return {}


def _fingerprint() -> Dict[str, Any]:
    return {"llm": _llm_fail_total(), "sites": _site_fail_totals()}


def _detect_new_problem(
    prev: Dict[str, Any], cur: Dict[str, Any]
) -> Optional[Tuple[str, str, Dict[str, int]]]:
    """
    Compare two fingerprints. Return (capability, description, detect_totals) for
    the most significant NEW failure, or None. LLM failures take precedence (they
    block the most), then the generic site with the largest recurring increase.
    """
    # LLM first — it gates the most behavior.
    llm_delta = int(cur.get("llm", 0)) - int(prev.get("llm", 0))
    if llm_delta >= _MIN_LLM_FAILS_TO_TRIGGER:
        return (
            "llm",
            f"The language model failed {llm_delta}× while I was working.",
            {"llm": int(cur.get("llm", 0))},
        )

    # Then the generic site with the biggest recurring jump.
    prev_sites = prev.get("sites", {}) or {}
    cur_sites = cur.get("sites", {}) or {}
    best_site, best_delta = None, 0
    for site, count in cur_sites.items():
        delta = int(count) - int(prev_sites.get(site, 0))
        if delta > best_delta:
            best_site, best_delta = site, delta
    if best_site and best_delta >= _MIN_SITE_FAILS_TO_TRIGGER:
        return (
            best_site,
            f"'{best_site}' failed {best_delta}× while I was working.",
            {"site": int(cur_sites[best_site])},
        )
    return None


# ── Capability health ─────────────────────────────────────────────────────────

def _capability_healthy(capability: str, ap: Optional[Dict[str, Any]] = None) -> bool:
    """
    Is the capability working again? For the LLM we can check concretely
    (config + circuit breaker + no fresh failures). For arbitrary sites we can
    only tell that failures have stopped growing since the problem was detected.
    """
    if capability == "llm":
        try:
            from brain.utils.llm_gate import llm_available
            from brain.utils.generate_response import _cb_is_open
        except ImportError:  # intentional: can't tell → don't block resumption
            return True
        if not llm_available() or _cb_is_open():
            return False
        if ap is not None:
            return _llm_fail_total() <= int(ap.get("detect_total", 0))
        return True

    # Generic site: healthy iff its count hasn't grown past the detection point.
    if ap is not None:
        return _site_fail_totals().get(capability, 0) <= int(ap.get("detect_total", 0))
    return True


def _reconcile_capability_health(context: Dict[str, Any]) -> None:
    """
    Keep context["_unhealthy_capabilities"] honest each cycle for capabilities we
    can health-check (currently the LLM). Planning (_generate_plan) reads this set
    to automatically route around a down capability — so the workaround persists
    even when the active committed goal is re-sourced from the GoalsAPI.
    """
    unhealthy: List[str] = list(context.get("_unhealthy_capabilities") or [])
    healthy_llm = _capability_healthy("llm")
    if healthy_llm and "llm" in unhealthy:
        unhealthy.remove("llm")
    elif not healthy_llm and "llm" not in unhealthy:
        unhealthy.append("llm")
    context["_unhealthy_capabilities"] = unhealthy


# ── Affect / reward nudges (light, honest) ─────────────────────────────────────

def _bump_problem_signal(context: Dict[str, Any], tool: bool = False) -> None:
    """A surfaced blocker is mildly stressful and focusing — nudge impasse/uncertainty.

    A registry-tool outage (tool=True) is curiosity-grade, not impasse-grade:
    a small wonder/uncertainty nudge only, so a dead tool can't pin the
    impasse signal."""
    try:
        emo = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            if tool:
                core["novelty_signal"] = min(1.0, float(core.get("novelty_signal", 0.0)) + 0.10)
                core["uncertainty"] = min(1.0, float(core.get("uncertainty", 0.0)) + 0.05)
            else:
                core["impasse_signal"] = min(1.0, float(core.get("impasse_signal", 0.0)) + 0.25)
                core["uncertainty"] = min(1.0, float(core.get("uncertainty", 0.0)) + 0.15)
            if "core_signals" in emo:
                emo["core_signals"] = core
            else:
                emo.update(core)
        context["affect_state"] = emo
    except Exception as _e:
        record_failure("problem_refocus._bump_problem_signal", _e)


def _release(context: Dict[str, Any], actual: float, source: str) -> None:
    try:
        from brain.control_signals.reward_signals.reward_signals import release_reward_signal
        from brain.control_signals.reward_signals.action_reward_ema import get_expected as _pe, update_expected as _upe
        release_reward_signal(
            context,
            signal_type="reward_signal",
            actual_reward=actual,
            expected_reward=_pe(context, source),
            effort=0.6,
            mode="phasic",
            source=source,
        )
        _upe(context, source, actual)
    except Exception as _e:
        record_failure("problem_refocus._release", _e)


# ── Fix micro-goal construction ────────────────────────────────────────────────

def _build_fix_goal(
    capability: str, desc: str, context: Dict[str, Any],
    hypotheses: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    label = _cap_label(capability)
    title = f"Figure out why {label} isn't working"
    now = now_iso_z()
    _is_tool = capability in _TOOL_CAPABILITIES
    goal: Dict[str, Any] = {
        "title": title,
        "name": title,
        "kind": "cognitive",          # internal — not synced to the GoalsAPI
        "tier": "micro_goal",
        "source": "problem_refocus",
        "driven_by": "curiosity" if _is_tool else "problem_solving",
        "status": "in_progress",
        "created_ts": now,
        "last_updated": now,
        "motivational_weight": _FIX_GOAL_WEIGHT_CAP,
        "_is_fix_goal": True,
        "_no_refocus_boost": True,    # exempt from problem_refocus re-boosting
        "_problem_capability": capability,
        "spec": {"description": desc, "driven_by": "problem_solving"},
        "milestones": [
            {"text": f"The cause of {label} failing was identified.", "met": False, "met_at": None},
            {"text": "A decision was made to fix it or work around it.", "met": False, "met_at": None},
        ],
    }
    # Diagnostic plan = the abduced candidate causes, ranked best-first. Each step
    # names a cause to check and whether to try a fix or route around it. Falls
    # back to a generic two-step probe if abduction produced nothing.
    if hypotheses:
        steps = [
            (f"Check if it's {h['cause']} — "
             + ("try the fix." if h.get("fixable") else "if so, route around it."))
            for h in hypotheses[:4]
        ]
    else:
        steps = [
            f"Check whether {label} is reachable (config, circuit-breaker, recent errors).",
            f"Decide whether the {label} problem is something I can fix or must work around.",
        ]
    try:
        from brain.cognition.planning.goals import set_goal_plan
        set_goal_plan(goal, steps)
    except Exception as _e:
        record_failure("problem_refocus._build_fix_goal", _e)
    return goal


# ── State-machine transitions ──────────────────────────────────────────────────

def _start_fix(
    context: Dict[str, Any],
    capability: str,
    desc: str,
    parked_goal: Dict[str, Any],
    detect_totals: Dict[str, int],
) -> Dict[str, Any]:
    # Abduction (Peirce 1903): generate ranked candidate causes for the failure.
    hypotheses: List[Dict[str, Any]] = []
    try:
        from brain.cognition.planning.diagnosis import abduce
        hypotheses = abduce(capability, context, description=desc)
    except Exception as _e:
        record_failure("problem_refocus._start_fix", _e)

    fix_goal = _build_fix_goal(capability, desc, context, hypotheses=hypotheses)
    detect_total = detect_totals.get("llm", detect_totals.get("site", 0))
    _is_tool = capability in _TOOL_CAPABILITIES
    context["_active_problem"] = {
        "capability": capability,
        "description": desc,
        # Tool outages never park the committed goal — the investigation runs
        # in the background as an ordinary curiosity goal.
        "parked_goal": {} if _is_tool else parked_goal,
        "parked_title": None if _is_tool else (parked_goal.get("title") or parked_goal.get("name")),
        "background": _is_tool,
        "fix_goal": fix_goal,
        "phase": "diagnosing",
        "attempts": 0,
        "hypotheses": hypotheses,   # ranked candidate causes (serialisable)
        "hyp_idx": 0,               # which candidate we're currently testing
        "hyp_tries": 0,             # cycles spent on the current candidate's fix
        "started_cycle": _cycle(context),
        "detect_total": int(detect_total),
    }
    _lead = hypotheses[0]["cause"] if hypotheses else "an unknown cause"
    if _is_tool:
        # Register the investigation as an ordinary low-weight goal in the tree
        # so it competes for attention normally (capped weight) instead of
        # holding the focus slot.
        try:
            from brain.cognition.planning.goals import add_goal
            add_goal(dict(fix_goal))
        except Exception as _e:
            record_failure("problem_refocus._start_fix.2", _e)
        _bump_problem_signal(context, tool=True)
        update_working_memory({
            "content": (
                f"Noticed {desc} A tool I sometimes use is down — "
                f"I'll look into it when there's slack. Most likely {_lead}."
            ),
            "event_type": "problem_detected",
            "importance": 2, "priority": 1,
        })
        log_activity(
            f"[problem_refocus] Noted {capability} tool outage (background "
            f"curiosity goal). Leading hypothesis: {_lead}."
        )
        return {"status": "started_background", "capability": capability, "lead_cause": _lead}

    # Interrupt: the problem is now what he's working on.
    context["committed_goal"] = fix_goal
    _bump_problem_signal(context)

    parked_title = parked_goal.get("title") or parked_goal.get("name") or "my goal"
    update_working_memory({
        "content": (
            f"⚠️ Problem hit while working on '{str(parked_title)[:60]}': {desc} "
            f"Pausing it. Most likely {_lead}."
        ),
        "event_type": "problem_detected",
        "importance": 4, "priority": 3,
    })
    log_activity(
        f"[problem_refocus] Detected {capability} problem — parked "
        f"'{str(parked_title)[:60]}'. Leading hypothesis: {_lead}."
    )
    return {"status": "started", "capability": capability, "lead_cause": _lead}


def _advance_fix(context: Dict[str, Any], ap: Dict[str, Any]) -> Dict[str, Any]:
    capability = ap["capability"]
    # Re-assert focus every cycle (the GoalsAPI resets the slot before us) —
    # but never for a background tool investigation: that goal competes at its
    # capped weight, it does not get re-boosted into the focus slot.
    if not ap.get("background"):
        context["committed_goal"] = ap["fix_goal"]

    # Recovery (whether from a fix or self-healing) ends the episode.
    if _capability_healthy(capability, ap):
        return _finish(context, ap, workaround=False)

    ap["attempts"] = int(ap.get("attempts", 0)) + 1

    # ── Abductive repair walk ────────────────────────────────────────────────
    # Step through the ranked candidate causes. For a confirmed FIXABLE cause,
    # apply its repair and give it a couple of cycles to take effect; for an
    # unfixable cause, move straight to the next candidate. When no fixable
    # candidate remains (or the overall budget is spent), route around it.
    try:
        from brain.cognition.planning.diagnosis import (
            check_cause, apply_fix, FIX_TRIES_PER_CAUSE,
        )
        hyps: List[Dict[str, Any]] = ap.get("hypotheses") or []
        idx = int(ap.get("hyp_idx", 0))

        while idx < len(hyps):
            h = hyps[idx]
            if h.get("fixable") and check_cause(capability, h["key"], context):
                # Try the repair for this cause, bounded by FIX_TRIES_PER_CAUSE.
                apply_fix(capability, h["key"], context)
                ap["hyp_tries"] = int(ap.get("hyp_tries", 0)) + 1
                ap["hyp_idx"] = idx
                log_activity(
                    f"[problem_refocus] Repair attempt {ap['hyp_tries']}/{FIX_TRIES_PER_CAUSE} "
                    f"for cause: {h['cause']}"
                )
                if ap["hyp_tries"] >= FIX_TRIES_PER_CAUSE:
                    idx += 1                # this repair didn't take — escalate
                    ap["hyp_idx"] = idx
                    ap["hyp_tries"] = 0
                return {"status": "repairing", "capability": capability, "cause": h["cause"]}
            # Unfixable or not-currently-true cause → discard and escalate.
            idx += 1
            ap["hyp_idx"] = idx
            ap["hyp_tries"] = 0

        # Exhausted every candidate cause → can't fix it → work around it.
        return _finish(context, ap, workaround=True)
    except Exception as _e:
        record_failure("problem_refocus._advance_fix", _e)

    # Fallback safety net (abduction unavailable): bounded blind retry.
    if ap["attempts"] >= MAX_FIX_ATTEMPTS:
        return _finish(context, ap, workaround=True)
    return {"status": "diagnosing", "capability": capability, "attempts": ap["attempts"]}


def _record_repair_belief(ap: Dict[str, Any], capability: str, workaround: bool) -> None:
    """
    Record the diagnosed cause of this failure as a causal-graph edge, so the
    next abduction surfaces it from learned structure. A resolved problem is
    Pearl Level-2 evidence (do(fix) → recovery, an intervention); a workaround is
    weaker observational evidence. Writer and reader share diagnosis.failure_node
    so the loop is guaranteed to close.
    """
    hyps = ap.get("hypotheses") or []
    if not hyps:
        return
    idx = min(int(ap.get("hyp_idx", 0)), len(hyps) - 1)
    cause = str(hyps[idx].get("cause", "")).strip()
    if not cause:
        return
    try:
        from brain.cognition.planning.diagnosis import failure_node
        from brain.symbolic.causal_graph import update_edge
        update_edge(
            cause, failure_node(capability),
            confirmed=True,
            intervention=not workaround,   # a successful fix is an intervention
            source="repair",
        )
        log_activity(f"[problem_refocus] Learned cause of {capability} failure: {cause[:60]}")
    except Exception as _e:
        record_failure("problem_refocus._record_repair_belief", _e)


def _finish(context: Dict[str, Any], ap: Dict[str, Any], workaround: bool) -> Dict[str, Any]:
    capability = ap["capability"]
    label = _cap_label(capability)
    parked = ap["parked_goal"] if isinstance(ap.get("parked_goal"), dict) else {}
    fix_goal = ap.get("fix_goal") or {}

    fix_goal["status"] = "completed"
    fix_goal["last_updated"] = now_iso_z()

    # Close the loop: write what we diagnosed as a causal belief so future
    # abduction learns from it (Phase 4 — confirmed beliefs → causal graph).
    _record_repair_belief(ap, capability, workaround)

    if workaround:
        # Resume the original goal, but force it to find another way.
        unhealthy = list(context.get("_unhealthy_capabilities") or [])
        if capability not in unhealthy:
            unhealthy.append(capability)
        context["_unhealthy_capabilities"] = unhealthy

        parked["_avoid_capability"] = capability
        parked["plan"] = []  # discard the old plan → re-plan without the capability
        for k in ("_drift_detected", "_drift_score", "_replan_count", "_stalled"):
            parked.pop(k, None)
        parked["last_updated"] = now_iso_z()

        note = (
            f"Couldn't fix {label} myself — working around it. "
            f"Resuming '{str(ap.get('parked_title') or 'my goal')[:60]}' a different way."
        )
        _release(context, 0.5, "problem_workaround")  # relief at finding a way
        event = "problem_workaround"
    else:
        note = (
            f"{label} is working again — resuming "
            f"'{str(ap.get('parked_title') or 'my goal')[:60]}'."
        )
        _release(context, 0.8, "problem_resolved")
        event = "problem_resolved"

    if ap.get("background"):
        # Never held the focus slot — nothing to restore. Mark the registered
        # curiosity goal done in the tree so it completes like any other goal
        # (no eternal half-done state).
        try:
            from brain.cognition.planning.goals import mark_goal_status_by_name
            mark_goal_status_by_name(
                str(fix_goal.get("title") or fix_goal.get("name") or ""), "completed")
        except Exception as _e:
            record_failure("problem_refocus._finish", _e)
    elif parked:
        context["committed_goal"] = parked
    else:
        context["committed_goal"] = None  # nothing to resume; let normal flow pick up
    context.pop("_active_problem", None)

    update_working_memory({
        "content": note, "event_type": event, "importance": 3, "priority": 2,
    })
    log_activity(f"[problem_refocus] {note}")
    return {"status": event, "capability": capability}


# ── Public entry ────────────────────────────────────────────────────────────────

def handle_problem_refocus(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run once per cognitive cycle from ORRIN_loop, AFTER the committed goal slot
    has been resolved from the GoalsAPI. Drives the detect → diagnose →
    resume/workaround state machine and overrides context["committed_goal"]
    while a problem is being handled.
    """
    if context is None:
        return {"status": "noop"}

    # Keep the "avoid this capability while planning" set current every cycle.
    _reconcile_capability_health(context)

    cur = _fingerprint()
    prev = context.get("_failure_baseline")
    context["_failure_baseline"] = cur

    ap = context.get("_active_problem")
    if isinstance(ap, dict):
        return _advance_fix(context, ap)

    if prev is None:
        return {"status": "baseline_init"}  # first call just seeds the baseline

    detection = _detect_new_problem(prev, cur)
    if not detection:
        return {"status": "ok"}

    capability, desc, detect_totals = detection
    goal = bound_goal(context)
    if capability in _TOOL_CAPABILITIES:
        # Background curiosity investigation — needs no goal to park.
        if isinstance(goal, dict) and goal.get("_is_fix_goal"):
            return {"status": "already_fixing"}
        return _start_fix(context, capability, desc, {}, detect_totals)
    if not (isinstance(goal, dict) and (goal.get("title") or goal.get("name"))):
        return {"status": "no_goal_to_park", "capability": capability}
    if goal.get("_is_fix_goal"):
        return {"status": "already_fixing"}

    return _start_fix(context, capability, desc, goal, detect_totals)
