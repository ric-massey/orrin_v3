# think/think_utils/select_function.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
from typing import Dict, Tuple, Union, Any
import uuid

from brain.think.bandit import contextual_bandit as bandit
# Shared constants + scoring layer, extracted to selection/ (Phase 4D).
from brain.think.think_utils.selection.constants import FALLBACK_ACTIONS, _ALWAYS_EXCLUDE  # noqa: F401
# Candidate generation + dispatch constraints, extracted to selection/candidates.py (Phase 4D).
from brain.think.think_utils.selection.scoring import _emo_mode_function_map  # noqa: F401
from brain.think.think_utils.selection.state import (  # noqa: F401
    _get_directive_text, _get_focus_goal_text,
    _dominant_signal_and_stagnation_signal, _recent_picks_from_ctx,
)
# Workspace→action routing, extracted to selection/routing.py (Phase 4D).
from brain.think.think_utils.selection.routing import _workspace_routes_for  # noqa: F401
from brain.think.think_utils.selection.candidates import (  # noqa: F401
    _planned_action_recruitment,
    _is_selectable_name, _is_dispatchable as _is_dispatchable, _load_behavioral_names,
    _load_actions as _load_actions, _load_action_defs,
)
# Feature extraction, extracted to selection/features.py (Phase 4D).
from brain.think.think_utils.selection.features import extract_features  # noqa: F401
# Post-pick refinement (ε-exploration / threat-reflex / anti-repeat / meta-rut),
# extracted to selection/pick.py (Phase 4.5A).
from brain.think.think_utils.selection.pick import (
    apply_exploration_and_reflex, apply_antirepeat_and_metarut,
)
# Per-cycle scoring-input assembly + the per-action scoring loop, extracted to
# selection/score_setup.py and selection/score_actions.py (Phase 4.5A).
from brain.think.think_utils.selection.score_setup import build_score_inputs
from brain.think.think_utils.selection.score_actions import score_candidates
from brain.think.think_utils.selection.scoring import (  # noqa: F401
    _SEMANTIC_PRIORS, _signal_pref_scores_for_dominant, _semantic_signal_prior,
    _devalue_prior, _novelty_score, _bandit_pick_with_info, _bandit_hint_scores,
    _ensure_min_candidates,
)
_log = get_logger(__name__)

# Sentinel distinguishing "threat_detector_response not passed" (new-style call,
# str return) from "passed" (legacy call, tuple return) — preserves the old
# `bool(kwargs)` legacy-detection semantics now that the parameter is explicit.
_UNSET: Any = object()

# Emergency-fallback candidates used when the cognitive-functions list is
# empty/missing or filtering empties the pool. Must be names present in
# COGNITIVE_FUNCTIONS (registry/cognition_registry.py) — ORRIN_loop dispatches
# `chosen` via COGNITIVE_FUNCTIONS.get(name); a name not in the registry is
# treated as "Unknown function requested" (bandit penalty + auto-repair),
# defeating the point of a *safe* fallback (Finding 11 — selector must always
# return a dispatchable function). The previous names (reflect_on_directive,
# plan_next_step, summarize_memory) were never registered under those names.



# Functions that should NEVER enter the cognitive selector — they are
# behavioral (outward-facing) or bookkeeping utilities that don't
# belong in the same bandit pool as real cognition choices.
# BEH_NAMES is the authoritative source; this is a belt-and-suspenders
# fallback for any that leak through before the file is read.

# ---------------------------------------------------------------------------
# Shape-based selectability filter (function_selection_fix_v2.md Phase 1).
#
# The candidate pool was polluted by ~160 non-behaviors: 76 corrupted
# auto-generated explore_* stubs (49 of them runaway "..._more_deeply" chains)
# plus per-cycle upkeep/accessor plumbing that already runs automatically each
# cycle. They diluted every novelty/bandit/curiosity signal and could win the
# argmax. _ALWAYS_EXCLUDE names such functions one-by-one; this filters them BY
# SHAPE so newly generated junk is dropped as a class without growing that list
# by hand (self-maintaining).
#
#   - explore_* : corrupted auto-generated goal-exploration stubs. The root
#                 cause is cured at source (behavior_generation suffix collapse +
#                 the persist_names explore_* filter); this is the in-selector
#                 containment / defense-in-depth.
#   - upkeep / accessor prefixes that already run automatically each cycle and,
#                 when *selected*, only double-applied (see _ALWAYS_EXCLUDE).
#
# is_*/maybe_* are deliberately NOT denied as a class — maybe_form_opinion and
# some is_* may be real cognition. Confirmed-plumbing accessors go in
# _NON_SELECTABLE_EXACT individually instead.

