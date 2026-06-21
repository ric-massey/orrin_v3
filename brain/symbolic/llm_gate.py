# brain/symbolic/llm_gate.py
# Gated LLM interface — the ONLY entry point for LLM calls in the symbolic
# architecture.  Every call goes through the reasoning router first.
#
# Pipeline:
#   1. reasoning_router.route() — check rules (+ meta-rules), analogy, symbolic BFS
#   2. Symbolic hit → return immediately, record in progress_tracker
#   3. LLM needed → concurrency check → generate_response() call
#   4. Successful LLM response → crystallize() → record in progress_tracker
#
# Progress tracking:
#   Every call records into progress_tracker (symbolic hits, LLM calls,
#   conflicts, exploration_drive scores, rule depth).  gate_report() returns a
#   7-day growth chart.
#
# Meta-rule feedback:
#   When a high-quality LLM response follows a conflict detection, we reward
#   the mr_flag_contradiction meta-rule (it correctly deferred).
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
import time
from typing import Dict, Optional

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.llm_gate import llm_callable_by
_log = get_logger(__name__)

_gate_lock = threading.Lock()
_session_llm_calls: int = 0
_session_symbolic_hits: int = 0


def gated_generate(
    prompt: str,
    *,
    caller: str = "unknown",
    context: Optional[Dict] = None,
    allow_symbolic: bool = True,
    outcome: float = 0.6,
) -> str:
    """
    Main entry point.  Returns answer string (symbolic or LLM).
    `outcome` is the estimated quality — used for crystallization threshold.
    """
    global _session_llm_calls, _session_symbolic_hits
    ctx = context or {}
    _conflict = False
    _meta_rule_id = ""
    _exploration_drive = 0.0

    # ── Symbolic routing ───────────────────────────────────────────────────
    if allow_symbolic:
        try:
            from brain.symbolic.reasoning_router import route
            routing = route(prompt, context=ctx)
            _conflict = routing.get("conflict", False)
            _meta_rule_id = routing.get("meta_rule_id", "")
            _drive = routing.get("drive") or {}
            _exploration_drive = _drive.get("score", 0.0)

            if routing.get("resolved"):
                answer = routing.get("answer", "")
                source = routing.get("source", "symbolic")

                if answer and source not in ("suppressed",):
                    with _gate_lock:
                        _session_symbolic_hits += 1
                    _rid = routing.get("rule_id", "")
                    _rule_depth = len(_get_rule_conditions(_rid)) if _rid else 0
                    _track_symbolic_hit(exploration_drive=_exploration_drive, rule_depth=_rule_depth)
                    if _meta_rule_id:
                        _track_meta_rule()
                    log_activity(
                        f"[llm_gate] Symbolic hit ({source}, meta={_meta_rule_id or 'none'}) "
                        f"— no LLM call for '{caller}'"
                    )
                    return answer

                elif source == "suppressed":
                    _track_symbolic_hit(exploration_drive=_exploration_drive)
                    log_activity(f"[llm_gate] Suppressed (low exploration_drive) for '{caller}'")
                    return ""

                # conflict → fall through to LLM, but note it
                if _conflict:
                    _track_conflict()
                    log_activity(f"[llm_gate] Conflict detected — LLM needed for '{caller}'")

        except Exception as e:
            log_activity(f"[llm_gate] router error: {e}")

    # ── Concurrency check ─────────────────────────────────────────────────
    try:
        from brain.utils.token_meter import active_call_count
        if active_call_count() >= 4:
            log_activity(f"[llm_gate] Concurrency limit — queuing '{caller}'")
            _wait_for_slot(max_wait=10.0)
    except Exception as _e:
        record_failure("llm_gate.gated_generate", _e)

    # Tool-only deployment: if this caller can't reach the API, don't fire a
    # blocked round-trip — the symbolic router above already had its chance.
    if not llm_callable_by(caller):
        return ""

    # ── LLM call ──────────────────────────────────────────────────────────
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        response = llm_ok(generate_response(prompt, caller=caller), caller) or ""
    except Exception as e:
        log_activity(f"[llm_gate] LLM error for '{caller}': {e}")
        return ""

    with _gate_lock:
        _session_llm_calls += 1

    _track_llm_call(exploration_drive=_exploration_drive)

    if response:
        log_activity(
            f"[llm_gate] LLM call #{_session_llm_calls} for '{caller}' "
            f"({len(response)} chars, conflict={_conflict})"
        )
        # If conflict was detected and LLM resolved it, reward the meta-rule
        if _conflict and _meta_rule_id:
            try:
                from brain.symbolic.meta_rules import reward_meta_rule
                reward_meta_rule(_meta_rule_id, delta=0.10)
            except Exception as _e:
                record_failure("llm_gate.gated_generate.2", _e)
        _maybe_crystallize(prompt, response, outcome, caller)

    return response


