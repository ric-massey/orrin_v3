# think/think_module.py
from __future__ import annotations
from core.runtime_log import get_logger

import sys
import time
from typing import Any, Dict, List

from utils.json_utils import load_json
from utils.emotion_utils import dominant_emotion
from utils.log import log_error

from utils.manage_cycle_count import manage_cycle_count
from think.think_utils.dreams_emotional_logic import dreams_and_emotional_logic
from think.think_utils.reflect_on_directive import reflect_on_directive
from think.think_utils.select_function import select_function  # NEW API supports legacy triple if kwargs passed
from think.think_utils.finalize import finalize_cycle
from think.think_utils.execute_cognitive_actions import execute_cognitive_action
from think.scratchpad import scratchpad_init, scratchpad_flush
from cognition.metacog import metacog_init, metacog_flush
from think.thought_stream import emit_thought

from behavior.speak import OrrinSpeaker
from cognition.selfhood.relationships import update_relationship_model
from cognition.selfhood.self_model_conflicts import update_self_model
from affect.affect_learning import update_affect_function_map

from paths import (
    SELF_MODEL_FILE, LONG_MEMORY_FILE, RELATIONSHIPS_FILE,
    COGNITIVE_FUNCTIONS_LIST_FILE, WORKING_MEMORY_FILE,
)
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# --- UI bridge: turn OrrinSpeaker output into REPLY lines without requiring .speak() ---
def _emit_reply_from_speaker(speaker: OrrinSpeaker, text: str, context: Dict[str, Any]) -> str:
    """
    Uses OrrinSpeaker.should_speak(..., force_speak=True) to craft the utterance,
    then prints 'REPLY: ...' to stdout so the Electron UI shows it.
    Never requires a .speak() method on OrrinSpeaker.
    """
    try:
        emo = context.get("affect_state") or {}
    except Exception:
        emo = {}
    utterance = ""
    try:
        # Force because these calls are explicit user-facing outputs
        utterance = speaker.should_speak(text or "", emo, context, force_speak=True) or (text or "")
    except Exception:
        utterance = text or ""
    try:
        sys.stdout.write(f"REPLY: {utterance}\n")
        sys.stdout.flush()
    except Exception as _e:
        record_failure("think_module._emit_reply_from_speaker", _e)
    # Deliver to the Face message awaiting a reply (no-op if nothing pending).
    try:
        from behavior.face_bridge import deliver_reply as _deliver_reply
        _deliver_reply(utterance)
    except Exception as _de:
        record_failure("think_module._emit_reply_from_speaker.2", _de)
    try:
        context["last_ai_timestamp"] = time.time()
    except Exception as _e:
        record_failure("think_module._emit_reply_from_speaker.3", _e)
    return utterance


def _load_available_functions() -> List[str]:
    names = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list)
    if not isinstance(names, list):
        return []
    # coerce to simple list[str]
    out: List[str] = []
    for it in names:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict) and "name" in it:
            out.append(str(it["name"]))
    return out


