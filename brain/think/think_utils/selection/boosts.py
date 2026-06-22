# think/think_utils/selection/boosts.py
#
# Per-function scoring boosts for select_function() (CODEBASE_CLEANUP_PLAN
# Phase 4.5A). Each function here computes ONE additive boost map
# (``{fn_name: delta}``) that select_function() folds into the per-action score.
# They were lifted verbatim out of the ~1,120-line select_function() body so the
# coordinator reads as an ordered list of scoring steps and each step is
# independently unit-testable. Behavior is preserved exactly: same inputs, same
# record_failure tags, same returned deltas — the per-weight multipliers and
# caps stay in select_function()'s scoring loop, which is the combiner.
from __future__ import annotations

from typing import Dict, List

from brain.utils.failure_counter import record_failure
from brain.think.think_utils.selection.routing import _workspace_routes_for
from brain.think.think_utils.selection.catalog import _capability_descriptions
from brain.think.think_utils.selection.text import _capability_overlap
from brain.think.think_utils.selection.tag_sets import (
    _USER_HELPFUL_FUNCTIONS, _INTROSPECTION_FUNCTIONS,
    _NEURO_NE_FOCUS, _NEURO_NE_SUPPRESS, _NEURO_CALM_SUPPRESS,
    _NEURO_STRESS_SUPPRESS, _NEURO_STRESS_RESTORE,
    _OUTWARD_HIGH, _OUTWARD_MED, _OUTWARD_LOW,
)


def compute_workspace_prior(context: Dict, actions: List[str]) -> Dict[str, float]:
    """Awareness→action coupling (Fix 2; Redgrave, Prescott & Gurney 1999).

    The Global Workspace already chose ONE conscious content this cycle; make it
    a real prior on the action pick, scaled by salience — a strong additive bias,
    NOT a hard override (I7). Monitor breakthroughs are routed separately, so
    they're skipped here to avoid double-counting. Disable with
    ORRIN_WORKSPACE_PRIOR=0.
    """
    _workspace_prior: Dict[str, float] = {}
    try:
        import os as _os_wp
        if _os_wp.environ.get("ORRIN_WORKSPACE_PRIOR", "1") != "0":
            _gw_ws  = context.get("global_workspace") or {}
            _ws_src = str(_gw_ws.get("source", ""))
            _ws_sal = float(_gw_ws.get("salience", 0.0) or 0.0)
            if _ws_src and not _ws_src.startswith("monitor:") and _ws_sal > 0.0:
                # source → the functions that ACT ON that kind of conscious content.
                _ws_routes = _workspace_routes_for(_gw_ws)
                # Headroom 0.35: strong enough to be a genuine prior (cf. tension 0.15,
                # ACC recruit ≤0.6), bounded so it never dominates the arg-max alone.
                _ws_gain = 0.35 * max(0.0, min(1.0, _ws_sal))
                for _wfn, _wwt in _ws_routes.items():
                    if _wfn in actions:
                        _workspace_prior[_wfn] = _ws_gain * _wwt
    except Exception as _wpe:
        record_failure("select_function.workspace_prior", _wpe)
    return _workspace_prior


def compute_unconscious_damp(context: Dict, actions: List[str]) -> Dict[str, float]:
    """Unconscious damp (Fix 1 teeth; Dehaene 2014 ignition is all-or-none).

    On a non-ignited cycle, damp the expensive/generative deliberate functions so
    a quiet cycle drifts toward cheap default-mode work instead of spinning up
    planning/codegen/research. Graded penalty, never a lockout. Disable with
    ORRIN_IGNITION_GATE=0 (the gate itself sets _conscious_cycle).
    """
    _unconscious_damp: Dict[str, float] = {}
    try:
        if context.get("_conscious_cycle") is False:
            _EFFORTFUL_FNS = frozenset({
                "plan_next_step", "plan_self_evolution", "redirect_goal_plan",
                "adapt_subgoals", "generate_intrinsic_goals", "decide_to_write_code",
                "write_cognitive_function", "skill_synthesis", "self_review",
                "web_research", "look_outward", "search_own_files",
            })
            for _efn in _EFFORTFUL_FNS:
                if _efn in actions:
                    _unconscious_damp[_efn] = -0.30
    except Exception as _ude:
        record_failure("select_function.unconscious_damp", _ude)
    return _unconscious_damp