# Functions that start with a denied prefix but ARE real behaviors — keep them.





# Functions that directly serve the user or produce external value.
# When user is present, these get a strong additive boost that overrides
# the intrinsic exploration_drive/reflection pull of the semantic emotion priors.
# Phase 4: literal FALLBACK only — the live set is tag-derived below
# (tags "outward" + "goal-progress" in capability_descriptions.json), so a newly
# tagged function participates without touching this list. (E6 cleanup: the
# dead pursue_committed_goal entry was dropped — it runs in the Executive lane
# and is never in the pool.)
# Cached learned per-function stats (avg_reward + usage count). Used to make
# selection reward-aware (Fix #2) and to nudge curiosity toward dormant functions
# (Fix #3). Refreshed at most every ~15s so we never hit disk in the hot path.
from brain.utils.failure_counter import record_failure
# Catalog/manifest + learned-stats loaders, extracted to selection/catalog.py
# (Phase 4D). Cache dicts are shared singletons; re-export (noqa F401) for the
# direct-cache readers below + external importers of _capability_descriptions.
from brain.think.think_utils.selection.catalog import (  # noqa: E402,F401
    _STATS_PATH, _STATS_CACHE, _CAPS_PATH as _CAPS_PATH, _CAPS_CACHE,
    _load_manifest, _capability_descriptions as _capability_descriptions,
    _fns_tagged, _tag_weights, _tagged_or, _learned_stats,
)

# Membership sets (which functions each scoring block applies to) live in
# selection/tag_sets.py (Phase 4.5A) so the coordinator and the extracted scoring
# steps (selection/boosts.py) can share them without a circular import. Re-import
# (noqa F401) so the in-body references + the golden tag test's `sf._NEURO_NE_FOCUS`
# / `sf._OUTWARD_MED` access paths are unchanged.
from brain.think.think_utils.selection.tag_sets import (  # noqa: E402,F401
    _USER_HELPFUL_DEFAULT, _INTROSPECTION_DEFAULT, _GOAL_DELIBERATION_FNS,
    _DELIBERATION_FNS, _EXECUTION_FNS, _BLIND_EXPLORE_FNS, _SAFE_TO_EXPLORE_DEFAULT,
    _USER_HELPFUL_FUNCTIONS, _INTROSPECTION_FUNCTIONS, _SAFE_TO_EXPLORE,
    _MODE_ALERT_FNS, _MODE_ENGAGED_FNS, _MODE_WANDERING_FNS,
    _MODE_WANDERING_REFLECT_FNS, _MODE_DROWSY_FNS,
    _NEURO_NE_FOCUS, _NEURO_NE_SUPPRESS, _NEURO_CALM_SUPPRESS,
    _NEURO_STRESS_SUPPRESS, _NEURO_STRESS_RESTORE,
    _OUTWARD_HIGH, _OUTWARD_MED, _OUTWARD_LOW,
)





# -------------------- basic loaders (unchanged API) --------------------



# Mirrors ORRIN_loop._build_kwargs_for's mapping keys — the arg names the
# dispatcher can actually supply. A cognition function requiring any param OUTSIDE
# this set (e.g. save_goals(goals), train_on(text), apply_fix(capability, key),
# ask_llm(query)) can never be dispatched bare by the selector — it just gets
# picked, skips, wastes the cycle, and feeds a false impasse signal. We drop such
# helpers from the candidate pool so only genuinely selectable cognition competes.
# Self-maintaining: new non-dispatchable helpers are filtered automatically,
# without having to keep growing _ALWAYS_EXCLUDE by hand.
#
# NOTE: "goal"/"focus_goal" are deliberately NOT here. The dispatcher only supplies
# them WHEN a goal exists (committed_goal/focus_goal non-None); listing them as
# always-supplyable made functions like pursue_goal/try_to_accomplish pass the
# filter, then get skipped at dispatch whenever there was no goal — the bulk of
# error_log.txt and a false-impasse drip. Goal pursuit itself runs via
# pursue_committed_goal (needs only `context`), which is unaffected.






