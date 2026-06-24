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
from brain.utils.json_utils import save_json, load_json
from brain.utils.log import log_model_issue, log_activity, log_error
from brain.utils.failure_counter import record_failure
from brain.loop.constants import _OUTWARD_FNS
from brain.loop.telemetry import _bridge
from brain.paths import (
    CONTEXT, WORKING_MEMORY_FILE,
)


_log = get_logger(__name__)
Context = Dict[str, Any]


def finalize_cycle(context: Context, result: Any, reward: Any, affect_state: Any, _cycle_num: Any) -> Context:
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
            except (TypeError, ValueError):  # intentional: unserializable context key → skip sizing
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


def persist_and_periodic(context: Context, _goals_api: Any, _mem_daemon: Any, _evaluator: Any, affect_state: Any) -> Context:
    """Per-cycle persistence + periodic background work, run after the action is
    accounted and before the maintenance tier: sync proposed goals + record goal
    progress, flush working memory to the v2 daemon (with periodic v1<->v2
    backfill), tick the evaluator, generate/check predictions, fire the dream
    cycle when idle, and converge the global workspace into one conscious moment.
    Mutates context in place; fail-safe.
    """
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
            _recent_wm_p: list[Any] = load_json(WORKING_MEMORY_FILE, default_type=list) or []
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


    return context