def compute_drive_pull(context: Dict, actions: List[str]) -> Dict[str, float]:
    """Per-function pull from competing motivations (drive competition).

    apply_drive_tensions() also bumps uncertainty and logs the hottest conflict
    (and populates context["_drive_conflicts"] / "_drive_strengths").
    """
    _drive_pull: Dict[str, float] = {}
    try:
        from brain.cognition.goal_competition import apply_drive_tensions, compute_drive_strengths, drive_pull_scores
        _conflicts = apply_drive_tensions(context)
        _strengths = context.get("_drive_strengths") or compute_drive_strengths(context)
        # Master plan 4.1: commitment strength is a tie-breaker input to goal
        # competition — a dearly-held vow pulls toward pursuit functions.
        _c = context.get("_commitment")
        _cs = float(_c.get("strength", 0.0)) if isinstance(_c, dict) else 0.0
        _drive_pull = drive_pull_scores(actions, _strengths, commitment_strength=_cs)
    except Exception as _e:
        record_failure("select_function.select_function.5", _e)
    return _drive_pull


def compute_chain_boost(recent: List[str], actions: List[str]) -> Dict[str, float]:
    """Function-chaining bonus from function_chains.json (procedural chunking).

    If the previous function has a known high-reward successor, add its stored
    bonus to that successor — basal-ganglia-style chunking learned during dream.
    """
    _chain_boost: Dict[str, float] = {}
    try:
        import json as _json
        from brain.paths import DATA_DIR as _DATA_DIR
        _chains_path = _DATA_DIR / "function_chains.json"
        if _chains_path.exists():
            _chains = _json.loads(_chains_path.read_text(encoding="utf-8"))
            _last_fn = (recent[-1] if recent else None)
            if _last_fn and _last_fn in _chains:
                for _succ, _entry in (_chains[_last_fn] or {}).items():
                    if _succ in actions:
                        _chain_boost[_succ] = float(
                            _entry.get("bonus", 0.0) if isinstance(_entry, dict) else 0.0
                        )
    except Exception as _e:
        record_failure("select_function.select_function.6", _e)
    return _chain_boost


def compute_energy_boost(context: Dict, actions: List[str]) -> Dict[str, float]:
    """Energy orientation: high energy → action fns up; low/rest → reflection up."""
    _energy_boost: Dict[str, float] = {}
    try:
        from brain.motivation.energy_orientation import energy_boost_scores as _ebs
        _energy_state = str(context.get("energy_state") or "medium")
        _action_bias  = float(context.get("action_vs_reflect_bias") or 0.5)
        _rest_mode    = bool(context.get("_rest_mode"))
        _energy_boost = _ebs(actions, _energy_state, _action_bias, _rest_mode)
    except Exception as _e:
        record_failure("select_function.select_function.7", _e)
    return _energy_boost


def compute_emo_mode_boost() -> Dict[str, float]:
    """Emotional mode → function score boosts.

    Bridges recommend_mode_from_affect_state()'s vocabulary
    ("focused"/"creative"/"exploratory") to direct per-function boosts via the
    weighted "emo_<mode>:<w>" tags in the capability manifest.
    """
    _emo_mode_boost: Dict[str, float] = {}
    try:
        from brain.affect.modes_and_affect import get_current_mode as _gcm
        from brain.think.think_utils.selection.scoring import _emo_mode_function_map
        _emo_mode = _gcm()
        # Phase 4: weighted "emo_<mode>:<w>" tags in the capability manifest are
        # the source of truth (literal fallbacks inside _emo_mode_function_map).
        _emo_mode_boost = _emo_mode_function_map().get(_emo_mode, {})
    except Exception as _e:
        record_failure("select_function.select_function.8", _e)
    return _emo_mode_boost


