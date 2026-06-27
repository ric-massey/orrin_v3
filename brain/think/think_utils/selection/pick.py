# think/think_utils/selection/pick.py
#
# Post-pick refinement for select_function() (CODEBASE_CLEANUP_PLAN Phase 4.5A).
#
# Once the scoring loop has ranked the candidates, two cohesive stages refine the
# argmax pick. They were lifted verbatim out of select_function() so the
# coordinator composes named steps rather than inlining ~250 lines of override
# logic. Behavior is preserved exactly — same RNG draw order in the ε branch,
# same record_failure tags, same context mutations.
from __future__ import annotations

import math as _math
import random as _rand
from typing import Any, Dict, List, Tuple

from brain.think.bandit import contextual_bandit as bandit
from brain.config import tuning as _tuning
from brain.utils.failure_counter import record_failure
from brain.think.think_utils.selection.catalog import _learned_stats
from brain.think.think_utils.selection.tag_sets import (
    _SAFE_TO_EXPLORE, _DELIBERATION_FNS, _EXECUTION_FNS,
)

# How many of the last N picks being deliberation (with zero execution) trips the
# meta-rut breaker.
_META_RUT_WINDOW = 5


def apply_exploration_and_reflex(
    chosen: str,
    scored: List[Tuple[str, float, Dict[str, float]]],
    actions: List[str],
    recent: List[str],
    context: Dict[str, Any],
    expl_drive: float,
    drive_pull: Dict[str, float],
) -> str:
    """ε-exploration → threat-arbiter reflex vote → inhibition cost, in order.

    Returns the (possibly overridden) chosen function. Runs only when there is a
    ranked candidate; the caller handles the empty-pool fallback.
    """
    # --- Phase 2: gated exploration (function_selection_fix_v2.md §3.2) ----
    # With probability ε, try a SAFE, rarely-used function instead of the
    # deterministic argmax — so dormant-but-reversible capability actually
    # gets sampled, the bandit accrues evidence for it, and the self-
    # reinforcing dead zone (never tried → never learned → never tried) is
    # broken. Gated on _SAFE_TO_EXPLORE (E4: rarely-used != safe-to-try) and
    # on low usage count; softmax over the candidates' OWN scores so we
    # explore plausible options rather than thrash into clearly-bad ones. ε
    # may be raised by exploration_drive but is capped at 0.30. This sits
    # BEFORE the threat-arbiter block, so a real reflex spike still overrides
    # whatever exploration picked. Setting context["_exploration_epsilon"]=0
    # disables the branch entirely (documented rollback).
    _expl_eps_base = float(context.get("_exploration_epsilon", 0.10) or 0.0)
    if _expl_eps_base > 0.0:
        _expl_eps = min(0.30, _expl_eps_base + 0.20 * max(0.0, expl_drive - 0.5))
        # Metacognitive rut breaker (LEARNING_DIAGNOSIS_2026-06-16 §5.3): the
        # stagnation detector in contextual_bandit only runs inside bandit.choose(),
        # which the real (weighted-sum) pick never calls — so the breaker built for
        # exactly this rut had 0 effect. Replicate its concentration check here and
        # raise ε when recent picks are dominated by a few arms, handing control back
        # to the value learner. Mirrors contextual_bandit._stagnation_epsilon_boost.
        try:
            _counts = (bandit.get_state() or {}).get("counts", {}) or {}
            _cand_total = sum(int(_counts.get(a, 0) or 0) for a in actions)
            if _cand_total >= int(_tuning.SELECTOR_RUT_MIN_TOTAL):
                _top3 = sum(sorted(
                    (int(_counts.get(a, 0) or 0) for a in actions), reverse=True)[:3])
                _conc = _top3 / max(_cand_total, 1)
                _trip = float(_tuning.SELECTOR_RUT_TRIP)
                if _conc > _trip:
                    _expl_eps = min(
                        float(_tuning.SELECTOR_RUT_EPS_CAP),
                        _expl_eps + float(_tuning.SELECTOR_RUT_EPS_GAIN)
                        * (_conc - _trip) / max(1.0 - _trip, 1e-6),
                    )
        except Exception as exc:
            record_failure("select_function.rut_exploration", exc)
        if _rand.random() < _expl_eps:
            _stats_now = _learned_stats()
            _tail = [
                (nm, sc) for (nm, sc, _f) in scored
                if nm in _SAFE_TO_EXPLORE
                and int((_stats_now.get(nm) or {}).get("count", 0)) < 8
                and nm not in recent
            ]
            if _tail:
                _T = 0.5  # softmax temperature
                _mx = max(sc for _, sc in _tail)
                _ws = [_math.exp((sc - _mx) / _T) for _, sc in _tail]
                _tot = sum(_ws) or 1.0
                _r, _acc = _rand.random() * _tot, 0.0
                for (_nm, _sc), _w in zip(_tail, _ws):
                    _acc += _w
                    if _r <= _acc:
                        chosen = _nm
                        from brain.utils.log import log_activity as _la
                        _la(f"[explore] ε-sampled dormant safe fn → {chosen} "
                            f"(ε={_expl_eps:.2f})")
                        break
    # ----------------------------------------------------------------------

    # threat_detector → weighted vote (V2: convergence, not override).
    # The threat_detector computes fight/flight/freeze → a recommended function.
    # Instead of a hard `if spike > 0.65: chosen = reflex` step-function override
    # (which made the choice flip-flop as the threat scalar crossed the
    # threshold), the reflex now joins the analytical (bandit) picks as a
    # high-weight proposal in the ActionArbiter. An acute spike still dominates;
    # a moderate spike blends with a strong planned pick; hysteresis against last
    # cycle's choice prevents the flip-flop. See think/action_arbiter.py.
    _AMY_SHORTCUT_MAP = {"speak": "speak", "dream": "idle_consolidation_cycle",
                          "introspective_planning": "introspective_planning"}
    try:
        _amy_resp    = context.get("threat_detector_response") or {}
        _amy_sc      = str(_amy_resp.get("shortcut_function") or "none")
        _amy_spike   = float(_amy_resp.get("spike_intensity") or 0.0)
        _mapped      = _AMY_SHORTCUT_MAP.get(_amy_sc, _amy_sc)
        # Only convene the arbiter when there is a real reflex bid to weigh in;
        # otherwise the analytical winner stands unchanged (zero behaviour drift).
        if _amy_sc != "none" and _amy_spike > 0.45 and _mapped in actions:
            from brain.think.action_arbiter import ActionProposal, resolve as _resolve
            # Normalise the top analytical scores to [0,1] (robust to negatives).
            _tops = [t for _, t, _ in scored[:5]]
            _lo, _hi = (min(_tops), max(_tops)) if _tops else (0.0, 1.0)
            _rng = (_hi - _lo) or 1.0
            _props = [
                ActionProposal(name=_nm, vote=max(0.0, min(1.0, (_t - _lo) / _rng)),
                               weight=1.0, source="bandit")
                for _nm, _t, _ in scored[:5]
            ]
            # Reflex lane: weight 1.2 + urgency=spike. At spike≈0.65 this is a
            # near-tie with the top analytical pick; above it the reflex wins,
            # below it the plan wins.
            _props.append(ActionProposal(
                name=_mapped, vote=min(1.0, _amy_spike), weight=1.2,
                urgency=min(1.0, _amy_spike), source="threat_detector",
            ))
            _incumbent = recent[-1] if recent else None
            _winner, _info = _resolve(_props, incumbent=_incumbent, margin=0.10)
            if _winner and _winner in actions:
                chosen = _winner
                from brain.utils.log import log_activity as _la
                _la(f"[action_arbiter] threat-vote → {chosen} "
                    f"(spike={_amy_spike:.2f}, hysteresis={_info.get('hysteresis')})")
    except Exception as _e:
        record_failure("select_function.select_function.12", _e)

    # Inhibition: record the emotional cost of not doing what drives wanted
    try:
        from brain.cognition.inhibition import apply_inhibition_costs
        apply_inhibition_costs(context, scored, chosen, drive_pull)
    except Exception as _e:
        record_failure("select_function.select_function.13", _e)

    return chosen


