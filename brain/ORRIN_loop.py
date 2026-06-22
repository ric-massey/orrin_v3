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
    names,
    discover_callable_maps,
    bandit_learn,
)

from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS

from brain.affect.affect_drift import check_affect_drift

from brain.cognition.planning.reflection import record_decision

from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import load_json
from brain.utils.log import log_error, log_private, log_activity, log_model_issue

from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure, dump_summary as _dump_failure_summary
from brain.utils.token_meter import dump_summary as _dump_token_summary


from brain.paths import (
    WORKING_MEMORY_FILE,
)

# ── Face & Brain UI telemetry ──────────────────────────────────
# Fail-safe UI/telemetry emission for the loop's lifecycle, extracted to
# brain/loop/telemetry.py (Phase 4A). The bridge buffers on a daemon thread and
# never raises, so cognition never blocks or crashes on telemetry.
from brain.loop.telemetry import (
    _bridge, _push_event,
)





Context = Dict[str, Any]


# Cognitive-function dispatch, extracted to brain/loop/invoke.py (Phase 4A).

# Boot / context construction, extracted to brain/loop/boot.py (Phase 4A).
from brain.loop.boot import _boot_context, _verify_production_capability  # noqa: F401

# Sense / state-refresh stage, extracted to brain/loop/sense.py (Phase 4A).
from brain.loop.sense import sense_and_refresh, _apply_transient_signal_decay  # noqa: F401
# Recall + integration stage, extracted to brain/loop/reflect.py (Phase 4A).
from brain.loop.reflect import integrate_recall_and_baseline, tier1_health_check
# Deliberation-prep stages (executive lane, metacog→workspace), Phase 4A.
from brain.loop.deliberate import prepare_workspace, ignite
# Action/cognition execution stages (Path A/B), Phase 4A.
from brain.loop.execute import execute_behavior_action, execute_cognition_function, execute_fallback
# Deterministic maintenance tier, Phase 4A.
from brain.loop.maintenance import run_maintenance_tier
# Post-cycle finalization stage, Phase 4A.
from brain.loop.finalize import finalize_cycle
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

            context = tier1_health_check(context)

            context = prepare_workspace(context)

            context = ignite(context)
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
                context, reward, acted_this_cycle = execute_behavior_action(context, result, _decision_id, _evaluator, BEH_NAMES)

            # Path B: cognition function
            elif isinstance(result, dict) and "next_function" in result:
                context, reward, acted_this_cycle = execute_cognition_function(context, result, _decision_id, _evaluator, _mem_daemon, affect_state)
            elif result is not None:
                context, reward, acted_this_cycle = execute_fallback(context, _evaluator, COG_MAP)
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
                                    # Learn from the watchdog action; the returned feats
                                    # are not consumed here (record_decision below omits
                                    # them), so don't bind them.
                                    bandit_learn(mv_type, context, _wd_reward, decision_id=_wd_decision_id)
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

            context = run_maintenance_tier(context)
            context = finalize_cycle(context, result, reward, affect_state, _cycle_num)

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
