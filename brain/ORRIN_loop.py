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

from brain.think.loop_helpers import (
    names,
    discover_callable_maps,
)

from brain.registry.behavior_registry import BEHAVIORAL_FUNCTIONS



from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.log import log_error, log_private, log_activity

from brain.utils.error_router import route_exception
from brain.cognition.repair.auto_repair import try_auto_repair
from brain.utils.failure_counter import record_failure, dump_summary as _dump_failure_summary
from brain.utils.token_meter import dump_summary as _dump_token_summary



# ── Face & Brain UI telemetry ──────────────────────────────────
# Fail-safe UI/telemetry emission for the loop's lifecycle, extracted to
# brain/loop/telemetry.py (Phase 4A). The bridge buffers on a daemon thread and
# never raises, so cognition never blocks or crashes on telemetry.
from brain.loop.telemetry import (
    _push_event,
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
from brain.loop.finalize import finalize_cycle, persist_and_periodic
# Action-accounting stage, Phase 4A.
from brain.loop.account import account_action
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

            context = account_action(context, result, acted_this_cycle, BEH_NAMES)

            context = persist_and_periodic(context, _goals_api, _mem_daemon, _evaluator, affect_state)
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