def compute_emo_route_boost(context: Dict, actions: List[str]) -> Dict[str, float]:
    """Emotion routing — deep cognitive policy signal (not just prompt influence).

    risk_estimate → verification; stagnation_signal → novelty; Confidence → prune; etc.
    """
    _emo_route_boost: Dict[str, float] = {}
    try:
        from brain.cognition.emotion_routing import emotion_bias as _eb
        _emo_state_full = context.get("affect_state") or {}
        for _fn in actions:
            _bias = _eb(_fn, _emo_state_full)
            if _bias != 0.0:
                _emo_route_boost[_fn] = _bias
    except Exception as _e:
        record_failure("select_function.select_function.10", _e)
    return _emo_route_boost


def compute_tension_boost(context: Dict) -> Dict[str, float]:
    """Tension + deadline urgency boost (folded into s_emo, capped, then ×w_emo).

    Active tensions nudge resolution-oriented functions; imminent/overdue
    deadlines bias toward the selectable goal-pursuit fns. Returns a single map —
    the deadline urgency lands on the same dict as the base tension boost (max of
    the two, preserving the original in-place semantics).
    """
    _tension_boost: Dict[str, float] = {}
    try:
        active_tensions = context.get("active_tensions") or []
        if active_tensions:
            for fn in ("reflection", "propose_value_revision", "plan_self_evolution", "self_review", "narrative_update"):
                _tension_boost[fn] = 0.15
    except Exception as _e:
        record_failure("select_function.select_function.3", _e)

    # Deadline urgency: imminent/overdue deadlines strongly bias toward goal pursuit
    try:
        _tp_alerts = (context.get("_temporal_pressure") or {}).get("deadline_alerts") or []
        if _tp_alerts:
            _phases = {a.get("phase", "") for a in _tp_alerts if isinstance(a, dict)}
            # E6: pursue_committed_goal lines dropped (dead — not in `actions`).
            # The deadline urgency now lands on the real selectable goal fns.
            if "overdue" in _phases or "imminent" in _phases:
                _tension_boost["assess_goal_progress"]  = max(_tension_boost.get("assess_goal_progress", 0), 0.25)
                _tension_boost["plan_next_step"]        = max(_tension_boost.get("plan_next_step", 0), 0.20)
            elif "approaching" in _phases:
                _tension_boost["assess_goal_progress"]  = max(_tension_boost.get("assess_goal_progress", 0), 0.15)
    except Exception as _e:
        record_failure("select_function.select_function.4", _e)
    return _tension_boost