def apply_antirepeat_and_metarut(
    chosen: str,
    scored: List[Tuple[str, float, Dict[str, float]]],
    recent: List[str],
    context: Dict[str, Any],
) -> "Tuple[str, bool, bool]":
    """Anti-repeat tracking + stagnation signal + meta-rut breaker.

    Returns (chosen, override_applied, immediate_repeat). The anti-repeat block is
    measurement-only (NO hard cap — boredom/habituation apply the pressure); the
    meta-rut breaker is the one path that can override `chosen`, forcing the
    highest-scoring execution fn after a full window of deliberation-only picks.
    """
    # Anti-repeat guard: prevent any function from monopolising cycles.
    # Fires on immediate repeat (regardless of stagnation_signal) OR consecutive run ≥2
    # OR domination of ≥35% of the last 10 picks.  Override picks the highest-
    # scoring alternative that hasn't appeared in the last 3 cycles.
    #
    # Distress exemption: regulation functions are exempt during high distress.
    # Gross (1998) process model: sustained regulation effort under high negative
    # affect is therapeutic repetition, not rut-formation — interrupting it with
    # novelty-seeking defeats the function of the regulation strategy entirely.
    # Nolen-Hoeksema et al. (2008): failed regulation attempts that are interrupted
    # before resolution produce worse outcomes than repeated sustained engagement.
    _REGULATION_GUARD_EXEMPT = frozenset({
        "attempt_regulation", "reflect_on_affect",
        "investigate_unexplained_emotions", "reflect_on_emotion_model",
        "apply_affective_feedback",
    })
    _guard_distress_high = False
    try:
        from brain.affect.observers import negative_load
        _guard_distress_high = negative_load(context.get("affect_state") or {}) > 0.55
    except Exception as _e:
        record_failure("select_function.select_function.14", _e)

    override_applied = False
    immediate_repeat = False
    _repeat_attempt = False
    _ema_delta = 0.0
    _reward_improving = False
    _consecutive = 0
    _dominated = False
    # Hard cap on refinement repeats: even while reward keeps improving, a single
    # function may not monopolise more than this many consecutive cycles.
    _MAX_REFINE_REPEATS = 4
    try:
        immediate_repeat = bool(recent and chosen == recent[-1])
        _window10 = recent[-10:]
        _dominated = (
            len(_window10) >= 6
            and _window10.count(chosen) >= max(3, int(len(_window10) * 0.35))
        )
        _consecutive = 0
        for _x in reversed(recent[-10:]):
            if _x == chosen:
                _consecutive += 1
            else:
                break
        # Ground-truth "trying to repeat" signal, measured BEFORE the override
        # rewrites `chosen` — this is what drives the stagnation signal (Fix #2)
        # regardless of whether the refinement exemption lets the repeat through.
        _repeat_attempt = bool(immediate_repeat or _dominated or _consecutive >= 2)

        # Controlled-refinement exemption (Fix #4): allow a repeat when this
        # function's reward EMA is still climbing (iterative refinement is paying
        # off) and we're under the hard consecutive cap. _fn_ema_delta is written
        # by finalize.py after each cycle's reward is observed.
        _ema_delta = float((context.get("_fn_ema_delta") or {}).get(chosen, 0.0))
        _reward_improving = _ema_delta > 0.0 and _consecutive < _MAX_REFINE_REPEATS

        # NO hard anti-repeat cap. Humans don't have a "you may not pick this twice"
        # rule — they keep doing something while it works or while they're learning
        # from it, and naturally tire of it when it stops paying off. So we do NOT
        # force a different choice here; his real top-scoring preference stands. The
        # pressure against MINDLESS repetition is natural instead:
        #   • stagnation_signal (below) rises on repeat attempts → boredom builds,
        #   • RPE-style habituation in the reward path (ORRIN_loop) makes pure,
        #     non-learning repetition progressively unrewarding so the bandit drifts
        #     off it on its own,
        #   • repetition that keeps IMPROVING reward (trying it differently to learn)
        #     stays rewarding and continues freely.
        # This surfaces what he actually WANTS to do, not a forced shuffle.
        _ = (_reward_improving, _dominated, immediate_repeat)  # kept for tracker/telemetry
    except Exception as _e:
        record_failure("select_function.select_function.15", _e)

    # Stagnation signal (Fix #2): drive it from the actual repeat *attempt*
    # detected above, routed through submit_affect so it lands in core_signals
    # (where _dominant_signal_and_stagnation_signal reads it first) and persists
    # across cycles via commit_affect — the old top-level writer in think_module
    # never reached core_signals and stayed pinned at 0.000.
    try:
        from brain.affect.arbiter import submit_affect
        if _repeat_attempt:
            submit_affect(context, "stagnation_signal", +0.06,
                          source="select_repeat", ttl_cycles=4)
        else:
            submit_affect(context, "stagnation_signal", -0.02,
                          source="select_fresh", ttl_cycles=4)
    except Exception as _e:
        record_failure("select_function.select_function.16", _e)

    # Similarity / repeat tracker (Fix #4): expose the repeat state so the metacog
    # layer can read it (and a future "experiment with variation" pattern extend it).
    context["_repeat_tracker"] = {
        "chosen": chosen,
        "immediate_repeat": immediate_repeat,
        "consecutive": _consecutive,
        "dominated": _dominated,
        "ema_delta": _ema_delta,
        "refine_allowed": _reward_improving,
        "override_applied": override_applied,
    }

    # Meta-rut breaker (think-vs-act). The anti-repeat guard above only catches a
    # single function name repeating; a *varied* run of deliberation functions that
    # never executes slips straight past it (assess → adjust → abduce → adapt …).
    # This measures the category-level think/act ratio over the recent window and,
    # when deliberation has fully crowded out doing, forces the highest-scoring
    # execution function. Independent of (and faster than) the metacog avoidance
    # detector, so a forming rut is broken before it entrenches.
    try:
        if chosen in _DELIBERATION_FNS:
            _rut_window = recent[-_META_RUT_WINDOW:]
            if len(_rut_window) >= _META_RUT_WINDOW:
                _acted = any(p in _EXECUTION_FNS for p in _rut_window)
                _all_think = all(p in _DELIBERATION_FNS for p in _rut_window)
                if _all_think and not _acted:
                    _exec_alts = sorted(
                        ((n, s) for (n, s, _) in scored if n in _EXECUTION_FNS),
                        key=lambda t: t[1], reverse=True,
                    )
                    if _exec_alts and _exec_alts[0][0] != chosen:
                        chosen = _exec_alts[0][0]
                        override_applied = True
                        from brain.utils.log import log_private as _lp
                        _lp(
                            f"[meta_rut] {_META_RUT_WINDOW} deliberation picks with no "
                            f"action → forcing execution: {chosen!r}"
                        )
    except Exception as _e:
        record_failure("select_function.select_function.17", _e)

    return chosen, override_applied, immediate_repeat
