"""Bandit feature extraction for selection (Phase 4D, from select_function.py).

extract_features(context) builds the contextual-bandit feature dict the selector
and learner share: affect/neuromodulator state, user-presence, action-debt,
local-search intent, tension, focus-goal/self-model signals. Public — re-exported
from select_function for its external importers (loop_helpers, contextual_bandit,
local_search_signal). Imports its readers downward (state, text) — no cycle.
"""
from __future__ import annotations

from typing import Any, Dict

from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure
from brain.paths import SELF_MODEL_FILE
from brain.think.think_utils.selection.state import _dominant_signal, _focus_goal_name
from brain.think.think_utils.selection.text import _kw_overlap_score


def extract_features(context: Dict[str, Any]) -> Dict[str, float]:
    ctx = context or {}
    es = ctx.get("affect_state", {}) or {}
    features: Dict[str, float] = {
        "bias_action": float(ctx.get("bias_action", 0.0) or 0.0),
        "pending_tools": float(len(ctx.get("pending_tools", []) or [])),
        "resource_deficit": float(es.get("resource_deficit", 0.0) or 0.0),
        "has_focus_goal": 1.0 if _focus_goal_name() else 0.0,
    }
    emo = _dominant_signal()
    features[f"emo_{emo}"] = 1.0
    # Explicit intercept so the bandit can learn a baseline
    features["__bias__"] = 1.0

    # Neuromodulator state features — bandit learns context→reward associations over time.
    # These also feed directly into the neuromodulator boost block in select_function().
    _ne = float(es.get("_ne_proxy") or es.get("activation_level") or 0.0)
    if _ne > 0.3:
        features["ne_high"] = round(min(1.0, _ne), 3)
    _sero = float(es.get("_stability_signal_proxy") or 0.0)
    if _sero > 0.1:
        features["stability_signal"] = round(min(1.0, _sero), 3)
    _bs_f = ctx.get("body_sense") or {}
    _cort = min(1.0, max(0, int(_bs_f.get("_stress_streak") or 0) - 20) / 200.0)
    if _cort > 0.05:
        features["stress_load_load"] = round(_cort, 3)

    # User-presence signal: critical for learning that helpfulness is rewarded.
    # finalize.py gives agentic_action 1.0 reward and cognition_only 0.2 — but
    # only if the bandit can see user_present as a feature can it learn that pattern.
    if (ctx.get("latest_user_input") or "").strip():
        features["user_present"] = 1.0

    # Local-search intent signal (Nelson & Narens, 1990 monitoring / FOK).
    # Graded 0..1 — the bandit learns to associate this feature with
    # search_own_files getting rewarded (Auer et al., 2002 contextual UCB).
    local_search_strength = float(ctx.get("_local_search_signal", 0.0) or 0.0)
    if local_search_strength > 0.0:
        features["signal_local_search"] = local_search_strength

    # Action-debt feature: bandit can learn that high debt predicts action functions
    # over cognition functions (temporal difference credit assignment).
    debt = int(ctx.get("action_debt", 0) or 0)
    if ctx.get("_goal_pressure_amplified"):
        debt = int(debt * 1.5)  # amplify so select_function scores goal fns higher
    if debt > 0:
        features["action_debt"] = min(1.0, debt / 5.0)

    # Tension active: 1.0 when formative tensions exist.
    # Bandit learns that reflection/values functions are rewarded during tension.
    try:
        if ctx.get("active_tensions"):
            features["tension_active"] = 1.0
    except Exception as _e:
        record_failure("select_function.extract_features", _e)

    # Goal stalled: 1.0 when the committed goal has hit the stall threshold.
    # Bandit learns that plan_self_evolution/reflection get rewarded when stalled.
    try:
        _cg = ctx.get("committed_goal") or {}
        if isinstance(_cg, dict) and _cg.get("_stalled"):
            features["goal_stalled"] = 1.0
    except Exception as _e:
        record_failure("select_function.extract_features.2", _e)

    # Deadline pressure: graded signal so bandit can learn goal-pursuit functions
    # get rewarded when time is running out.
    try:
        _tp = ctx.get("_temporal_pressure") or {}
        _alerts = _tp.get("deadline_alerts") or []
        if _alerts:
            _phases = {a.get("phase", "") for a in _alerts if isinstance(a, dict)}
            if "overdue" in _phases or "imminent" in _phases:
                features["deadline_pressure"] = 1.0
            elif "approaching" in _phases:
                features["deadline_pressure"] = 0.6
            elif "near" in _phases:
                features["deadline_pressure"] = 0.3
    except Exception as _e:
        record_failure("select_function.extract_features.3", _e)

    # Identity investment: keyword overlap between the active goal and identity_story
    # + core_values. Higher overlap → bandit learns goal-pursuit functions get rewarded.
    try:
        _cg = ctx.get("committed_goal") or {}
        if isinstance(_cg, dict):
            _goal_text = ((_cg.get("title") or "") + " " + (_cg.get("description") or "")).strip()
            if _goal_text:
                _sm: Dict[str, Any] = load_json(SELF_MODEL_FILE, default_type=dict) or {}
                _id_story = str(_sm.get("identity_story", "") or "")
                _cv = _sm.get("core_values") or []
                _cv_text = " ".join(
                    (v["value"] if isinstance(v, dict) else str(v)) for v in _cv
                )
                _id_combined = (_id_story + " " + _cv_text)
                features["identity_investment"] = min(1.0, _kw_overlap_score(_goal_text, _id_combined) * 3.0)
    except Exception as _e:
        record_failure("select_function.extract_features.4", _e)

    # Distress-present feature: graded signal so the bandit can learn that
    # regulation functions produce higher reward when distress is elevated.
    # Aldao et al. (2010): strategy selection effectiveness is context-dependent —
    # the bandit must observe the context (distress level) to learn the association.
    # Without this feature the reward gradient exists but the bandit cannot see
    # the input that predicts it, so the pattern never generalises.
    try:
        from brain.affect.observers import negative_load
        _distress = negative_load(ctx.get("affect_state") or {})
        if _distress > 0.35:
            features["distress_present"] = min(1.0, _distress / 2.5)
    except Exception as _e:
        record_failure("select_function.extract_features.5", _e)

    return features