def compute_neuro_boost(context: Dict, has_committed_goal: bool) -> Dict[str, float]:
    """Neuromodulator-driven function selection boosts.

    Translates chemical state (NE / stability_signal / stress_load) directly into
    behavioral choice — without this block these signals stay in affect_state and
    do nothing.
    """
    _neuro_boost: Dict[str, float] = {}
    try:
        _emo_full      = context.get("affect_state") or {}
        _ne_level      = float(_emo_full.get("_ne_proxy") or _emo_full.get("activation_level") or 0.0)
        _sero_level    = float(_emo_full.get("_stability_signal_proxy") or 0.0)
        _bs_nb         = context.get("body_sense") or {}
        _stress_streak = int(_bs_nb.get("_stress_streak", 0) or 0)
        _stress_load_load = min(1.0, max(0, _stress_streak - 20) / 200.0)

        # gain_signal (Sara 2009): high activation_level narrows attention to the goal at hand.
        # Suppresses exploration and mind-wandering; pushes pursuit and assessment up.
        # Phase 4: membership via "neuro_*" tags. E6: pursue_committed_goal
        # dropped from the focus list (dead — never in `actions`).
        if _ne_level > 0.45:
            _ne_scale = (_ne_level - 0.45) / 0.55  # 0→1 above threshold
            for fn in _NEURO_NE_FOCUS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) + _ne_scale * 0.22
            for fn in _NEURO_NE_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _ne_scale * 0.15

        # stability_signal (Dayan & Huys 2009): promotes patience and persistence.
        # High stability_signal → stay on the current goal, don't reflexively switch to regulation.
        # E6: the persistence boost used to land on pursue_committed_goal, which is
        # never in the pool — moved to attend_goal, the thin selectable "consciously
        # stay with the goal" proxy (same relocation as the commitment bias).
        if _sero_level > 0.12 and has_committed_goal:
            _sero_scale = min(1.0, (_sero_level - 0.12) / 0.38)
            _neuro_boost["attend_goal"] = (
                _neuro_boost.get("attend_goal", 0.0) + _sero_scale * 0.18
            )
            for fn in _NEURO_CALM_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _sero_scale * 0.10

        # stress_load allostatic load (McEwen 2007): sustained stress impairs executive function.
        # Suppress high-cost planning; push toward simple, restorative actions.
        if _stress_load_load > 0.10:
            for fn in _NEURO_STRESS_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _stress_load_load * 0.28
            for fn in _NEURO_STRESS_RESTORE:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) + _stress_load_load * 0.12
    except Exception as _e:
        record_failure("select_function.select_function.9", _e)
    return _neuro_boost


def update_attention_debt(context: Dict) -> "tuple[bool, int]":
    """User attention debt: grows when user is present but no reply was generated.

    Mutates context["_user_attention_debt"] in place (escalating social pressure)
    and returns (user_spoke, attention_debt) — both consumed by the helpfulness
    boost and the reason payload.
    """
    _user_spoke = bool((context.get("latest_user_input") or "").strip())
    _last_responded = (context.get("_last_responded_input") or "").strip()
    _latest_input   = (context.get("latest_user_input") or "").strip()
    if _user_spoke and _latest_input != _last_responded:
        # User spoke but hasn't been answered yet — increment debt
        _debt = int(context.get("_user_attention_debt", 0) or 0)
        context["_user_attention_debt"] = min(_debt + 1, 10)
    elif not _user_spoke:
        # User is quiet — slowly forgive the debt
        _debt = int(context.get("_user_attention_debt", 0) or 0)
        if _debt > 0:
            context["_user_attention_debt"] = max(0, _debt - 1)
    _attention_debt = int(context.get("_user_attention_debt", 0) or 0)
    return _user_spoke, _attention_debt


def compute_helpfulness_boost(actions: List[str], user_spoke: bool, attention_debt: int) -> Dict[str, float]:
    """Usefulness/helpfulness boost when the user has spoken (or debt is owed).

    Helpful functions get a strong additive boost that overrides intrinsic
    exploration_drive and reflection pull; pure introspection is dampened — it can
    wait. Attention debt makes the social pull escalate until Orrin replies.
    """
    _helpfulness_boost: Dict[str, float] = {}
    _debt_bonus = min(0.50, 0.10 * attention_debt)  # up to +0.50 after 5 ignored cycles
    if user_spoke or attention_debt > 0:
        for fn in actions:
            if fn in _USER_HELPFUL_FUNCTIONS:
                _helpfulness_boost[fn] = 0.45 + _debt_bonus  # persistent social pull
            elif fn in _INTROSPECTION_FUNCTIONS:
                _helpfulness_boost[fn] = -0.25  # introspection must wait when user is present
    return _helpfulness_boost


