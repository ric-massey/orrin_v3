from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger
import json

from brain.utils.json_utils import load_json, save_json
from brain.utils.timing import get_time_since_last_active
from brain.utils.log import log_private, log_model_issue
from brain.utils.events import emit_event, DECISION
from brain.behavior.tools.toolkit import evaluate_tool_use
from brain.cognition.planning.motivations import adjust_goal_weights
from brain.cog_memory.working_memory import update_working_memory
from brain.control_signals.update_signal_state import update_signal_state
from brain.think.think_utils.escalate import is_agentic_action
from brain.paths import (
    ACTION_FILE,
    COGNITION_STATE_FILE,
    COGNITION_HISTORY_FILE,
    BEHAVIORAL_FUNCTIONS_LIST_FILE,  # use the real constant
)
from brain.utils.timeutils import now_iso_z
_log = get_logger(__name__)

# NEW: ensure we can display and score 'reason' whether it's a dict or a string
def _reason_text(reason) -> str:
    if isinstance(reason, dict):
        try:
            return json.dumps(reason, ensure_ascii=False)
        except (TypeError, ValueError):  # intentional: unserializable reason → str()
            return str(reason)
    return str(reason)

# Delegate to the canonical reward emitter (affect.reward_signals.release_reward)
# so the wrapper logic lives in exactly one place.
from brain.control_signals.reward_signals.reward_signals import release_reward as _reward
from brain.utils.failure_counter import record_failure

# Satisfaction scoring (with its _OUTWARD_ACTION_FNS / _OUTWARD_PRESSURE_RAMP
# constants) lives in satisfaction.py; finalize_cycle calls it to score outcomes.
from brain.think.think_utils.satisfaction import _state_satisfaction

# P1 reward split (ORRIN_PRODUCTION_REWARD_PLAN). Intake stays rewarded — just
# strictly less than making — so a gradient finally exists from learning → producing.
# Fixed by an ORDERING, not free choice: intake at 0.5 sits at neutral (the EMA
# midpoint), leaving +0.5 up to production (1.0, well outside EMA noise → a real
# gradient) and −0.3 down to cognition-only (0.2). The floor clamps intake when it
# is modulated down (novelty decay / habituation) so it can never fall below the
# cognition-only penalty and flip the ordering — a barren production environment
# must never punish Orrin into paralysis.
INTAKE_REWARD = 0.5
INTAKE_REWARD_FLOOR = 0.35


def realized_reward_with_prejudice(act_key: str, actual_fb: float) -> float:
    """R10-8 account seam, extracted so it is provable by harness (F-LN8): an
    action the gate refused this cycle (LLM circuit open, tool absent) produced
    no effect no matter how cleanly it "ran" — pay it zero-with-prejudice so its
    EMA decays below the selection default instead of sitting high on the
    strength of not raising. Fail-safe: on any error the reward passes through."""
    try:
        from brain.control_signals.reward_signals.impossibility import is_impossible as _is_imp
        if _is_imp(act_key):
            return 0.0
    except Exception as _ie:
        record_failure("finalize.finalize_cycle.impossible", _ie)
    return actual_fb


