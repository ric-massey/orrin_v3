# brain/cognition/metacog_analyze.py
#
# Metacognitive pattern analysis for metacog.py (CODEBASE_CLEANUP_PLAN 4.5C),
# lifted verbatim to bring that module under the 600-line soft limit. Runs at
# flush time over the recent function-pick / action-debt / affect history and
# returns the list of self-observations (rut / oscillation / goal-debt /
# stagnation patterns), with imperfect-metacognition noise (occasional misses +
# vague false-positive impressions). metacog.py re-imports metacog_analyze for
# metacog_flush and its external callers (calibration, behavioral_adaptation,
# life_capsule_ingest).
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import random
from collections import Counter
from typing import Any, Dict, List, Optional

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure

# How many recent function picks to look at for rut detection.
_RUT_WINDOW       = 8    # last N function picks
_RUT_THRESHOLD    = 0.75 # if one fn fills > this fraction → rut
_OSC_WINDOW       = 6    # pairs of picks to check for A↔B oscillation
_GOAL_DEBT_WARN   = 4    # cycles with action debt before surfacing it
_EMO_STAGNANT_WIN = 10   # recent_picks length proxy for stagnation check

# Probabilistic noise — metacognition is imperfect: patterns are missed and
# sometimes faint signals get amplified into vague feelings of wrongness.
_MISS_RATE      = 0.15   # probability that a real pattern goes unnoticed
_FALSE_POS_RATE = 0.08   # probability that a vague (unfounded) impression arises

_VAGUE_IMPRESSIONS = [
    "Something feels slightly off in my recent thinking, though I can't quite name it.",
    "There may be a pattern I'm not fully seeing — something about how I've been approaching things.",
    "I notice something shifting in how I've been responding lately, though I'm not certain what.",
]


