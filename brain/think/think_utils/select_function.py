# think/think_utils/select_function.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
from typing import Dict, Tuple, Union, Any
import uuid
import statistics as _statistics

from brain.think.bandit import contextual_bandit as bandit
from brain.config import tuning as _tuning
# Shared constants + scoring layer, extracted to selection/ (Phase 4D).
from brain.think.think_utils.selection.constants import FALLBACK_ACTIONS, _ALWAYS_EXCLUDE  # noqa: F401
# Candidate generation + dispatch constraints, extracted to selection/candidates.py (Phase 4D).
from brain.think.think_utils.selection.scoring import _emo_mode_function_map  # noqa: F401
from brain.think.think_utils.selection.state import (  # noqa: F401
    _get_directive_text, _get_focus_goal_text,
    _dominant_emotion_and_stagnation_signal, _recent_picks_from_ctx,
)
# Workspace→action routing, extracted to selection/routing.py (Phase 4D).
from brain.think.think_utils.selection.routing import _workspace_routes_for  # noqa: F401
from brain.think.think_utils.selection.candidates import (  # noqa: F401
    _planned_action_recruitment,
    _is_selectable_name, _is_dispatchable, _load_behavioral_names,
    _load_actions, _load_action_defs,
)
# Feature extraction, extracted to selection/features.py (Phase 4D).
from brain.think.think_utils.selection.features import extract_features  # noqa: F401
# Per-function scoring boosts, extracted to selection/boosts.py (Phase 4.5A).
from brain.think.think_utils.selection.boosts import (
    compute_workspace_prior, compute_unconscious_damp, compute_drive_pull,
    compute_chain_boost, compute_energy_boost, compute_emo_mode_boost,
    compute_emo_route_boost, compute_tension_boost, compute_neuro_boost,
    update_attention_debt, compute_helpfulness_boost, compute_outward_boost,
    compute_goal_recruit, apply_attention_mode, apply_monitor_route,
)
# Post-pick refinement (ε-exploration / threat-reflex / anti-repeat / meta-rut),
# extracted to selection/pick.py (Phase 4.5A).
from brain.think.think_utils.selection.pick import (
    apply_exploration_and_reflex, apply_antirepeat_and_metarut,
)
# Per-action scoring loop + its input bundle, extracted to selection/score_actions.py
# (Phase 4.5A).
from brain.think.think_utils.selection.score_actions import (
    ScoreInputs, score_candidates,
)
from brain.think.think_utils.selection.scoring import (  # noqa: F401
    _SEMANTIC_PRIORS, _emotion_pref_scores_for_dominant, _semantic_emotion_prior,
    _devalue_prior, _novelty_score, _bandit_pick_with_info, _bandit_hint_scores,
    _ensure_min_candidates,
)
_log = get_logger(__name__)

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
    _STATS_PATH, _STATS_CACHE, _CAPS_PATH, _CAPS_CACHE,
    _load_manifest, _capability_descriptions, _fns_tagged, _tag_weights,
    _tagged_or, _learned_stats,
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
    _dominant_emotion, _focus_goal_name,
)

# -------------------- small helpers (additive) --------------------
# Text/keyword-overlap utilities, extracted to selection/text.py (Phase 4D).
# Re-exported (noqa F401) so external importers + tests keep their existing
# `from …select_function import _tokenize/_capability_overlap/…` paths.
from brain.think.think_utils.selection.text import (  # noqa: E402,F401
    _tokenize, _kw_overlap_score, _CAP_STOPWORDS, _capability_overlap,
)
















# -------------------- public features (your original, unchanged) --------------------


