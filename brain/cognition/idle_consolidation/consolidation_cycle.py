# brain/cognition/idle_consolidation/consolidation_cycle.py
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
# Late-phase symbolic-intelligence maintenance, extracted to dream_symbolic.py
# (Phase 4.5C).
from brain.cognition.idle_consolidation.symbolic_consolidation import run_symbolic_maintenance
_log = get_logger(__name__)


_LAST_DREAM_TS: float = 0.0
_DREAM_MIN_INTERVAL_S: float = 6 * 3600   # 6 hours minimum between dream cycles
_IDLE_THRESHOLD_S: float = 300            # 5 minutes of no user input = idle
_DREAM_COUNT: int = 0                     # incremented each run; used for projection check cadence
_IS_DREAMING: bool = False                # re-entry guard: prevents two concurrent dream cycles
_DREAM_LOCK: threading.Lock = threading.Lock()  # guards all _DREAM_* globals

# ── Sleep-phase flag (SL1) ──────────────────────────────────────────────────
# A process-local "Orrin is asleep" gate, same module-gate pattern as the host
# guard's heavy_cycles_paused / resource_floor_shedding. The felt body (body_sense)
# and the other resource_deficit writers read this to attribute the dream's own
# RSS/CPU/latency spike to a *sleep* phase rather than to distress (§3.2 SL1).
#
# The dream runs on a daemon thread while the main cognitive loop keeps cycling,
# so the loop needs to know "we're asleep right now" without a handle on the
# dream. Staleness-guarded: if a dream thread dies mid-run and never clears the
# flag, consolidating_now() auto-expires it after _DREAM_PHASE_MAX_S so a crashed
# dream can never permanently mask the felt body (which would hide real distress).
_DREAM_PHASE: bool = False
_DREAM_PHASE_TS: float = 0.0
_DREAM_PHASE_MAX_S: float = 1800.0   # a dream this long is treated as stale, not asleep


def set_consolidating(active: bool) -> None:
    """Mark the sleep phase on/off. Called around the dream cycle; also usable by
    tests to simulate sleep. Thread-safe."""
    global _DREAM_PHASE, _DREAM_PHASE_TS
    with _DREAM_LOCK:
        _DREAM_PHASE = bool(active)
        _DREAM_PHASE_TS = time.time() if active else 0.0


def consolidating_now() -> bool:
    """True while a dream cycle is in flight (the felt body should read vitals as
    normal-for-sleeping, not as distress). Auto-expires a stale flag so a crashed
    dream can't permanently mask the felt body."""
    with _DREAM_LOCK:
        if not _DREAM_PHASE:
            return False
        if (time.time() - _DREAM_PHASE_TS) > _DREAM_PHASE_MAX_S:
            return False
        return True


def should_consolidate(context: Dict[str, Any]) -> bool:
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


def idle_consolidation_cycle(context: Dict[str, Any] = None) -> Dict[str, Any]:
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
    set_consolidating(True)
    context = context or {}
    _dream_completed = False

    log_activity(f"[dream] Dream cycle starting{'' if llm_up else ' (LLM-free / symbolic-only)'}.")

    # ── Episode replay (hippocampal consolidation) ────────────────────────
    # Scan cognition history for high-reward sequences and strengthen bandit
    # weights for those function chains. Must run first so strengthened weights
    # influence the rest of the dream cycle's own function selections.
    try:
        from brain.cognition.idle_consolidation.episode_replay import run_episode_replay as _rer
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
                text = (gated_generate(prompts[k], caller=f"idle_consolidation_cycle/{k}", outcome=0.65) or "").strip()
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
        record_failure("idle_consolidation_cycle.idle_consolidation_cycle", _e)

    # Episodic → semantic extraction: distill recent cognition_history entries
    # into structured (action, context, outcome) facts. Runs after the prose
    # insights are written so semantic facts can complement (not replace) the
    # narrative consolidation. No extra LLM call — heuristic over reward + features.
    try:
        from brain.cognition.idle_consolidation.semantic_extractor import extract_semantic_facts as _esf
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
            record_failure("idle_consolidation_cycle.idle_consolidation_cycle.2", _e)
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
                "source": "idle_consolidation_cycle",
                "evidence": processing_text,
                "status": "pending",
            })
            save_json(VALUE_REVISIONS, existing_revs[-20:])
            log_activity("[dream] Value-revision candidate surfaced from dream cycle.")
        except Exception as _e:
            record_failure("idle_consolidation_cycle.idle_consolidation_cycle.3", _e)

    # Check recombination output for wonder triggers
    try:
        from brain.cognition.wonder import detect_wonder_trigger as _dwt
        if results.get("recombination"):
            _dwt(results["recombination"], context)
    except Exception as _e:
        record_failure("idle_consolidation_cycle.idle_consolidation_cycle.4", _e)

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
        from brain.cognition.self_state.autobiography import narrative_update as _narrative_update
        _narrative_update(context)
    except Exception as _ae:
        log_activity(f"[dream] autobiography narrative_update skipped: {_ae}")

    # Latent identity consolidation — slow EMA nudge of the stable identity vector.
    # Dream cycles are the right cadence: too fast and the vector loses stability,
    # too slow and it can't track genuine long-term value shifts.
    try:
        from brain.cognition.self_state.latent_identity import update_latent_identity as _uli, identity_drift_warning as _idw
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
        from brain.cognition.self_state.tensions import detect_tensions as _detect_tensions
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
                record_failure("idle_consolidation_cycle.idle_consolidation_cycle.5", _e)
    except Exception as _rfe:
        log_activity(f"[dream] reflection audit skipped: {_rfe}")

    run_symbolic_maintenance(context, dream_entry, _this_count, _dream_completed)

    # Dreaming = rest — reduce accumulated resource_deficit.
    # This runs on the dream DAEMON thread, so it must never write AFFECT_STATE_FILE
    # (that races the main loop's update_affect_state). Instead submit a proposal to
    # the thread-safe arbiter inbox with context=None; the main loop drains and
    # applies it during commit_affect(). resource_deficit is a registered scalar
    # target, so the arbiter applies the reduction directly (clamped, budgeted).
    try:
        from brain.control_signals.arbiter import submit_affect as _submit_affect
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
        record_failure("idle_consolidation_cycle.idle_consolidation_cycle.10", _e)

    with _DREAM_LOCK:
        _IS_DREAMING = False
    set_consolidating(False)   # leave the sleep phase — felt body returns to its wake band

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
