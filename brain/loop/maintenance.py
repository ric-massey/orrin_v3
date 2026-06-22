"""Cognitive-loop deterministic maintenance tier (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`run_maintenance_tier()` runs the cadence-driven closure/upkeep that was
selection-starved when left to the bandit (cold-start trap): goal retirement,
satiety closure, stale-plan pruning, and the other periodic housekeeping that
must happen regardless of what the cycle chose. Decoupled from selection (no
double execution — the same precedent as the per-cycle update_affect_state
upkeep), keyed off the cycle count. Pure `context -> context`; fail-safe.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
from typing import Any, Dict
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.log import log_activity, log_private
from brain.utils.failure_counter import record_failure, dump_summary as _dump_failure_summary
from brain.utils.token_meter import dump_summary as _dump_token_summary

_log = get_logger(__name__)
Context = Dict[str, Any]


def run_maintenance_tier(context) -> Context:
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


    return context


def periodic_housekeeping(context) -> Context:
    """End-of-cycle cadence housekeeping, keyed off the cognitive cycle count:
    the per-cycle 'cycle complete' status print, a forced GC every 50 cycles
    (release torch/heap back to the OS), failure/token summaries + self-extension
    integrate-or-atrophy + failure-ledger review every 100, and the fine-tuning
    job check every 500. Mutates context in place; fail-safe.
    """
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


    return context