def compute_outward_boost(context: Dict, actions: List[str], stats: Dict, has_committed_goal: bool) -> Dict[str, float]:
    """Standing outward-presence boost (embodied/situated cognition).

    Graded by artifact-producing vs exploration vs sensing tiers, reward-damped
    (low-yield reads get a small nudge), amplified by outward-debt, and shielded
    (Shah/Friedman/Kruglanski 2002) so curiosity reads don't crowd out goal work
    while a committed goal is active. `stats` is the shared _learned_stats() map,
    passed in so it is fetched once per cycle.
    """
    _outward_boost: Dict[str, float] = {}
    for _fn in actions:
        if _fn in _OUTWARD_HIGH:
            _outward_boost[_fn] = 0.20
        elif _fn in _OUTWARD_MED:
            _outward_boost[_fn] = 0.13
        elif _fn in _OUTWARD_LOW:
            _outward_boost[_fn] = 0.07

    # Reward-aware damping (Fix #2): scale each boost by how well the function has
    # actually paid off — full boost at avg_reward ≥ 0.5, fading to 0.3× by ≤ 0.1.
    for _fn in list(_outward_boost.keys()):
        _ar = float((stats.get(_fn) or {}).get("avg_reward", 0.5))
        _rf = max(0.3, min(1.0, (_ar - 0.1) / 0.4))
        _outward_boost[_fn] *= _rf

    # Amplify outward boost when outward-debt is high (too many internal-only cycles).
    _od = int(context.get("_outward_debt", 0) or 0)
    if _od >= 8:
        _od_scale = min(2.0, 1.0 + (_od - 8) * 0.07)
        _outward_boost = {k: v * _od_scale for k, v in _outward_boost.items()}

    # Goal shielding (Shah, Friedman & Kruglanski 2002): while a committed goal is
    # active, scale DOWN the standing outward boost for pure-exploration reads so
    # look_outward can't monopolise cycles despite goal pursuit being higher-reward.
    if has_committed_goal:
        _EXPLORE_READS = frozenset({
            "look_outward", "seek_novelty", "look_around",
            "search_own_files", "grep_files", "search_files",
        })
        for _fn in list(_outward_boost.keys()):
            if _fn in _EXPLORE_READS:
                _outward_boost[_fn] *= 0.4
    return _outward_boost


def compute_goal_recruit(context: Dict, actions: List[str], defs: Dict) -> Dict[str, float]:
    """Goal-specific recruitment (function_selection_fix_v2.md §4.2).

    Derive which functions THIS goal needs from its OWN title/description/tags via
    the curated capability descriptions, so different goal TYPES recruit visibly
    different function sets rather than collapsing onto assess_goal_progress.
    Capped at +0.40 so it is comparable to s_attn and never dominates alone.
    """
    _goal_recruit: Dict[str, float] = {}
    try:
        _grg = context.get("committed_goal") or {}
        if isinstance(_grg, dict):
            _grg_text = " ".join(
                str(_grg.get(k, "") or "") for k in ("title", "name", "description")
            ).strip()
            # Goals created by generate_intrinsic_goals carry their description
            # nested at spec.description (often naming the exact functions to
            # use, e.g. "Use write_cognitive_function or write_tool ...") —
            # without it the recruiter only ever sees the title.
            _grg_spec = _grg.get("spec") or {}
            if isinstance(_grg_spec, dict):
                _spec_desc = str(_grg_spec.get("description") or "").strip()
                if _spec_desc:
                    _grg_text = (_grg_text + " " + _spec_desc).strip()
            _grg_tags = _grg.get("tags") or []
            if isinstance(_grg_tags, list) and _grg_tags:
                _grg_text = (_grg_text + " " + " ".join(str(t) for t in _grg_tags)).strip()
            if _grg_text:
                _caps = _capability_descriptions()
                for _nm in actions:
                    _ref = _caps.get(_nm) or defs.get(_nm, _nm)
                    _sim = _capability_overlap(_ref, _grg_text)
                    if _sim > 0.0:
                        _goal_recruit[_nm] = min(0.40, 0.6 * _sim)
    except Exception as _e:
        record_failure("select_function.select_function.11", _e)
    return _goal_recruit