# -------------------- main selection (multi-factor) --------------------
def select_function(context: Dict, *args: Any, **kwargs: Any) -> Union[str, Tuple[str, Dict, bool]]:
    """
    Back-compat selector with multi-factor scoring (no new files):
      - Directive alignment (keyword overlap)
      - Focus-goal alignment (keyword overlap)
      - Emotion bias (if AFFECT_STATE_FILE holds per-emotion fn weights)
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

    # Legacy signals from kwargs (if present)
    if "threat_detector_response" in kwargs:
        try:
            _amy = kwargs["threat_detector_response"]
            # threat_detector_response may be a dict (from process_affective_signals) or a float
            if isinstance(_amy, dict):
                feats["threat_detector_response"] = float(_amy.get("spike_intensity") or 0.0)
            else:
                feats["threat_detector_response"] = float(_amy)
        except Exception:
            feats["threat_detector_response"] = 0.0

    is_legacy = bool(args) or bool(kwargs)
    decision_id = str(uuid.uuid4())

    # Multi-factor data
    directive = _get_directive_text()
    focus_goal_text = _get_focus_goal_text()
    recent = _recent_picks_from_ctx(context)
    dominant, stagnation_signal = _dominant_emotion_and_stagnation_signal(context)
    emo_pref = _emotion_pref_scores_for_dominant(actions)
    band_hint = _bandit_hint_scores(actions, feats)

    # Semantic emotion priors: fire immediately from cycle 1.
    # As the learned map fills in, learned scores gain weight (0.5 each when both present).
    sem_prior = _semantic_emotion_prior(actions, dominant)

    # Weights: emotion raised to 0.25 now that it carries real signal.
    # Novelty weight reduced (was 0.20) — was driving look_outward to 33% of cycles.
    # stagnation_signal can still amplify novelty but from a lower base.
    # Values live in config.tuning (Finding 9 — single place to view/tune the
    # selector's parameter space).
    w_dir = _tuning.SELECTOR_W_DIR
    w_goal = _tuning.SELECTOR_W_GOAL
    w_emo = _tuning.SELECTOR_W_EMO
    base_w_novel = _tuning.SELECTOR_BASE_W_NOVEL   # reduced from 0.20 to prevent novelty-seeking domination
    w_novel = min(0.25, base_w_novel * (1.0 + 2.0 * stagnation_signal))  # stagnation_signal still helps, capped lower
    w_band = _tuning.SELECTOR_W_BAND  # bandit hint (raised 0.15→0.25, fn_selection_fix_v2 §3.3: now
                   # that the pool is clean (Phase 1) and the cold-arm optimism
                   # survives normalization, the learned/exploratory hint can
                   # compete with the additive boosts — still a hint, not decider.
    w_drive = _tuning.SELECTOR_W_DRIVE  # net drive-pull bias

    # === Attention-mode modulation (signal_router → selection) ===
    # The signal_router computes attention_mode from signal priority; here we
    # let that mode actually change what gets picked by adjusting weights
    # and adding per-function affinities.  Without this the mode is cosmetic.
    attention_mode = str(context.get("attention_mode") or "neutral")
    # Attention-mode modulation: adjusts dir/goal/emo/novel weights + builds the
    # per-function affinity map. (Multipliers/caps/boosts live in config.tuning.)
    w_dir, w_goal, w_emo, w_novel, _attn_fn_boost = apply_attention_mode(
        attention_mode, w_dir, w_goal, w_emo, w_novel
    )

    # Phase 3 (dual_process_loop.md §6.2 → §11): a Metacog Monitor breakthrough
    # that WON consciousness biases the deliberate pick toward its requested route
    # (re-plan / diagnose / decide / …). Adds to _attn_fn_boost and stamps
    # context["_bt_pending"] for the §20.1 dismissal-recalibration verdict.
    apply_monitor_route(context, _attn_fn_boost)

    # ── Workspace → action coupling (Fix 2; Redgrave, Prescott & Gurney 1999) ──
    # The Global Workspace already chose ONE conscious content this cycle. In the
    # brain, the basal-ganglia selector is driven by the currently salient cortical
    # representation — the "spotlight" and the motor selector are the SAME
    # bottleneck. Here they had drifted apart: the workspace winner only biased
    # selection when it was a Monitor breakthrough (above); for ordinary conscious
    # content (a feeling, the goal, a percept, a thought) it touched nothing, so
    # awareness and action were decoupled. This makes the conscious content a real
    # prior on the action pick, scaled by its salience — a strong additive bias,
    # NOT a hard override (I7: bias, never preempt). Monitor breakthroughs are
    # already routed above, so they're skipped here to avoid double-counting.
    # Disable with ORRIN_WORKSPACE_PRIOR=0.
    _workspace_prior = compute_workspace_prior(context, actions)

    # ── Unconscious damp (Fix 1 teeth; Dehaene 2014 ignition is all-or-none) ────
    # On a non-ignited cycle the loop stayed in low-power default mode: deliberate
    # System-2 functions should not win the slot. Damp the expensive/generative
    # deliberate functions so a quiet cycle drifts toward cheap default-mode work
    # (light reflection, rest) instead of spinning up planning/codegen/research.
    # Graded penalty, never a lockout — the floor still forces ignition eventually.
    # Disable with ORRIN_IGNITION_GATE=0 (the gate itself sets _conscious_cycle).
    _unconscious_damp = compute_unconscious_damp(context, actions)

    # Tension boost (active tensions → resolution fns) + deadline urgency
    # (imminent/overdue → goal-pursuit fns), folded into one map.
    _tension_boost = compute_tension_boost(context)

    # ── ACC→dlPFC control recruitment ───────────────────────────────────────
    # When the committed goal is blocked on a deliberate/generative action the
    # background Executive can't run (pursue marked goal["_needs_deliberate_action"],
    # e.g. decide_to_write_code), let the impasse that the block PRODUCES recruit the
    # conscious selector toward actually doing it — instead of toward affect-
    # regulation/introspection, which is where the impasse_signal prior otherwise
    # routes (soothing the feeling, not resolving the cause). Scaled by impasse so the
    # alarm clears by the goal getting done. Additive bias, never a forced pick (I7).
    _recruit_boost: Dict[str, float] = {}
    try:
        # An explicit planned handoff is already evidence of relevance. It
        # should not need to manufacture distress before becoming viable;
        # impasse amplifies the bounded recruitment instead.
        _recruit_boost = _planned_action_recruitment(context, actions)
    except Exception as _e:
        record_failure("select_function.select_function.recruit", _e)

    # Drive competition: compute per-function pull from competing motivations.
    # apply_drive_tensions() also bumps uncertainty and logs the hottest conflict.
    _drive_pull = compute_drive_pull(context, actions)

    # Function chaining bonus: if the previous function has a known high-reward
    # successor in function_chains.json, add its stored bonus to that successor.
    # This implements basal-ganglia-style procedural chunking learned during dream.
    _chain_boost = compute_chain_boost(recent, actions)

    # Energy orientation boost: high energy → action functions up; low/rest → reflection up.
    _energy_boost = compute_energy_boost(context, actions)

    # === Emotional mode → function selection translation ===
    # recommend_mode_from_affect_state() returns "focused"/"creative"/"exploratory" etc.
    # select_function reads attention_mode ("alert"/"wandering"/"drowsy") from signal_router.
    # These are two different vocabularies that never talked to each other — this block
    # bridges them by translating the emotional mode into direct function score boosts.
    _emo_mode_boost = compute_emo_mode_boost()

    # Compute goal status before neuromodulator block — used at line 749.
    # Was previously defined at line 815, causing NameError inside the try block
    # that silently killed all NE, stability_signal, and stress_load boosts.
    _goal_obj_pre = context.get("committed_goal") if context else None
    _has_committed_goal = (
        isinstance(_goal_obj_pre, dict)
        and bool(_goal_obj_pre.get("title") or _goal_obj_pre.get("name"))
        and _goal_obj_pre.get("status") not in ("completed", "abandoned", "failed")
    )

    # === Neuromodulator-driven function selection boosts ===
    # These translate chemical state (NE / stability_signal / stress_load) directly
    # into behavioral choice — without this these signals stay in affect_state and
    # do nothing.
    _neuro_boost = compute_neuro_boost(context, _has_committed_goal)

    # User attention debt: grows when user is present but no reply was generated;
    # feeds the helpfulness bias so unanswered presence escalates pressure to engage.
    # (Mutates context["_user_attention_debt"]; returns _user_spoke for the reason payload.)
    _user_spoke, _attention_debt = update_attention_debt(context)

    # Usefulness/helpfulness boost: when the user has spoken (or debt is owed),
    # helpful functions get a strong additive boost over intrinsic exploration/
    # reflection pull, and pure introspection is dampened — it can wait.
    _helpfulness_boost = compute_helpfulness_boost(actions, _user_spoke, _attention_debt)

    # Emotion routing — deep cognitive policy signal (not just prompt influence).
    # risk_estimate → verification; stagnation_signal → novelty; Confidence → prune; etc.
    _emo_route_boost = compute_emo_route_boost(context, actions)

    # Standing outward-presence boost (embodied/situated cognition): graded tiers
    # (artifact > exploration > sensing), reward-damped, outward-debt-amplified, and
    # goal-shielded so curiosity reads don't crowd out goal work. `_stats` is fetched
    # once here and reused by the scoring loop below.
    _stats = _learned_stats()
    _outward_boost = compute_outward_boost(context, actions, _stats, _has_committed_goal)

    # Goal-specific recruitment (function_selection_fix_v2.md §4.2): derive which
    # functions THIS goal needs from its OWN title/description/tags via the curated
    # capability descriptions, so different goal TYPES recruit visibly different
    # function sets rather than collapsing onto assess_goal_progress.
    _goal_recruit = compute_goal_recruit(context, actions, defs)

    # Curiosity nudge (Fix #3): when his exploration drive is up, make functions he
    # has rarely/never tried a little more appealing — an intrinsic pull toward
    # unfamiliar capability, NOT a forced override. Gated on exploration_drive, fades
    # as a function accumulates use, and skips the corrupted self-generated duplicates
    # so it surfaces real dormant tools rather than junk. This is how he comes to
    # *want* to exercise more of his repertoire instead of looping on a familiar few.
    _expl_drive = float(((context.get("affect_state") or {}).get("core_signals") or {}).get("exploration_drive", 0.0))
    # Cognitive-control strength for goal-shielding (Fix #1): how firmly a committed
    # goal is held (motivation + confidence), amplified below by impasse — the
    # curiosity trap forms precisely when stuck-but-committed. Used to damp blind
    # exploration so the single arg-max affect (exploration_drive) can't monopolise
    # selection against the goal. Miller & Cohen (2001) guided activation; Shah,
    # Friedman & Kruglanski (2002) goal shielding.
    _cs_now  = ((context.get("affect_state") or {}).get("core_signals") or {})
    _impasse = float(_cs_now.get("impasse_signal", 0.0) or 0.0)
    _goal_commit = max(0.0, min(1.0, 0.5 * (float(_cs_now.get("motivation", 0.0) or 0.0)
                                            + float(_cs_now.get("confidence", 0.0) or 0.0))))

    # Goal-type action gating (means-ends): an action that EXCLUSIVELY serves a
    # different kind of goal than the committed one must not win the slot — a
    # code-writing action on a research goal, or research on a code goal, is working
    # on the wrong end-state. Classify once here; penalise mismatches in the loop.
    # Only exclusive "doing" actions are gated; shared/reflective functions stay free.
    _goal_type = "general"
    _mismatch_fn = None
    _type_family: frozenset = frozenset()   # the committed goal type's instrumental actions
    if _has_committed_goal:
        try:
            from brain.cognition.planning.goal_types import (
                goal_type_of, is_mismatched_doing_action as _mismatch_fn, EXCLUSIVE_DOING,
            )
            _goal_type = goal_type_of(context.get("committed_goal") or {})
            # Type-based recruitment (EXPLORE_EXPLOIT_VALUE_PLAN §6.4 Fix A; Miller & Cohen
            # 2001 guided activation): a strongly-typed goal categorically recruits its OWN
            # means — e.g. an acquire_knowledge goal pulls research_topic/wikipedia_search —
            # which fuzzy capability-text overlap fails to distinguish from look_outward.
            _type_family = EXCLUSIVE_DOING.get(_goal_type, frozenset())
        except Exception as _gte:
            record_failure("select_function.goal_type", _gte)
            _mismatch_fn = None

    # Explore/exploit value governs the outward-exploration reads (replaces the
    # look_outward wall-clock cooldown + the standing MED outward boost for these fns,
    # so they are not double-counted). cognition.exploration_value.
    try:
        from brain.cognition.exploration_value import reach_value as _reach_value_fn, _OUTWARD_FNS as _REACH_FNS
    except Exception:
        _reach_value_fn = None
        _REACH_FNS = frozenset()

    # Prior outcome-devaluation baseline (LEARNING_DIAGNOSIS_2026-06-16 §5.2): the
    # median learned avg_reward over candidates that have enough evidence. A prior on
    # an arm whose reward sits below this median is decayed in the loop below, so a
    # static prior can no longer keep boosting an arm the agent has proven is low-yield.
    _deval_min = int(_tuning.SELECTOR_DEVAL_MIN_PULLS)
    _evidenced = [
        float((_stats.get(a) or {}).get("avg_reward", 0.5) or 0.5)
        for a in actions
        if int((_stats.get(a) or {}).get("count", 0) or 0) >= _deval_min
    ]
    _pool_median_reward = _statistics.median(_evidenced) if _evidenced else None
    context["_escape_available"] = any(
        name != "generate_intrinsic_goals"
        and name not in _GOAL_DELIBERATION_FNS
        for name in actions
    )

    # Bundle the loop's inputs and run the per-action scoring loop
    # (selection/score_actions.py): it sums the weighted components + boost maps
    # into each candidate's total, then applies the penalty/gate cascade.
    _score_inputs = ScoreInputs(
        w_dir=w_dir, w_goal=w_goal, w_emo=w_emo, w_novel=w_novel,
        w_band=w_band, w_drive=w_drive,
        directive=directive, focus_goal_text=focus_goal_text, recent=recent,
        emo_pref=emo_pref, sem_prior=sem_prior, band_hint=band_hint,
        drive_pull=_drive_pull, tension_boost=_tension_boost,
        attn_fn_boost=_attn_fn_boost, energy_boost=_energy_boost,
        helpfulness_boost=_helpfulness_boost, emo_route_boost=_emo_route_boost,
        chain_boost=_chain_boost, neuro_boost=_neuro_boost,
        emo_mode_boost=_emo_mode_boost, outward_boost=_outward_boost,
        goal_recruit=_goal_recruit, recruit_boost=_recruit_boost,
        workspace_prior=_workspace_prior, unconscious_damp=_unconscious_damp,
        has_committed_goal=_has_committed_goal, goal_type=_goal_type,
        mismatch_fn=_mismatch_fn, type_family=_type_family,
        stats=_stats, pool_median_reward=_pool_median_reward,
        expl_drive=_expl_drive, goal_commit=_goal_commit, impasse=_impasse,
        reach_value_fn=_reach_value_fn, reach_fns=_REACH_FNS,
    )
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
            chosen, scored, actions, recent, context, _expl_drive, _drive_pull
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
        chosen, scored, recent, context
    )

    # Reason payload
    features_on = {k: v for k, v in feats.items() if isinstance(v, (int, float)) and abs(v) > 0}
    ranked = [(n, round(s, 4)) for n, s, _ in scored[:6]]
    comp = {n: cs for (n, _, cs) in scored[:6]}

    reason = {
        "via": "multi-factor",
        "weights": {"dir": w_dir, "goal": w_goal, "emo": w_emo, "novel": w_novel, "band": w_band, "drive": w_drive},
        "features_on": features_on,
        "dominant_affect": dominant,
        "stagnation_signal": stagnation_signal,
        "attention_mode": attention_mode,
        "energy_state": str(context.get("energy_state") or "medium"),
        "energy_boosts": {k: round(v, 3) for k, v in _energy_boost.items() if abs(v) > 0.01},
        "neuro_boosts":  {k: round(v, 3) for k, v in _neuro_boost.items()  if abs(v) > 0.01},
        "workspace_prior": {k: round(v, 3) for k, v in _workspace_prior.items() if abs(v) > 0.01},
        "conscious_cycle": context.get("_conscious_cycle", True),
        "user_spoke": _user_spoke,
        "helpfulness_boosts": {k: round(v, 3) for k, v in _helpfulness_boost.items() if abs(v) > 0.01},
        "candidates": list(actions),
        "ranked": ranked,
        "component_scores": comp,
        "decision_id": decision_id,
        "anti_repeat": {
            "applied": override_applied,
            "stagnation_signal": stagnation_signal,
            "immediate_repeat": immediate_repeat,
        },
        "drive_conflicts": [
            {"drives": list(c["drives"]), "label": c["label"], "intensity": c["intensity"]}
            for c in (context.get("_drive_conflicts") or [])[:3]
        ],
    }

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
