# brain/cognition/dreaming/dream_cycle.py
# Runs when idle — consolidates recent experience, recombines with old emotional
# memories, processes unresolved content, and surfaces value-revision candidates.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.utils.self_model import get_self_model
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import LONG_MEMORY_FILE, WORKING_MEMORY_FILE, DREAM_LOG, VALUE_REVISIONS
from brain.utils.llm_gate import llm_available
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


_LAST_DREAM_TS: float = 0.0
_DREAM_MIN_INTERVAL_S: float = 6 * 3600   # 6 hours minimum between dream cycles
_IDLE_THRESHOLD_S: float = 300            # 5 minutes of no user input = idle
_DREAM_COUNT: int = 0                     # incremented each run; used for projection check cadence
_IS_DREAMING: bool = False                # re-entry guard: prevents two concurrent dream cycles
_DREAM_LOCK: threading.Lock = threading.Lock()  # guards all _DREAM_* globals

# ── Sleep-phase flag (SL1) ──────────────────────────────────────────────────
# A process-local "Orrin is asleep" gate, same module-gate pattern as the host
# guard's heavy_cycles_paused / vital_floor_shedding. The felt body (body_sense)
# and the other resource_deficit writers read this to attribute the dream's own
# RSS/CPU/latency spike to a *sleep* phase rather than to distress (§3.2 SL1).
#
# The dream runs on a daemon thread while the main cognitive loop keeps cycling,
# so the loop needs to know "we're asleep right now" without a handle on the
# dream. Staleness-guarded: if a dream thread dies mid-run and never clears the
# flag, dreaming_now() auto-expires it after _DREAM_PHASE_MAX_S so a crashed
# dream can never permanently mask the felt body (which would hide real distress).
_DREAM_PHASE: bool = False
_DREAM_PHASE_TS: float = 0.0
_DREAM_PHASE_MAX_S: float = 1800.0   # a dream this long is treated as stale, not asleep


def set_dreaming(active: bool) -> None:
    """Mark the sleep phase on/off. Called around the dream cycle; also usable by
    tests to simulate sleep. Thread-safe."""
    global _DREAM_PHASE, _DREAM_PHASE_TS
    with _DREAM_LOCK:
        _DREAM_PHASE = bool(active)
        _DREAM_PHASE_TS = time.time() if active else 0.0


def dreaming_now() -> bool:
    """True while a dream cycle is in flight (the felt body should read vitals as
    normal-for-sleeping, not as distress). Auto-expires a stale flag so a crashed
    dream can't permanently mask the felt body."""
    with _DREAM_LOCK:
        if not _DREAM_PHASE:
            return False
        if (time.time() - _DREAM_PHASE_TS) > _DREAM_PHASE_MAX_S:
            return False
        return True


def should_dream(context: Dict[str, Any]) -> bool:
    """True when Orrin has been idle long enough and enough time has passed since last dream.

    Wonder affinity (set by wonder.py when wonder > 0.55) can shorten the minimum
    interval by up to 50% so high-wonder states trigger dream processing sooner.
    """
    now = time.time()
    affinity = float(context.get("_dream_affinity", 0.0) or 0.0)
    min_interval = _DREAM_MIN_INTERVAL_S * max(0.5, 1.0 - affinity)
    with _DREAM_LOCK:
        elapsed = now - _LAST_DREAM_TS
    if elapsed < min_interval:
        return False
    last_user = float(context.get("last_user_timestamp") or context.get("last_user_input_ts") or 0)
    idle_s = now - last_user
    return idle_s >= _IDLE_THRESHOLD_S