def think(context: Dict[str, Any]) -> Dict[str, Any]:
    cycle_start_time = time.perf_counter()

    try:
        # === 0) Init per-cycle workspaces ===
        scratchpad_init(context)
        metacog_init(context)

        # === 0b) Manage cycle count & defaults ===
        context, _cc = manage_cycle_count(context)
        cycle_count = (_cc.get("count", 0) if isinstance(_cc, dict) else int(_cc or 0))
        emit_thought("cycle_start", f"Cycle {cycle_count}", cycle=cycle_count)
        context.setdefault("committed_goal", None)
        context.setdefault("action_debt", 0)
        context.setdefault("act_now", False)
        context.setdefault("reflection_budget_exhausted", False)
        context.setdefault("recent_picks", [])  # NEW: track choices for stagnation_signal/novelty
        context.pop("minimum_viable_action", None)
        context.pop("_inner_loop_output", None)   # never let last cycle's reasoning bleed into expression

        # === 1) Load critical state ===
        self_model      = load_json(SELF_MODEL_FILE,        default_type=dict)
        long_memory     = load_json(LONG_MEMORY_FILE,       default_type=list)
        relationships   = load_json(RELATIONSHIPS_FILE,     default_type=dict)

        context["relationships"] = relationships
        working_memory            = context.get("working_memory", [])
        wm_updater                = context.get("update_working_memory")
        speaker                   = context.get("speaker", OrrinSpeaker(self_model, long_memory))

        # === 2) Dreams & emotional logic ===
        context, affect_state, threat_detector_response = dreams_and_emotional_logic(context)

        # === 2b) Introspective perception — imperfect by design ===
        # Computes what Orrin *thinks* he feels, which may differ from ground truth.
        # Ground truth continues to drive unconscious machinery (attention, rewards, drives).
        # The perceived state is what enters the system prompt and inner loop reasoning.
        try:
            from affect.introspection import compute_perceived_state as _cps
            _introspection = _cps(context)
            context["perceived_affect_state"]          = _introspection["perceived_affect_state"]
            context["introspection_clarity"]              = _introspection["introspection_clarity"]
            context["introspection_uncertain"]            = _introspection["uncertain"]
            context["introspection_granularity_failure"]  = _introspection.get("granularity_failure", False)
            # Sync into runtime_ctx so build_system_prompt() can access it without threading context
            from utils.runtime_ctx import get_cycle_context as _gcc
            _rtx = _gcc()
            if isinstance(_rtx, dict):
                _rtx["perceived_affect_state"]         = _introspection["perceived_affect_state"]
                _rtx["introspection_clarity"]             = _introspection["introspection_clarity"]
                _rtx["introspection_uncertain"]           = _introspection["uncertain"]
                _rtx["introspection_granularity_failure"] = _introspection.get("granularity_failure", False)
        except Exception as _e:
            record_failure("think_module.think", _e)

        # === 2c) Ambient thought (DMN equivalent) ===
        # Background fragments generated from emotional state, unresolved goals,
        # tensions. Suppressed during high cognitive load; surfaces during wandering.
        try:
            from cognition.ambient_thought import update_ambient as _ua, surface_text as _st
            _ambient_result = _ua(context)
            context["ambient_texture"]  = _ambient_result.get("surfaced", [])
            context["_ambient_surface_text"] = _st(_ambient_result.get("surfaced", []))
        except Exception:
            context["ambient_texture"]        = []
            context["_ambient_surface_text"]  = ""

        # === 2d) Rumination — specific, charged, uninvited return ===
        # Unlike ambient thought: one specific topic, partially intrudes even during
        # alert mode, amplified by suppression (Wegner rebound), never self-extinguishes.
        try:
            from cognition.rumination import update_rumination as _ur, surface_text as _rst, mark_resolved as _mr
            _rum_result = _ur(context)
            _surfaced_loop = _rum_result.get("surfaced")
            context["ruminative_loop"] = _surfaced_loop
            context["_rumination_text"] = _rst(_surfaced_loop)
            # Resolution path: a brooding loop that has returned many times without
            # resolution is automatically shifted toward reflective mode so it can decay.
            # Treynor et al. (2003): brooding that cannot find an outlet must be actively
            # redirected rather than left to cycle. mark_resolved() reduces charge by 75%
            # and shifts the loop to reflective mode — it does not erase the concern,
            # it opens a resolution pathway. Trigger: brooding mode + 8+ returns.
            if (
                _surfaced_loop
                and _surfaced_loop.get("mode") == "brooding"
                and int(_surfaced_loop.get("return_count", 0)) >= 8
            ):
                _mr(_surfaced_loop["id"])
        except Exception:
            context["ruminative_loop"]  = None
            context["_rumination_text"] = ""

        # === 2e) Theory of Mind — active real-time simulation of the other person ===
        # Infers what the person is currently thinking/wanting/expecting THIS moment.
        # Distinct from person_model (static trait prior): ToM is per-turn live inference.
        # Only runs when there is user input; returns None on autonomous cycles.
        try:
            from cognition.theory_of_mind import simulate as _tom_sim
            _tom_result = _tom_sim(context)
            context["theory_of_mind"]     = _tom_result
            context["_tom_text"]          = (_tom_result or {}).get("surface_text", "")
        except Exception:
            context["theory_of_mind"] = None
            context["_tom_text"]      = ""

        # === 2f) Felt time — subjective temporal texture ===
        # Time as experienced density and weight, not just a timestamp.
        # Informed by event density, cycles since last contact, and activation_level modulation.
        try:
            from cognition.temporal_state import update_temporal_state as _uft
            _ftime_result = _uft(context)
            context["temporal_state"]      = _ftime_result
            context["_ftime_text"]    = _ftime_result.get("surface_text", "")
        except Exception:
            context["temporal_state"]   = None
            context["_ftime_text"] = ""

        # === 2g) Energy mode — activation_level/engagement mode with EMA smoothing ===
        # Computes a stable cognitive mode (active/rest/reactive/neutral) from the
        # emotional state. EMA-smoothed so the mode shifts slowly (human-paced, ~8
        # cycle half-life). Sets energy_state, action_vs_reflect_bias, _rest_mode,
        # and _energy_mode_text on context — these drive select_function biases and
        # surface as a line in the inner loop.
        try:
            from motivation.energy_orientation import inject_into_context as _iem
            _iem(context)
        except Exception:
            context.setdefault("energy_mode", "neutral")
            context.setdefault("energy_state", "medium")
            context.setdefault("action_vs_reflect_bias", 0.5)
            context.setdefault("_rest_mode", False)
            context.setdefault("_energy_mode_text", "")

        # === 2h) Knowledge graph — observe from user input, inject context ===
        # Heuristic entity/relation extraction from user text each cycle.
        # Keeps a persistent world model of people, projects, concepts Orrin encounters.
        # LLM-assisted consolidation happens separately during dream_cycle.
        try:
            from cognition.knowledge_graph import observe as _kg_observe, get_context_for_prompt as _kg_ctx
            _kg_user_text = (context.get("latest_user_input") or "").strip()
            if _kg_user_text:
                _kg_observe(_kg_user_text, source="user_input", context=context)
                try:
                    from cognition.concept_memory import learn_from_text as _cm_learn
                    _cm_learn(_kg_user_text, source="user_input")
                except Exception as _e:
                    record_failure("think_module.think.2", _e)
            _kg_query = _kg_user_text or (context.get("committed_goal") or {}).get("title", "")
            context["_kg_text"] = _kg_ctx(_kg_query, limit=4) if _kg_query else ""
        except Exception:
            context["_kg_text"] = ""

        # === 2i) Concept memory — inject definitions for words in user input ===
        # Provides structured semantic knowledge (dog, earth, emotion, etc.) without LLM.
        try:
            from cognition.concept_memory import get_context_for_prompt as _cm_ctx
            _cm_query = (context.get("latest_user_input") or "").strip() or _kg_query
            context["_concept_text"] = _cm_ctx(_cm_query, limit=4) if _cm_query else ""
        except Exception:
            context["_concept_text"] = ""

        # === 3) Signals / attention ===
        top_signals = context.get("top_signals", [])
        context["filtered_signals"] = top_signals  # back-compat
        update_relationship_model(context)

        # Act-now nudge if stalled on a committed goal
        try:
            debt = int(context.get("action_debt", 0) or 0)
            if bool(context.get("committed_goal")) and debt >= 2:
                context["act_now"] = True
                context["reflection_budget_exhausted"] = True
                context["discouraged_functions"] = ["reflect", "plan", "analyz", "deliberat"]
                mv = (context["committed_goal"] or {}).get("next_action")
                if isinstance(mv, dict):
                    context["minimum_viable_action"] = mv
                if callable(wm_updater):
                    wm_updater("⏱️ Commit→Act: Reflection budget exhausted; biasing toward action.")
        except Exception as _e:
            record_failure("think_module.think.3", _e)

        # === 3b) Salience map — snapshot what's active before reasoning begins ===
        try:
            from think.state_processor import compute_cycle_state as _cs
            context["_cycle_state"] = _cs(context, user_input=context.get("latest_user_input", ""))
        except Exception as _e:
            record_failure("think_module.think.4", _e)

        # === 3c) Latent identity drift — surface to working memory if significant ===
        try:
            from cognition.selfhood.latent_identity import identity_drift_warning as _idw
            _drift_warning = _idw(context)
            if _drift_warning:
                from cog_memory.working_memory import update_working_memory as _uwm_drift
                _uwm_drift({
                    "content": _drift_warning,
                    "event_type": "identity_drift",
                    "importance": 3,
                    "priority": 2,
                    "tags": ["drift", "identity", "latent"],
                })
        except Exception as _e:
            record_failure("think_module.think.5", _e)

        # === 4) Directive reflection (kept as-is) ===
        if cycle_count % 30 == 0:
            _ = reflect_on_directive(self_model, context)

        # === 5) Available functions (for transparency/UI only) ===
        context["available_functions"] = context.get("available_functions") or _load_available_functions()

        # === 6) Pick next cognitive function via selector ===
        sel = select_function(context, threat_detector_response=threat_detector_response)

        # Defaults
        fn_name: str = ""
        reason: Dict[str, Any] = {"via": "auto-selected", "candidates": context.get("available_functions", [])}
        is_action: bool = False
        selected_args = None        # CHANGED: capture args if selector provided them
        selected_kwargs = None      # CHANGED: capture kwargs if selector provided them

        if isinstance(sel, tuple) and len(sel) == 3:
            fn_name, reason, is_action = sel
        elif isinstance(sel, str):
            fn_name = sel
        elif isinstance(sel, dict):
            # CHANGED: only treat as an action if it declares a behavior 'type'
            if "type" in sel:
                try:
                    execute_cognitive_action(sel, context)
                    is_action = True
                except Exception as _e:
                    record_failure("think_module.think.6", _e)
                # even if executed, allow returning the chosen name for logging if present
                fn_name = sel.get("name") or fn_name
            else:
                # Dict-shaped cognition selection: accept name + optional args/kwargs
                fn_name = (sel.get("name") or sel.get("next_function") or "").strip()
                if isinstance(sel.get("args"), (list, tuple)):
                    selected_args = list(sel["args"])
                if isinstance(sel.get("kwargs"), dict):
                    selected_kwargs = dict(sel["kwargs"])

        if not isinstance(fn_name, str) or not fn_name.strip():
            # Before bailing: drain one pending action so the queue isn’t silently skipped.
            _pending = context.get("pending_actions")
            if isinstance(_pending, list) and _pending:
                _queued = _pending.pop(0)
                if isinstance(_queued, dict) and _queued.get("type"):
                    return {"context": context, "action": _queued}
            return {"context": context}

        fn_name = fn_name.strip()
        goal_title_for_emit = (context.get("committed_goal") or {}).get("title", "")
        emit_thought(
            "function_selected",
            f"Selected: {fn_name}",
            full_trace=str(reason)[:400] if reason else "",
            goal=goal_title_for_emit,
            cycle=cycle_count,
        )

        # NOTE: stagnation_signal is now driven authoritatively by select_function's
        # anti-repeat guard, which submits it through submit_affect() into
        # core_signals (where the reader looks first) so it actually persists and
        # accumulates across cycles. The old top-level `emo["stagnation_signal"] +=`
        # writer here was clobbered by per-cycle decay and never reached core_signals,
        # leaving the signal stuck at 0.000 — removed to avoid a dead second source.

        # Stash decision metadata on context so downstream executors can learn/reward
        try:
            context["last_decision"] = {
                "picked": fn_name,
                "reason": reason,  # includes features_on, candidates, scores, decision_id (from selector)
                "ts": time.time(),
            }
        except Exception as _e:
            record_failure("think_module.think.7", _e)

        # Link dominant emotion → function with last cycle's actual reward as signal.
        # Previously called without reward_signal so it always incremented +1.0 —
        # making it a pure frequency counter, not a learner. Using context["last_reward"]
        # (set by finalize_cycle at end of previous cycle) gives a real outcome signal.
        dom_emo = dominant_emotion(affect_state)
        if dom_emo:
            try:
                _last_reward = float(context.get("last_reward") or 0.5)
                update_affect_function_map(dom_emo, fn_name, reward_signal=_last_reward)
            except Exception as _e:
                record_failure("think_module.think.8", _e)

        # === 7) Symbolic context pass (no automatic LLM) ===
        # LLM is a tool Orrin can call explicitly via cognitive functions —
        # not a background engine that runs every cycle. The inner_loop
        # (draft→critique→revise via LLM) is intentionally skipped here.
        # action_gate and individual functions may still invoke LLM as a
        # deliberate tool when the selected function requires it.
        _inner_meta = "output"
        context["_inner_meta"] = _inner_meta

        # === 8) Basal ganglia: evaluate + maybe act ===
        from think.think_utils.action_gate import evaluate_and_act_if_needed
        _ = evaluate_and_act_if_needed(
            context,
            affect_state=affect_state,
            long_memory=long_memory,
            speaker=speaker,
        )
        context.pop("_inner_loop_act_bias", None)
        context.pop("_inner_meta", None)

        # === 10) Finalize cycle (pass FULL reason dict) ===
        user_input = context.get("latest_user_input")

        # Keep the full reason dict (or wrap a string)
        full_reason = reason if isinstance(reason, dict) else {"note": str(reason), "via": "unknown"}

        # (optional) expose top data back on context for downstream logging
        try:
            context["last_candidates"] = list(full_reason.get("candidates") or [])[:12]
            context["last_ranked"] = list(full_reason.get("ranked") or [])[:12]
        except Exception as _e:
            record_failure("think_module.think.9", _e)

        # Flush scratchpad + metacog before finalizing
        try:
            scratchpad_flush(context)
        except Exception as _e:
            record_failure("think_module.think.10", _e)
        try:
            metacog_flush(context)
        except Exception as _e:
            record_failure("think_module.think.11", _e)

        try:
            _ = finalize_cycle(
                context,
                user_input,
                fn_name,
                full_reason,    # <-- pass the full reason dict
                speaker,
            )
        except Exception as _fe:
            log_error(f"[think] finalize_cycle failed: {_fe}")

        # === 11) Update self model (non-blocking) ===
        try:
            update_self_model()
        except Exception as _e:
            record_failure("think_module.think.12", _e)

        # === 12) Persist pieces onto context ===
        context["self_model"] = self_model
        context["long_memory"] = long_memory
        # Don't overwrite affect_state with start-of-cycle snapshot — keep live in-cycle updates
        if "affect_state" not in context:
            context["affect_state"] = affect_state
        # Reload working_memory from disk to include all writes made during this cycle
        try:
            context["working_memory"] = load_json(WORKING_MEMORY_FILE, default_type=list)
        except Exception:
            context.setdefault("working_memory", working_memory)
        context["cycle_count"] = {"count": cycle_count}
        context["last_think_time"] = time.time()
        cycle_duration_s = time.perf_counter() - cycle_start_time
        context["last_cycle_duration"] = cycle_duration_s
        try:
            from observability.metrics import step_latency_ms_gauge
            step_latency_ms_gauge.set(cycle_duration_s * 1000.0)
        except Exception as _e:
            record_failure("think_module.think.13", _e)
        context.pop("filtered_signals", None)

        # === 13) Return Orrin-friendly shape (with optional args/kwargs) ===
        if is_action:
            return {"action": {"name": fn_name, "type": fn_name}, "context": context}

        out = {"next_function": fn_name, "context": context}
        # CHANGED: pass through args/kwargs when provided so ORRIN.py can forward them
        if selected_args is not None:
            out["args"] = selected_args
        if selected_kwargs is not None:
            out["kwargs"] = selected_kwargs
        return out

    except Exception as e:
        # Do not raise here; ORRIN.py has routing/repair. Just annotate context so fallback can proceed.
        log_error(f"THINK() CRASHED: {e}\n{__import__('traceback').format_exc()}")
        context["last_think_error"] = str(e)
        return {"context": context}
