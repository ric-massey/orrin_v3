# brain/ORRIN_loop.py
# V1 cognitive loop extracted as a callable for integration with v2's main.py.
# Call run_cognitive_loop(...) in a daemon thread from main.py.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import os
import signal
import time
import traceback
import warnings
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv
_log = get_logger(__name__)
load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

warnings.filterwarnings(
    "ignore",
    message="`clean_up_tokenization_spaces` was not set.*",
    category=FutureWarning,
    module="transformers",
)

from brain.think.think_module import think
from brain.think.think_utils.action_gate import take_action

from brain.think.loop_helpers import (
    emit_trace,
    compute_reward,
    emotional_delta_reward,
    blend_reward,
    reason_string,
    names,
    discover_callable_maps,
    execute_action_via_registries,
    bandit_learn,
)

from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS

from brain.affect.affect_drift import check_affect_drift

from brain.cognition.planning.reflection import record_decision

from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_error, log_private, log_activity, log_model_issue
from brain.utils.emotion_utils import log_penalty_signal, log_uncertainty_spike

from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure, dump_summary as _dump_failure_summary
from brain.utils.token_meter import dump_summary as _dump_token_summary


from brain.paths import (
    CONTEXT, WORKING_MEMORY_FILE,
)

# ── Face & Brain UI telemetry ──────────────────────────────────
# Fail-safe UI/telemetry emission for the loop's lifecycle, extracted to
# brain/loop/telemetry.py (Phase 4A). The bridge buffers on a daemon thread and
# never raises, so cognition never blocks or crashes on telemetry.
from brain.loop.telemetry import (
    _bridge, _push_event, _ui_stage, _ui_memory,
)





Context = Dict[str, Any]

# Functions that engage Orrin with his environment rather than pure internal computation.
# Clark (1997) embodied cognition; Lave (1988) situated action.
# Used by the outward-debt counter below and by finalize.py's satisfaction scorer.
_OUTWARD_FNS: frozenset = frozenset({
    "look_outward", "look_around", "leave_note", "write_desktop_note",
    "survey_environment", "read_clipboard", "announce_to_dashboard",
    "seek_novelty", "pursue_committed_goal", "write_cognitive_function",
    "write_tool", "wikipedia_search", "read_rss", "research_topic",
    "fetch_and_read", "search_own_files", "grep_files", "check_user_presence",
    "save_note", "notify_user",
})

# Cognitive-function dispatch, extracted to brain/loop/invoke.py (Phase 4A).
from brain.loop.invoke import _invoke_cognition

# Boot / context construction, extracted to brain/loop/boot.py (Phase 4A).
from brain.loop.boot import _boot_context, _verify_production_capability  # noqa: F401

