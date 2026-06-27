"""Cognitive-loop recall + integration stage (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`integrate_recall_and_baseline()` runs right after perception, before cognition:
it queries the v2 MemoryDaemon for relevant memories (and mirrors them to the UI
inspector), injects any memory-pattern / formative-tension / consolidation /
integration-lag / stagnation signals into the cycle, refreshes the self-model
periodically, publishes the context for `build_system_prompt`, and snapshots the
emotional baseline used for this cycle's spike detection + agency-based causal
learning. It mutates the cycle context in place and returns it.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Dict
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.failure_counter import record_failure

from brain.loop.telemetry import _ui_memory

_log = get_logger(__name__)
Context = Dict[str, Any]


def integrate_recall_and_baseline(context: Context, _mem_daemon: Any) -> Context:
    # Query v2 MemoryDaemon for semantically relevant memories.
    # When comprehension parsed an input concept this cycle, use it as the
    # query so retrieved memories are relevant to what was just said, not
    # just to whatever goal/thought was already active.
    if _mem_daemon:
        import brain.memory_io as memory_io
        try:
            _input_concept = (context.get("_last_comprehension") or {}).get("concept") or ""
            _mem_query = _input_concept.strip() or None
            injected = memory_io.inject_into_context(_mem_daemon, context, query_text=_mem_query, k=6)
            if not injected:
                context.setdefault("retrieved_memories", [])
            _ui_memory("read", context.get("retrieved_memories"), store="long")
        except Exception:
            context.setdefault("retrieved_memories", [])
    else:
        context.setdefault("retrieved_memories", [])

    # Memory pattern: when retrieved memories share a theme, inject a
    # pattern insight into working_memory so inner_loop reasoning picks it up.
    try:
        _memories = context.get("retrieved_memories") or []
        if len(_memories) >= 2:
            from collections import Counter as _Counter
            _types = _Counter(
                (m.get("event_type") or (m.get("meta") or {}).get("event_type") or "")
                for m in _memories
                if isinstance(m, dict)
            )
            _dom_type, _dom_count = (_types.most_common(1)[0] if _types else ("", 0))
            if _dom_count >= 2 and _dom_type:
                _pattern = (
                    f"[Memory pattern] {_dom_count} recent memories involve '{_dom_type}'. "
                    "Consider whether this pattern should shape the current approach."
                )
                context["memory_pattern"] = {"type": _dom_type, "count": _dom_count}
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm(_pattern)
    except Exception as _mpe:
        record_failure("ORRIN_loop.memory_pattern", _mpe)

    # Formative tensions: inject active tensions into context and working memory.
    try:
        from brain.cognition.self_state.tensions import inject_tension_signals as _its2
        _its2(context)
    except Exception as _tse:
        record_failure("ORRIN_loop.inject_tension_signals", _tse)
    context.setdefault("active_tensions", [])

    # Periodic tension detection: scan for NEW tensions outside dream cycle.
    # Dream-only detection means tensions could go unnoticed for hours between sleeps.
    try:
        _tc_tens = get_cycle_count()
        if _tc_tens > 0 and _tc_tens % 30 == 0:
            from brain.cognition.self_state.tensions import detect_tensions as _dt2
            _dt2(context)
    except Exception as _dte:
        record_failure("ORRIN_loop.detect_tensions_periodic", _dte)

    # Emotional consolidation drain: apply one tick of gradual emotional
    # residue from significant past events.
    try:
        from brain.control_signals.consolidation import drain_consolidations as _drain_consol
        _drain_consol(context)
    except Exception as _consol_e:
        record_failure("ORRIN_loop.drain_consolidations", _consol_e)

    # Integration lag drain: apply deferred emotional deltas when their
    # cycles-left counter reaches 0 (the "it hits you later" effect).
    try:
        from brain.control_signals.integration_lag import process_integration_queue as _piq
        _piq(context)
    except Exception as _iq_e:
        record_failure("ORRIN_loop.process_integration_queue", _iq_e)

    # stagnation_signal escalation: track consecutive bored cycles and inject
    # escalating pressure/penalty_signal signals when stagnation_signal compounds.
    try:
        from brain.control_signals.stagnation_signal_escalation import update_stagnation_signal_escalation as _ube
        _ube(context)
    except Exception as _be_e:
        record_failure("ORRIN_loop.stagnation_signal_escalation", _be_e)

    # Refresh self_model from disk every 10 cycles so value/belief changes
    # made by cognition functions (value_evolution, etc.) propagate to the
    # system prompt without requiring a restart.
    _cycle_n_sm = get_cycle_count()
    if _cycle_n_sm % 10 == 0:
        try:
            from brain.utils.self_model import get_self_model as _gsm
            context["self_model"] = _gsm()
        except Exception as e:
            record_failure("ORRIN_loop.refresh_self_model", e)

    # Make the current context available to build_system_prompt() via the
    # process-local store, without threading context through every call chain.
    try:
        from brain.utils.runtime_ctx import set_cycle_context as _scc
        _scc(context)
    except Exception as e:
        record_failure("ORRIN_loop.set_cycle_context", e)

    # ── Snapshot emotional baseline for spike detection ────────────────
    try:
        _emo_now  = context.get("affect_state") or {}
        _emo_core = _emo_now.get("core_signals") or _emo_now
        context["_emo_pre_cycle"] = {
            k: float(v) for k, v in _emo_core.items()
            if isinstance(v, (int, float))
        }
        # Agency-based causal learning — attribute the felt change. Last
        # cycle's action stashed (fn, pre-affect); its consequences have now
        # drained into this cycle's start-affect. Record the dominant signal
        # that moved as a do(action)→effect edge (Pearl Level 2). Only the
        # single dominant, clearly-above-drift change → salient links, not
        # noise; the causal graph's evidence/confound machinery refines it.
        _iv = context.pop("_iv_pending", None)
        if isinstance(_iv, dict) and _iv.get("fn") and isinstance(_iv.get("core"), dict):
            _prev = _iv["core"]
            _sig, _dd = None, 0.0
            for _k, _pv in _prev.items():
                _nv = context["_emo_pre_cycle"].get(_k)
                if isinstance(_nv, (int, float)) and abs(_nv - _pv) > abs(_dd):
                    _dd, _sig = (_nv - _pv), _k
            if _sig is not None and abs(_dd) >= 0.04:
                from brain.symbolic.causal_graph import (
                    record_intervention as _rec_iv,
                    is_established as _is_est,
                )
                _effect = f"{_sig} {'rises' if _dd > 0 else 'falls'}"
                # Don't keep re-intervening on established ground truth —
                # it burns cycles and adds noise to the world model.
                if not _is_est(_iv["fn"], _effect):
                    _rec_iv(_iv["fn"], _effect)
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.8", _e)

    return context


def _h1_maybe_recruit(alert: Dict[str, Any], ignored_n: int, context: Context) -> None:
    """Phase 2 bridge: once an alert's neglect counter crosses the recruit
    threshold, escalate the chronic deficit into a survival-tier restoration goal
    (deduped against re-recruitment). Best-effort — never let it break the health
    read."""
    try:
        from brain.cognition.planning.survival_goals import (
            recruit_survival_goal, RECRUIT_AFTER_CYCLES,
        )
        if ignored_n >= RECRUIT_AFTER_CYCLES:
            recruit_survival_goal(alert, context)
    except Exception as _e:
        record_failure("ORRIN_loop.tier1_recruit", _e)


def tier1_health_check(context: Context) -> Context:
    """Tier-1 interoception: read the setpoint_regulation daemon's latest
    snapshot and fold it into the cycle — warnings/criticals become escalating
    raw_signals the selector weighs, repeated-neglect criticals add direct
    emotional cost, and the suggested-fn / _tier1_critical flags drive the
    post-think override. Reads the daemon's output only (it runs on its own
    thread); mutates the cycle context in place and returns it.
    """
    # ── Tier 1: setpoint_regulation health check ──────────────────────────────
    # Read the daemon's latest snapshot. Warnings become raw_signals that
    # the signal_router weighs in function selection. Critical alerts set a flag
    # the post-think override block can act on. The daemon itself runs
    # unconditionally on its own thread — this is just reading its output.
    #
    # Compounding stakes: critical alerts that are repeatedly ignored escalate
    # in signal strength and apply direct emotional cost.
    # McEwen (1998) allostatic load theory: repeated or unresolved homeostatic
    # stress produces cumulative physiological cost that escalates nonlinearly —
    # the body keeps score regardless of whether conscious attention is paid.
    # Selye (1956) general adaptation syndrome: the alarm → resistance →
    # exhaustion progression means that ignoring alarm signals does not cancel
    # them; it accelerates progression toward the exhaustion phase.
    # Baumeister et al. (1994) ego depletion: unresolved demands consume
    # regulatory resources each cycle, compounding the load on subsequent regulation.
    try:
        from brain.runtime_coupling.setpoint_regulation import get_state as _h1_get
        _h1 = _h1_get()
        context["health_score"] = _h1.get("health_score", 1.0)
        # Reset the preempt key each cycle BEFORE scanning alerts: context persists
        # across cycles, so a critical that clears must un-set this or the preempt
        # would latch on forever. The loop re-sets it True if a critical is present.
        context["_setpoint_critical"] = False
        context.pop("_setpoint_critical_reason", None)
        _h1_critical_fn = None
        _h1_ignored = context.setdefault("_h1_ignored_cycles", {})
        _h1_active_ids: set[str] = set()

        for _h1_alert in _h1.get("alerts", []):
            _aid  = _h1_alert.get("id", "")
            _sev  = _h1_alert.get("severity")
            _desc = _h1_alert.get("description", "")
            _tags = _h1_alert.get("tags", [])
            _sfn  = _h1_alert.get("suggested_fn")
            _h1_active_ids.add(_aid)

            if _sev == "critical":
                # Accumulate neglect counter
                _h1_ignored[_aid] = _h1_ignored.get(_aid, 0) + 1
                _ignored_n = _h1_ignored[_aid]
                # Signal strength escalates with each ignored cycle (cap 0.99)
                _escalated_str = min(0.99, 0.80 + _ignored_n * 0.04)
                from brain.utils.signal_utils import create_signal as _cs
                context.setdefault("raw_signals", []).append(
                    _cs(source="setpoint_regulation", content=_desc,
                        signal_strength=_escalated_str, tags=_tags)
                )
                context["_tier1_critical"] = True
                # Reconcile the key the goal-system preempt consumer reads
                # (goal_closure._survival_critical). Producer and consumer used to
                # pass in the night: tier1 wrote _tier1_critical, the preempt read
                # _setpoint_critical (never set). Set it here, with the alert id/desc
                # stashed so the preempt can name *why* it yielded.
                context["_setpoint_critical"] = True
                if not context.get("_setpoint_critical_reason"):
                    context["_setpoint_critical_reason"] = _aid or _desc
                if _sfn and not _h1_critical_fn:
                    _h1_critical_fn = _sfn
                # Direct emotional cost after 3+ ignored cycles
                if _ignored_n >= 3:
                    try:
                        _h1_emo  = context.get("affect_state") or {}
                        _h1_core = _h1_emo.get("core_signals") or _h1_emo
                        _cost = min(0.06, 0.02 * min(_ignored_n, 10))
                        _h1_core["risk_estimate"]     = min(1.0, float(_h1_core.get("risk_estimate")     or 0) + _cost)
                        _h1_core["impasse_signal"] = min(1.0, float(_h1_core.get("impasse_signal") or 0) + _cost * 0.5)
                        if "core_signals" in _h1_emo:
                            _h1_emo["core_signals"] = _h1_core
                        context["affect_state"] = _h1_emo
                    except Exception as _e:
                        record_failure("ORRIN_loop.run_cognitive_loop.9", _e)
                # Phase 2 — chronic-deficit recruiter: a critical that stays ignored
                # past the recruit threshold escalates from a signal nudge into a
                # committed restoration intention (the autonomic→cortical bridge).
                _h1_maybe_recruit(_h1_alert, _ignored_n, context)
            elif _sev == "warning":
                # Warnings now carry their own neglect counter too — the chronic case
                # is precisely a sub-acute deficit that keeps recurring unaddressed.
                _h1_ignored[_aid] = _h1_ignored.get(_aid, 0) + 1
                _ignored_n = _h1_ignored[_aid]
                from brain.utils.signal_utils import create_signal as _cs
                context.setdefault("raw_signals", []).append(
                    _cs(source="setpoint_regulation", content=_desc,
                        signal_strength=0.65, tags=_tags)
                )
                _h1_maybe_recruit(_h1_alert, _ignored_n, context)

        # Clear neglect counters for alerts that have resolved
        for _stale_id in list(_h1_ignored.keys()):
            if _stale_id not in _h1_active_ids:
                del _h1_ignored[_stale_id]

        context["_tier1_suggested_fn"] = _h1_critical_fn
        if _h1_critical_fn is None:
            # All critical alerts cleared — reset override pacing state
            context.pop("_t1_override_hist", None)
    except Exception as _h1e:
        record_failure("ORRIN_loop.setpoint_regulation_read", _h1e)

    return context