# Current-state readers, extracted to selection/state.py (Phase 4D).
from brain.think.think_utils.selection.state import (  # noqa: F401
    _dominant_signal, _focus_goal_name,
)

# -------------------- small helpers (additive) --------------------
# Text/keyword-overlap utilities, extracted to selection/text.py (Phase 4D).
# Re-exported (noqa F401) so external importers + tests keep their existing
# `from …select_function import _tokenize/_capability_overlap/…` paths.
from brain.think.think_utils.selection.text import (  # noqa: E402,F401
    _tokenize, _kw_overlap_score, _CAP_STOPWORDS,
    _capability_overlap as _capability_overlap,
)
















# -------------------- public features (your original, unchanged) --------------------


# -------------------- main selection (multi-factor) --------------------
def select_function(
    context: Dict[str, Any],
    *,
    threat_detector_response: Any = _UNSET,
) -> Union[str, Tuple[str, Dict[str, Any], bool]]:
    """
    Back-compat selector with multi-factor scoring (no new files):
      - Directive alignment (keyword overlap)
      - Focus-goal alignment (keyword overlap)
      - Emotion bias (if SIGNAL_STATE_FILE holds per-emotion fn weights)
      - Novelty/recency (rare & not recently used → higher)
      - stagnation_signal boosts novelty weight
      - Bandit scores used as a hint (small weight), not the decider

    - New style: select_function(context) -> "fn_name"
    - Legacy: select_function(context, ...) -> (fn_name, reason, is_action)
    """
    # Candidates + definitions (if present in JSON)
    actions, defs = _load_action_defs()
    actions = _ensure_min_candidates(actions)

    # LLM-as-tool gating: functions tagged requires_llm are skipped cleanly when
    # the LLM tool is down — not candidates, no error, no template fallback.
    # When the tool comes back they rejoin the pool automatically.
    try:
        from brain.utils.llm_gate import filter_llm_dependent
        filtered = filter_llm_dependent(actions)
        # If filtering empties the pool, fall back to safe defaults — never
        # restore the LLM-dependent candidates (the old `or actions` fallback
        # is exactly how requires_llm functions kept getting selected and
        # failing while the tool was down).
        actions = filtered if filtered else _ensure_min_candidates([])
    except Exception as _e:
        record_failure("select_function.select_function", _e)

    # Drop functions the dispatcher has already refused this session
    # (unsatisfiable required args). Selecting them again just burns the cycle.
    try:
        _undisp = set(context.get("_undispatchable_fns") or [])
        if _undisp:
            remaining = [a for a in actions if a not in _undisp]
            actions = remaining if remaining else _ensure_min_candidates([])
    except Exception as _e:
        record_failure("select_function.select_function.2", _e)

    feats = extract_features(context)

    # Legacy signals from the threat_detector_response kwarg (if passed)
    if threat_detector_response is not _UNSET:
        try:
            _amy = threat_detector_response
            # threat_detector_response may be a dict (from process_signals) or a float
            if isinstance(_amy, dict):
                feats["threat_detector_response"] = float(_amy.get("spike_intensity") or 0.0)
            else:
                feats["threat_detector_response"] = float(_amy)
        except Exception:
            feats["threat_detector_response"] = 0.0

    is_legacy = threat_detector_response is not _UNSET
    decision_id = str(uuid.uuid4())

    # Build all per-cycle scoring inputs (weights, priors, boost maps) once,
    # then run the per-action scoring loop (selection/score_actions.py).
    _score_inputs = build_score_inputs(actions, defs, context, feats)
    scored = score_candidates(actions, defs, _score_inputs, context)

    scored.sort(key=lambda t: t[1], reverse=True)
    if context.get("goal_lens"):
        try:
            _lens_ranked = [
                {"function": nm, "score": round(sc, 3), "lens_prior": round(float(parts.get("goal_lens", 0.0)), 3)}
                for nm, sc, parts in scored[:8]
            ]
            context.setdefault("_goal_lens_telemetry", {})["selection_top"] = _lens_ranked
        except Exception as exc:
            record_failure("select_function.goal_lens_telemetry", exc)

    # Consume the one-cycle goal-deliberation lockout now that scoring is done,
    # so it affects exactly this selection and not subsequent ones.
    context.pop("_suppress_goal_deliberation", None)

    if scored:
        chosen = scored[0][0]
        # ε-exploration → threat-arbiter reflex vote → inhibition cost (in order).
        chosen = apply_exploration_and_reflex(
            chosen, scored, actions, _score_inputs.recent, context,
            _score_inputs.expl_drive, _score_inputs.drive_pull
        )

    elif actions:
        # Validate the fallback exists in the registry before returning it;
        # an unknown name causes the bandit to penalise a selection it generated.
        try:
            from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS as _cf_reg
            _valid = [a for a in actions if a in _cf_reg]
            chosen = _valid[0] if _valid else ""
        except Exception:
            chosen = actions[0]
    else:
        chosen = ""

    # Anti-repeat tracking + stagnation signal + meta-rut breaker (the one path
    # that can override `chosen`: forces an execution fn after a full window of
    # deliberation-only picks).
    chosen, override_applied, immediate_repeat = apply_antirepeat_and_metarut(
        chosen, scored, _score_inputs.recent, context
    )

    # Reason payload
    features_on = {k: v for k, v in feats.items() if isinstance(v, (int, float)) and abs(v) > 0}
    ranked = [(n, round(s, 4)) for n, s, _ in scored[:6]]
    comp = {n: cs for (n, _, cs) in scored[:6]}

    reason = {
        "via": "multi-factor",
        "weights": {"dir": _score_inputs.w_dir, "goal": _score_inputs.w_goal, "emo": _score_inputs.w_emo, "novel": _score_inputs.w_novel, "band": _score_inputs.w_band, "drive": _score_inputs.w_drive},
        "features_on": features_on,
        "dominant_affect": _score_inputs.dominant,
        "stagnation_signal": _score_inputs.stagnation_signal,
        "attention_mode": _score_inputs.attention_mode,
        "energy_state": str(context.get("energy_state") or "medium"),
        "energy_boosts": {k: round(v, 3) for k, v in _score_inputs.energy_boost.items() if abs(v) > 0.01},
        "neuro_boosts":  {k: round(v, 3) for k, v in _score_inputs.neuro_boost.items()  if abs(v) > 0.01},
        "workspace_prior": {k: round(v, 3) for k, v in _score_inputs.workspace_prior.items() if abs(v) > 0.01},
        "conscious_cycle": context.get("_conscious_cycle", True),
        "user_spoke": _score_inputs.user_spoke,
        "helpfulness_boosts": {k: round(v, 3) for k, v in _score_inputs.helpfulness_boost.items() if abs(v) > 0.01},
        "candidates": list(actions),
        "ranked": ranked,
        "component_scores": comp,
        "decision_id": decision_id,
        "anti_repeat": {
            "applied": override_applied,
            "stagnation_signal": _score_inputs.stagnation_signal,
            "immediate_repeat": immediate_repeat,
        },
        "drive_conflicts": [
            {"drives": list(c["drives"]), "label": c["label"], "intensity": c["intensity"]}
            for c in (context.get("_drive_conflicts") or [])[:3]
        ],
    }

    # G2 (Run 11 §3): a decision whose driving context carries an answered
    # question's subject CITES it in this payload — the readable event that
    # proves an answer changed a later decision.
    try:
        from brain.cognition.answer_citation import annotate_reason
        annotate_reason(reason, context, chosen)
    except Exception as _e:
        record_failure("select_function.answer_citation", _e)

    # TD(λ): stamp eligibility trace for the chosen function at decision time.
    # bandit.update() in bandit_learn() will apply reward backward through these traces.
    if chosen:
        try:
            bandit.step_traces(chosen, feats)
        except Exception as _e:
            record_failure("select_function.select_function.18", _e)

    # §20.1 dismissal-recalibration: was the breakthrough that won consciousness
    # HONORED (the deliberate pick took its route) or DISMISSED (picked something
    # else despite it)? The Monitor consumes this next cycle to adapt the kind's
    # threshold — the watched governing the watcher.
    _btp = context.get("_bt_pending")
    if isinstance(_btp, dict) and _btp.get("route_fns"):
        context["_breakthrough_outcome"] = {
            "kind": _btp.get("kind"),
            "honored": chosen in set(_btp["route_fns"]),
        }
        context.pop("_bt_pending", None)

    if is_legacy:
        return chosen, reason, False
    return chosen