# ─── Tracking helpers ─────────────────────────────────────────────────────────

def _get_rule_conditions(rule_id: str) -> list:
    try:
        from brain.symbolic.rule_engine import get_all_rules
        for r in get_all_rules():
            if r.get("id") == rule_id:
                return r.get("conditions") or []
    except Exception as _e:
        record_failure("llm_gate._get_rule_conditions", _e)
    return []


def _track_symbolic_hit(*, exploration_drive: float = 0.0, rule_depth: int = 0) -> None:
    try:
        from brain.symbolic.progress_tracker import record_symbolic_hit
        record_symbolic_hit(rule_depth=rule_depth, exploration_drive=exploration_drive)
    except Exception as _e:
        record_failure("llm_gate._track_symbolic_hit", _e)


def _track_llm_call(*, exploration_drive: float = 0.0) -> None:
    try:
        from brain.symbolic.progress_tracker import record_llm_call
        record_llm_call(exploration_drive=exploration_drive)
    except Exception as _e:
        record_failure("llm_gate._track_llm_call", _e)


def _track_conflict() -> None:
    try:
        from brain.symbolic.progress_tracker import record_conflict
        record_conflict()
    except Exception as _e:
        record_failure("llm_gate._track_conflict", _e)


def _track_meta_rule() -> None:
    try:
        from brain.symbolic.progress_tracker import record_meta_rule_application
        record_meta_rule_application()
    except Exception as _e:
        record_failure("llm_gate._track_meta_rule", _e)


def _maybe_crystallize(prompt: str, response: str, outcome: float, caller: str) -> None:
    try:
        from brain.symbolic.crystallization import crystallize
        crystallize(prompt, response, outcome=outcome, caller=caller)
    except Exception as e:
        log_activity(f"[llm_gate] crystallize error: {e}")


def _wait_for_slot(max_wait: float = 10.0) -> None:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            from brain.utils.token_meter import active_call_count
            if active_call_count() < 4:
                return
        except Exception:
            return
        time.sleep(0.5)


# ─── Stats / reporting ────────────────────────────────────────────────────────

def gate_stats() -> Dict:
    """Session stats: symbolic vs LLM breakdown."""
    total = _session_llm_calls + _session_symbolic_hits
    if total == 0:
        return {"llm": 0, "symbolic": 0, "total": 0, "symbolic_ratio": 0.0}
    return {
        "llm": _session_llm_calls,
        "symbolic": _session_symbolic_hits,
        "total": total,
        "symbolic_ratio": round(_session_symbolic_hits / total, 3),
    }


def gate_report(days: int = 7) -> Dict:
    """
    Full intelligence growth report for the last N days.
    Flushes current session into progress_tracker first.
    """
    try:
        from brain.symbolic.progress_tracker import report, flush
        flush()
        return report(days=days)
    except Exception as e:
        log_activity(f"[llm_gate] progress report failed: {e}")
        return {"summary": f"Report unavailable: {e}", "days": []}
