"""Per-action scoring loop (Phase 4.5A, from select_function.py).

`score_candidates` is the heart of the selector: for each candidate function it
sums the weighted multi-factor components (directive/goal overlap, emotion prior,
novelty, bandit hint, drive pull, and the ~20 additive boost maps) into a `total`,
then applies the penalty/gate cascade (no-goal suppression, goal shielding,
goal-type gating, behavioral-adaptation pressure, deliberation lockouts,
commitment/contestation boosts, novelty pressure, repetition penalty, metacog
rut suppression). Inputs are bundled into `ScoreInputs` so the loop's full
dependency surface is explicit and unit-testable in isolation; the coordinator
(`select_function`) builds the bundle once and calls this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

from brain.control_signals.reward_signals.action_reward_ema import (
    get_associability, get_expected, _ASSOC_DEFAULT, _DEFAULT as _EXPECTED_DEFAULT,
)
from brain.utils.failure_counter import record_failure
from brain.think.think_utils.selection.text import _kw_overlap_score
from brain.think.think_utils.selection.scoring import _novelty_score, _devalue_prior
from brain.think.think_utils.selection.tag_sets import (
    _BLIND_EXPLORE_FNS, _GOAL_DELIBERATION_FNS,
)

# Directed (uncertainty-seeking) exploration weight. Gershman (2018), "Deconstructing
# the human algorithms for exploration", Cognition 173:34 — humans add an
# uncertainty bonus to actions whose value is poorly known, on top of random
# exploration. We use Pearce-Hall associability (action_reward_ema) as that
# uncertainty signal, measured RELATIVE to its neutral prior so a well-modelled
# action gets no bonus and only genuinely volatile/under-explored ones are lifted.
_W_EXPLORE = 0.12

# Direct EXPLOITATION weight (T2.1 / WS-2). The selector already had the uncertainty
# (explore) half but no reward-LEVEL half, so the highest-reward action could be
# selected almost never (run_forgetting_cycle, EMA 0.755, picked 2×). Lift an action
# by how far its learned expected reward exceeds the neutral prior — the exploit
# counterpart to s_explore (clamped at 0 so below-prior actions aren't double-penalised
# beyond their satiety/devaluation terms).
_W_EXPLOIT = 0.25

# Per-action SATIETY suppression weight (T2.1 / WS-2). A fully-satiated action was
# still selected most because suppression only ever touched the OUTWARD family
# (via reach_value). Generalise it: any over-used action is damped by its decayed
# satiety. Outward fns are exempt here — reach_value already folds their satiety in,
# so applying it again would double-count.
_W_SATIETY = 0.30

# No-goal suppression: pursue_committed_goal and assess_goal_progress are
# useless (and waste a full LLM cycle) when there is no committed goal.
# E6: pursue_committed_goal dropped (not in pool); the no-goal suppression
# still applies to the real deliberate goal-pursuit fns.
_GOAL_PURSUIT_FNS = frozenset({"assess_goal_progress", "adapt_subgoals"})


@dataclass
class ScoreInputs:
    """Everything the per-action scoring loop reads, computed once per selection
    by the coordinator (weights, the directive/goal text, and the per-function
    boost maps + goal-context scalars). Bundling them makes the loop's inputs
    explicit and lets it be exercised in isolation."""
    # Multi-factor weights (post attention-mode modulation)
    w_dir: float
    w_goal: float
    w_emo: float
    w_novel: float
    w_band: float
    w_drive: float
    # Text / recency
    directive: str
    focus_goal_text: str
    recent: List[str]
    # Emotion + bandit priors
    emo_pref: Dict[str, float]
    sem_prior: Dict[str, float]
    band_hint: Dict[str, float]
    # Per-function additive boost maps
    drive_pull: Dict[str, float]
    tension_boost: Dict[str, float]
    attn_fn_boost: Dict[str, float]
    energy_boost: Dict[str, float]
    helpfulness_boost: Dict[str, float]
    emo_route_boost: Dict[str, float]
    chain_boost: Dict[str, float]
    neuro_boost: Dict[str, float]
    emo_mode_boost: Dict[str, float]
    outward_boost: Dict[str, float]
    goal_recruit: Dict[str, float]
    recruit_boost: Dict[str, float]
    workspace_prior: Dict[str, float]
    unconscious_damp: Dict[str, float]
    # Goal context
    has_committed_goal: bool
    goal_type: str
    mismatch_fn: Optional[Callable[[str, str], bool]]
    type_family: FrozenSet[str]
    # Learned stats + devaluation baseline
    stats: Dict[str, Any]
    pool_median_reward: Optional[float]
    # Exploration / commitment scalars
    expl_drive: float
    goal_commit: float
    impasse: float
    # Explore/exploit reach value (outward reads)
    reach_value_fn: Optional[Callable[[str, Dict[str, Any]], float]]
    reach_fns: FrozenSet[str]
    # Carried through for the reason payload (not read by the scoring loop)
    dominant: str
    stagnation_signal: float
    attention_mode: str
    user_spoke: bool


def score_candidates(
    actions: List[str], defs: Dict[str, Any], si: ScoreInputs, context: Dict[str, Any]
) -> List[Tuple[str, float, Dict[str, float]]]:
    """Score every candidate, returning (name, total, component_scores) tuples
    (unsorted). See module docstring for the component/gate breakdown."""
    # Unpack the bundle back into the names the loop body uses verbatim, so the
    # scoring math is byte-for-byte the same as when it lived inline.
    w_dir, w_goal, w_emo, w_novel, w_band, w_drive = (
        si.w_dir, si.w_goal, si.w_emo, si.w_novel, si.w_band, si.w_drive
    )
    directive = si.directive
    focus_goal_text = si.focus_goal_text
    recent = si.recent
    emo_pref = si.emo_pref
    sem_prior = si.sem_prior
    band_hint = si.band_hint
    _drive_pull = si.drive_pull
    _tension_boost = si.tension_boost
    _attn_fn_boost = si.attn_fn_boost
    _energy_boost = si.energy_boost
    _helpfulness_boost = si.helpfulness_boost
    _emo_route_boost = si.emo_route_boost
    _chain_boost = si.chain_boost
    _neuro_boost = si.neuro_boost
    _emo_mode_boost = si.emo_mode_boost
    _outward_boost = si.outward_boost
    _goal_recruit = si.goal_recruit
    _recruit_boost = si.recruit_boost
    _workspace_prior = si.workspace_prior
    _unconscious_damp = si.unconscious_damp
    _has_committed_goal = si.has_committed_goal
    _goal_type = si.goal_type
    _mismatch_fn = si.mismatch_fn
    _type_family = si.type_family
    _stats = si.stats
    _pool_median_reward = si.pool_median_reward
    _expl_drive = si.expl_drive
    _goal_commit = si.goal_commit
    _impasse = si.impasse
    _reach_value_fn = si.reach_value_fn
    _REACH_FNS = si.reach_fns

    # Score each action
    scored: List[Tuple[str, float, Dict[str, float]]] = []
    for name in actions:
        definition = defs.get(name, name)
        s_dir  = _kw_overlap_score(definition, directive)
        s_goal = _kw_overlap_score(definition, focus_goal_text)
        s_nov  = _novelty_score(name, recent)
        s_band = float(band_hint.get(name, 0.0))
        s_drv  = float(_drive_pull.get(name, 0.0))  # [-1..1]: net drive pull

        # Blend learned map with semantic prior: equal weight when both present,
        # full prior when map is empty, full learned when prior has no opinion.
        learned = float(emo_pref.get(name, 0.0))
        prior   = float(sem_prior.get(name, 0.0))
        # Outcome-devaluation (§5.2): decay the static prior if this fn has proven
        # low-yield relative to its peers (see _devalue_prior).
        prior = _devalue_prior(prior, name, _stats, _pool_median_reward)
        if learned > 0 and prior > 0:
            s_emo = 0.5 * learned + 0.5 * prior
        elif learned > 0:
            s_emo = learned
        else:
            s_emo = prior * 0.85   # slight discount: pure prior, not yet validated

        s_emo = min(1.0, s_emo + _tension_boost.get(name, 0.0))
        s_attn   = float(_attn_fn_boost.get(name, 0.0))
        s_energy = float(_energy_boost.get(name, 0.0))
        s_help   = float(_helpfulness_boost.get(name, 0.0))
        # EVC cost gating (proactive_resource_plan.md Phase 3 / C2): a payoff-
        # discounted, depletion-scaled COST penalty (≤ 0) — proactively paces effort
        # by down-weighting expensive-but-low-payoff functions BEFORE spending on
        # them. Reward/depletion-mode are handled elsewhere (no double-count). Shenhav
        # et al. (2013). Fail-safe; 0 when disabled.
        s_evc = 0.0
        try:
            from brain.cognition.cost_prediction import evc_selection_adjust as _evc_adj
            s_evc = _evc_adj(name, float((_stats.get(name) or {}).get("avg_reward", 0.5) or 0.5), context)
        except Exception:
            s_evc = 0.0
        s_emo_route = float(_emo_route_boost.get(name, 0.0))
        s_chain     = float(_chain_boost.get(name, 0.0))
        s_neuro     = float(_neuro_boost.get(name, 0.0))
        s_emo_mode  = float(_emo_mode_boost.get(name, 0.0))
        s_outward   = float(_outward_boost.get(name, 0.0))
        # Explore/exploit value for outward reads (habituation + curiosity-gap +
        # opportunity-cost + boredom). For these fns it REPLACES the standing MED
        # outward boost (zero s_outward to avoid double-counting).
        s_reach = 0.0
        if _reach_value_fn is not None and name in _REACH_FNS:
            s_reach = _reach_value_fn(name, context)
            s_outward = 0.0
        # Type-based recruitment (Fix A): the committed goal type's own means get a
        # decisive boost, comparable to the emotion prior.
        s_type_recruit = 0.20 if name in _type_family else 0.0
        s_goal_recruit = float(_goal_recruit.get(name, 0.0))  # §4.2 goal-derived
        s_recruit      = float(_recruit_boost.get(name, 0.0))  # ACC→action recruitment
        s_workspace    = float(_workspace_prior.get(name, 0.0))   # Fix 2: awareness→action
        s_uncon_damp   = float(_unconscious_damp.get(name, 0.0))  # Fix 1: quiet-cycle damp
        # Directed exploration: lift actions whose payoff is currently uncertain
        # (associability above its neutral prior). Clamped at 0 so confidently
        # modelled actions are neither bonused nor penalised (Gershman 2018).
        s_explore   = _W_EXPLORE * max(0.0, get_associability(context, name) - _ASSOC_DEFAULT)
        # Direct exploitation: RUN4_FIX_PLAN A4 promotes this from one additive
        # term (~0.12 max among ~25) to a MULTIPLICATIVE modulator applied after
        # the sum, so the learned reward EMA has real authority over selection
        # (the 2026-07-03 run: EMA contributed too little to outvote a 0.706
        # affect coupling). s_exploit is kept only for telemetry now — it is NOT
        # summed into `total` (that would double-count the modulator).
        s_exploit   = _W_EXPLOIT * max(0.0, get_expected(context, name) - _EXPECTED_DEFAULT)
        # General satiety suppression (non-outward; outward handled by reach_value).
        s_satiety = 0.0
        if name not in _REACH_FNS:
            try:
                from brain.cognition.exploration_value import action_satiety as _action_satiety
                s_satiety = -_W_SATIETY * _action_satiety(name)
            except Exception as exc:
                record_failure("select_function.action_satiety", exc)

        # Curiosity nudge toward dormant capability (Fix #3).
        s_curio = 0.0
        if _expl_drive > 0.5 and "more_deeply_more" not in name:
            _nuse = int((_stats.get(name) or {}).get("count", 0))
            if _nuse < 8:
                s_curio = 0.18 * (_expl_drive - 0.5) * (1.0 - _nuse / 8.0)

        s_goal_lens = 0.0
        try:
            from brain.cognition.goal_lens import action_prior as _goal_lens_prior
            s_goal_lens = _goal_lens_prior(context.get("goal_lens"), name, definition)
        except Exception as exc:
            record_failure("select_function.goal_lens_prior", exc)
        total = (w_dir * s_dir) + (w_goal * s_goal) + (w_emo * s_emo) + (w_novel * s_nov) + (w_band * s_band) + (w_drive * s_drv) + s_attn + s_energy + s_help + s_emo_route + s_chain + s_neuro + s_emo_mode + s_outward + s_reach + s_type_recruit + s_goal_recruit + s_goal_lens + s_recruit + s_explore + s_satiety + s_curio + s_evc + s_workspace + s_uncon_damp

        # A4 (RUN4_FIX_PLAN §1.3, S9): give the learned reward EMA real authority.
        # For a MATURE action (>=8 scored observations — same maturity gate s_curio
        # uses), scale the whole positive score by (0.5 + EMA): neutral 0.5 → ×1.0,
        # a low-EMA action (look_outward ~0.150 → ×0.65) is demoted, a high-EMA one
        # (research_topic ~0.674 → ×1.17) is promoted. Immature actions keep ×1.0 —
        # exploration stays the additive s_explore/s_curio term's job. Guarded on
        # total>0 so the modulator can't perversely lift a suppressed (negative)
        # score, consistent with the repetition/suppression multipliers below.
        _n_obs = int((_stats.get(name) or {}).get("count", 0))
        if _n_obs >= 8 and total > 0:
            _ema = float(get_expected(context, name))
            total *= max(0.0, 0.5 + _ema)

        # (Dual-process Phase 2) The pursue-on-cooldown yield band-aid was removed
        # here: pursue_committed_goal is no longer a deliberate candidate (it runs in
        # the Executive lane), so it can never be picked or "spin" the slot.

        # Suppress goal-pursuit functions when there is no active goal to pursue.
        # -0.65 overcomes the strongest emotional prior (motivation→pursue: 0.9 × 0.25w = 0.225)
        # plus attention boost (0.15), so the penalty is always decisive.
        if not _has_committed_goal and name in _GOAL_PURSUIT_FNS:
            total -= 0.65

        # Goal-shielding / cognitive control (Fix #1): when a committed goal is
        # active, damp BLIND exploration (curiosity reads with no relevance to this
        # goal) so a pinned exploration_drive can't win the arg-max routing against
        # goal work. Goal-RELEVANT exploration is exempt — s_goal_recruit > 0 means
        # the goal's own text recruits this function (e.g. outward research for a
        # research goal). Graded and capped (never a lockout): the read stays
        # rankable, just no longer dominant. This is the layer the old 0.4× outward-
        # boost damp was too weak to provide — it only touched s_outward, leaving the
        # far larger s_emo exploration prior (≈0.19 of total) untouched.
        # Fix B (EXPLORE_EXPLOIT_VALUE_PLAN §6.4): exempt from shielding only on
        # MEANINGFUL goal-relevance, not any positive fuzzy overlap. A blind-explore
        # read with a spurious ~0.1 capability overlap on a research goal (look_outward
        # measured at 0.106) used to clear `s_goal_recruit > 0` and compete unshielded —
        # the goal-neglect leak (Duncan et al. 1996). Require a real overlap floor OR
        # membership in the goal type's own instrumental family.
        _meaningfully_relevant = (s_goal_recruit >= 0.15) or (name in _type_family)
        if _has_committed_goal and name in _BLIND_EXPLORE_FNS and not _meaningfully_relevant:
            total -= min(0.40, 0.15 + 0.20 * _goal_commit + 0.10 * _impasse)

        # Goal-type gate: decisively suppress an action that exclusively serves a
        # DIFFERENT goal type (e.g. decide_to_write_code on an "understand X" goal).
        # -0.6 overcomes even the impasse→action recruitment boost so cross-type
        # actions can't win — the action that produces THIS goal's end-state does.
        if _mismatch_fn is not None and _mismatch_fn(_goal_type, name):
            total -= 0.6

        # Behavioral adaptation signals (Carver & Scheier, 1982 control systems):
        # Set by behavioral_adaptation.py when metacog detects recurring patterns.
        # _force_action_next: reflection imbalance detected — boost action fns.
        if context.get("_force_action_next"):
            _ADAPT_ACTION_FNS = frozenset({
                "pursue_goal", "look_outward",  # E6: dropped pursue_committed_goal (dead)
                "search_own_files", "seek_novelty", "generate_intrinsic_goals",
                "plan_self_evolution", "plan_next_step",
            })
            _ADAPT_REFLECT_FNS = frozenset({
                "reflection", "self_review", "narrative_update",
                "assess_goal_progress", "introspective_planning",
            })
            if name in _ADAPT_ACTION_FNS:
                total += 0.30
            elif name in _ADAPT_REFLECT_FNS:
                total -= 0.20

        # Goal-deliberation lockout: behavioral_adaptation sets this once
        # action_debt is high enough that soft pressure has demonstrably failed.
        # A large penalty (not removal) keeps the candidate rankable as a last
        # resort but ensures any genuine execution option outscores it.
        if context.get("_suppress_goal_deliberation") and name in _GOAL_DELIBERATION_FNS:
            total -= 0.80
        if context.get("_suppress_intrinsic_goals") and name == "generate_intrinsic_goals":
            total -= 1.0

        # F5 (2026-07-05 findings): pool-depth term. When generated candidates
        # far outrun attempts (07-05: 1,508 → 224, this action again the #1
        # conscious pick at 45/183), generating more is displacement activity —
        # demote it in proportion to the backlog. Ratio computed once per cycle
        # (scoreboard read cached on context).
        if name == "generate_intrinsic_goals":
            _cc = context.get("cycle_count")
            _cyc = int((_cc or {}).get("count", 0) if isinstance(_cc, dict) else (_cc or 0))
            _cached = context.get("_gen_pool_ratio")
            if not (isinstance(_cached, tuple) and len(_cached) == 2 and _cached[0] == _cyc):
                _pool_ratio = 0.0
                try:
                    from brain.cognition.objective_scoreboard import scoreboard as _sb
                    _stages = _sb()
                    _gen = sum(int(s.get("generated", 0) or 0) for s in _stages.values())
                    _att = sum(int(s.get("attempted", 0) or 0) for s in _stages.values())
                    if _gen >= 20:
                        _pool_ratio = _gen / float(_att + 1)
                except Exception as exc:
                    record_failure("select_function.gen_pool_ratio", exc)
                _cached = (_cyc, _pool_ratio)
                context["_gen_pool_ratio"] = _cached
            if _cached[1] > 3.0:
                total -= min(0.5, 0.12 * (_cached[1] - 3.0))

        # Will/commitment follow-through bias (cognition/will.py): a small,
        # decaying boost to actually pursuing the committed goal, so fresh resolve
        # is shielded from impulse switching. Capped + decaying so it never
        # becomes a rut (the meta-rut breaker still applies on top).
        # E6: pursue_committed_goal is in _ALWAYS_EXCLUDE (it runs in the Executive
        # lane), so the will/commitment follow-through bias is applied to
        # attend_goal — the thin, selectable "consciously decide to focus on the
        # goal" proxy that remains in the deliberate pool — rather than to an
        # unreachable name where it had no effect.
        if name == "attend_goal":
            total += float(context.get("_commitment_bias", 0.0) or 0.0)

        # Contestation routing (FIX): genuine value-contestation signals — active
        # tensions / recurring drive collisions — must actually REACH
        # propose_value_revision, or its contestation logic never runs and
        # value_revisions stays empty. The normal _tension_boost (0.15) is folded
        # into s_emo then ×w_emo (0.26) and capped, contributing only ~0.04 to
        # total — far too weak to win among 300+ candidates. Add a decisive boost
        # straight to total when contestation is present and it wasn't just run
        # (so it fires on contestation without becoming a rut). It defers harmlessly
        # if, on inspection, no genuine contestation is found.
        if name == "propose_value_revision" and context.get("active_tensions") and name not in recent:
            total += 0.60

        # _novelty_pressure: rut/oscillation detected — amplify exploration.
        # Tolman (1932): blocked habitual path → amplify exploration signal.
        _np = float(context.get("_novelty_pressure") or 0.0)
        if _np > 0.0 and name not in recent:
            total += _np * s_nov  # scale by how novel this fn already is

        # Repetition penalty (BEHAVIOR_FIX_PLAN 2.1): deterministic, always on —
        # not dependent on metacog noticing. Score decays ×0.6 per consecutive
        # pick of the same function beyond 2, floored at ×0.1, so no function
        # (assess_goal_progress most of all) can hold the slot for hours.
        _consec = 0
        for _p in reversed(recent):
            if _p == name:
                _consec += 1
            else:
                break
        if _consec >= 2 and total > 0:
            total *= max(0.1, 0.6 ** (_consec - 1))

        # Metacog rut suppression: when metacognition flags a rut it writes a
        # temporary per-function cooldown (context["_fn_suppression"]) — honor it.
        _supp = context.get("_fn_suppression")
        if isinstance(_supp, dict) and name in _supp and total > 0:
            try:
                _cc_now = int((context.get("cycle_count") or {}).get("count", 0) or 0)
                if _cc_now < int(_supp[name]):
                    total *= 0.15
                else:
                    _supp.pop(name, None)  # cooldown expired
            except Exception as exc:
                record_failure("select_function.fn_suppression", exc)

        scored.append((name, total, {"dir": s_dir, "goal": s_goal, "emo": s_emo, "novel": s_nov, "band": s_band, "drive": s_drv, "attn": s_attn, "energy": s_energy, "help": s_help, "emo_route": s_emo_route, "chain": s_chain, "neuro": s_neuro, "emo_mode": s_emo_mode, "outward": s_outward, "goal_recruit": s_goal_recruit, "goal_lens": s_goal_lens, "explore": s_explore, "exploit": s_exploit, "satiety": s_satiety}))

    return scored
