"""Cognitive-loop background-service startup (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`start_background_services()` brings up the daemons the loop depends on but does
not drive: the ToolRunner (drains queued tool requests), the EvaluatorDaemon
(delayed reward resolution), the always-on Layer-0 embodiment threads
(setpoint_regulation, sensory_stream, drive_engine, social_presence,
subconscious), and the optional continuous Executive daemon. The embodiment /
Executive starts keep no handle (they own their own threads); the loop needs the
ToolRunner + Evaluator handles back for its per-cycle health-watchdog + ticks, so
those are returned. Each start is fail-safe.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from brain.core.runtime_log import get_logger
from brain.utils.log import log_error, log_activity
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)


def start_background_services(stop_event: Any) -> Tuple[Any, Any, Any]:
    # Start background tool runner (drains queued tool requests every 30s)
    _tool_runner = None
    _ToolRunner_cls: Any = None
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

    return _tool_runner, _ToolRunner_cls, _evaluator


def shutdown_loop(context: Dict[str, Any], _tool_runner: Any) -> None:
    """Loop teardown after the while-loop exits: stop the ToolRunner, write the
    session epilogue (a short reflection + session_close autobiography entry, so a
    routine restart isn't a small amnesia — budgeted and crash-proof so it can
    never block shutdown), and release the embedder model to avoid the
    sentence-transformers/torch semaphore leak at interpreter exit. Fail-safe.
    """
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
        from brain.cognition.self_state.autobiography import session_epilogue
        session_epilogue(context)
    except Exception as e:
        record_failure("ORRIN_loop.session_epilogue", e)

    # (T0.4) Emit a final reflection on a GRACEFUL OPERATOR STOP, not only on
    # modeled death. The run that drove this plan ended on an operator stop with
    # final_thoughts.json untouched, so the next boot had no handoff to read.
    # final_reflection writes the handoff WITHOUT setting the death flag, so this
    # is continuity ("read the unfinished list first"), not a death.
    try:
        from brain.cognition.terminal import final_reflection
        final_reflection(context, reason="operator_stop")
    except Exception as e:
        record_failure("ORRIN_loop.operator_stop_final_reflection", e)

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
