"""Per-cycle scoring-input assembly (Phase 4.5A, from select_function.py).

`build_score_inputs` computes the selector's scoring inputs once per cycle —
directive/goal text, emotion + bandit priors, the multi-factor weights (with
attention-mode modulation), and every per-function boost map — and returns them
as the `ScoreInputs` bundle that `score_actions.score_candidates` consumes. Kept
separate from the scoring loop so each stays focused and under the size limit.
"""
from __future__ import annotations

import statistics as _statistics
from typing import Any, Callable, Dict, List, Optional

from brain.config import tuning as _tuning
from brain.utils.failure_counter import record_failure
from brain.think.think_utils.selection.scoring import (
    _emotion_pref_scores_for_dominant, _semantic_emotion_prior, _bandit_hint_scores,
)
from brain.think.think_utils.selection.state import (
    _get_directive_text, _get_focus_goal_text, _recent_picks_from_ctx,
    _dominant_emotion_and_stagnation_signal,
)
from brain.think.think_utils.selection.candidates import _planned_action_recruitment
from brain.think.think_utils.selection.catalog import _learned_stats
from brain.think.think_utils.selection.boosts import (
    compute_workspace_prior, compute_unconscious_damp, compute_drive_pull,
    compute_chain_boost, compute_energy_boost, compute_emo_mode_boost,
    compute_emo_route_boost, compute_tension_boost, compute_neuro_boost,
    update_attention_debt, compute_helpfulness_boost, compute_outward_boost,
    compute_goal_recruit, apply_attention_mode, apply_monitor_route,
)
from brain.think.think_utils.selection.tag_sets import _GOAL_DELIBERATION_FNS
from brain.think.think_utils.selection.score_actions import ScoreInputs


def build_score_inputs(
    actions: List[str], defs: Dict[str, Any], context: Dict[str, Any], feats: Dict[str, Any]
) -> ScoreInputs:
    """Compute the selector's per-cycle scoring inputs once: directive/goal text,
    emotion + bandit priors, the multi-factor weights (with attention-mode
    modulation), and every per-function boost map. Has the side effects the setup
    has always had (monitor-route stamping, attention-debt update, _escape_available);
    returns the ScoreInputs bundle the per-action scoring loop consumes."""
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

    # Demand competition: compute per-function pull from competing motivations.
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
    _mismatch_fn: Optional[Callable[[str, str], bool]] = None
    _type_family: frozenset[str] = frozenset()   # the committed goal type's instrumental actions
    if _has_committed_goal:
        try:
            from brain.cognition.planning.goal_types import (
                goal_type_of, is_mismatched_doing_action, EXCLUSIVE_DOING,
            )
            _mismatch_fn = is_mismatched_doing_action
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
    _reach_value_fn: Optional[Callable[[str, Dict[str, Any]], float]] = None
    _REACH_FNS: frozenset[str] = frozenset()
    try:
        from brain.cognition.exploration_value import reach_value, _OUTWARD_FNS
        _reach_value_fn = reach_value
        _REACH_FNS = _OUTWARD_FNS
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

    return ScoreInputs(
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
        dominant=dominant, stagnation_signal=stagnation_signal,
        attention_mode=attention_mode, user_spoke=_user_spoke,
    )