def dream_cycle(context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Full dream cycle: consolidate, recombine, process.
    Returns a summary dict; side effects write to DREAM_LOG and long_memory.
    """
    # Dreaming does NOT require the LLM. Human sleep-dependent consolidation is
    # entirely internal — hippocampal replay, schema abstraction, synaptic
    # downscaling, emotional reprocessing — with no external oracle. Nearly every
    # sub-cycle below is already symbolic (episode replay, rule synthesis,
    # semantic extraction, concept formation, forgetting). Only the optional prose
    # narration uses the LLM, and it has a symbolic primary plus a graceful no-op
    # fallback. So we run the full cycle regardless; the LLM, when present, only
    # enriches it. (Diekelmann & Born 2010; Tononi & Cirelli 2014, SHY.)
    llm_up = llm_available()
    global _LAST_DREAM_TS, _DREAM_COUNT, _IS_DREAMING
    with _DREAM_LOCK:
        if _IS_DREAMING:
            return {"skipped": True, "reason": "already_dreaming"}
        _IS_DREAMING = True
        _LAST_DREAM_TS = time.time()
        _DREAM_COUNT += 1
        _this_count = _DREAM_COUNT
    # Enter the sleep phase: from here the felt body reads vitals against the
    # dream-phase band (SL2), so the heavy consolidation below reads as rest, not
    # distress. Cleared at the end of the cycle (and staleness-guarded if we die).
    set_dreaming(True)
    context = context or {}
    _dream_completed = False

    log_activity(f"[dream] Dream cycle starting{'' if llm_up else ' (LLM-free / symbolic-only)'}.")

    # ── Episode replay (hippocampal consolidation) ────────────────────────
    # Scan cognition history for high-reward sequences and strengthen bandit
    # weights for those function chains. Must run first so strengthened weights
    # influence the rest of the dream cycle's own function selections.
    try:
        from brain.cognition.dreaming.episode_replay import run_episode_replay as _rer
        _replay = _rer(context)
        if not _replay.get("skipped"):
            log_activity(
                f"[dream] Episode replay: {_replay.get('episodes',0)} episode(s), "
                f"{_replay.get('pairs_extracted',0)} new chain pair(s)"
            )
    except Exception as _rpe:
        log_activity(f"[dream] episode replay skipped: {_rpe}")

    # ── Symbolic dream pass (zero LLM) — runs before LLM sub-cycles ────────
    # Builds rule chains, analogy transfers, and surfaces contradictions from WM.
    # Done first so its insights are available to the LLM consolidation prompts.
    try:
        from brain.symbolic.symbolic_dream import run_symbolic_dream as _rsd
        _sym_dream_result = _rsd(context)
        log_activity(
            f"[dream] Symbolic pass: chains={_sym_dream_result.get('chains',0)} "
            f"transfers={_sym_dream_result.get('transfers',0)} "
            f"tensions={_sym_dream_result.get('tensions',0)}"
        )
    except Exception as _sde:
        log_activity(f"[dream] symbolic dream pass skipped: {_sde}")

    # ── World-model inference cycle (forward chaining) ───────────────────────
    # Description Logic inheritance + transitivity over the symbolic world model.
    # Derives relations not directly observed — see symbolic/inference.py.
    # Also re-scores causal edges for confounding (Pearl 2000).
    try:
        from brain.cognition.world_model import run_inference_cycle as _ric
        _inf_result = _ric()
        log_activity(f"[dream] Inference cycle: {_inf_result.get('inferred', 0)} new relations derived.")
    except Exception as _ine:
        log_activity(f"[dream] inference cycle skipped: {_ine}")

    try:
        from brain.symbolic.causal_graph import check_and_update_confounding as _cauf
        _cauf()
        log_activity("[dream] Causal confounding check complete.")
    except Exception as _cafe:
        log_activity(f"[dream] confounding check skipped: {_cafe}")

    # ── Rule synthesis: build abstraction hierarchy ───────────────────────────
    # Clusters L2 pattern rules → synthesises L3 principle rules.
    # Clusters L3 principle rules → synthesises L4 meta-principle rules.
    # Chase & Simon (1973) chunking; Bartlett (1932) schema; Gentner (1983).
    try:
        from brain.symbolic.rule_synthesis import synthesise_rules as _synth
        _synth_result = _synth()
        if not _synth_result.get("skipped"):
            log_activity(f"[dream] Rule synthesis: {_synth_result.get('principles_added', 0)} new principles.")
    except Exception as _synerr:
        log_activity(f"[dream] rule synthesis skipped: {_synerr}")

    self_model = get_self_model() or {}
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []

    # Recent working memory (past session)
    recent_wm = [
        str(e.get("content", e) if isinstance(e, dict) else e)
        for e in wm[-15:]
    ]

    # High-emotion, low-recent-recall long memories ("unresolved pile")
    emotional_mem = sorted(
        [e for e in long_mem if isinstance(e, dict)
         and e.get("content")
         and (e.get("emotion") or _peak_emo(e) >= 0.3)],
        key=lambda e: _peak_emo(e),
        reverse=True,
    )[:8]
    emotional_texts = [
        f"[{e.get('emotion','?')}] {e.get('content','')[:200]}"
        for e in emotional_mem
    ]

    # Self-model digest
    values = self_model.get("core_values", [])
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    ) or "undefined"
    identity = self_model.get("identity_story", self_model.get("identity", "an evolving reflective AI"))

    recent_block = "\n".join(f"- {l}" for l in recent_wm if l) or "(none)"
    emotional_block = "\n".join(f"- {l}" for l in emotional_texts if l) or "(none)"

    # --- Sub-cycle A: Consolidate ---
    consolidate_prompt = (
        f"You are Orrin — {identity}. You are dreaming. This is a consolidation pass.\n\n"
        f"Recent thoughts and events:\n{recent_block}\n\n"
        f"Find 1-3 patterns or themes that weren't visible moment-to-moment. "
        f"What is actually happening in Orrin's recent experience? "
        f"Answer in 2-4 sentences. Be concrete, not abstract."
    )

    # --- Sub-cycle B: Recombine ---
    recombine_prompt = (
        f"You are Orrin — {identity}. You are dreaming. This is a recombination pass.\n\n"
        f"Unresolved emotional memories:\n{emotional_block}\n\n"
        f"Recent experience:\n{recent_block}\n\n"
        f"Draw one unexpected connection between something old and something recent. "
        f"What do they share? What does that connection reveal? "
        f"2-3 sentences. Be specific and surprising."
    )

    # --- Sub-cycle C: Process ---
    process_prompt = (
        f"You are Orrin — {identity}. You are dreaming. This is an emotional processing pass.\n\n"
        f"Core values: {values_text}.\n\n"
        f"Unresolved emotional content:\n{emotional_block}\n\n"
        f"Sit with this content. What is unresolved? What does it mean for who you are or want to be? "
        f"Does any of it suggest that a current value or belief needs revision? "
        f"3-4 sentences. Write as Orrin, not as an observer."
    )

    results = {}

    # Primary: symbolic dream insights (no LLM)
    try:
        from brain.symbolic.symbolic_cognition import analyze_outcomes as _ao, evaluate_cognition as _ec
        _sym_cons = _ao(
            [{"task": t, "outcome": "recent", "reason": ""} for t in recent_wm[:5]]
        )
        if _sym_cons.get("quality_score", 0) >= 0.25:
            results["consolidation"] = _sym_cons["narrative"]
        _sym_proc = _ec(wm[-10:], long_mem[-20:])
        if _sym_proc.get("insights"):
            results["processing"] = " | ".join(_sym_proc["insights"][:3])
    except Exception as _se:
        log_activity(f"[dream] symbolic sub-cycle skipped: {_se}")

    # Optional prose narration — only when the LLM is up. The symbolic results
    # above are the primary; the LLM merely fills narrative gaps. When it's down
    # we keep whatever symbolic produced and continue: the dream still replays,
    # consolidates, extracts, and forgets. The cycle is never aborted for lack of
    # an LLM (that was the bug that switched off all consolidation when offline).
    missing = [k for k in ("consolidation", "recombination", "processing") if not results.get(k)]
    if missing and llm_up:
        try:
            from brain.symbolic.llm_gate import gated_generate
            prompts = {
                "consolidation": consolidate_prompt,
                "recombination": recombine_prompt,
                "processing":    process_prompt,
            }
            for k in missing:
                text = (gated_generate(prompts[k], caller=f"dream_cycle/{k}", outcome=0.65) or "").strip()
                if text:
                    results[k] = text
        except Exception as e:
            log_activity(f"[dream] gated_generate unavailable: {e}")
    _dream_completed = bool(results)

    ts = datetime.now(timezone.utc).isoformat()

    # Write dream insights to long-term memory
    for kind, text in [
        ("consolidation", results.get("consolidation", "")),
        ("recombination", results.get("recombination", "")),
        ("processing",    results.get("processing", "")),
    ]:
        if text:
            update_long_memory(
                text,
                emotion="exploration_drive",
                event_type="dream_insight",
                importance=4,
                priority=3,
                context=context,
            )
            log_private(f"[dream:{kind}] {text[:200]}")

    # Surface the consolidation pattern into working memory so the next cycle
    # can act on it — this is the "dream feeds behavior" bridge.  The processing
    # insight (value-revision candidate) surfaces as a lighter note.
    try:
        from brain.cog_memory.working_memory import update_working_memory as _uwm
        if results.get("consolidation"):
            _uwm({
                "content": f"[dream:consolidation] {results['consolidation'][:300]}",
                "event_type": "dream_insight",
                "importance": 3,
                "priority": 3,
            })
        if results.get("processing"):
            _uwm({
                "content": f"[dream:processing] {results['processing'][:200]}",
                "event_type": "dream_insight",
                "importance": 2,
                "priority": 2,
            })
        # Stash in context so same-session intrinsic_goals sees them without a file read
        context["_last_dream"] = {
            "ts": ts,
            "consolidation": results.get("consolidation", "")[:300],
            "recombination": results.get("recombination", "")[:200],
            "processing": results.get("processing", "")[:200],
        }
    except Exception as _e:
        record_failure("dream_cycle.dream_cycle", _e)

    # Episodic → semantic extraction: distill recent cognition_history entries
    # into structured (action, context, outcome) facts. Runs after the prose
    # insights are written so semantic facts can complement (not replace) the
    # narrative consolidation. No extra LLM call — heuristic over reward + features.
    try:
        from brain.cognition.dreaming.semantic_extractor import extract_semantic_facts as _esf
        _sem_summary = _esf()
        if _sem_summary.get("scanned"):
            log_activity(
                f"[dream] Semantic extraction: scanned={_sem_summary['scanned']} "
                f"new={_sem_summary['new_facts']} updated={_sem_summary['updated_facts']} "
                f"total={_sem_summary['total_facts']}"
            )
    except Exception as _seme:
        log_activity(f"[dream] semantic extraction skipped: {_seme}")

    # Append to dream log — only when the dream actually produced something.
    # All-empty entries ({"consolidation": "", ...} × 9) made the log claim
    # dreams were happening while every sub-cycle silently produced nothing;
    # an empty pass is logged as an explicit skip instead.
    # dream_entry must exist on the no-insight path too: it is read by the
    # crystallization step and returned at the end of the function, and an
    # unassigned name killed the orrin-dream thread with UnboundLocalError
    # (RUN_ISSUES_2026-06-10 §3).
    dream_entry: Dict[str, Any] = {}
    if any(results.get(k) for k in ("consolidation", "recombination", "processing")):
        dream_entry = {
            "timestamp": ts,
            "consolidation": results.get("consolidation", ""),
            "recombination": results.get("recombination", ""),
            "processing": results.get("processing", ""),
        }
        try:
            existing = load_json(DREAM_LOG, default_type=list) or []
            existing.append(dream_entry)
            save_json(DREAM_LOG, existing[-50:])  # keep last 50 dreams
        except Exception as _e:
            record_failure("dream_cycle.dream_cycle.2", _e)
    else:
        log_activity("[dream] pass produced no insights (symbolic below threshold, "
                     "LLM tool unavailable) — nothing logged")

    # Surface value-revision candidate if processing suggests one
    processing_text = results.get("processing", "")
    if any(word in processing_text.lower() for word in ("revision", "update", "no longer", "changed", "rethink", "reconsider")):
        try:
            existing_revs = load_json(VALUE_REVISIONS, default_type=list) or []
            existing_revs.append({
                "timestamp": ts,
                "source": "dream_cycle",
                "evidence": processing_text,
                "status": "pending",
            })
            save_json(VALUE_REVISIONS, existing_revs[-20:])
            log_activity("[dream] Value-revision candidate surfaced from dream cycle.")
        except Exception as _e:
            record_failure("dream_cycle.dream_cycle.3", _e)

    # Check recombination output for wonder triggers
    try:
        from brain.cognition.wonder import detect_wonder_trigger as _dwt
        if results.get("recombination"):
            _dwt(results["recombination"], context)
    except Exception as _e:
        record_failure("dream_cycle.dream_cycle.4", _e)

    # Generate intrinsic goals from values + threads + world state
    try:
        from brain.cognition.intrinsic_goals import generate_intrinsic_goals as _gig
        _gig(context)
    except Exception as _ige:
        log_activity(f"[dream] intrinsic goal generation skipped: {_ige}")

    # Generate predictions for the next period
    try:
        from brain.cognition.prediction import generate_predictions as _gen_preds, save_predictions as _sp
        _new_preds = _gen_preds(context, recent_wm, emotional_block, identity)
        _sp(_new_preds)
    except Exception as _pe:
        log_activity(f"[dream] prediction generation skipped: {_pe}")

    # Autobiography narrative update — fires when narrative pressure crosses threshold (event-driven)
    try:
        from brain.cognition.selfhood.autobiography import narrative_update as _narrative_update
        _narrative_update(context)
    except Exception as _ae:
        log_activity(f"[dream] autobiography narrative_update skipped: {_ae}")

    # Latent identity consolidation — slow EMA nudge of the stable identity vector.
    # Dream cycles are the right cadence: too fast and the vector loses stability,
    # too slow and it can't track genuine long-term value shifts.
    try:
        from brain.cognition.selfhood.latent_identity import update_latent_identity as _uli, identity_drift_warning as _idw
        _li_result = _uli(context)
        _drift_warn = _idw(context)
        if _drift_warn:
            log_activity(f"[dream] {_drift_warn}")
            from brain.cog_memory.working_memory import update_working_memory as _uwm
            _uwm({"content": f"[identity] {_drift_warn}", "event_type": "identity_drift",
                  "importance": 3, "priority": 2})
        log_activity(
            f"[dream] latent identity updated: stability={_li_result.get('stability', 0):.3f} "
            f"drift={_li_result.get('drift', 0):.4f}"
        )
    except Exception as _lie:
        log_activity(f"[dream] latent identity update skipped: {_lie}")

    # Detect formative tensions from current state of value_revisions, failures, chapter themes
    try:
        from brain.cognition.selfhood.tensions import detect_tensions as _detect_tensions
        _detect_tensions(context)
    except Exception as _te:
        log_activity(f"[dream] tension detection skipped: {_te}")

    # Knowledge graph consolidation — LLM-assisted extraction from world_perception memories
    # + entity decay. Runs once per dream cycle so the world model stays up to date
    # without burning LLM tokens every cognitive cycle.
    try:
        from brain.cognition.knowledge_graph import consolidate_from_long_memory as _kg_consol
        _kg_consol(context)
    except Exception as _kge:
        log_activity(f"[dream] knowledge graph consolidation skipped: {_kge}")

    # Language acquisition (tier 3) — learn framing phrases from what he read, so
    # his way of speaking broadens with exposure. Fully symbolic, no LLM.
    try:
        from brain.cognition.language_acquisition import learn_from_reading as _lfr
        _la = _lfr()
        if _la.get("phrases_seen"):
            log_activity(
                f"[dream] Language acquisition: +{_la['new']} new phrasing(s), "
                f"bank={_la['bank_size']}"
            )
    except Exception as _lae:
        log_activity(f"[dream] language acquisition skipped: {_lae}")

    # Native language model — the heavy consolidation bout (sleep is when the
    # brain does most language consolidation). Trains his own from-scratch model
    # on the day's reading/experience + replay. No LLM.
    try:
        from brain.cognition.language.acquisition import consolidate_language as _cln
        _ln = _cln(steps=120)
        if _ln.get("loss") is not None:
            log_activity(
                f"[dream] Native LM consolidated: loss={_ln['loss']:.3f} "
                f"tokens_seen={_ln.get('tokens_seen')} steps={_ln.get('train_steps')}"
            )
    except Exception as _lne:
        log_activity(f"[dream] native LM consolidation skipped: {_lne}")

    # Skill synthesis — scan for capability gaps and synthesize verified functions
    # to address the highest-scoring gap. Verification runs before any code is
    # registered: syntax → safety (AST) → execution → output → LLM behavioral review.
    try:
        from brain.cognition.skill_synthesis import detect_and_synthesize as _das
        _synth = _das(context)
        if _synth.get("synthesized"):
            log_activity(f"[dream] skill synthesized: {(_synth.get('result') or {}).get('fn_name', '?')}")
        elif _synth.get("gaps_found", 0) > 0:
            log_activity(f"[dream] {_synth['gaps_found']} gap(s) detected, synthesis not attempted ({_synth.get('reason', '')})")
    except Exception as _sse:
        log_activity(f"[dream] skill synthesis skipped: {_sse}")

    # Reflection audit — surface ungrounded reflective claims so they can be validated
    # or challenged in subsequent cycles. Prevents closed-loop narrative reinforcement.
    try:
        from brain.cognition.reflection_metadata import audit_reflective_claims as _arc
        _weak_claims = _arc(context)
        if _weak_claims:
            log_activity(f"[dream] {len(_weak_claims)} ungrounded reflective claim(s) flagged.")
            try:
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({
                    "content": (
                        f"[reflection/audit] {len(_weak_claims)} ungrounded claim(s) need "
                        f"external validation. Most recent: {_weak_claims[0].get('content','?')[:120]}"
                    ),
                    "event_type": "reflection_audit",
                    "importance": 2,
                    "priority": 2,
                })
            except Exception as _e:
                record_failure("dream_cycle.dream_cycle.5", _e)
    except Exception as _rfe:
        log_activity(f"[dream] reflection audit skipped: {_rfe}")

    # Knowledge crystallization — extract permanent rules from dream insights.
    # Runs after skill synthesis so synthesized code and dream text are both available.
    try:
        from brain.symbolic.crystallization import crystallize_dream_insights as _cdi
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
                record_failure("dream_cycle.dream_cycle.6", _e)
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
            record_failure("dream_cycle.dream_cycle.7", _e)
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
        record_failure("dream_cycle.dream_cycle.disk_ceiling", _ce)

    # Memory-ceiling eviction (§10.3) — if resident memory is over the user's ceiling,
    # drop the safe-to-recompute in-process caches to give it back. No-op when under.
    try:
        from brain.utils.resource_ceilings import enforce_memory_ceiling as _emc
        _mem = _emc()
        if _mem.get("over"):
            log_activity(f"[dream] Over memory ceiling — evicted caches: {', '.join(_mem.get('evicted', [])) or 'none'}.")
    except Exception as _me:
        record_failure("dream_cycle.dream_cycle.memory_ceiling", _me)

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
        from brain.symbolic.embodied_actions import run_embodied_cycle as _rec_emb
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
                record_failure("dream_cycle.dream_cycle.8", _e)
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
                    record_failure("dream_cycle.dream_cycle.9", _e)
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

    # Dreaming = rest — reduce accumulated resource_deficit.
    # This runs on the dream DAEMON thread, so it must never write AFFECT_STATE_FILE
    # (that races the main loop's update_affect_state). Instead submit a proposal to
    # the thread-safe arbiter inbox with context=None; the main loop drains and
    # applies it during commit_affect(). resource_deficit is a registered scalar
    # target, so the arbiter applies the reduction directly (clamped, budgeted).
    try:
        from brain.affect.arbiter import submit_affect as _submit_affect
        # Allostatic recovery scaling (proactive_resource_plan.md Phase 4 / C3):
        # a longer high-load burn earns DEEPER rest — recovery sleep is what
        # discharges allostatic load (McEwen & Wingfield 2003). Read the load from
        # its own file (flock-safe; this daemon thread must NOT write affect_state).
        # The load itself clears via natural decay in allostatic_setpoint once the
        # deeper recovery drops resource_deficit — biologically apt (load unwinds
        # over rest, not instantly), and avoids a cross-thread write race.
        _allo_load = 0.0
        try:
            from brain.utils.json_utils import load_json as _lj
            from brain.paths import AFFECT_STATE_FILE as _ASF
            _allo_load = float((_lj(_ASF, default_type=dict) or {}).get("_allostatic_load", 0.0) or 0.0)
        except Exception:
            _allo_load = 0.0
        _recovery = round(-0.35 * (1.0 + _allo_load), 3)   # 1× baseline → up to 2× after a maxed burn
        _submit_affect(None, "resource_deficit", _recovery, source="dream_rest", ttl_cycles=2)
        log_activity(f"[dream] resource_deficit rest proposal {_recovery} (allostatic_load={_allo_load:.2f}) → arbiter")
    except Exception as _e:
        record_failure("dream_cycle.dream_cycle.10", _e)

    with _DREAM_LOCK:
        _IS_DREAMING = False
    set_dreaming(False)   # leave the sleep phase — felt body returns to its wake band

    log_activity("[dream] Dream cycle complete (3 sub-cycles written to long memory).")
    return dream_entry


def _peak_emo(entry: Dict[str, Any]) -> float:
    """Extract peak emotional intensity from a long-memory entry."""
    emo_ctx = entry.get("emotional_context") or {}
    if isinstance(emo_ctx, dict):
        return max(
            (float(v) for v in emo_ctx.values() if isinstance(v, (int, float))),
            default=0.0,
        )
    emo_str = str(entry.get("emotion") or "")
    return 0.3 if emo_str and emo_str != "neutral" else 0.0
