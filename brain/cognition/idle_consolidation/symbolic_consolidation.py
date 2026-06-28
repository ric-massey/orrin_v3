# brain/cognition/idle_consolidation/symbolic_consolidation.py
#
# Late-phase symbolic-intelligence maintenance for the consolidation cycle
# (CODEBASE_CLEANUP_PLAN 4.5C), lifted verbatim from idle_consolidation_cycle() to bring that
# module under the 600-line soft limit. A sequence of independent, individually
# fail-safe phases run once per consolidation pass: knowledge crystallization, rule-set
# health audit, progress/outcome flush, rule abstraction/compression, concept
# formation, symbolic prediction, rule-verifier review, self-model rebuild,
# grounding audit, active experimentation, sandbox probes, forgetting, ceiling
# eviction, self-improvement, embodied observation, benchmark, temporal-plan
# review, and the evolution projection check. Coupled to the parent only through
# (context, dream_entry, this_count, dream_completed).
from __future__ import annotations

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure


def run_symbolic_maintenance(context, dream_entry, this_count, dream_completed):
    """Run the dream cycle's symbolic-maintenance phases (fail-safe, in order)."""
    _this_count = this_count
    _dream_completed = dream_completed
    # Knowledge crystallization — extract permanent rules from dream insights.
    # Runs after skill synthesis so synthesized code and dream text are both available.
    try:
        from brain.symbolic.crystallization import crystallize_idle_insights as _cdi
        _cryst_count = _cdi(dream_entry)
        if _cryst_count:
            log_activity(f"[dream] crystallized {_cryst_count} new symbolic rule(s) from dream insights")
    except Exception as _cre:
        log_activity(f"[dream] crystallization skipped: {_cre}")

    # Rule set health audit — prune stale/subsumed rules, log health ratio.
    # Runs every dream cycle (6h+ cadence) to keep the rule set lean.
    try:
        from brain.symbolic.crystallization import audit_rule_set as _ars
        _audit = _ars()
        log_activity(
            f"[dream] Rule set audit: total={_audit['total']} "
            f"subsumed={_audit['subsumed']} stale={_audit['stale_zero_hits']} "
            f"health={_audit['health_ratio']:.2f}"
        )
    except Exception as _are:
        log_activity(f"[dream] rule audit skipped: {_are}")

    # Symbolic progress flush — persist today's symbolic intelligence growth stats.
    try:
        from brain.symbolic.progress_tracker import flush as _pt_flush
        _snap = _pt_flush()
        log_activity(
            f"[dream] Symbolic progress: ratio={_snap.get('symbolic_ratio',0):.1%} "
            f"rules={_snap.get('rules_total',0)} "
            f"crystallized_today={_snap.get('crystallized_today',0)}"
        )
    except Exception as _pte:
        log_activity(f"[dream] progress flush skipped: {_pte}")

    # Closure/lifecycle outcome flush (Phase E) — persist today's goal closure
    # metrics alongside the symbolic progress report.
    try:
        from brain.cognition.planning.outcome_metrics import report as _om_report
        _omr = _om_report()
        log_activity(f"[dream] {_omr.get('summary', 'outcome metrics')}")
    except Exception as _ome:
        log_activity(f"[dream] outcome metrics flush skipped: {_ome}")

    # Rule hierarchy abstraction — merge similar rules into parent rules.
    # Enforces its own 4h cooldown; safe to call every dream cycle.
    try:
        from brain.symbolic.rule_abstraction import abstract_rules as _abr
        _abr_result = _abr()
        if not _abr_result.get("skipped"):
            log_activity(
                f"[dream] Rule abstraction: {_abr_result.get('clusters',0)} cluster(s) → "
                f"{_abr_result.get('parents_added',0)} parent(s)"
            )
    except Exception as _abre:
        log_activity(f"[dream] rule abstraction skipped: {_abre}")

    # Rule compression — identify specific rules with shared condition tokens and
    # synthesize abstract meta-rules covering them (prefrontal schema extraction).
    try:
        from brain.symbolic.rule_compressor import run_rule_compression as _rrc
        _comp = _rrc()
        if not _comp.get("skipped"):
            log_activity(
                f"[dream] Rule compression: {_comp.get('clusters',0)} cluster(s) → "
                f"{_comp.get('meta_rules_added',0)} meta rule(s), "
                f"{_comp.get('tombstoned',0)} tombstoned"
            )
    except Exception as _rce:
        log_activity(f"[dream] rule compression skipped: {_rce}")

    # Concept formation — every 2nd dream cycle. Clusters rules into named concepts.
    if _this_count % 2 == 0:
        try:
            from brain.symbolic.concept_formation import form_concepts as _fc
            _fc_result = _fc()
            if not _fc_result.get("skipped"):
                log_activity(
                    f"[dream] Concept formation: {_fc_result.get('concepts_formed',0)} new concept(s) "
                    f"(total={_fc_result.get('total_concepts',0)})"
                )
        except Exception as _fce:
            log_activity(f"[dream] concept formation skipped: {_fce}")

    # Symbolic prediction cycle — generate predictions from recent rule firings + chain.
    try:
        from brain.symbolic.prediction_engine import run_symbolic_prediction_cycle as _rspc
        _pred_result = _rspc(context)
        if _pred_result.get("new_predictions"):
            log_activity(
                f"[dream] Symbolic predictions: {_pred_result['new_predictions']} new "
                f"({_pred_result.get('chained',0)} chained)"
            )
    except Exception as _prde:
        log_activity(f"[dream] symbolic prediction cycle skipped: {_prde}")

    # Rule verifier review — surface pending rule revisions.
    try:
        from brain.symbolic.rule_verifier import get_pending_revisions as _gpr
        _revisions = _gpr()
        if _revisions:
            log_activity(f"[dream] {len(_revisions)} rule(s) pending revision review.")
            try:
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({
                    "content": (
                        f"[rule_verifier] {len(_revisions)} rule(s) have degraded confidence "
                        f"and need review. Most recent: "
                        f"{_revisions[-1].get('rule_conclusion','?')[:100]}"
                    ),
                    "event_type": "rule_revision",
                    "importance": 3,
                    "priority": 2,
                })
            except Exception as _e:
                record_failure("idle_consolidation_cycle.idle_consolidation_cycle.6", _e)
    except Exception as _rve:
        log_activity(f"[dream] rule verifier review skipped: {_rve}")

    # Symbolic self-model rebuild — reflects on own rule/concept quality symbolically.
    # Generates meta-rules for weak/strong domains and logs the health snapshot.
    try:
        from brain.symbolic.symbolic_self_model import build_symbolic_self_model as _bssm, generate_self_meta_rules as _gsmr
        _ssm = _bssm()
        _new_meta = _gsmr()
        log_activity(
            f"[dream] Symbolic self-model: "
            f"strong={_ssm.get('strong_areas')}, weak={_ssm.get('weak_areas')}, "
            f"causal_edges={_ssm.get('causal_edges_total',0)}, "
            f"new_meta_rules={len(_new_meta)}"
        )
    except Exception as _ssme:
        log_activity(f"[dream] symbolic self-model skipped: {_ssme}")

    # Grounding health audit — log how well-grounded the rule set is against real actions.
    try:
        from brain.symbolic.ground_truth import audit_grounding_health as _agh
        _gh = _agh()
        log_activity(
            f"[dream] Grounding audit: tracked={_gh['total_tracked']} "
            f"well_grounded={_gh['well_grounded']} poorly={_gh['poorly_grounded']} "
            f"mean={_gh['mean_grounding']:.2f}"
        )
    except Exception as _ghe:
        log_activity(f"[dream] grounding audit skipped: {_ghe}")

    # Active experimentation — advance one step of the hypothesis→test→consolidate pipeline.
    # One step per dream cycle keeps the loop from burning tokens all at once.
    try:
        from brain.cognition.experimentation import run_experiment_cycle as _rec
        _exp_result = _rec(context)
        if _exp_result.get("step"):
            log_activity(f"[dream] experiment step: {_exp_result['step']} → {_exp_result.get('status', '?')}")
    except Exception as _exe:
        log_activity(f"[dream] experiment cycle skipped: {_exe}")

    # Symbolic sandbox experiments — high-exploration_drive sub-goals probe the symbolic layer.
    try:
        from brain.symbolic.autonomous_experiment import run_experiment_cycle as _saec
        _saexp = _saec(context)
        if _saexp.get("experiments_run"):
            log_activity(
                f"[dream] Symbolic experiments: {_saexp['experiments_run']} run "
                f"(from {_saexp.get('goals_checked', 0)} goals)"
            )
    except Exception as _saee:
        log_activity(f"[dream] symbolic experiments skipped: {_saee}")

    # Rule/concept forgetting — idle decay, overfit pruning, concept retirement.
    try:
        from brain.symbolic.rule_forgetting import run_forgetting_cycle as _rfc
        _forget = _rfc(context)
        if _forget.get("total_changes"):
            log_activity(
                f"[dream] Forgetting: decayed={_forget['decayed']} "
                f"pruned={_forget['pruned']} retired={_forget['retired']}"
            )
        try:
            from brain.symbolic.progress_tracker import record_forgetting as _rf
            _rf(
                decayed=_forget.get("decayed", 0),
                pruned=_forget.get("pruned", 0),
                retired=_forget.get("retired", 0),
            )
        except Exception as _e:
            record_failure("idle_consolidation_cycle.idle_consolidation_cycle.7", _e)
    except Exception as _fge:
        log_activity(f"[dream] forgetting cycle skipped: {_fge}")

    # Disk-ceiling forgetting (§10.3) — if his mind has grown past the user's ceiling,
    # trim the safe growable stores back under budget. No-op when under the ceiling.
    try:
        from brain.utils.resource_ceilings import enforce_disk_ceiling as _edc
        _ceil = _edc()
        if _ceil.get("over"):
            log_activity(f"[dream] Over disk ceiling — trimmed {sum(_ceil.get('trimmed', {}).values())} entries to stay under.")
    except Exception as _ce:
        record_failure("idle_consolidation_cycle.idle_consolidation_cycle.disk_ceiling", _ce)

    # Memory-ceiling eviction (§10.3) — if resident memory is over the user's ceiling,
    # drop the safe-to-recompute in-process caches to give it back. No-op when under.
    try:
        from brain.utils.resource_ceilings import enforce_memory_ceiling as _emc
        _mem = _emc()
        if _mem.get("over"):
            log_activity(f"[dream] Over memory ceiling — evicted caches: {', '.join(_mem.get('evicted', [])) or 'none'}.")
    except Exception as _me:
        record_failure("idle_consolidation_cycle.idle_consolidation_cycle.memory_ceiling", _me)

    # Symbolic self-improvement — rehabilitate rules, calibrate router thresholds,
    # prune underused meta-rules. Has its own 4h internal cooldown.
    try:
        from brain.symbolic.self_improvement import run_self_improvement as _rsi
        _si = _rsi(context)
        if not _si.get("skipped") and _si.get("changes_made"):
            log_activity(
                f"[dream] Self-improvement: {_si['changes_made']} change(s) "
                f"(rehab={_si.get('rehabilitated',0)}, "
                f"calibrate={_si.get('calibrated',0)}, "
                f"meta={_si.get('meta_adjusted',0)})"
            )
        if _si.get("proposals"):
            log_activity(
                f"[dream] Self-improvement proposals: {len(_si['proposals'])} "
                f"(first: {_si['proposals'][0].get('reason','?')[:80]})"
            )
    except Exception as _sie:
        log_activity(f"[dream] self-improvement skipped: {_sie}")

    # Embodied observation — read real system state to ground symbolic rules.
    try:
        from brain.symbolic.host_actions import run_embodied_cycle as _rec_emb
        _emb = _rec_emb(context)
        if _emb.get("observations"):
            log_activity(
                f"[dream] Embodied: {_emb['observations']} observation(s) "
                f"({', '.join(_emb.get('actions_run', []))})"
            )
    except Exception as _embe:
        log_activity(f"[dream] embodied cycle skipped: {_embe}")

    # Benchmark — every 5th dream cycle. Fixed test suite for tracking performance.
    if _this_count % 5 == 0 and _dream_completed:
        try:
            from brain.symbolic.benchmark import run_benchmark as _rbm, get_benchmark_trend as _gbt
            _bm = _rbm()
            _trend = _gbt()
            log_activity(
                f"[dream] Benchmark: score={_bm['score']:.2f} "
                f"({_bm['passed']}/{_bm['total']}) trend={_trend.get('trend','?')}"
            )
            try:
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({
                    "content": (
                        f"[benchmark] Score={_bm['score']:.2f} "
                        f"({_bm['passed']}/{_bm['total']} tests passed). "
                        f"Domain scores: " +
                        ", ".join(f"{d}={v:.2f}" for d, v in _bm.get("domain_scores", {}).items())
                    ),
                    "event_type": "benchmark_result",
                    "importance": 3,
                    "priority": 2,
                })
            except Exception as _e:
                record_failure("idle_consolidation_cycle.idle_consolidation_cycle.8", _e)
        except Exception as _bme:
            log_activity(f"[dream] benchmark skipped: {_bme}")

    # Long-horizon plan review — surface active plans needing next-step attention.
    try:
        from brain.symbolic.temporal_planner import get_active_plans as _gap, get_plan_stats as _gps
        _active = _gap()
        if _active:
            _ps = _gps()
            log_activity(
                f"[dream] Temporal plans: {_ps['active']} active, "
                f"{_ps['completed']} completed, avg_steps={_ps['avg_steps']}"
            )
            # Surface the next step of the oldest active plan into WM
            oldest = _active[0]
            next_step = next(
                (s for s in oldest.get("steps", []) if s.get("status") == "pending"), None
            )
            if next_step:
                try:
                    from brain.cog_memory.working_memory import update_working_memory as _uwm
                    _uwm({
                        "content": (
                            f"[plan:{oldest['id'][:8]}] Next step: {next_step['conclusion'][:150]}"
                        ),
                        "event_type": "plan_step",
                        "importance": 3,
                        "priority": 3,
                    })
                except Exception as _e:
                    record_failure("idle_consolidation_cycle.idle_consolidation_cycle.9", _e)
    except Exception as _tpe:
        log_activity(f"[dream] temporal plan review skipped: {_tpe}")

    # Evolution projection check — every 3rd COMPLETED dream run. Gate on _dream_completed
    # so a crash mid-run doesn't consume the slot without doing the work.
    if _this_count % 3 == 0 and _dream_completed:
        try:
            from brain.cognition.planning.evolution import check_projection_against_reality as _cpgr
            _cpgr(context)
        except Exception as _ece:
            log_activity(f"[dream] evolution projection check skipped: {_ece}")
