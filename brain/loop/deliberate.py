"""Cognitive-loop deliberation-prep stages (Phase 4A, extracted from the
ORRIN_loop entrypoint).

These run after interoception and before think(): the Executive procedural lane's
read-only dry-run + the Metacognitive Monitor offering candidates to the Global
Workspace, with one pre-think `update_workspace` so a breakthrough that won
consciousness can bias the deliberate pick (§7.1 ordering: Executive → Monitor →
Workspace → think). They bias, never preempt; all fail-safe.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Dict
from brain.utils.failure_counter import record_failure

from brain.loop.telemetry import _bridge

_log = get_logger(__name__)
Context = Dict[str, Any]


def prepare_workspace(context) -> Context:
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

    return context
