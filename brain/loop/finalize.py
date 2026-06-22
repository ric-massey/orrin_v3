"""Cognitive-loop post-cycle finalization (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`finalize_cycle()` runs the after-action stages once a cycle's decision has been
executed: the health-streak monitor, Layer-0 post-cycle plasticity + drive
satisfaction, affect convergence (integrate this cycle's affect proposals), and
long-memory consolidation. It reads the cycle's result/reward/affect_state and
mutates context in place. Fail-safe — the pulse tick, the ORRIN_ONCE exit, the
per-cycle GC/finetune cadence, and the cadence sleep stay in the loop.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Dict
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.json_utils import save_json
from brain.utils.log import log_model_issue
from brain.utils.failure_counter import record_failure
from brain.loop.constants import _OUTWARD_FNS
from brain.paths import (
    CONTEXT, WORKING_MEMORY_FILE,
)


_log = get_logger(__name__)
Context = Dict[str, Any]


def finalize_cycle(context, result, reward, affect_state, _cycle_num) -> Context:
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

    return context
