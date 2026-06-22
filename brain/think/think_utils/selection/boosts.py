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