def _dominant_signal(context: Dict[str, Any]) -> Optional[str]:
    """Return name of highest-value core affect signal, or None."""
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return None
    numeric = {k: float(v) for k, v in core.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    return max(numeric, key=numeric.get)


def _try_suppress(action: str, n_cycles: int, reason: str,
                  context: Optional[Dict[str, Any]] = None) -> None:
    """
    Tell the contextual bandit to mute `action` for N cycles. Best-effort:
    if the bandit can't be imported (in tests, partial installs) we just log.

    Also writes a selection-level cooldown (context["_fn_suppression"]) that
    select_function honors directly — the bandit mute is only a scoring hint
    (w_band), which is why rut notes alone changed nothing (audit §6).
    """
    if not action:
        return
    if isinstance(context, dict):
        try:
            _cc = int((context.get("cycle_count") or {}).get("count", 0) or 0)
            context.setdefault("_fn_suppression", {})[action] = _cc + int(n_cycles)
        except (ValueError, TypeError, AttributeError):  # intentional: bad cycle data → skip suppression
            pass
    try:
        from brain.think.bandit.contextual_bandit import suppress_action as _suppress
        _suppress(action, n_cycles)
        log_private(f"[metacog/suppress] '{action}' muted for {n_cycles} cycles — {reason}")
    except Exception as _e:
        log_private(f"[metacog/suppress] could not suppress '{action}': {_e}")


def metacog_analyze(context: Dict[str, Any]) -> List[str]:
    """
    Inspect cross-cycle signals and return a list of pattern-observation strings.
    Each observation is written to working memory so Orrin can notice and respond.
    Called inside metacog_flush, after trace condensation.
    """
    observations: List[str] = []
    picks: List[str] = list(context.get("recent_picks") or [])

    # ── 1. Function rut detection ─────────────────────────────────────────────
    # If one function dominates the last N picks, Orrin is stuck in a loop.
    if len(picks) >= _RUT_WINDOW:
        window = picks[-_RUT_WINDOW:]
        counts = Counter(window)
        top_fn, top_count = counts.most_common(1)[0]
        if top_count / _RUT_WINDOW >= _RUT_THRESHOLD:
            observations.append(
                f"Cognitive rut: I've chosen '{top_fn}' in {top_count} of my last "
                f"{_RUT_WINDOW} cycles. I may be stuck — consider whether something else needs attention."
            )
            # Mute the rut-causing action so the next cycle is forced to try something else.
            _try_suppress(top_fn, 15, f"rut ({top_count}/{_RUT_WINDOW})", context)

            # Fix 7 (explore_loop_fix_plan.md §5): when the rut fn is GOAL-DRIVEN, the
            # bandit mute can't stop it — the committed goal's pursuit/executive path
            # bypasses bandit suppression (E6). Feed the rut into Fix 2's hard escalator
            # by bumping THIS goal's monitor stall, so a persistent goal-driven rut
            # reaches the hard-disengage backstop instead of being only an inert mute.
            _GOAL_DRIVEN_FNS = {
                "search_own_files", "research_topic", "fetch_and_read", "wikipedia_search",
                "grep_files", "look_outward", "look_around", "seek_novelty",
                "pursue_committed_goal", "assess_goal_progress",
            }
            _gd = bound_goal(context)
            if isinstance(_gd, dict) and (_gd.get("title") or _gd.get("id")) and top_fn in _GOAL_DRIVEN_FNS:
                _gid = str(_gd.get("id") or _gd.get("title") or "goal")
                _gs = context.setdefault("_monitor_state", {}).setdefault(
                    _gid, {"sig": None, "stall": 0, "met": 0, "prog": None})
                _gs["stall"] = int(_gs.get("stall", 0)) + int(top_count)
                log_private(f"[metacog] goal-driven rut on '{top_fn}' → +{top_count} stall "
                            f"to '{_gid}' (Fix 7 → Fix 2 hard escalator).")

    # ── 2. Oscillation detection ──────────────────────────────────────────────
    # A↔B↔A↔B pattern in recent picks: two functions alternating.
    if len(picks) >= _OSC_WINDOW:
        window = picks[-_OSC_WINDOW:]
        # Check for strict alternation: every even and every odd index is the same
        evens = set(window[::2])
        odds  = set(window[1::2])
        if len(evens) == 1 and len(odds) == 1 and evens != odds:
            fn_a = evens.pop()
            fn_b = odds.pop()
            observations.append(
                f"Oscillation: I've been alternating between '{fn_a}' and '{fn_b}' "
                f"for {_OSC_WINDOW} cycles without resolution. There may be an unresolved tension here."
            )
            # Break the oscillation by suppressing one of the two — pick the one
            # most recently chosen so the immediate next cycle is forced elsewhere.
            _last_pick = window[-1]
            _try_suppress(_last_pick, 10, f"oscillation with '{fn_a if _last_pick == fn_b else fn_b}'", context)

    # ── 3. Goal debt avoidance ────────────────────────────────────────────────
    # action_debt grows when a committed goal gets no action taken on it.
    debt = int(context.get("action_debt", 0) or 0)
    goal = bound_goal(context) or {}
    goal_title = goal.get("title", "") if isinstance(goal, dict) else ""
    try:
        from brain.cognition.action_accounting import cycle_produced_goal_action
        _acted_on_goal = cycle_produced_goal_action(context)
    except Exception:
        _acted_on_goal = False
    if debt >= _GOAL_DEBT_WARN and goal_title and not _acted_on_goal:
        observations.append(
            f"Goal avoidance: {debt} consecutive cycles without taking action on "
            f"'{goal_title}'. I'm thinking but not doing."
        )
        # When debt becomes severe (~3x the warning threshold), suppress the
        # functions that have been substituting for goal action. Otherwise
        # observation alone can fail to break a 60+ cycle avoidance loop.
        if debt >= _GOAL_DEBT_WARN * 3 and picks:
            # Suppress the most-frequent non-goal-pursuit function from recent picks.
            _PURSUE = {"pursue_committed_goal", "pursue_goal", "advance_goal_plan"}
            recent_for_susp = picks[-_RUT_WINDOW:]
            substitute_counts = Counter(p for p in recent_for_susp if p not in _PURSUE)
            if substitute_counts:
                top_sub, n = substitute_counts.most_common(1)[0]
                if n >= 3:  # need real substitution pressure, not noise
                    _try_suppress(top_sub, 8, f"goal-avoidance ({debt} debt, {n}/{_RUT_WINDOW} subs)", context)

    # ── 4. Affective stagnation ───────────────────────────────────────────────
    # If the dominant affect hasn't changed across recent cycles, flag it.
    dom_now = _dominant_signal(context)
    prev_dom = context.get("_metacog_prev_dominant_signal")
    stagnant_count = int(context.get("_metacog_emo_stagnant_count", 0) or 0)

    if dom_now and dom_now == prev_dom:
        stagnant_count += 1
        context["_metacog_emo_stagnant_count"] = stagnant_count
        context["_metacog_emo_change_run"] = 0
        # Fires exactly ONCE per stagnation episode (== not >=), so it can't flood
        # the working memory per-cycle (Fix 8 — the alert was already single-shot).
        if stagnant_count == _EMO_STAGNANT_WIN:
            observations.append(
                f"Affective stagnation: '{dom_now}' has been my dominant affect for "
                f"{stagnant_count} consecutive cycles. This pattern may warrant deliberate attention."
            )
    else:
        # Fix 8: require a SUSTAINED change (≥2 cycles) before re-arming, so a single
        # -cycle affect blip can't reset the counter and let the same alert re-fire.
        _chg = int(context.get("_metacog_emo_change_run", 0) or 0) + 1
        context["_metacog_emo_change_run"] = _chg
        if _chg >= 2:
            context["_metacog_emo_stagnant_count"] = 0
    context["_metacog_prev_dominant_signal"] = dom_now

    # ── 5. Critique density ───────────────────────────────────────────────────
    # If the inner loop applied heavy critique this cycle, surface it as a note.
    inner_result = context.get("_last_inner_result") or {}
    if isinstance(inner_result, dict):
        if inner_result.get("critique_applied") and inner_result.get("escalated"):
            conf = inner_result.get("confidence", 0.5)
            observations.append(
                f"High uncertainty this cycle: reasoning escalated to deep model "
                f"(confidence={conf:.2f}). The topic may need more information or clarification."
            )

    # ── 6. Reflection–action imbalance ───────────────────────────────────────
    # If recent picks are all reflective functions with no action taken, surface it.
    _REFLECTIVE = frozenset({
        "reflection", "reflect_on_directive", "self_review", "narrative_update",
        "assess_goal_progress", "plan_next_step", "introspective_planning",
    })
    _ACTIVE = frozenset({
        "pursue_committed_goal", "plan_self_evolution", "generate_intrinsic_goals",
        "look_outward", "search_files", "search_own_files", "grep_files",
    })
    if len(picks) >= 6:
        recent6 = picks[-6:]
        reflective_count = sum(1 for p in recent6 if any(r in p for r in _REFLECTIVE))
        active_count = sum(1 for p in recent6 if any(a in p for a in _ACTIVE))
        if reflective_count >= 5 and active_count == 0:
            observations.append(
                "Reflection–action imbalance: my last 6 cycles have been almost entirely "
                "reflective with no outward action. I may be over-processing instead of moving."
            )

    # ── Calibration check ─────────────────────────────────────────────────────
    # Self-monitoring of how well predicted outcomes match reality. Sustained
    # over/under-confidence becomes an observation (Nelson & Narens 1990).
    try:
        from brain.cognition.calibration import calibration_observation, get_calibration
        _cal_obs = calibration_observation(context)
        if _cal_obs:
            # Rate-limit: this fired every cycle once |bias| crossed the
            # deadband, writing the same "I've been underconfident" line to
            # metacog_log/WM every ~12 seconds. Surface it only when the bias
            # has moved meaningfully since the last note, or after a long gap.
            _cal_now = get_calibration(context)
            _last = context.get("_metacog_last_cal_note") or {}
            _cycle = int(context.get("cycle_count", {}).get("count", 0)) if isinstance(context.get("cycle_count"), dict) else 0
            _bias_moved = abs(float(_cal_now.get("bias", 0.0)) - float(_last.get("bias", 99.0))) > 0.03
            _long_gap = (_cycle - int(_last.get("cycle", -10**9))) >= 100
            if _bias_moved or _long_gap:
                observations.append(_cal_obs)
                context["_metacog_last_cal_note"] = {
                    "bias": float(_cal_now.get("bias", 0.0)), "cycle": _cycle,
                }
    except Exception as _e:
        record_failure("metacog.metacog_analyze", _e)

    # ── Probabilistic noise — imperfect metacognition ─────────────────────────
    # Real patterns are occasionally missed; faint impressions occasionally arise.
    observations = [obs for obs in observations if random.random() > _MISS_RATE]
    if random.random() < _FALSE_POS_RATE:
        observations.append(random.choice(_VAGUE_IMPRESSIONS))

    return observations