# Sense / state-refresh stage, extracted to brain/loop/sense.py (Phase 4A).
from brain.loop.sense import sense_and_refresh, _apply_transient_signal_decay  # noqa: F401
# Recall + integration stage, extracted to brain/loop/reflect.py (Phase 4A).
from brain.loop.reflect import integrate_recall_and_baseline, tier1_health_check
def run_cognitive_loop(
    pulse=None,
    goals_api=None,
    memory_daemon=None,
    stop_event=None,
    cycle_sleep: float = 20.0,
) -> None:
    """
    Main cognitive loop. Runs forever (until stop_event is set or KeyboardInterrupt).

    Args:
        pulse: v2 Pulse instance — ticked each cognitive cycle so watchdogs know brain is alive.
        goals_api: v2 GoalsAPI instance — used directly via goal_io + its event bus.
        memory_daemon: v2 MemoryDaemon instance — used directly via memory_io.
        stop_event: threading.Event — set externally to stop the loop cleanly.
        cycle_sleep: seconds to sleep between cognitive cycles (default 10).
    """
    # SIGTERM → set stop_event so the loop exits cleanly (same path as KeyboardInterrupt).
    import threading as _thr_sig
    if stop_event is None:
        stop_event = _thr_sig.Event()
    def _sigterm_handler(*_):
        log_activity("SIGTERM received — stopping cognitive loop.")
        stop_event.set()
    # Signal handlers can only be installed from the main thread. When the loop
    # runs in a worker thread (the launcher's `orrin-brain` thread), skip it — the
    # launcher already owns SIGTERM/SIGINT and drives shutdown via stop_event.
    if _thr_sig.current_thread() is _thr_sig.main_thread():
        try:
            signal.signal(signal.SIGTERM, _sigterm_handler)
        except (OSError, ValueError) as _e:
            record_failure("ORRIN_loop.run_cognitive_loop", _e)

    # Goals: talk to the single GoalsAPI directly + subscribe to its event bus
    # (no adapter object). Failed-goal reactions are event-driven, not polled.
    _goals_api = goals_api
    if _goals_api:
        try:
            import brain.goal_io as goal_io
            goal_io.install_event_handler(_goals_api)
        except Exception as _gie:
            log_error(f"goal_io.install_event_handler failed: {_gie}")

    # Memory: call the v2 memory engine directly via memory_io (no adapter object).
    _mem_daemon = memory_daemon

    # Start background tool runner (drains queued tool requests every 30s)
    _tool_runner = None
    _ToolRunner_cls = None
    try:
        from brain.agency.tool_runner import ToolRunner as _ToolRunner_cls
        _tool_runner = _ToolRunner_cls(interval_s=30.0)
        _tool_runner.start()
    except Exception as e:
        log_error(f"ToolRunner failed to start: {e}")

    # Evaluator daemon (delayed reward signals)
    _evaluator = None
    try:
        from brain.eval.evaluator_daemon import EvaluatorDaemon
        _evaluator = EvaluatorDaemon()
    except Exception as e:
        log_error(f"EvaluatorDaemon failed to init: {e}")

    # ── Layer 0: always-on embodiment threads ──────────────────────────
    # These run independently of the cognitive loop. The loop reads their
    # state each cycle — it does not trigger them.
    try:
        from brain.embodiment import setpoint_regulation as _setpoint_regulation_mod
        _setpoint_regulation_mod.start()
        log_activity("[embodiment] setpoint_regulation daemon started.")
    except Exception as _e0:
        log_error(f"[embodiment] setpoint_regulation failed to start: {_e0}")

    try:
        from brain.embodiment import sensory_stream as _sensory_mod
        _sensory_mod.start()
        log_activity("[embodiment] sensory_stream started.")
    except Exception as _e0:
        log_error(f"[embodiment] sensory_stream failed to start: {_e0}")

    try:
        from brain.embodiment import drive_engine as _drive_mod
        _drive_mod.start()
        log_activity("[embodiment] drive_engine started.")
    except Exception as _e0:
        log_error(f"[embodiment] drive_engine failed to start: {_e0}")

    try:
        from brain.embodiment import social_presence as _social_mod
        _social_mod.start()
        log_activity("[embodiment] social_presence started.")
    except Exception as _e0:
        log_error(f"[embodiment] social_presence failed to start: {_e0}")

    try:
        from brain.embodiment import subconscious as _subcon_mod
        _subcon_mod.start()
        log_activity("[embodiment] subconscious started.")
    except Exception as _e0:
        log_error(f"[embodiment] subconscious failed to start: {_e0}")

    # ── Phase 5: continuous Executive daemon (gated OFF by default) ────────────
    # Starts ONLY when ORRIN_EXECUTIVE_DAEMON is set; otherwise a no-op and the
    # interleaved Phase-4 executive_tick remains in charge. When it runs, the
    # interleaved call below is skipped (mutual exclusion) so goals advance
    # continuously off the 20s cycle without double execution.
    try:
        from brain.cognition.planning import executive as _executive_mod
        if _executive_mod.start(stop_event) is not None:
            log_activity("[executive] continuous Executive daemon started (Phase 5).")
    except Exception as _e0:
        log_error(f"[executive] daemon failed to start: {_e0}")

    context = _boot_context()

    # Boot-time scratchpad audit: warn about cognition modules that bypass the wrapper
    try:
        from brain.think.think_generate import audit_direct_callers as _audit
        _audit(warn_only=True)
    except Exception as _audit_e:
        log_error(f"[boot] scratchpad audit failed: {_audit_e}")

    # Build callable maps AFTER boot so agency functions (added in _boot_context) are included
    COG_MAP, BEH_MAP = discover_callable_maps()
    BEH_NAMES = set(names(BEHAVIORAL_FUNCTIONS))

    _final_reflection_done = False

    _watchdog_check_every = 10  # check tool runner health every N cycles
    _cycle_num = 0

    while True:
        # C5 CORRIGIBILITY (proactive_resource_plan.md): the shutdown path is
        # checked FIRST, every cycle, with NO dependency on energy/EVC/τ/_rest_mode.
        # The reaper (Layer 0) and SIGTERM set stop_event independently; the energy
        # layer can bias function choice but can NEVER block or delay this exit, so a
        # self-regulating agent can never resist shutdown to "protect its recovery."
        # Empirically verified: the reaper hard-killed the loop at resource_deficit
        # 0.947 without obstruction. Soares et al. (2015) corrigibility.
        if stop_event and stop_event.is_set():
            log_activity("Cognitive loop stop event received; exiting.")
            break

        # ── Mortality: natural lifespan endpoint ───────────────────────────
        if context.get("_orrin_dying"):
            log_activity("[mortality] Lifespan elapsed — Orrin's loop is ending.")
            break

        # ── ToolRunner watchdog: restart if thread died ────────────────────
        _cycle_num += 1
        if _evaluator is None and _cycle_num % 100 == 0:
            try:
                from brain.eval.evaluator_daemon import EvaluatorDaemon as _ED_retry
                _evaluator = _ED_retry()
                log_activity("[evaluator] EvaluatorDaemon re-init succeeded.")
            except Exception as _ed_retry_e:
                log_error(f"[evaluator] Re-init retry failed: {_ed_retry_e}")
        if _cycle_num % _watchdog_check_every == 0 and _ToolRunner_cls is not None:
            if _tool_runner is None or not _tool_runner._thread.is_alive():
                log_error("[watchdog] ToolRunner thread died — restarting.")
                try:
                    _tool_runner = _ToolRunner_cls(interval_s=30.0)
                    _tool_runner.start()
                except Exception as _wr_e:
                    log_error(f"[watchdog] ToolRunner restart failed: {_wr_e}")

        # ── Terminal mode: reaper fired, dying window is open ──────────────
        try:
            from reaper.reaper import is_dying as _is_dying
            if _is_dying():
                if not _final_reflection_done:
                    _final_reflection_done = True
                    log_activity("[terminal] Dying window active — running final reflection.")
                    try:
                        from brain.cognition.terminal import final_reflection as _final_reflection
                        _final_reflection(context if "context" in dir() else {})
                    except Exception as _e:
                        log_error(f"final_reflection failed: {_e}")
                # Loop continues but only final_reflection runs; reaper will kill later
                import time as _t; _t.sleep(2)
                continue
        except ImportError as _e:
            record_failure("ORRIN_loop.run_cognitive_loop.2", _e)

        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            log_activity(f"Starting cycle at {timestamp}")
            _push_event("cycle_start", ts=timestamp, cycle=get_cycle_count())

            context, affect_state = sense_and_refresh(_goals_api, timestamp)
            if context.get("emergency_action"):
                emergency = context["emergency_action"]
                log_error(f"EMERGENCY ACTION TRIGGERED: {emergency.get('reason', str(emergency))}")
                log_private(f"EMERGENCY ACTION: {emergency}")
                break

            context = integrate_recall_and_baseline(context, _mem_daemon)

            acted_this_cycle = False
            try:
                from brain.cognition.action_accounting import reset_cycle_action_flags
                reset_cycle_action_flags(context)
                context["_cycle_index"] = int(get_cycle_count())
            except Exception as _e:
                record_failure("ORRIN_loop.reset_cycle_action_flags", _e)
            result           = None
            reward           = 0.0
            feats            = {}

            context = tier1_health_check(context)

            # ── Executive (procedural lane) — dual_process_loop.md §6.1 ─────────
            # PHASE 1: READ-ONLY DRY RUN. Observes the committed goals' next steps
            # and records what the background "dribble" WOULD advance, on
            # context["_exec_dryrun"] (telemetry/baseline only). Writes nothing,
            # executes nothing — placed before think() so the cycle order
            # (Executive → … → think) is already correct for Phase 2+. Fail-safe.
            try:
                from brain.cognition.planning import executive as _exec_mod
                # Skip the interleaved tick when the Phase-5 continuous daemon owns
                # execution (mutual exclusion — no double execution, I3).
                _exec_summary = None if _exec_mod.is_daemon_running() else _exec_mod.executive_tick(context)
                if _exec_summary is None:
                    _exec_summary = context.get("_exec_dryrun")  # daemon's latest, for telemetry
                # Surface the §19.1 `executive` block to the UI (telemetry only).
                _tb_exec = _bridge()
                if _tb_exec is not None and isinstance(_exec_summary, dict):
                    try:
                        _tb_exec.update(executive=_exec_summary)
                    except Exception:
                        pass
            except Exception as _exe:
                record_failure("ORRIN_loop.executive_tick", _exe)

            # ── Metacog Monitor → Workspace breakthrough (Phase 3) ─────────────
            # The watcher observes the Executive's background progress and OFFERS
            # candidates to the Global Workspace (stuck / objective-unmet /
            # milestone / idle; dumb watchdog I12). Then update_workspace runs ONCE
            # here, BEFORE think(), so the deliberate pick can react to a
            # breakthrough that won consciousness (§7.1 ordering: Executive →
            # Monitor → Workspace → think). It biases the next pick, never preempts
            # (I7). Fail-safe; the end-of-cycle update_workspace still runs to
            # capture the post-action conscious moment.
            try:
                from brain.cognition.metacog import metacog_monitor as _mon
                _mon(context, _exec_summary if "_exec_summary" in dir() else None)
            except Exception as _mone:
                record_failure("ORRIN_loop.metacog_monitor", _mone)
            try:
                from brain.cognition.global_workspace import update_workspace as _uw_pre
                _uw_pre(context)
                # Mirror the §19.1 monitor + workspace blocks to the UI (fail-safe).
                _tb_mon = _bridge()
                if _tb_mon is not None:
                    try:
                        _tb_mon.update(
                            monitor={
                                "recent_breakthroughs": context.get("_monitor_breakthroughs") or [],
                                "watchdog": context.get("_monitor_watchdog") or [],
                            },
                            workspace={
                                "conscious": context.get("global_workspace") or {},
                                # The full competition this cycle (Fix 4): ranked
                                # candidates update_workspace stashed — so the UI
                                # can show what almost became conscious and why
                                # this won, not just the winner.
                                "candidates": context.get("_workspace_candidates") or [],
                            },
                        )
                    except Exception:
                        pass
            except Exception as _uwe:
                record_failure("ORRIN_loop.workspace_pre_think", _uwe)

            # ── Conscious ignition gate (Dehaene 2014; Baars 1988; Kahneman 2011) ─
            # Consciousness is a threshold crossing ("ignition"), not a metronome.
            # The unconscious substrate above (affect, embodiment, signals,
            # subconscious threads, workspace competition) ran this cycle REGARDLESS.
            # But only a salient / uncertain / conflicted cycle IGNITES into full
            # deliberate cognition. should_think() is the bar; the periodic floor
            # (MAX_SILENT_CYCLES) guarantees he never goes fully dormant.
            #
            # On a quiet (non-ignited) cycle Orrin stays in low-power default mode:
            # think() still runs for bookkeeping + cheap symbolic selection, but
            # deliberate System-2 recruitment (inner_loop) is withheld (see
            # think_module §7) and the selector damps expensive deliberate functions
            # (see select_function "unconscious damp"). This restores the
            # conscious/unconscious distinction that "always_on" had collapsed.
            # Disable with ORRIN_IGNITION_GATE=0 → exact old always-on behaviour.
            _ignited, _ign_reason = True, "always_on"
            if os.environ.get("ORRIN_IGNITION_GATE", "1") != "0":
                try:
                    from brain.think.consciousness_trigger import should_think as _should_think
                    _ignited, _ign_reason = _should_think(context)
                except Exception as _ige:
                    record_failure("ORRIN_loop.ignition_gate", _ige)
                    _ignited, _ign_reason = True, "ignition_error_failopen"
            context["_conscious_cycle"] = bool(_ignited)
            context["_ignition_reason"] = str(_ign_reason)
            if _ignited:
                log_activity(f"[consciousness] ignited: {_ign_reason}")
                # Only an ignited cycle resets the silent-run counter, so the
                # periodic floor in should_think() actually measures quiet time.
                context["_last_think_cycle"] = get_cycle_count()
                _ui_stage("plan", "Planning — deliberating the next move.")
            else:
                log_activity(f"[consciousness] quiet — unconscious cycle ({_ign_reason})")
                _ui_stage("plan", "Idling — below the threshold of deliberate thought.")
            result = think(context)

            _decision_id = (context.get("last_decision") or {}).get("reason", {}).get("decision_id")
            # Guarantee every cycle has a traceable decision_id so the evaluator WAL
            # never silently drops entries because the selector didn't run (exception,
            # action path, fallback).
            if not _decision_id:
                import uuid as _uuid
                _decision_id = str(_uuid.uuid4())
                try:
                    _ld = context.setdefault("last_decision", {})
                    _ld.setdefault("reason", {})["decision_id"] = _decision_id
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.10", _e)

            # Path A: behavior action
            if isinstance(result, dict) and "action" in result:
                action = result["action"]
                speaker = context.get("speaker")
                action_type = action.get("type")
                try:
                    from brain.cognition.metacog import metacog_note as _mn
                    _mn(context, "action", f"chose action {action_type!r}")
                except Exception as e:
                    record_failure("ORRIN_loop.metacog_note_action", e)

                if action_type not in BEH_NAMES:
                    log_error(f"Unknown action type: {action_type}. Skipping.")
                    log_model_issue(f"Unknown action type attempted: {action_type}")
                    try:
                        route_exception(RuntimeError(f"Unknown action {action_type}"),
                                        phase="action", context=context, extra={"action": action_type})
                    except Exception as e:
                        record_failure("ORRIN_loop.route_exception_action", e)
                    _ = try_auto_repair({"type": "UnknownAction", "msg": str(action_type),
                                         "trace": "", "phase": "action"}, context)
                    reward = -0.3
                    feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
                    record_decision(str(action_type or "unknown_action"),
                                    reason_string({"error": "unknown_action"}, reward, feats, "think.action"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_ua
                            _ew_append_ua(_decision_id, str(action_type or "unknown_action"), feats, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.11", _e)
                else:
                    try:
                        success = take_action(action, context, speaker)
                        acted_this_cycle = bool(success)
                        if success:
                            context["last_action_ts"] = time.time()
                            log_activity(f"Action Taken: {action_type}")
                            _push_event("function_executed", fn=action_type, cycle=get_cycle_count())
                        else:
                            log_error("take_action returned False")
                            log_penalty_signal(context, "impasse_signal", increment=0.3)
                        # 0.8 for success; negative reward for failures so the bandit
                        # can distinguish bad actions from neutral ones (floor was 0.0).
                        base_reward = 0.8 if success else -0.3
                        # For speak-family actions, modulate reward by ground truth
                        # grounding score so the bandit learns from real outcomes, not
                        # just whether the output pipe succeeded. Claim 3 fix: speak
                        # failures should produce real penalty, not constant 0.8.
                        if success and action_type in {"speak", "user_response", "ask_user"}:
                            # ── Store conversation exchange in long-term memory ──
                            # This is the most important write: every real exchange with
                            # Ric needs to persist. Without this, Orrin has no history.
                            try:
                                from brain.cog_memory.long_memory import update_long_memory as _ulm
                                _user_said  = (context.get("latest_user_input") or "").strip()
                                _orrin_said = (action.get("content") or context.get("_last_spoken") or "").strip()
                                if _user_said and _orrin_said:
                                    _ulm(
                                        f"[Conversation] Ric: {_user_said[:500]}\nOrrin: {_orrin_said[:500]}",
                                        event_type="conversation",
                                        importance=4,
                                        context=context,
                                    )
                                elif _orrin_said:
                                    _ulm(
                                        f"[Orrin said] {_orrin_said[:600]}",
                                        event_type="orrin_speech",
                                        importance=2,
                                        context=context,
                                    )
                            except Exception as _lm_e:
                                log_error(f"[long_memory] conversation write failed: {_lm_e}")

                            try:
                                from brain.symbolic.ground_truth import grounding_score as _gs
                                _gs_val = _gs(action_type)
                                # Blend: 60% base, 40% grounding signal so variance is real
                                # _gs_val=0.5 neutral → 0.8; _gs_val=0.2 poor → 0.56; _gs_val=0.8 good → 0.92
                                base_reward = 0.6 * base_reward + 0.4 * (0.4 + _gs_val * 0.8)
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.12", _e)
                        # Weight by goal progress when a goal is active
                        try:
                            from brain.cognition.planning.goal_progress import goal_weighted_reward as _gwr
                            reward = _gwr(base_reward, context, action_was_taken=acted_this_cycle, fn_name=action_type)
                        except Exception:
                            reward = base_reward
                        # Set acceptance flag so finalize's bonus applies correctly
                        context["last_acceptance_pass"] = bool(success)
                        feats = bandit_learn(action_type, context, reward, decision_id=_decision_id)
                        record_decision(action_type,
                                        reason_string({"success": success}, reward, feats, "think.action"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_a
                                _ew_append_a(_decision_id, action_type, feats, get_cycle_count(),
                                             committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _ewa_e:
                                log_model_issue(f"[evaluator] Path A WAL append failed: {_ewa_e}")
                    except Exception as e:
                        route_exception(e, phase="action", context=context)
                        _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                             "trace": "", "phase": "action"}, context)
                        log_error(f"Action execution failed: {e}")
                        log_penalty_signal(context, "impasse_signal", increment=0.3)
                        reward = 0.0
                        feats = bandit_learn(str(action_type or "unknown_action"), context, reward, decision_id=_decision_id)
                        record_decision(str(action_type or "unknown_action"),
                                        reason_string({"error": str(e)}, reward, feats, "think.action"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_ae
                                _ew_append_ae(_decision_id, str(action_type or "unknown_action"), feats or {}, get_cycle_count(),
                                              committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _ewa_e2:
                                log_model_issue(f"[evaluator] Path A WAL append (error branch) failed: {_ewa_e2}")

            # Path B: cognition function
            elif isinstance(result, dict) and "next_function" in result:
                fn_name = result["next_function"]

                # Tier 1 critical override — survival beats the bandit.
                # If setpoint_regulation flagged a critical condition this cycle, replace
                # the bandit's choice with the suggested repair function — but only
                # if that function is actually registered and callable.
                #
                # Bounded, not absolute: a persistent alert used to re-fire this
                # override on EVERY cycle, which (a) made update_affect_state
                # ~23% of all decisions and (b) vetoed every ε-exploration pick,
                # so dormant functions never got trials. Two bounds fix that:
                #   • cooldown — the same repair fn runs at most once per
                #     _T1_COOLDOWN cycles; between firings the bandit's pick
                #     stands (the alert signal still reaches the router).
                #   • futility — if the alert survives _T1_FUTILE consecutive
                #     overrides, the repair clearly isn't repairing; stand down
                #     for _T1_BACKOFF cycles and let normal cognition (incl.
                #     problem_refocus) take a different angle.
                _T1_COOLDOWN, _T1_FUTILE, _T1_BACKOFF = 3, 5, 50
                try:
                    if context.get("_tier1_critical") and context.get("_tier1_suggested_fn"):
                        _t1_fn = context["_tier1_suggested_fn"]
                        _t1_hist = context.setdefault("_t1_override_hist", {})
                        _t1_h = _t1_hist.setdefault(_t1_fn, {"streak": 0, "last_cycle": -10**9, "backoff_until": 0})
                        _t1_now = get_cycle_count()
                        if _t1_h["streak"] >= _T1_FUTILE and _t1_now >= _t1_h["backoff_until"]:
                            _t1_h["streak"] = 0  # backoff served — eligible again
                        if (_t1_fn in COGNITIVE_FUNCTIONS
                                and _t1_now >= _t1_h["backoff_until"]
                                and (_t1_now - _t1_h["last_cycle"]) >= _T1_COOLDOWN):
                            _t1_h["streak"] += 1
                            _t1_h["last_cycle"] = _t1_now
                            if _t1_h["streak"] >= _T1_FUTILE:
                                _t1_h["backoff_until"] = _t1_now + _T1_BACKOFF
                                log_activity(
                                    f"[setpoint_regulation] override futile: {_t1_fn!r} ran "
                                    f"{_T1_FUTILE}× without clearing the alert — standing down "
                                    f"{_T1_BACKOFF} cycles")
                            log_activity(f"[setpoint_regulation] critical override: {fn_name!r} → {_t1_fn!r}")
                            fn_name = _t1_fn
                    # Reset neglect counters when the suggested repair function runs —
                    # the alarm has been answered; allostatic load begins to recover.
                    _t1_sfn = context.get("_tier1_suggested_fn")
                    if _t1_sfn and fn_name == _t1_sfn:
                        _h1_ign = context.get("_h1_ignored_cycles", {})
                        for _aid in list(_h1_ign.keys()):
                            _h1_ign[_aid] = 0
                    context.pop("_tier1_critical", None)
                    context.pop("_tier1_suggested_fn", None)
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.13", _e)

                try:
                    from brain.cognition.metacog import metacog_note as _mn
                    _mn(context, "selection", f"selected function {fn_name!r}")
                except Exception as e:
                    record_failure("ORRIN_loop.metacog_note_selection", e)
                meta_or_fn = COGNITIVE_FUNCTIONS.get(fn_name)
                fn = (meta_or_fn.get("function") if isinstance(meta_or_fn, dict) else meta_or_fn)

                try:
                    if callable(fn):
                        # Pre-step environment snapshot for delta-based reward.
                        _snap = None
                        _tick_ms = None
                        _env_delta = None
                        try:
                            from brain.cognition.planning.env_snapshot import (
                                take_snapshot as _snap,
                                apply_milestone_updates as _tick_ms,
                                delta_reward as _env_delta,
                            )
                        except Exception as e:
                            record_failure("ORRIN_loop.import_env_snapshot", e)
                        _pre_snap = _snap(context) if _snap else {}

                        _emo_pre = dict(context.get("affect_state") or {})
                        # Proactive-resource Phase 0 (OBSERVE-ONLY): time the act so
                        # the interoceptive cost model can learn expected cost and
                        # report prediction error / would-be EVC / τ candidate. No
                        # behavior change. docs/proactive_resource_plan.md.
                        _intero_t0 = time.perf_counter()
                        fn_result = _invoke_cognition(
                            fn, fn_name, context,
                            args=result.get("args") if isinstance(result, dict) else None,
                            kwargs=result.get("kwargs") if isinstance(result, dict) else None,
                        )
                        try:
                            _lat_ms = (time.perf_counter() - _intero_t0) * 1000.0
                            from brain.cognition.interoception import observe as _intero_observe
                            _io = _intero_observe(fn_name, _lat_ms, context)
                            _tb_io = _bridge()
                            if _tb_io is not None and _io:
                                try:
                                    _tb_io.update(interoception=_io)
                                except Exception:
                                    pass
                        except Exception as _ioe:
                            record_failure("ORRIN_loop.interoception_observe", _ioe)
                        _emo_post = dict(context.get("affect_state") or {})

                        # Post-step: tick milestones, snapshot again, compute reward.
                        _ticked_n = 0
                        try:
                            if _tick_ms is not None:
                                _ticked_n = _tick_ms(context)
                                context["_milestones_ticked_this_cycle"] = int(_ticked_n or 0)
                                # Complete the COMMITTED goal the moment its milestones
                                # are all genuinely met. It's excluded from the main-loop
                                # satiety sweep and the Executive's pursue is unreliable,
                                # so an all-met committed goal otherwise sits in_progress
                                # forever with impasse climbing. mark_goal_completed re-checks
                                # milestones (hollow guard), so this only closes a goal that
                                # is genuinely finished (milestones tick on real artifacts:
                                # note_written / research / production traces — env_snapshot).
                                _cgoal = context.get("committed_goal")
                                if isinstance(_cgoal, dict) and _cgoal.get("status") != "completed":
                                    _gms = [m for m in (_cgoal.get("milestones") or []) if isinstance(m, dict)]
                                    _cyc_now = get_cycle_count()
                                    # Progress clock: reset whenever a milestone ticks (or first sight).
                                    if _ticked_n or _cgoal.get("_last_progress_cycle") is None:
                                        _cgoal["_last_progress_cycle"] = _cyc_now
                                    if _gms and all(m.get("met") for m in _gms):
                                        try:
                                            from brain.cognition.planning.goals import (
                                                mark_goal_completed as _mgc,
                                                merge_updated_goal_into_tree as _mugit,
                                            )
                                            from brain.cognition.planning import goal_arbiter as _ga
                                            _mgc(_cgoal, context=context)
                                            if _cgoal.get("status") == "completed":
                                                _ga.apply((lambda _g: (lambda _t: _mugit(_t, _g)))(_cgoal),
                                                          source="loop.milestones_all_met")
                                                if (context.get("committed_goal") or {}).get("id") == _cgoal.get("id"):
                                                    context["committed_goal"] = None
                                                log_activity(f"[loop] Goal completed (milestones met): {(_cgoal.get('title') or '?')[:50]}")
                                        except Exception as _mce:
                                            record_failure("ORRIN_loop.complete_on_milestones", _mce)
                                    else:
                                        # Leave an unproductive goal when its local
                                        # reward rate has fallen below Orrin's learned
                                        # global background and the smooth leave hazard fires.
                                        from brain.cognition.reward_rate import (
                                            accrue_leave_pressure as _alp,
                                            is_stagnating as _is_stag,
                                            should_force_switch as _sfs,
                                        )
                                        _alp(context)
                                        if _is_stag(context) and _sfs(context):
                                            try:
                                                from brain.cognition.planning.pursue_goal import _degrade_or_disengage as _dod
                                                _dod(
                                                    _cgoal,
                                                    context,
                                                    (_cgoal.get("title") or "?"),
                                                    "local reward rate below background",
                                                )
                                            except Exception as _sde:
                                                record_failure("ORRIN_loop.stall_degrade", _sde)
                            _post_snap = _snap(context) if _snap else {}
                            _env_r = _env_delta(_pre_snap, _post_snap) if _env_delta else 0.5
                        except Exception:
                            _env_r = 0.5
                            _post_snap = {}

                        # Detect dispatch-level failure: _invoke_cognition returns
                        # {"status": "error", "error": "unsatisfiable_args: [...]"}
                        # when a cognitive function's required args can't be filled
                        # from context (e.g. add_goal(goal=), apply_emotion_routing(fn_scores=)).
                        # Without this the bandit was logging "Executed" for non-runs
                        # and rewarding them at the 0.20 underperformer floor.
                        _dispatch_failed = (
                            isinstance(fn_result, dict)
                            and fn_result.get("status") == "error"
                        )
                        if _dispatch_failed:
                            log_activity(
                                f"Skipped: {fn_name} (dispatch failed: "
                                f"{fn_result.get('error', 'unknown')})"
                            )
                        else:
                            log_activity(f"Executed: {fn_name}")
                        _push_event("function_executed", fn=fn_name, cycle=get_cycle_count())
                        _fn_str = str(fn_result or "")
                        _is_failure = _dispatch_failed or (
                            _fn_str.startswith("❌") or
                            _fn_str.startswith("Failed") or
                            "ERROR" in _fn_str[:30]
                        )
                        _status_r = 0.1 if _is_failure else 0.5
                        try:
                            from brain.cognition.action_accounting import mark_consequential_cognition
                            _reach = context.get("_last_reach_outcome")
                            mark_consequential_cognition(
                                context,
                                env_r=_env_r,
                                ticked_n=_ticked_n,
                                is_failure=_is_failure,
                                info_gain=(
                                    getattr(_reach, "info_gain", None)
                                    if _reach is not None else None
                                ),
                            )
                        except Exception as _e:
                            record_failure("ORRIN_loop.mark_consequential_cognition", _e)

                        # === Agency-based causal learning (Pearl Level 2) — stash ===
                        # Learn what this action does to Orrin's felt state. The felt
                        # consequence isn't visible yet: commit_affect (cycle end) only
                        # QUEUES the cycle's affect changes, which drain at NEXT cycle's
                        # update_affect_state. So stash (action, this cycle's pre-affect)
                        # and attribute the change at the start of next cycle, once it
                        # has actually landed. Gopnik (child-as-scientist) / Damasio
                        # (somatic markers) / Thorndike (law of effect): you learn
                        # causation by acting and noticing how you feel afterward.
                        if not _is_failure:
                            try:
                                _base_core = context.get("_emo_pre_cycle") or {}
                                if isinstance(_base_core, dict) and _base_core:
                                    context["_iv_pending"] = {
                                        "fn": fn_name,
                                        "core": {k: float(v) for k, v in _base_core.items()
                                                 if isinstance(v, (int, float))},
                                    }
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.14", _e)

                        # === Waking temporal causal discovery (booster) ===
                        # discover_from_wm_sequence otherwise only runs during dreams,
                        # so event→event regularities accrue too slowly. Run it on the
                        # recent WM window periodically while awake too. Pure reuse.
                        try:
                            if get_cycle_count() % 20 == 0:
                                from brain.symbolic.causal_graph import discover_from_wm_sequence as _dfs
                                _recent_wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                                _dfs([e for e in _recent_wm[-25:] if isinstance(e, dict)])
                        except Exception as _e:
                            record_failure("ORRIN_loop.run_cognitive_loop.15", _e)

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

                        # Expose for finalize.py's reward_signal signal.
                        context["_step_delta_reward"] = reward
                        # Feed env-delta reward back into the depth bandit when
                        # pursue_committed_goal ran this cycle (it stashes its chosen depth).
                        _pg_depth = context.pop("_pursue_goal_depth", None)
                        if _pg_depth is not None:
                            try:
                                from brain.cognition.planning.thinking_depth import update_depth as _ud
                                _ud(_pg_depth, reward)
                            except Exception as e:
                                record_failure("ORRIN_loop.update_depth", e)
                        # Mark acceptance: succeeded + (no goal OR goal was referenced in WM)
                        try:
                            _goal_title = ((context.get("committed_goal") or {}).get("title") or "").lower()
                            _wm_refs = any(
                                _goal_title in str(e).lower()
                                for e in (context.get("working_memory") or [])[-3:]
                            ) if _goal_title else True
                            context["last_acceptance_pass"] = not _is_failure and _wm_refs
                        except Exception:
                            context["last_acceptance_pass"] = not _is_failure
                        # Update emotion→function map with actual reward (not always 1.0).
                        # think_module.py uses last_reward from the *previous* cycle as a
                        # proxy; here we update with the real outcome for better accuracy.
                        try:
                            _core_pre = (_emo_pre.get("core_signals") or _emo_pre) or {}
                            _dom_emo = max(
                                (_core_pre or {}),
                                key=lambda k: float(_core_pre.get(k) or 0.0),
                            ) if _core_pre else ""
                            if _dom_emo:
                                from brain.affect.affect_learning import update_affect_function_map as _uefm
                                _uefm(_dom_emo, fn_name, reward_signal=reward)
                        except Exception as e:
                            record_failure("ORRIN_loop.emotion_function_map", e)
                        feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                        record_decision(fn_name, reason_string({"status": "ok", "fn_result": _fn_str[:80]}, reward, feats, "think.fn"),
                                        reward=reward, context=context)
                        # Tag memory write + append pending reward to WAL
                        if _decision_id:
                            try:
                                _cur_cycle = get_cycle_count()
                                _goal_id = str((context.get("committed_goal") or {}).get("id") or
                                               (context.get("committed_goal") or {}).get("title") or "")
                                if _mem_daemon:
                                    import brain.memory_io as memory_io
                                    memory_io.write(
                                        _mem_daemon, "function_output", _fn_str[:200],
                                        meta={
                                            "decision_id": _decision_id,
                                            "fn": fn_name,
                                            "cycle": _cur_cycle,
                                        },
                                    )
                                    _ui_memory("write",
                                               [{"id": fn_name, "summary": _fn_str[:140]}],
                                               store="long")
                                if _evaluator:
                                    from brain.eval.evaluator_wal import append_pending as _ew_append
                                    _ew_append(_decision_id, fn_name, feats, _cur_cycle,
                                               committed_goal_id=_goal_id or None)
                            except Exception as _ew_e:
                                log_model_issue(f"[evaluator] WAL append failed: {_ew_e}")
                    else:
                        log_model_issue(f"Unknown function requested: {fn_name}")
                        try:
                            route_exception(RuntimeError(f"Unknown function {fn_name}"),
                                            phase="cognition", context=context, extra={"fn": fn_name})
                        except Exception as e:
                            record_failure("ORRIN_loop.route_exception_cognition", e)
                        _ = try_auto_repair({"type": "UnknownFunction", "msg": str(fn_name),
                                             "trace": "", "phase": "cognition"}, context)
                        reward = -0.3
                        feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                        record_decision(fn_name, reason_string({"error": "unknown_fn"}, reward, feats, "think.fn"),
                                        reward=reward, context=context)
                        if _evaluator:
                            try:
                                from brain.eval.evaluator_wal import append_pending as _ew_append_ufn
                                _ew_append_ufn(_decision_id, fn_name, feats, get_cycle_count(),
                                               committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                            except Exception as _e:
                                record_failure("ORRIN_loop.run_cognitive_loop.24", _e)
                except Exception as e:
                    route_exception(e, phase="cognition", context=context, extra={"fn": fn_name})
                    _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                         "trace": "", "phase": "cognition"}, context)
                    log_error(f"Function {fn_name} crashed: {e}")
                    log_penalty_signal(context, "impasse_signal", increment=0.3 + 0.3 * float(affect_state.get("conflict_signal") or 0.4))
                    reward = 0.0
                    feats = bandit_learn(fn_name, context, reward, decision_id=_decision_id)
                    record_decision(fn_name, reason_string({"error": str(e)}, reward, feats, "think.fn"),
                                    reward=reward, context=context)

            # Path C: fallback (skipped entirely on silent/unconscious cycles)
            elif result is not None:
                log_model_issue("No valid instruction from think(). Fallback to selector.")
                log_uncertainty_spike(context, increment=0.1)
                import uuid as _uuid_fb
                _fb_decision_id = str(_uuid_fb.uuid4())
                sel = None
                try:
                    from brain.think.think_utils.select_function import select_function
                    sel = select_function(context)
                except Exception as _e:
                    log_model_issue(f"select_function failed: {_e}")

                if not sel or not isinstance(sel, str):
                    fb_meta_or_fn = COGNITIVE_FUNCTIONS.get("reflect_on_self_beliefs")
                    fb_fn = (fb_meta_or_fn.get("function") if isinstance(fb_meta_or_fn, dict) else fb_meta_or_fn)
                    if callable(fb_fn):
                        try:
                            fb_fn()
                            log_activity("Fallback executed: reflect_on_self_beliefs")
                            reward = 0.5
                        except Exception as e:
                            route_exception(e, phase="cognition", context=context,
                                            extra={"fn": "reflect_on_self_beliefs"})
                            _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                                 "trace": "", "phase": "cognition"}, context)
                            log_error(f"Fallback function crashed: {e}")
                            reward = 0.0
                    else:
                        log_model_issue("No fallback function available.")
                        reward = 0.0
                    feats = bandit_learn("reflect_on_self_beliefs", context, reward, decision_id=_fb_decision_id)
                    record_decision("reflect_on_self_beliefs",
                                    reason_string({"status": "fallback"}, reward, feats, "fallback.fn"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_c1
                            _ew_append_c1(_fb_decision_id, "reflect_on_self_beliefs", feats or {}, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _ewc1_e:
                            log_model_issue(f"[evaluator] Path C WAL append failed: {_ewc1_e}")
                else:
                    exec_result = execute_action_via_registries(sel, context, COG_MAP)
                    reward = compute_reward(exec_result)
                    feats = bandit_learn(sel, context, reward, decision_id=_fb_decision_id)
                    record_decision(sel, reason_string(exec_result, reward, feats, "fallback.sel"),
                                    reward=reward, context=context)
                    if _evaluator:
                        try:
                            from brain.eval.evaluator_wal import append_pending as _ew_append_c2
                            _ew_append_c2(_fb_decision_id, sel, feats or {}, get_cycle_count(),
                                          committed_goal_id=(context.get("committed_goal") or {}).get("id") or None)
                        except Exception as _ewc2_e:
                            log_model_issue(f"[evaluator] Path C (sel) WAL append failed: {_ewc2_e}")
                    if isinstance(exec_result, dict) and exec_result.get("success"):
                        acted_this_cycle = True
                        context["last_action_ts"] = time.time()

            if not context.get("_reward_rate_updated_this_cycle"):
                try:
                    from brain.cognition.reward_rate import update_reward_rate
                    update_reward_rate(
                        context,
                        reward=float(reward or 0.0),
                        committed_goal_id=(
                            (context.get("committed_goal") or {}).get("id")
                        ),
                    )
                    context["_reward_rate_updated_this_cycle"] = True
                except Exception as _e:
                    record_failure("ORRIN_loop.update_reward_rate_fallback", _e)

            acted_this_cycle = acted_this_cycle or bool(context.pop("__acted_this_tick__", False))

            # Emotion drift check always runs — it's unconscious monitoring, not conscious thought
            try:
                check_affect_drift(context)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.25", _e)

            try:
                if context.get("committed_goal"):
                    context["action_debt"] = 0 if acted_this_cycle else int(context.get("action_debt", 0)) + 1
            except Exception as _e:
                log_model_issue(f"Guardrail accounting issue: {_e}")

            # Stall watchdog (raised from 90→180 because inner-loop cycles are longer)
            try:
                STALL_SEC = 180
                now = time.time()
                if context.get("committed_goal"):
                    last_ts = float(context.get("last_action_ts", 0.0) or 0.0)
                    if (now - last_ts) > STALL_SEC:
                        goal = context.get("committed_goal") or {}
                        mv = goal.get("next_action")
                        if isinstance(mv, dict):
                            mv_type = mv.get("type")
                            if mv_type in BEH_NAMES:
                                try:
                                    ok = take_action(mv, context, context.get("speaker"))
                                    if ok:
                                        acted_this_cycle = True
                                        context["last_action_ts"] = time.time()
                                        context["action_debt"] = 0
                                        log_activity(f"Watchdog executed MV action: {mv_type}")
                                    else:
                                        log_model_issue("Watchdog tried MV action; take_action returned False.")
                                    _wd_reward = 0.8 if ok else 0.0
                                    import uuid as _uuid_wd
                                    _wd_decision_id = str(_uuid_wd.uuid4())
                                    feats = bandit_learn(mv_type, context, _wd_reward, decision_id=_wd_decision_id)
                                    record_decision(mv_type, "watchdog minimum viable action",
                                                    reward=_wd_reward, context=context)
                                except Exception as _e:
                                    route_exception(_e, phase="action", context=context,
                                                    extra={"mv_type": mv_type})
                                    _ = try_auto_repair({"type": _e.__class__.__name__, "msg": str(_e),
                                                         "trace": "", "phase": "action"}, context)
                                    log_model_issue(f"Watchdog MV action failed: {_e}")
            except Exception as _e:
                log_model_issue(f"Watchdog error: {_e}")

            # Transparency trace
            try:
                chosen = None
                if isinstance(result, dict):
                    if "action" in result:
                        a = result["action"]
                        chosen = f"ACTION:{a.get('type', 'unknown')}"
                    elif "next_function" in result:
                        chosen = f"FN:{result.get('next_function')}"
                emit_trace(
                    chosen=chosen,
                    debt=context.get("action_debt", 0),
                    mode=context.get("mode"),
                    emotions=context.get("affect_state", {}),
                    committed=bool(context.get("committed_goal")),
                    last_action_ts=context.get("last_action_ts"),
                )
            except Exception as _e:
                log_model_issue(f"Trace emit failed: {_e}")

            # Push new goal proposals to the single GoalsAPI
            if _goals_api:
                import brain.goal_io as goal_io
                try:
                    goal_io.sync_proposed_goals(_goals_api, context)
                except Exception as e:
                    log_error(f"goal_io.sync_proposed_goals failed: {e}")

                # Record goal progress note every 5 cycles so long memory has a trail
                if context.get("committed_goal"):
                    try:
                        goal_io.record_goal_progress(context)
                    except Exception as e:
                        log_error(f"goal_io.record_goal_progress failed: {e}")

            # Write memory events to v2 MemoryDaemon
            if _mem_daemon:
                import brain.memory_io as memory_io
                try:
                    memory_io.flush_working_memory(_mem_daemon, context)
                except Exception as e:
                    log_error(f"memory_io.flush_working_memory failed: {e}")

                _cycle_n = get_cycle_count()
                # Every 10 cycles: backfill v2 compaction summaries → v1 long_memory.json
                if _cycle_n > 0 and _cycle_n % 10 == 0:
                    try:
                        added = memory_io.promote_summaries_to_long_memory(_mem_daemon, max_items=5)
                        if added:
                            log_activity(f"Promoted {added} v2 summary item(s) to long memory.")
                    except Exception as e:
                        log_error(f"memory_io.promote_summaries_to_long_memory failed: {e}")
                # Every 5 cycles: backfill recent long_memory.json entries → v2 so they're searchable
                if _cycle_n > 0 and _cycle_n % 5 == 0:
                    try:
                        ingested = memory_io.backfill_long_memory_to_v2(_mem_daemon, max_items=10)
                        if ingested:
                            log_activity(f"Backfilled {ingested} long memory item(s) to v2.")
                    except Exception as e:
                        log_error(f"memory_io.backfill_long_memory_to_v2 failed: {e}")

            # Evaluator tick — resolve pending delayed rewards from the WAL
            if _evaluator:
                try:
                    _evaluator.tick(context, get_cycle_count())
                except Exception as _ev_e:
                    log_model_issue(f"evaluator.tick failed: {_ev_e}")

            # Prediction generation — turn the causal model (now fed by agency-based
            # intervention edges) into falsifiable predictions while AWAKE, not only
            # during dreams. Rate-limited so predictions.json doesn't flood. This is
            # the consumer that closes the learning loop: edges → predictions →
            # (confirmed) → rules → understanding.
            try:
                if get_cycle_count() % 5 == 0:
                    from brain.cognition.prediction import generate_predictions as _gp, save_predictions as _sp
                    _recent_wm_p = load_json(WORKING_MEMORY_FILE, default_type=list) or []
                    _sp(_gp(context, _recent_wm_p[-15:]))
            except Exception as _ge:
                log_error(f"generate_predictions failed: {_ge}")

            # Prediction check — evaluate pending predictions, fire surprise signals
            try:
                from brain.cognition.prediction import check_predictions as _cp
                _cp(context)
            except Exception as _pe:
                log_error(f"check_predictions failed: {_pe}")

            # Dream cycle — fires when idle and 6h have elapsed since last dream.
            # Skipped while HostResourceGuard/VitalFloor has paused heavy cycles:
            # dream is restorative as felt experience, but its consolidation
            # footprint is memory-hungry and must yield under host/process pressure.
            try:
                from brain.cognition.dreaming.dream_cycle import should_dream, dream_cycle as _dream_cycle
                from reaper.host_resources import heavy_cycles_paused as _heavy_paused
                from reaper.vital_floor import vital_floor_shedding as _vital_shedding
                if (not _heavy_paused()) and (not _vital_shedding()) and should_dream(context):
                    import threading as _thr
                    _dt = _thr.Thread(
                        target=_dream_cycle, args=(context,),
                        name="orrin-dream", daemon=True,
                    )
                    _dt.start()
            except Exception as _de:
                log_error(f"dream_cycle check failed: {_de}")

            # Global workspace (unity layer): converge this cycle's parallel
            # contents into a single conscious moment, broadcast it, and extend
            # the continuous stream of experience. Makes him one experiencer
            # rather than a committee of subsystems.
            try:
                from brain.cognition.global_workspace import update_workspace as _uw
                _moment = _uw(context)
                if _moment:
                    tb = _bridge()
                    if tb is not None:
                        tb.update(extra={"awareness": _moment.get("content", "")})
            except Exception as _gwe:
                record_failure("ORRIN_loop.run_cognitive_loop.26", _gwe)

            # Second-order volition (free will): periodically reflect on the
            # desire currently in consciousness and either own or disown it
            # against his values — self-authorship, not just acting on impulse.
            try:
                if get_cycle_count() % 20 == 0:
                    from brain.cognition.selfhood.second_order_volition import reflect_on_desire as _rod
                    _rod(context)
            except Exception as _rve:
                record_failure("ORRIN_loop.run_cognitive_loop.27", _rve)

            # Will/commitment: decay the active resolve and expose its
            # follow-through bias (cleared automatically when goal done/faded).
            try:
                from brain.cognition.will import tick_commitment as _tick_commit
                _tick_commit(context)
            except Exception as _twe:
                record_failure("ORRIN_loop.run_cognitive_loop.28", _twe)

            # Native language faculty (#4): a LIGHT learning bout during idle
            # stretches, on top of the big consolidation in sleep. Idle-only and
            # infrequent so it never lags a conversation or hogs the 8 GB.
            try:
                _lang_user = bool((context.get("latest_user_input") or "").strip())
                if (not _lang_user) and get_cycle_count() % 100 == 0:
                    from brain.cognition.language.acquisition import consolidate_language as _cl
                    _cl(steps=12)

                # Roll completed short-term goals up into the long-term aspirations
                # they serve, and protect those aspirations from being lost or
                # wrongly completed — so long-term goals actually advance.
                if get_cycle_count() % 25 == 0:
                    try:
                        from brain.cognition.intrinsic_goals import credit_aspirations as _ca
                        _ca(context)
                    except Exception as _cae:
                        record_failure("ORRIN_loop.run_cognitive_loop.29", _cae)

                # P2 — fail artifact-gated production goals that blew their deadline
                # with nothing produced (turns the hollow "0 failures" into a real,
                # staked non-zero). P6 — reconcile the goal stores so the new
                # executable path can't reopen the resurrect/orphan-RUNNING desync
                # bugs, and existing-path desyncs become self-healing + measured.
                # Both run on the same 200-cycle epoch (one cadence constant).
                if get_cycle_count() % 200 == 0:
                    try:
                        from brain.cognition.planning.goals import fail_overdue_artifact_goals as _foag
                        _foag(context)
                    except Exception as _fae:
                        record_failure("ORRIN_loop.run_cognitive_loop.foag", _fae)
                    try:
                        from brain.cognition.planning.goal_reconcile import reconcile_goal_stores as _rgs
                        _rgs(context)
                    except Exception as _rge:
                        record_failure("ORRIN_loop.run_cognitive_loop.reconcile", _rge)

                # Bored, not busy → browse the shelf and read a particular book.
                # Boredom (stagnation) is the pull; this is reading by his own
                # restlessness, not a schedule. Throttled so it never hogs the CPU.
                if not _lang_user:
                    _stag = float(
                        (affect_state.get("core_signals") or affect_state).get("stagnation_signal", 0.0)
                    )
                    # Reading is the other memory-hungry heavy cycle: skip it while
                    # host/process resource guards have paused heavies.
                    from reaper.host_resources import heavy_cycles_paused as _heavy_paused
                    from reaper.vital_floor import vital_floor_shedding as _vital_shedding
                    if _stag > 0.5 and get_cycle_count() % 40 == 0 and not _heavy_paused() and not _vital_shedding():
                        from brain.cognition.language.acquisition import read_a_book as _rab
                        _line = _rab(context, steps=30)
                        if _line:
                            context["last_thought"] = _line
            except Exception as _lge:
                record_failure("ORRIN_loop.run_cognitive_loop.30", _lge)

            # ── Deterministic closure/maintenance tier (RECONCILED plan B/C/E) ──
            # Closure machinery already exists but was selection-starved — the
            # emotion-cued bandit never picked it (no prior, cold-start trap). Run
            # it here on slow cadences, decoupled from selection. fade_goals is in
            # _ALWAYS_EXCLUDE so it never ALSO competes as a deliberate choice
            # (no double execution). This is the same precedent the codebase uses
            # for update_affect_state and the apply_* per-cycle upkeep.
            try:
                _mcycle = get_cycle_count()

                # B1 — Goal retirement (% 50): drop terminal/invalid goals from the
                # active tree via the deterministic prune path (NOT bandit-selectable).
                if _mcycle > 0 and _mcycle % 50 == 0:
                    try:
                        from brain.cognition.planning.goals import (
                            load_goals, prune_goals, save_goals,
                        )
                        def _flat(_gs):
                            for _g in _gs:
                                if isinstance(_g, dict):
                                    yield _g
                                    yield from _flat(_g.get("subgoals") or [])
                        _before = load_goals()
                        _n_before = sum(1 for _ in _flat(_before))
                        _after = prune_goals(_before)
                        _n_after = sum(1 for _ in _flat(_after))
                        _retired = _n_before - _n_after
                        if _retired > 0:
                            save_goals(_after)
                            log_activity(
                                f"[maintenance] Retired {_retired} terminal/invalid goal(s)."
                            )
                        # Population gauge — record active count + mean age (Phase E).
                        try:
                            from datetime import datetime as _dt, timezone as _tz
                            from brain.cognition.planning.outcome_metrics import (
                                record_retired, record_goal_population,
                                record_maintenance_execution,
                            )
                            if _retired > 0:
                                record_retired(_retired)
                            _ages = []
                            _now = _dt.now(_tz.utc)
                            for _g in _flat(_after):
                                _c = _g.get("created_at") or _g.get("timestamp")
                                if isinstance(_c, str) and _c:
                                    try:
                                        _ct = _dt.fromisoformat(_c.replace("Z", "+00:00"))
                                        _ages.append((_now - _ct).total_seconds())
                                    except Exception:
                                        pass
                            _avg_age = (sum(_ages) / len(_ages)) if _ages else 0.0
                            record_goal_population(_n_after, _avg_age)
                            record_maintenance_execution()
                        except Exception as _me:
                            record_failure("ORRIN_loop.run_cognitive_loop.31", _me)
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.32", _e)

                # B2 — Goal fading (% 60): decay unattended goals toward dormant.
                # fade_goals is self-contained and records abandonment closures.
                if _mcycle > 0 and _mcycle % 60 == 0:
                    try:
                        from brain.cognition.planning.goal_lifecycle import fade_goals
                        fade_goals(context)
                        from brain.cognition.planning.outcome_metrics import (
                            record_maintenance_execution, flush as _om_flush,
                        )
                        record_maintenance_execution()
                        _om_flush()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.33", _e)

                # B3 — Population satiety (% 40): close exploration/understanding
                # goals whose drive is quenched, population-wide (not just focus).
                # Capped per pass; milestone-bearing/committed/lifetime goals skip
                # (they close via milestones / pursue_goal). is_sated's cycle-1 guard
                # and mark_goal_completed's hollow guard remain in force.
                if _mcycle > 0 and _mcycle % 40 == 0:
                    try:
                        from brain.cognition.planning.goals import (
                            load_goals, mark_goal_completed, merge_updated_goal_into_tree,
                            _TERMINAL_STATUSES,
                        )
                        from brain.cognition.planning import goal_arbiter
                        from brain.cognition.planning.goal_satiety import (
                            is_sated, _is_filesystem_exploration,
                        )
                        from brain.cognition.planning.outcome_metrics import (
                            record_satiety_closure, record_maintenance_execution,
                        )
                        _explore_markers = (
                            "understand", "learn about", "find out", "research",
                            "explore", "read more about",
                        )
                        _committed = (context.get("committed_goal") or {})
                        _committed_id = _committed.get("id") if isinstance(_committed, dict) else None
                        _K = 5
                        _checked = 0
                        _sated_closed = 0
                        for _g in load_goals():
                            if _checked >= _K:
                                break
                            if not isinstance(_g, dict):
                                continue
                            _status = str(_g.get("status") or "").lower()
                            if _status in _TERMINAL_STATUSES or _status in ("dormant", "paused"):
                                continue
                            if _g.get("never_complete"):
                                continue
                            if _committed_id and _g.get("id") == _committed_id:
                                continue
                            # Task/directional goals are not satiety-gated (mirror
                            # pursue_goal's tier split): trivial/minor close via
                            # milestones; aspiration/long_term never close here.
                            # mark_goal_completed's hollow guard still protects any
                            # milestone-bearing exploration goal from premature close.
                            if str(_g.get("tier") or "").lower() in (
                                "trivial", "minor", "aspiration", "long_term"
                            ):
                                continue
                            _blob = f"{_g.get('title') or ''} {_g.get('name') or ''}".lower()
                            _is_explore = (
                                any(m in _blob for m in _explore_markers)
                                or _is_filesystem_exploration(_g)
                            )
                            if not _is_explore:
                                continue
                            _checked += 1
                            _sated, _reason = is_sated(_g, context)
                            if not _sated:
                                continue
                            mark_goal_completed(_g, context=context)
                            if _g.get("status") == "completed":
                                goal_arbiter.apply(
                                    (lambda _gg: (lambda _t: merge_updated_goal_into_tree(_t, _gg)))(_g),
                                    source="maintenance.satiety",
                                )
                                _sated_closed += 1
                                log_activity(
                                    f"[maintenance] Satiety-closed "
                                    f"'{(_g.get('title') or _g.get('name') or '?')[:50]}' ({_reason})."
                                )
                        if _sated_closed:
                            record_satiety_closure(_sated_closed)
                        record_maintenance_execution()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.34", _e)
            except Exception as _mte:
                record_failure("ORRIN_loop.run_cognitive_loop.35", _mte)

            # Flush metacog trace to working memory as introspection
            try:
                from brain.cognition.metacog import metacog_flush as _mcf
                _mcf(context)
            except Exception as e:
                record_failure("ORRIN_loop.metacog_flush", e)

            # Decay behavioral adaptation pressures (Carver & Scheier, 1982):
            # Corrective signals should attenuate as the discrepancy is addressed,
            # not persist indefinitely. See behavioral_adaptation.py.
            try:
                from brain.cognition.behavioral_adaptation import decay_behavioral_pressure as _dbp
                _dbp(context)
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.36", _e)

            # ── Health streak monitor: track sustained health, fire setpoint_regulation reward ──
            # Runs every 5 cycles (cheap: reads one JSON, writes one JSON).
            # Positive health streak → emotional uplift + bandit reward.
            # Sustained sick cycles → mild distress signal + WM note.
            try:
                if _cycle_num % 5 == 0:
                    from brain.cognition.health_monitor import check_and_reward as _health_check
                    _health_check(context)
            except Exception as _hm_e:
                record_failure("ORRIN_loop.health_monitor", _hm_e)

            # ── Layer 0 post-cycle: plasticity + drive satisfaction ───────────
            _cycle_fn = (
                result.get("next_function") if isinstance(result, dict) and "next_function" in result
                else result.get("action", {}).get("type") if isinstance(result, dict) and "action" in result
                else ""
            ) or ""
            # Expose the chosen function so finalize.py's outward reward scorer can read it.
            context["last_function_chosen"] = _cycle_fn

            # Benchmark sampling (no-op unless ORRIN_BENCHMARK=1) — records the
            # per-cycle (stagnation_signal, chosen function) for B2 and, every 100
            # cycles, long-memory size + RSS for B1. See brain/benchmarks/.
            try:
                from brain.benchmarks import record_sample as _bench_sample
                _bench_sample(context)
            except Exception as _be:
                record_failure("ORRIN_loop.run_cognitive_loop.37", _be)

            # Outward-debt counter: tracks consecutive cycles without environmental
            # engagement.  Penalty accumulates in finalize._state_satisfaction.
            # Resets to 0 whenever an outward-facing function runs.
            if _cycle_fn in _OUTWARD_FNS:
                context["_outward_debt"] = 0
            else:
                context["_outward_debt"] = min(30, int(context.get("_outward_debt", 0) or 0) + 1)

            try:
                from brain.embodiment import plasticity as _plasticity_mod
                _plasticity_mod.apply_plasticity(_cycle_fn, context, reward)
            except Exception as _pe:
                record_failure("ORRIN_loop.plasticity", _pe)
            try:
                from brain.embodiment import drive_engine as _drive_mod
                _drive_mod.evaluate_cycle(_cycle_fn, context, reward)
            except Exception as _dse:
                record_failure("ORRIN_loop.drive_satisfy", _dse)
            try:
                from brain.motivation import substrate as _motiv_mod
                _motiv_mod.evaluate_cycle_satisfaction(_cycle_fn, reward)
            except Exception as _mse:
                record_failure("ORRIN_loop.motivation_satisfy", _mse)
            # Meta-controller threshold bandit: record outcome so UCB1 can adapt
            try:
                arm_id = context.get("_meta_ctrl_arm")
                if arm_id is not None:
                    from brain.think.meta_controller import record_outcome as _mc_record
                    _mc_record(int(arm_id), reward)
            except Exception as _mcre:
                record_failure("ORRIN_loop.meta_ctrl_record", _mcre)
            # Mark Orrin responded if he spoke this cycle
            try:
                if any(
                    isinstance(r, dict) and r.get("type") in {"speak", "respond", "reply"}
                    for r in [result] if isinstance(result, dict)
                ):
                    from brain.embodiment import social_presence as _social_mod
                    _social_mod.mark_orrin_responded()
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.38", _e)

            # Backstop: guarantee a Face message gets answered this cycle even if
            # the action gate didn't pick a speak action. No-op if already replied.
            try:
                from brain.behavior.face_bridge import force_reply as _force_reply
                _force_reply(context)
            except Exception as _fre:
                record_failure("ORRIN_loop.run_cognitive_loop.39", _fre)

            # Sync context["working_memory"] back to working_memory.json so dashboard and
            # update_working_memory() see the same data.
            # Strip embeddings and chunk items before saving — they're recomputed on demand
            # and their presence causes the file to balloon to 30+ MB (REAPER bait).
            try:
                wm = context.get("working_memory")
                if isinstance(wm, list):
                    _WM_STRIP = frozenset({"embedding", "items"})
                    _WM_MAX_CONTENT = 500
                    _wm_slim = []
                    for _wme in wm:
                        if isinstance(_wme, dict):
                            _s = {k: v for k, v in _wme.items() if k not in _WM_STRIP}
                            if isinstance(_s.get("content"), str) and len(_s["content"]) > _WM_MAX_CONTENT:
                                _s["content"] = _s["content"][:_WM_MAX_CONTENT]
                            _wm_slim.append(_s)
                        else:
                            _wm_slim.append(_wme)
                    save_json(WORKING_MEMORY_FILE, _wm_slim)
            except Exception as e:
                record_failure("ORRIN_loop.save_working_memory", e)

            # ── Affect convergence: integrate this cycle's affect proposals ────
            # Every subsystem that wanted to change affect this cycle submitted a
            # proposal via affect.arbiter.submit_affect() instead of mutating
            # affect_state directly. Commit integrates them all at once (weighted
            # sum nets contradictions), applies the homeostatic stability budget,
            # and queues the result into the affect_buffer so it drains gradually
            # through next cycle's update_affect_state. This is the single commit
            # point that replaces the old last-writer-wins races.
            try:
                from brain.affect.arbiter import commit_affect as _commit_affect
                _commit_affect(context)
            except Exception as _aae:
                record_failure("ORRIN_loop.affect_commit", _aae)

            # Persist context — strip large arrays that live in their own files
            try:
                # Defense-in-depth against context.json bloat: NEVER persist
                # foreign data-stores or context-in-itself. Even if a path pollutes
                # the live context (e.g. a blanket load_all_known_json merge), these
                # keys belong in their OWN files and must not balloon context.json
                # (which the per-cycle save + the 7s daemon load otherwise turn into
                # a memory leak — see meta_reflect fix).
                _CTX_STRIP = (
                    "long_memory", "context", "reflection_log", "habituation",
                    "cognition_history", "attention_history", "speech_log",
                    "causal_graph", "predictions", "knowledge_graph",
                    "symbolic_dream_log", "self_improvement_log", "dream_log",
                    "metacog_log", "chat_log", "memory_graph", "events", "trace",
                    "telemetry_history",
                )
                _ctx_to_save = {k: v for k, v in context.items() if k not in _CTX_STRIP}
                # Cap working_memory in context.json to last 25 entries
                if isinstance(_ctx_to_save.get("working_memory"), list):
                    _ctx_to_save["working_memory"] = _ctx_to_save["working_memory"][-25:]
                # Strip candidates list from last_decision.reason — it holds 200+ entries
                # and is the primary cause of context.json balloon (was 833KB).
                _ld = _ctx_to_save.get("last_decision")
                if isinstance(_ld, dict) and isinstance(_ld.get("reason"), dict):
                    _ld = dict(_ld)
                    _ld["reason"] = {k: v for k, v in _ld["reason"].items() if k != "candidates"}
                    _ctx_to_save["last_decision"] = _ld
                # Automatic bloat containment: the blacklist above only covers
                # *known* offenders, so any new bloat source leaks until someone
                # notices (the 833KB candidates incident). Strip any key whose
                # serialized size exceeds the cap and log its name, so future
                # bloat is contained and identified the cycle it appears.
                import json as _ctx_json
                _CTX_KEY_MAX_BYTES = 100_000
                for _ck in list(_ctx_to_save.keys()):
                    try:
                        _csz = len(_ctx_json.dumps(_ctx_to_save[_ck], default=str))
                    except Exception:
                        continue
                    if _csz > _CTX_KEY_MAX_BYTES:
                        del _ctx_to_save[_ck]
                        log_model_issue(
                            f"context.json bloat guard: stripped key '{_ck}' "
                            f"({_csz} bytes > {_CTX_KEY_MAX_BYTES}) — add it to its "
                            f"own file or to _CTX_STRIP"
                        )
                save_json(CONTEXT, _ctx_to_save)
            except Exception as _e:
                log_model_issue(f"Context save failed: {_e}")

            # ── Long-memory consolidation: every 5 cycles, promote important
            # working-memory entries that haven't been persisted yet.
            # This ensures cognitive observations, insights, and perceptions
            # accumulate into genuine long-term memory even on non-speech cycles.
            try:
                _cons_cycle = get_cycle_count()
                if _cons_cycle > 0 and _cons_cycle % 5 == 0:
                    from brain.cog_memory.long_memory import update_long_memory as _ulm_cons
                    _wm_now = context.get("working_memory") or []
                    for _wme in _wm_now[-10:]:
                        if not isinstance(_wme, dict):
                            continue
                        _wme_content = str(_wme.get("content", "")).strip()
                        _wme_type    = _wme.get("event_type", "thought")
                        _wme_imp     = int(_wme.get("importance", 1) or 1)
                        # Only promote entries with real substance
                        if (
                            _wme_imp >= 3
                            and len(_wme_content) > 60
                            and not _wme.get("_promoted_to_lm")
                            and not _wme.get("internal_telemetry")  # diagnostics/dicts never become autobiographical memory
                            and _wme_type not in ("system", "reward", "reward_penalty", "choice")
                        ):
                            _ulm_cons(
                                _wme_content,
                                event_type=_wme_type,
                                importance=_wme_imp,
                                context=context,
                            )
                            _wme["_promoted_to_lm"] = True
            except Exception as _cons_e:
                record_failure("ORRIN_loop.lm_consolidation", _cons_e)

            # Tick the v2 pulse so watchdogs see the brain is alive
            if pulse is not None:
                try:
                    pulse.tick()
                except Exception as e:
                    record_failure("ORRIN_loop.pulse_tick", e)

            if os.getenv("ORRIN_ONCE") == "1":
                log_activity("Single-cycle mode; exiting after one tick.")
                break

            cycle_num = get_cycle_count()
            print(f"Orrin cognitive cycle {cycle_num} complete.")

            # Periodic GC: force Python to release heap back to OS every 50 cycles.
            # SentenceTransformer's PyTorch allocator expands the heap; gc.collect()
            # ensures Python's reference-counted objects are cleaned up promptly.
            if cycle_num > 0 and cycle_num % 50 == 0:
                try:
                    import gc as _gc
                    _gc.collect()
                    try:
                        import torch as _torch
                        if _torch.cuda.is_available():
                            _torch.cuda.empty_cache()
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.40", _e)
                    log_private(f"[loop] GC pass at cycle {cycle_num}")
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.41", _e)

            if cycle_num > 0 and cycle_num % 100 == 0:
                try:
                    _dump_failure_summary()
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.42", _e)
                try:
                    _dump_token_summary()
                except Exception as _e:
                    record_failure("ORRIN_loop.run_cognitive_loop.43", _e)
                try:
                    from brain.cognition.self_extension import maybe_integrate_or_atrophy as _mia
                    _mia(context)
                except Exception as _miae:
                    record_failure("ORRIN_loop.integrate_or_atrophy", _miae)
                # Phase 2.2: failure-ledger review. The cadence here only polls
                # the gate — the function itself runs nothing unless ≥3 new
                # failures accumulated since the last review (event-driven).
                try:
                    from brain.cognition.reflection.review_failures import review_failures as _rvf
                    _rvf(context)
                except Exception as _rvfe:
                    record_failure("ORRIN_loop.review_failures", _rvfe)

            # Every 500 cycles (~2-3 hours at 20s/cycle): check for completed
            # fine-tuning jobs and update model_config if one succeeded.
            # Fine-tuning is how Orrin's generation actually changes over time.
            if cycle_num > 0 and cycle_num % 500 == 0:
                try:
                    from brain.cognition.finetuning.finetune_pipeline import check_pending_jobs as _cpj
                    _ft_updates = _cpj()
                    if _ft_updates:
                        log_activity(f"[finetune] Job updates: {_ft_updates}")
                except Exception as _fte:
                    record_failure("ORRIN_loop.finetune_check", _fte)

            # Metabolism (§7, mapping #1): a smaller body runs at a slower metabolic
            # rate — the cadence multiplier stretches the inter-cycle sleep on a small
            # machine and compresses it on a large one. Not distress, just a smaller
            # heart at a lower rate. Fails safe to ×1.0.
            try:
                from brain.cognition.metabolism import cadence_multiplier as _cad
                _cycle_sleep_eff = cycle_sleep * _cad()
            except Exception:
                _cycle_sleep_eff = cycle_sleep
            time.sleep(_cycle_sleep_eff)

        except KeyboardInterrupt:
            print("\nCognitive loop stopped manually.")
            log_activity("Cognitive loop manually interrupted.")
            break

        except Exception as e:
            route_exception(e, phase="loop", context=context)
            _ = try_auto_repair({"type": e.__class__.__name__, "msg": str(e),
                                 "trace": "", "phase": "loop"}, context)
            print(f"Cognitive loop crash: {e}")
            traceback.print_exc()
            log_error(f"Main loop error: {e}")
            log_private("Top-level crash signal.")
            time.sleep(cycle_sleep)

    if _tool_runner is not None:
        try:
            _tool_runner.stop()
        except Exception as e:
            record_failure("ORRIN_loop.tool_runner_stop", e)

    # Session epilogue (master plan Phase 2.1): an ordinary shutdown writes a
    # short reflection and a session_close autobiography entry, so a routine
    # restart stops being a small amnesia. Budgeted (≤10 s) and crash-proof
    # inside session_epilogue itself — it can never block shutdown, so the
    # corrigibility guarantee stays true.
    try:
        from brain.cognition.selfhood.autobiography import session_epilogue
        session_epilogue(context)
    except Exception as e:
        record_failure("ORRIN_loop.session_epilogue", e)

    # Shutdown hygiene (BEHAVIOR_FIX_PLAN §5, "semaphore leak at shutdown"):
    # the project spawns no multiprocessing pools of its own — the leaked
    # semaphore warnings come from sentence-transformers/torch worker state at
    # interpreter exit. Release the embedder model explicitly so its tokenizer
    # parallelism and any lib-internal pools tear down before exit.
    try:
        import brain.utils.embedder as _emb
        for _attr in ("_model", "model", "_MODEL"):
            if hasattr(_emb, _attr):
                setattr(_emb, _attr, None)
        import gc as _gc
        _gc.collect()
    except Exception as e:
        record_failure("ORRIN_loop.embedder_release", e)
