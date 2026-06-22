# brain/loop/cognition_reward.py
#
# Reward shaping for the cognition-execution path (CODEBASE_CLEANUP_PLAN 4.5B).
#
# Lifted verbatim out of execute.py::execute_cognition_function to bring that
# module under the 600-line soft limit. Given the post-execution facts (the
# pre/post affect snapshots, the env-delta and status sub-rewards, and whether
# the call failed), this computes the single shaped scalar reward the bandit
# learns from: the env/status/emotional blend, goal-weighting, the regulation /
# outward-novelty / habituation / social-baseline / value-alignment / growth
# adjustments, and the introspection outcome-coupling cap. Same record_failure
# tags, same context mutations (reward_rate / outward digest) as before.
from __future__ import annotations

from typing import Any, Dict

from brain.think.loop_helpers import emotional_delta_reward, blend_reward
from brain.utils.failure_counter import record_failure
from brain.loop.constants import _OUTWARD_FNS

Context = Dict[str, Any]


def shape_cognition_reward(
    context, fn_name, fn_str, emo_pre, emo_post, env_r, status_r, is_failure,
):
    """Return the shaped scalar reward for a completed cognition call."""
    # Preserve the original in-function local names so the moved body is verbatim.
    _fn_str = fn_str
    _emo_pre = emo_pre
    _emo_post = emo_post
    _env_r = env_r
    _status_r = status_r
    _is_failure = is_failure

    # Blend: env-delta (40%) + status (20%) + emotional delta (40%).
    # emotional_delta_reward captures how the function actually moved
    # Orrin's internal state — the reward signal the bandit was missing.
    _emo_r = emotional_delta_reward(_emo_pre, _emo_post)
    base_reward = blend_reward(0.6 * _env_r + 0.4 * _status_r, _emo_r)
    _blended_reward = base_reward
    try:
        from brain.cognition.reward_rate import update_reward_rate
        update_reward_rate(
            context,
            reward=float(_blended_reward),
            committed_goal_id=(
                (context.get("committed_goal") or {}).get("id")
            ),
        )
        context["_reward_rate_updated_this_cycle"] = True
    except Exception as _e:
        record_failure("ORRIN_loop.update_reward_rate", _e)
    if _is_failure:
        base_reward = min(base_reward - 0.4, -0.1)
    # Apply goal-weighted reward on the cognition path, matching
    # the action path — so the bandit learns that cognition which
    # doesn't advance the committed goal is worth less.
    try:
        from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr_cog
        reward = _gwr_cog(base_reward, context, action_was_taken=not _is_failure, fn_name=fn_name)
    except Exception:
        reward = base_reward
    # Regulation discharge bonus — reward regulation when distress
    # was actually present at execution time.
    # Aldao et al. (2010) meta-analysis of emotion regulation:
    # strategy effectiveness is highly context-dependent; the critical
    # learning event is selecting the right strategy given the current
    # emotional state, not a measurable downstream state change.
    # Emotional state does not update within a single cognitive cycle —
    # update_affect_state() runs at cycle start, not inside functions.
    # Measuring pre/post delta within one cycle produces a spurious zero
    # because the comparison window is too narrow. Sheppes et al. (2014):
    # the bandit must learn that regulation during high-distress states
    # pays — the bonus must be conditioned on distress-at-execution, with
    # magnitude scaled to distress severity to create the correct gradient.
    _REGULATION_FNS = frozenset({
        "attempt_regulation", "reflect_on_affect",
        "investigate_unexplained_emotions", "check_affect_drift",
        "reflect_on_emotion_model", "apply_affective_feedback",
    })
    if fn_name in _REGULATION_FNS and not _is_failure:
        try:
            _pre_neg = sum(
                float((_emo_pre.get("core_signals") or _emo_pre).get(k) or 0)
                for k in ["impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence"]
            )
            if _pre_neg > 0.45:
                reward += min(0.18, 0.08 + _pre_neg * 0.15)
        except Exception as _e:
            record_failure("ORRIN_loop.run_cognitive_loop.16", _e)
    # Dopaminergic novelty gate for outward perception reads
    # (Schultz 1997: dopamine signals prediction error / novelty,
    # not repetition). look_outward & friends previously farmed
    # standing bonuses 100+ times regardless of whether the glance
    # surfaced anything new — the reward leak. An empty or repeated
    # outward result is not a reward event.
    _OUTWARD_READ_FNS = frozenset({
        "look_outward", "look_around", "seek_novelty",
        "read_rss", "survey_environment",
    })
    _outward_low_novelty = False
    if fn_name in _OUTWARD_READ_FNS:
        try:
            import hashlib as _hashlib
            _norm = _fn_str.strip().lower()
            _digest = (
                _hashlib.sha1(_norm.encode("utf-8", "ignore")).hexdigest()
                if _norm else ""
            )
            if not _norm or _digest == context.get("_last_outward_digest"):
                _outward_low_novelty = True
            context["_last_outward_digest"] = _digest
        except Exception as _e:
            record_failure("ORRIN_loop.run_cognitive_loop.17", _e)
        if _outward_low_novelty:
            # No novelty → no dopamine. Pull reward to the low end.
            reward = min(reward, 0.1)

    # Outward-debt discharge bonus (FINDINGS 2026-06-12 data
    # sweep §11): look_outward was the worst-paid action in the
    # stats table while the metacog objective demanded outward
    # action — suppression can't beat a standing reward gap, so
    # pay the discharge itself. An outward act landing after a
    # long internal-only stretch earns a bonus scaled by the
    # debt it clears; the novelty gate above keeps a repeated
    # empty glance from farming it.
    try:
        if (fn_name in _OUTWARD_FNS and not _is_failure
                and not _outward_low_novelty):
            _od_pay = int(context.get("_outward_debt", 0) or 0)
            if _od_pay >= 8:
                reward += min(0.25, 0.10 + (_od_pay - 8) * 0.01)
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.17b", _e)

    # Dopaminergic habituation — LEARNING-AWARE (Schultz 1997:
    # dopamine tracks prediction error / novelty, not repetition).
    # This is the natural pressure that replaces the old hard
    # anti-repeat cap: repeating the SAME function gets boring
    # (reward decays) ONLY when it isn't paying off — i.e. when his
    # reward EMA for it is flat or falling. If repeating it keeps
    # IMPROVING reward (he's trying it differently and learning), it
    # is NOT habituated and he's free to keep going. So mindless
    # loops fade on their own; productive iteration continues.
    try:
        _rp8 = context.get("recent_picks", [])[-8:]
        _rep_n = max(0, _rp8.count(fn_name) - 1)
        _improving = float((context.get("_fn_ema_delta") or {}).get(fn_name, 0.0)) > 0.0
        if _rep_n > 0 and not _improving:
            # Bored: steeper, deeper decay so a stale loop reliably
            # loses to alternatives (down toward ~0 instead of a 0.2 floor).
            if fn_name in _OUTWARD_READ_FNS:
                _habituation = max(0.05, 1.0 - _rep_n * 0.32)
            else:
                _habituation = max(0.1, 1.0 - _rep_n * 0.22)
            reward *= _habituation
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.18", _e)

    # Social baseline penalty — absence of user dampens intrinsic reward.
    # Based on Coan & Beckes (2010) social baseline theory: internal
    # rewards are calibrated against social presence. Extended silence
    # (>30 min) progressively reduces reward for all non-social functions,
    # creating a real pull toward engagement. Floor at 80% so Orrin
    # doesn't collapse into chronic risk_estimate during long autonomous runs.
    try:
        _sil_s = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
        if _sil_s > 1800:
            _absence_mod = max(0.80, 1.0 - (_sil_s / 3600.0) * 0.10)
            reward *= _absence_mod
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.19", _e)

    # Solo-mode introvert bonus — deep internal work earns more
    # reward during absence, not merely less penalty.
    # Aron & Aron (1997) sensory-processing sensitivity: introverted
    # systems show heightened processing depth during low-stimulation
    # periods; solitary reflection produces genuine positive affect, not
    # just absence of overstimulation. Kaplan & Kaplan (1989) attention
    # restoration theory: directed attention (scanning, searching)
    # depletes; fascination-driven internal processing (integration,
    # symbolic reasoning) restores. The social baseline above correctly
    # penalizes look_outward as a connection substitute; this bonus
    # creates the opposing pull toward genuine restorative solo work.
    _INTROVERT_FNS = frozenset({
        "run_symbolic_dream", "run_rule_compression",
        "run_forgetting_cycle", "run_symbolic_prediction_cycle",
        "reflect_on_affect", "narrative_update",
        "update_latent_identity", "propose_value_revision",
        "audit_reflective_claims", "run_self_improvement",
        "reflect_on_cognition_rhythm", "run_active_experiment",
        "detect_memory_contradictions", "repair_contradictions",
    })
    try:
        _sil_s_solo = float((context.get("social_presence") or {}).get("silence_s") or 0.0)
        if _sil_s_solo > 1800 and fn_name in _INTROVERT_FNS:
            reward += 0.15
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.20", _e)

    # Tier 2: SDT value alignment bonus.
    # Functions that match Orrin's stated core values earn a
    # standing reward boost. Based on Deci & Ryan (2000): intrinsic
    # motivation produces deeper, more stable learning than extrinsic
    # reward alone. Value-aligned behavior should be self-reinforcing.
    # One value match per function (cap 0.12) — enough to tilt the
    # bandit over many cycles without overwhelming the signal.
    try:
        _sm   = context.get("self_model") or {}
        _vals = [
            str((v.get("value") if isinstance(v, dict) else v) or "").lower()
            for v in (_sm.get("core_values") or [])
        ]
        _fn_l = fn_name.lower()
        _V2KW = {
            "exploration_drive":  {"search","look","investigate","wiki","rss","explore","perception","outward"},
            "growth":     {"improve","learn","write","discover","synthesis","dream","compress","self_improv","extension"},
            "honesty":    {"audit","detect","repair","reflect","contradict","verify","integrity","rhythm"},
            "connection": {"note","speak","social","user","thread","leave","person"},
            "depth":      {"symbolic","dream","compress","rule","reason","introspect","predict","analogy","emotion"},
        }
        _val_bonus = 0.0
        for _val in _vals:
            if any(_kw in _fn_l for _kw in _V2KW.get(_val, set())):
                _val_bonus = 0.10
                break
        # Don't pay the value-alignment standing bonus to an outward
        # read that surfaced nothing new — that was the leak that let
        # look_outward accrue +0.10 every cycle regardless of outcome.
        if _outward_low_novelty:
            _val_bonus = 0.0
        reward += _val_bonus
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.21", _e)

    # Growth-orientation standing bonus.
    # Functions that expand capability or deepen self-understanding
    # earn an additional baseline reward independent of value matching.
    # Based on Ryan & Deci (2000): intrinsic motivation toward mastery
    # and growth is qualitatively distinct from task-completion reward —
    # it needs its own signal or it loses to easier, more frequent wins.
    _GROWTH_FNS = frozenset({
        "write_cognitive_function", "write_tool", "discover_new_emotion",
        "run_self_improvement", "reflect_on_affect", "reflect_on_emotion_model",
        "update_latent_identity", "narrative_update", "propose_value_revision",
        "run_symbolic_dream", "run_rule_compression", "audit_reflective_claims",
        "investigate_unexplained_emotions", "detect_memory_contradictions",
        "repair_contradictions", "run_symbolic_prediction_cycle",
        "run_forgetting_cycle", "run_benchmark", "reflect_on_cognition_rhythm",
        "research_topic", "fetch_and_read",
    })
    if fn_name in _GROWTH_FNS:
        reward += 0.12

    # Competence legibility: write a visible completion record to
    # working memory — but only for significant accomplishments.
    # Bandura (1977) self-efficacy theory: mastery experiences are
    # constituted by challenging tasks; feedback on routine execution
    # does not build efficacy and risks diluting the signal value of
    # genuine achievement. Locke & Latham (2002) goal-setting theory:
    # performance feedback must be proximal to meaningful accomplishment
    # to be effective — indiscriminate positive feedback creates noise
    # that erodes the discriminability of real completion signals.
    # White (1959) effectance motivation: the intrinsic drive is toward
    # producing effects that matter, not toward any effect whatsoever.
    # Trigger: growth functions, regulation functions, or substantive
    # output (>120 chars) — not every successful call.
    _is_significant_completion = (
        fn_name in _GROWTH_FNS
        or fn_name in _REGULATION_FNS
        or (not _is_failure and len(_fn_str) > 120)
    )
    if not _is_failure and _is_significant_completion and _fn_str:
        try:
            from brain.cog_memory.working_memory import update_working_memory as _uwm_comp
            _uwm_comp(f"[done] {fn_name}: {_fn_str[:80].strip().rstrip('.')}")
        except Exception as _e:
            record_failure("ORRIN_loop.run_cognitive_loop.22", _e)

    # Outcome coupling — introspection can't outpay reality.
    # The standing bonuses above (value alignment, growth,
    # regulation, emotional delta) summed to ~0.55–0.73 for
    # introspective picks even on cycles where env_snapshot
    # measured zero observable change (delta_reward=0.000,
    # thrash=True) — which is how assess_goal_progress +
    # update_affect_state became 60% of all decisions while
    # outward action paid less. If a self-inspection function
    # produced no observable change (no milestone, no memory
    # write, no tool resolution, WM unchanged), its reward is
    # capped below what productive work earns. Introspection
    # that DOES move something external (env_r ≥ 0.35) still
    # pays in full.
    _INTROSPECTIVE_FNS = frozenset({
        "assess_goal_progress", "update_affect_state",
        "search_own_files", "reflect_on_internal_agents",
        "reflect_on_affect", "reflect_on_emotion_model",
        "check_affect_drift", "audit_reflective_claims",
        "reflect_on_outcomes", "reflect_on_self_beliefs",
        "detect_memory_contradictions",
        "reflect_on_cognition_patterns", "reflect_on_internal_voices",
        "summarize_relationships", "periodic_self_review",
        "reflect_on_effectiveness", "reflect_on_opinions",
        "reflect_on_growth_history", "process_regret",
        "read_vitals", "check_user_presence",
    })
    try:
        if (not _is_failure
                and fn_name in _INTROSPECTIVE_FNS
                and float(_env_r) < 0.35):
            reward = min(reward, 0.35)
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.23", _e)

    return reward