def finalize_cycle(context, user_input, next_function, reason, speaker):
    """
    Final step of each Orrin cognitive cycle: logs feedback, updates histories,
    handles social_deficit/self-questioning, and saves the chosen action.
    """
    reason_text = _reason_text(reason)  # NEW

    # R1 — feed this cycle's executed function to the signal→action follow-through
    # audit (records its action class + resolves any corrective whose K-cycle window
    # has elapsed). Best-effort: telemetry must never break the cycle's finalize.
    try:
        from brain.cognition.signal_action_audit import tick as _sa_tick
        _sa_tick(context, next_function)
    except Exception as _sae:
        record_failure("finalize_cycle.signal_action_audit", _sae)

    # Log which function was chosen
    update_working_memory({
        "content": f"🧠 Chose: {next_function} — {reason_text}",  # NEW: use readable text
        "event_type": "choice",
        "importance": 2,
        "priority": 2,
        "referenced": 1
    })
    evaluate_tool_use([{
        "content": user_input or "No input this cycle.",
        "timestamp": now_iso_z()
    }])
    update_working_memory({
        "content": f"⏳ Last active: {get_time_since_last_active()}",
        "event_type": "system",
        "importance": 1,
        "priority": 1
    })

    # --- Agentic-vs-Cognition Reward System ---
    # `next_function` is the COGNITIVE pick, and select_function structurally
    # excludes every behavioral/agentic function from its candidate pool — so
    # is_agentic_action(next_function) alone is always False even when Orrin
    # actually wrote a file this cycle. Also honor what genuinely executed via the
    # action_gate path: __acted_this_tick__ + last_action_taken type (AGENTIC_TYPES).
    is_agentic = is_agentic_action(next_function, behavior_list_path=BEHAVIORAL_FUNCTIONS_LIST_FILE)
    try:
        from brain.cognition.action_accounting import cycle_produced_goal_action
        from brain.think.think_utils.action_gate import AGENTIC_TYPES
        _acted = bool(context.get("__acted_this_tick__"))
        _acted_type = (context.get("last_action_taken") or {}).get("type")
        if (_acted and _acted_type in AGENTIC_TYPES) or cycle_produced_goal_action(context):
            is_agentic = True
    except Exception as _e:  # best-effort agentic detection — never break finalize
        record_failure("finalize.agentic_detect", _e)

    # P1 — three-tier reward split (the keystone). Until now consequential
    # cognition paid the SAME 1.0 as producing a real artifact, so reading
    # Wikipedia and spawning a goal earned exactly what writing a file earned and
    # there was no pull from intake → making. Production is *only* an effect-ledger
    # row that landed this cycle (set by express_to_user / code_writer); engaged
    # intake (consequential cognition, outward acts that touched the world without
    # a durable novel artifact) pays the middle rung; pure reflection pays the floor.
    _production = bool(context.get("_production_effect_this_cycle"))
    if _production:
        is_agentic = True  # production is the strongest form of agentic engagement
        _reward(context, signal="reward_signal", actual=1.0, expected=0.6, effort=0.7, mode="phasic", source="production_effect")
        update_working_memory({
            "content": f"✅ Rewarded production (durable effect): {next_function}",
            "event_type": "reward",
            "importance": 2,
            "priority": 2
        })
    elif is_agentic:
        _intake = max(INTAKE_REWARD_FLOOR, INTAKE_REWARD)
        _reward(context, signal="reward_signal", actual=_intake, expected=0.5, effort=0.5, mode="phasic", source="intake")
        update_working_memory({
            "content": f"↔ Intake / consequential cognition (below production): {next_function}",
            "event_type": "reward",
            "importance": 1,
            "priority": 1
        })
    else:
        _reward(context, signal="reward_signal", actual=0.2, expected=0.4, effort=0.2, mode="tonic", source="cognition_only")
        update_working_memory({
            "content": f"⚠️ Cognition action only (not agentic): {next_function}",
            "event_type": "reward_penalty",
            "importance": 1,
            "priority": 1
        })

    # --- Environment-delta reward (replaces LLM self-feedback grading) ---
    # Reward comes from what changed in the system this step, not from asking
    # the model to rate its own output text.  ORRIN_loop.py sets
    # context["_step_delta_reward"] after each cognition call using env_snapshot.
    # Finalize reads it here to fire the reward_signal signal; then clears the key.
    _delta_r = context.pop("_step_delta_reward", None)
    if _delta_r is not None:
        actual_fb = float(_delta_r)
    else:
        # Fallback: rule-based satisfaction when ORRIN_loop didn't set a delta.
        actual_fb = _state_satisfaction(context, is_agentic)

    # Internal success ≠ reward (BEHAVIOR_FIX_PLAN 2.1): reflective/deliberation
    # functions always "succeed" at producing internal state (assessing always
    # yields an assessment) — that self-reinforcement was the engine of the
    # assess_goal_progress rut (semantic_facts success ×95, audit §6). Without a
    # downstream effect this cycle (an action taken), their reward is compressed
    # toward neutral so the bandit/EMA can't learn "always pick reflection".
    try:
        from brain.think.think_utils.select_function import _DELIBERATION_FNS
        if (not is_agentic
                and next_function in _DELIBERATION_FNS
                and not cycle_produced_goal_action(context)
                and actual_fb > 0.4):
            actual_fb = 0.4 + (actual_fb - 0.4) * 0.5
    except Exception as _e:
        record_failure("finalize.finalize_cycle", _e)
    # Route the primary per-cycle reward through the RewardEngine so its expected
    # baseline comes from the per-function EMA (the single baseline, V3_AUDIT D5)
    # rather than a hardcoded expected=0.5. action_type is the cycle's chosen
    # function so each function learns its own expectation.
    try:
        from brain.control_signals.reward_signals.reward_engine import submit_reward as _submit_reward
        _act_key = str(context.get("last_function_chosen") or "cycle")
        # R10-8 / F-LN8: zero-with-prejudice for gate-refused actions (the seam
        # lives in realized_reward_with_prejudice so the harness can prove it).
        actual_fb = realized_reward_with_prejudice(_act_key, actual_fb)
        # Calibration: record the forecast (per-function expected reward) against
        # the realized reward BEFORE submit_reward updates the EMA. Nelson &
        # Narens (1990) monitoring → control; consumed by meta_controller.
        # Snapshot the per-function EMA before the reward updates it so the
        # anti-repeat guard can tell whether this function's reward is still
        # improving (controlled-refinement exemption, Fix #4).
        _ema_before = None
        try:
            from brain.control_signals.reward_signals.action_reward_ema import get_expected as _get_exp
            from brain.cognition.calibration import record as _cal_record
            _ema_before = _get_exp(context, _act_key)
            _cal_record(context, _ema_before, actual_fb)
        except Exception as _ce:
            record_failure("finalize.finalize_cycle.2", _ce)
        _submit_reward(
            context,
            actual=actual_fb,
            action_type=_act_key,
            kind="reward_signal",
            effort=0.5,
            mode="phasic",
            source="env_delta",
        )
        if _ema_before is not None:
            try:
                from brain.control_signals.reward_signals.action_reward_ema import get_expected as _get_exp2
                context.setdefault("_fn_ema_delta", {})[_act_key] = (
                    _get_exp2(context, _act_key) - _ema_before
                )
            except Exception as _de:
                record_failure("finalize.finalize_cycle.3", _de)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.4", _e)
        _reward(context, signal="reward_signal", actual=actual_fb, expected=0.5, effort=0.5,
                mode="phasic", source="env_delta")

    # Attention value learning: sources that were active this cycle get credit
    # or penalty based on whether the cycle produced high reward.
    try:
        from brain.think.attention_weights import update_attention_weights as _uaw
        _uaw(context, actual_fb)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.5", _e)

    # Vocabulary feedback weighting: if the user responded this cycle and we
    # spoke last cycle, credit the phrase that preceded the user's response.
    try:
        _user_responded = bool((context.get("latest_user_input") or "").strip())
        _prev_phrase_hash = context.pop("_pending_vocab_phrase_hash", None)
        if _user_responded and _prev_phrase_hash:
            from brain.utils.json_utils import load_json as _lvj, save_json as _svj
            from brain.paths import DATA_DIR as _DATA_DIR
            _vw_path = _DATA_DIR / "vocab_weights.json"
            _vw = _lvj(_vw_path, default_type=dict) or {}
            _entry = _vw.get(_prev_phrase_hash) or {"uses": 0, "successes": 0, "weight": 1.0}
            _entry["uses"] = int(_entry.get("uses", 0)) + 1
            _entry["successes"] = int(_entry.get("successes", 0)) + 1
            # Weight grows toward 2.0 as success rate improves
            _rate = _entry["successes"] / max(1, _entry["uses"])
            _entry["weight"] = round(1.0 + _rate, 3)
            _vw[_prev_phrase_hash] = _entry
            _svj(_vw_path, _vw)
        # Record this cycle's phrase so next cycle can credit it if user responds
        _this_phrase_hash = context.pop("_last_vocab_phrase_hash", None)
        if _this_phrase_hash:
            context["_pending_vocab_phrase_hash"] = _this_phrase_hash
    except Exception as _e:
        record_failure("finalize.finalize_cycle.6", _e)

    # Rule verifier outcome — adjust confidence of any rule that fired this cycle.
    try:
        from brain.symbolic.rule_verifier import apply_outcome as _rva
        _user_q = (context.get("latest_user_input") or context.get("user_input") or "").strip()
        _rva(actual_fb, query=_user_q, context=context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.7", _e)

    # Trace buffering — record high-outcome cycles for future fine-tuning.
    # Only fires when the cycle produced a real user response and scored well.
    try:
        _user_in = (context.get("latest_user_input") or "").strip()
        _last_resp = (context.get("_last_responded_input") or "").strip()
        _orrin_resp = (context.get("_last_spoken") or context.get("_last_reply") or "").strip()
        if _user_in and _orrin_resp and actual_fb >= 0.55:
            from brain.utils.trace_buffer import record_trace as _rt
            _sys_prompt = (context.get("system_prompt") or "")[:800]
            _rt(
                user_input=_user_in,
                system_prompt=_sys_prompt,
                response=_orrin_resp,
                outcome_score=actual_fb,
                context_snapshot=context,
                fn_name=str(next_function),
            )
    except Exception as _e:
        record_failure("finalize.finalize_cycle.8", _e)

    # Adjust goal weights from emotional state (no LLM needed — rule-based).
    try:
        adjust_goal_weights()
    except Exception as _e:
        record_failure("finalize.finalize_cycle.9", _e)

    # --- Shadow/Self-Question (curated pool, emotion-weighted, no LLM needed) ---
    try:
        import random as _random
        _emo_state = (context.get("affect_state") or {})
        _core_emo  = (_emo_state.get("core_signals") or _emo_state)
        _dom = max(
            ((k, float(v)) for k, v in (_core_emo or {}).items() if isinstance(v, (int, float))),
            key=lambda kv: kv[1], default=("neutral", 0.0)
        )[0]

        _SHADOW_POOLS = {
            "impasse_signal": [
                "Am I actually blocked, or just reluctant?",
                "What would I do differently if I weren't afraid of failing here?",
                "Is my impasse_signal pointing at a real obstacle or at myself?",
            ],
            "threat_level": [
                "What am I protecting myself from by not acting?",
                "What's the worst realistic outcome — and can I survive it?",
                "Am I afraid of succeeding as much as failing?",
            ],
            "exploration_drive": [
                "What assumption am I making that I haven't questioned yet?",
                "What would I explore if I had no consequences?",
                "What question would make me most uncomfortable to answer honestly?",
            ],
            "motivation": [
                "Am I moving toward something or away from something?",
                "What would I sacrifice to achieve this?",
                "Is this goal really mine, or have I inherited it?",
            ],
            "stagnation_signal": [
                "What have I been avoiding under the guise of having nothing to do?",
                "What genuinely interests me that I keep deprioritizing?",
                "Am I bored or just unwilling to start something hard?",
            ],
            "uncertainty": [
                "What would I do if I accepted I'll never have full certainty?",
                "Am I waiting for permission that will never come?",
                "What does my uncertainty protect me from having to decide?",
            ],
        }
        _DEFAULT_SHADOWS = [
            "What am I not saying to myself that I need to hear?",
            "Where am I confusing comfort with correctness?",
            "What would I do differently if I knew no one was watching — including myself?",
            "Am I growing, or just busy?",
            "What truth am I working hardest to avoid?",
            "What would the most honest version of me say right now?",
            "Is what I'm doing right now aligned with what I actually care about?",
        ]

        pool = _SHADOW_POOLS.get(_dom, _DEFAULT_SHADOWS)
        shadow_question = _random.choice(pool)

        if shadow_question:
            update_working_memory({
                "content": f"🌓 Shadow question: {shadow_question}",
                "event_type": "self_query",
                "importance": 1,
                "priority": 1
            })
            _reward(context, signal="novelty", actual=0.5, expected=0.4, effort=0.1, mode="tonic", source="self_question")
    except Exception as _e:
        record_failure("finalize.finalize_cycle.10", _e)

    # --- social_deficit and User Input ---
    affect_state = context.get("affect_state", {}) or {}
    if affect_state.get("social_deficit", 0.0) > 0.6 and not user_input and not context.get("speech_done"):
        message = "It's been a while since we've talked. I miss your input. Do you want to chat?"
        update_working_memory({
            "content": message,
            "event_type": "social_deficit",
            "importance": 2,
            "priority": 2
        })
        tone = {"tone": "vulnerable", "intention": "reconnect"}
        rendered = speaker.speak_final(message, tone, context)
        if rendered:
            try:
                import sys as _sys
                _sys.stdout.write(f"REPLY: {rendered}\n")
                _sys.stdout.flush()
            except Exception as _e:
                record_failure("finalize.finalize_cycle.11", _e)
        context["speech_done"] = True
        affect_state["social_deficit"] = affect_state.get("social_deficit", 0.0) * 0.5
        # pass context so state updates in-place consistently
        update_signal_state(context=context)

        _reward(context, signal="connection", actual=0.7, expected=0.4, effort=0.4, mode="tonic", source="social_deficit_reconnect")

    # --- Cognition History and Repeat Count Logging ---
    # Satisfaction from real state, not LLM opinion on a log string.
    # rate_satisfaction() was calling the LLM every cycle to parse JSON metadata —
    # completely ungrounded. This reads actual observables instead.
    satisfaction = _state_satisfaction(context, is_agentic)
    cog_state = load_json(COGNITION_STATE_FILE, default_type=dict) or {}
    last_choice = cog_state.get("last_cognition_choice")
    repeat_count = (cog_state.get("repeat_count", 0) + 1) if last_choice == next_function else 1

    try:
        from brain.cognition.cognitive_cost import apply_cognitive_costs
        apply_cognitive_costs(context, next_function, repeat_count)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.12", _e)

    try:
        from brain.cognition.temporal_pressure import apply_temporal_pressure
        apply_temporal_pressure(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.13", _e)

    try:
        from brain.cognition.runtime_lifetime import apply_lifetime_pressure
        _lifetime = apply_lifetime_pressure(context)
        if _lifetime.get("terminate"):
            context["_runtime_ending"] = True
    except Exception as _e:
        record_failure("finalize.finalize_cycle.14", _e)

    try:
        from brain.cognition.self_state.fragmentation import apply_fragmentation_cost
        apply_fragmentation_cost(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.15", _e)

    # Calibrated reward check — grounded in goal closure, predictions, contradictions.
    # This runs AFTER agentic/env-delta rewards to avoid double-counting but ensures
    # external-grounding signals actually feed the bandit on cycles where they fire.
    try:
        from brain.cognition.reward_calibrator import (
            check_and_reward_goal_closure as _cgc,
            check_and_reward_prediction_accuracy as _cpa,
            check_and_reward_contradiction_resolution as _ccr,
        )
        _cgc(context)
        _cpa(context)
        _ccr(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.16", _e)

    try:
        from brain.cognition.perception.environment import update_environment_state
        update_environment_state(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.17", _e)

    try:
        from brain.cognition.associative_memory import maybe_surface_association
        maybe_surface_association(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.18", _e)

    try:
        from brain.cognition.habituation import apply_habituation
        apply_habituation(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.19", _e)

    try:
        from brain.cognition.self_generated.autogenerated_thoughts import maybe_generate_thought
        maybe_generate_thought(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.20", _e)

    try:
        from brain.cognition.opinions import maybe_form_opinion
        maybe_form_opinion(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.21", _e)

    try:
        from brain.cognition.smoothed_state import update_smoothed_state
        update_smoothed_state(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.22", _e)

    try:
        from brain.cognition.regret import maybe_surface_regret
        maybe_surface_regret(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.23", _e)

    # Emotional regulation: attempt a regulation strategy when a negative
    # emotion is intense enough. Rate-limited to every ~10 cycles internally.
    try:
        from brain.control_signals.regulation import attempt_regulation as _attempt_reg
        _attempt_reg(context)
    except Exception as _e:
        record_failure("finalize.finalize_cycle.24", _e)

    cognition_log = load_json(COGNITION_HISTORY_FILE, default_type=list)
    if not isinstance(cognition_log, list):
        cognition_log = []
    # Migrate-in-place: slim entries persisted before the strip list grew —
    # otherwise the old ~4 KB entries keep the file at ~2 MB for 500 more cycles.
    for _old in cognition_log:
        _r = _old.get("reason") if isinstance(_old, dict) else None
        if isinstance(_r, dict):
            for _k in ("candidates", "component_scores", "neuro_boosts",
                       "energy_boosts", "helpfulness_boosts"):
                _r.pop(_k, None)
    # Strip bulky diagnostics from reason before persisting. candidates (200+
    # entries) and component_scores (~1.8 KB/entry — measured 53% of the file)
    # made cognition_history.json ~2 MB at the 500-entry cap, and that file is
    # re-parsed + re-serialized every cycle: a direct contributor to the cycle
    # slowdown behind the HARD:pulse_too_slow death. Keep ranked (top scored),
    # features_on, dominant_affect, and weights.
    _REASON_STRIP = ("candidates", "component_scores", "neuro_boosts",
                     "energy_boosts", "helpfulness_boosts")
    _reason_slim: dict | None = None
    if isinstance(reason, dict):
        _reason_slim = {
            k: v for k, v in reason.items()
            if k not in _REASON_STRIP
        }
    cognition_log.append({
        "choice": next_function,
        "reason": _reason_slim,
        "timestamp": now_iso_z(),
        "reward": round(float(actual_fb), 4),
        "is_agentic": bool(is_agentic),
        # Lane tag (Gap 3): finalize records think()'s pick — always the
        # deliberate (conscious-slot) lane. The executive lane's advances are
        # tracked on its own summary/queue, not in this history.
        "lane": "deliberate",
    })
    cognition_log = cognition_log[-500:]  # cap to prevent unbounded growth
    save_json(COGNITION_HISTORY_FILE, cognition_log)

    # 🧭 recent_picks tracking (feeds novelty/stagnation_signal in select_function)
    try:
        rp = context.get("recent_picks", [])
        if not isinstance(rp, list):
            rp = []
        rp.append(next_function)
        context["recent_picks"] = rp[-50:]  # keep a small rolling window
    except Exception as _e:
        record_failure("finalize.finalize_cycle.25", _e)

    save_json(COGNITION_STATE_FILE, {
        "last_cognition_choice": next_function,
        "repeat_count": repeat_count,
        "satisfaction": satisfaction,
        "recent_picks": context.get("recent_picks", []),  # <-- persisted for transparency
    })
    log_private(f"Cognition log now has {len(cognition_log)} entries. Last: {cognition_log[-1]}")

    # === Outcome-driven Brain: Per-tick decision record ===
    try:
        tick = (context.get("cycle_count") or {}).get("count", 0)
        # Keep the telemetry line SLIM: the full goal object, candidate list and
        # raw result used to be embedded here (~12 KB/line, unbounded growth and
        # the same candidates-list bloat already stripped from context.json /
        # cognition_history). Store compact summaries instead — the full records
        # live in cognition_history.json.
        _gc = bound_goal(context) or context.get("focus_goal") or {}
        goal_summary = None
        if isinstance(_gc, dict):
            goal_summary = {"id": _gc.get("id"), "title": _gc.get("title") or _gc.get("name")}
        elif _gc:
            goal_summary = {"title": str(_gc)[:80]}

        def _cand_name(c):
            if isinstance(c, (list, tuple)) and c:
                return str(c[0])
            if isinstance(c, dict):
                return str(c.get("name") or c.get("fn") or "")
            return str(c)[:40]

        _cands = context.get("last_candidates", []) or []
        event_payload = {
            "tick": tick,
            "goal": goal_summary,
            "decision": {
                "picked": next_function,
                "reason": str(reason)[:200],
                "candidate_count": len(_cands),
                "top_candidates": [_cand_name(c) for c in _cands[:3]],
                "is_action": bool(is_agentic),
            },
            "tools_used": context.get("last_tools", []),
            "reward": {
                "reward_signal": float(context.get("last_reward", 0.0)),
                "novelty": float(context.get("last_novelty", 0.0)),
                "acceptance_passed": bool(context.get("last_acceptance_pass", False)),
            },
            "followups": context.get("pending_actions", []),
        }
        emit_event(DECISION, event_payload)

        # The primary bandit update happens in ORRIN_loop.py after outcomes are
        # known (after think() returns). We do NOT call record_outcome_ctx here
        # because that wrote to the legacy bandit with a stale, text-derived score,
        # creating conflicting learning signals with the primary contextual bandit.
        # Use the delta-based reward (actual_fb) when available; fall back to
        # rule-based satisfaction so think_module.py reads a grounded signal.
        context["last_reward"] = actual_fb
    except Exception as _e:
        log_model_issue(f"Event emit/bandit record failed: {_e}")

    # --- Save action for next cycle ---
    action = {"next_function": next_function, "reason": reason}
    save_json(ACTION_FILE, action)
    return action
