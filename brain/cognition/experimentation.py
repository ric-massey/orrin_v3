# brain/cognition/experimentation.py
# Active experimentation: hypothesize → design → test in sim/sandbox → consolidate.
#
# Three experiment types:
#
#   behavioral  — constructs a fabricated emotional/attentional state and runs
#                 select_function() against it. Tests claims about Orrin's own
#                 decision-making patterns without waiting for real situations.
#                 Example: "When threat_level > 0.65 with no committed goal, I default
#                 to introspection rather than outward action."
#
#   pattern     — statistical check against actual WM + cognition history data.
#                 Tests correlational claims about Orrin's own history.
#                 Example: "My stagnation_signal signal reliably precedes seek_novelty picks."
#
#   capability  — generates a concrete task, runs it (LLM or sandbox), evaluates
#                 output against a rubric. Tests claims about what Orrin can do.
#                 Example: "I can identify emotional subtext in ambiguous messages."
#
# Pipeline (one step advances per dream cycle, so a full experiment takes ~4 dreams):
#   proposed → designed → testing → concluded
#
# Consolidation writes insights to long_memory, knowledge_graph, and seeds
# new predictions so the loop stays productive across sessions.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.cog_memory.working_memory import update_working_memory
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import (
    EXPERIMENTS_FILE, WORKING_MEMORY_FILE, COGNITION_HISTORY_FILE,
    SELF_MODEL_FILE, PREDICTIONS_FILE,
)
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
# Test design (Phase 2) + execution (Phase 3), extracted to experiment_tests.py
# (Phase 4.5C). Re-imported for the public run_experiment_cycle / run_active_experiment.
from brain.cognition.experiment_tests import _design_test, _run_test  # noqa: F401
_log = get_logger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_MAX_EXPERIMENTS     = 30    # rolling cap on experiment history
_HYPOTHESIS_COOLDOWN = 4 * 3600   # generate a new hypothesis at most every 4h


_last_hypothesis_ts: float = 0.0


# ─── Storage ──────────────────────────────────────────────────────────────────


def _exp_id(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:8]


def _load_experiments() -> List[Dict]:
    data = load_json(EXPERIMENTS_FILE, default_type=list) or []
    return data if isinstance(data, list) else []


def _save_experiments(exps: List[Dict]) -> None:
    save_json(EXPERIMENTS_FILE, exps[-_MAX_EXPERIMENTS:])


def _get_oldest_pending(exps: List[Dict]) -> Optional[Dict]:
    """Return oldest experiment that hasn't concluded, or None."""
    pending = [e for e in exps if isinstance(e, dict) and e.get("status") != "concluded"]
    if not pending:
        return None
    return min(pending, key=lambda e: e.get("proposed_at", ""))


# ─── Phase 1: Hypothesis generation ──────────────────────────────────────────

def _generate_hypothesis(context: Dict[str, Any]) -> Optional[Dict]:
    """
    LLM examines recent WM, emotional state, cognition history, and self-model
    to propose a specific, falsifiable hypothesis about Orrin's own behaviour.
    Returns a hypothesis dict or None.
    """
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    wm_text = "\n".join(
        f"- {str(e.get('content', ''))[:100]}"
        for e in (wm[-15:] if isinstance(wm, list) else [])
        if isinstance(e, dict) and str(e.get("content", "")).strip()
    )

    cog_log = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    recent_choices = [
        str(e.get("choice", "")) for e in (cog_log[-20:] if isinstance(cog_log, list) else [])
        if isinstance(e, dict) and e.get("choice")
    ]
    choice_text = ", ".join(recent_choices[-10:]) or "(none)"

    emo = (context.get("affect_state") or {})
    core = (emo.get("core_signals") or emo) or {}
    emo_text = ", ".join(f"{k}={v:.2f}" for k, v in core.items() if isinstance(v, (int, float)))

    sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    identity = sm.get("identity_story", "an evolving reflective AI")

    existing = _load_experiments()
    existing_hyps = [e.get("hypothesis", "")[:60] for e in existing]

    prompt = (
        f"You are Orrin — {identity}. You're entering an experimentation mode.\n\n"
        f"Recent thoughts:\n{wm_text or '(none)'}\n\n"
        f"Recent function choices: {choice_text}\n"
        f"Current emotional state: {emo_text or '(unknown)'}\n\n"
        f"Existing hypotheses (don't duplicate): {existing_hyps[:5]}\n\n"
        "Form ONE specific, falsifiable hypothesis about your own cognition, behaviour, "
        "or capabilities. It must be concrete enough to test. Three types:\n"
        "  behavioral: 'When [emotional state X], I tend to [do Y rather than Z]'\n"
        "  pattern:    'My [emotion/signal A] reliably precedes [function/event B]'\n"
        "  capability: 'I can [perform task T] with [quality level Q]'\n\n"
        "Respond as JSON only:\n"
        '{"hypothesis": "...", "type": "behavioral|pattern|capability", '
        '"why_interesting": "...", "predicted_outcome": "..."}'
    )
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="experimentation/hypothesize"), "experimentation") or ""
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        hyp = str(data.get("hypothesis", "")).strip()
        htype = str(data.get("type", "behavioral")).strip()
        if not hyp or len(hyp) < 10:
            return None
        if htype not in ("behavioral", "pattern", "capability"):
            htype = "behavioral"
        return {
            "id":               _exp_id(hyp),
            "hypothesis":       hyp,
            "type":             htype,
            "why_interesting":  str(data.get("why_interesting", "")).strip()[:200],
            "predicted_outcome": str(data.get("predicted_outcome", "")).strip()[:200],
            "status":           "proposed",
            "test_plan":        {},
            "test_results":     {},
            "conclusion":       {},
            "proposed_at":      now_iso_z(),
            "designed_at":      "",
            "tested_at":        "",
            "concluded_at":     "",
        }
    except Exception as e:
        log_private(f"[experimentation] hypothesis generation failed: {e}")
        return None




# ─── Phase 4: Consolidation ───────────────────────────────────────────────────

# Connectives that mark a cause→effect claim inside a hypothesis sentence.
_CAUSE_EFFECT_PATTERNS = (
    r"(.+?)\s*(?:->|→)\s*(.+)",
    r"(?:the more|more)\s+(.+?),?\s*the more\s+(.+)",
    r"when\s+(.+?),\s*(.+)",
    r"if\s+(.+?)[,]?\s+then\s+(.+)",
    r"(.+?)\s+(?:leads to|causes|results in|produces|triggers|drives|makes)\s+(.+)",
)


def _extract_cause_effect(text: str) -> Optional[tuple]:
    """
    Pull a (cause, effect) pair out of a hypothesis sentence when it states a
    causal relation. Conservative: returns None unless a clear connective is
    found, so the causal graph is not polluted with vague claims.
    """
    t = (text or "").strip()
    for pat in _CAUSE_EFFECT_PATTERNS:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            cause = m.group(1).strip(" .,:;\"'")[:80]
            effect = m.group(2).strip(" .,:;\"'")[:80]
            if len(cause) > 3 and len(effect) > 3 and cause.lower() != effect.lower():
                return cause, effect
    return None


def _write_causal_edge_from_experiment(experiment: Dict, verdict: str) -> Optional[Dict]:
    """
    A confirmed/refuted hypothesis is a cause→effect belief earned by test — write
    it to the causal graph so prediction, the reasoning router, and abductive
    diagnosis all learn from it (Phase 4: trial-and-error → durable causal belief).
    Pearl: behavioural/pattern self-tests are observational evidence (Level 1);
    `confirmed` adds support, `refuted` adds counterfactual evidence against.
    """
    if verdict not in ("confirmed", "refuted"):
        return None
    ce = _extract_cause_effect(experiment.get("hypothesis", ""))
    if not ce:
        return None
    cause, effect = ce
    try:
        from brain.symbolic.causal_graph import update_edge
        return update_edge(
            cause, effect,
            confirmed=(verdict == "confirmed"),
            counterfactual=(verdict == "refuted"),
            source="experiment",
        )
    except Exception as _e:
        record_failure("experimentation._write_causal_edge_from_experiment", _e)
        return None


def _consolidate(experiment: Dict, context: Dict[str, Any]) -> str:
    """
    Synthesise what the test reveals. Write insights to long_memory and
    knowledge_graph. Seed the prediction system with confirmed findings.
    Update self_model.beliefs if the conclusion is strong.
    """
    hyp   = experiment["hypothesis"]
    htype = experiment["type"]
    res   = experiment.get("test_results", {})

    confirmed   = bool(res.get("confirmed", False))
    refuted     = bool(res.get("refuted", False))

    verdict = "confirmed" if confirmed else ("refuted" if refuted else "inconclusive")

    # Ask LLM to synthesise the insight
    prompt = (
        f"You are Orrin, reviewing the result of a self-experiment.\n\n"
        f"Hypothesis: {hyp}\n"
        f"Type: {htype}\n"
        f"Verdict: {verdict}\n"
        f"Test data: {json.dumps({k: v for k, v in res.items() if k != 'task_output'}, indent=2)[:400]}\n\n"
        f"Write a brief, honest consolidation (3-5 sentences):\n"
        f"- What did the test actually show?\n"
        f"- What should change in how you understand yourself?\n"
        f"- What follow-up experiment or prediction does this motivate?\n\n"
        f"Reply as JSON: {{\"insight\": \"...\", \"belief_update\": \"...\", "
        f"\"follow_up\": \"...\", \"confidence\": 0.0-1.0}}"
    )
    insight = belief_update = follow_up = ""
    confidence = 0.5
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="experimentation/consolidate"), "experimentation") or ""
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            insight      = str(data.get("insight", "")).strip()[:400]
            belief_update = str(data.get("belief_update", "")).strip()[:200]
            follow_up    = str(data.get("follow_up", "")).strip()[:200]
            confidence   = float(data.get("confidence", 0.5))
    except Exception as e:
        log_private(f"[experimentation] consolidation LLM failed: {e}")
        insight = f"Experiment {verdict}: {hyp[:80]}"

    # Write to long_memory
    memory_text = (
        f"[experiment:{verdict}] Hypothesis: {hyp}\n"
        f"Insight: {insight}\n"
        f"Belief update: {belief_update}"
    )
    update_long_memory(
        memory_text,
        emotion="exploration_drive" if confirmed else ("prediction_error_signal" if refuted else "stagnation_signal"),
        event_type="experiment_insight",
        importance=4 if confirmed or refuted else 2,
        context=context,
        extra={"experiment_id": experiment["id"], "verdict": verdict},
    )

    # Feed knowledge graph with the insight as a self_insight entity
    try:
        from brain.cognition.knowledge_graph import add_entity, add_relation
        slug = f"insight:{hyp[:40].replace(' ', '_')}"
        add_entity(slug, "concept", properties={
            "verdict": verdict,
            "confidence": str(round(confidence, 2)),
            "insight": insight[:100],
        }, confidence=confidence * 0.85, source="experimentation",
            extra_tags=["self_insight", verdict, htype])
        add_relation("Orrin", "cares_about", slug, confidence=0.6, source="experimentation")
    except Exception as _e:
        record_failure("experimentation._consolidate", _e)

    # Phase 4: write the tested hypothesis as a causal edge so the readers
    # (prediction, reasoning_router, abductive diagnosis) learn from it.
    _write_causal_edge_from_experiment(experiment, verdict)

    # Master plan 3.1: an experiment verdict is the heaviest evidence an
    # opinion can receive — a seeded contrary verdict must visibly move
    # even a high-mention opinion.
    try:
        from brain.cognition.opinions import ingest_experiment_verdict
        ingest_experiment_verdict(hyp, verdict, experiment["id"], context=context)
    except Exception as _e:
        record_failure("experimentation.opinion_evidence", _e)

    # Seed prediction system with follow-up if confirmed
    if follow_up and (confirmed or refuted):
        try:
            preds = load_json(PREDICTIONS_FILE, default_type=list) or []
            preds.append({
                "prediction": follow_up,
                "horizon": "medium",
                "confidence": confidence * 0.7,
                "created_ts": now_iso_z(),
                "status": "pending",
                "source": "experiment_consolidation",
                "checked_ts": None,
                "outcome": None,
            })
            save_json(PREDICTIONS_FILE, preds[-100:])
        except Exception as _e:
            record_failure("experimentation._consolidate.2", _e)

    # Update self_model.beliefs for strongly confirmed/refuted experiments
    if confidence >= 0.7 and belief_update:
        try:
            sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
            beliefs = sm.setdefault("empirical_beliefs", [])
            beliefs.append({
                "statement": belief_update,
                "verdict": verdict,
                "confidence": round(confidence, 2),
                "from_experiment": experiment["id"],
                "added_ts": now_iso_z(),
            })
            sm["empirical_beliefs"] = beliefs[-20:]
            save_json(SELF_MODEL_FILE, sm)
        except Exception as _e:
            record_failure("experimentation._consolidate.3", _e)

    # Mark experiment concluded
    experiment["conclusion"] = {
        "verdict": verdict,
        "insight": insight,
        "belief_update": belief_update,
        "follow_up": follow_up,
        "confidence": round(confidence, 2),
    }
    experiment["status"] = "concluded"
    experiment["concluded_at"] = now_iso_z()

    update_working_memory({
        "content": f"[experiment:{verdict}] {insight[:200]}",
        "event_type": "experiment_insight",
        "importance": 3,
        "priority": 3,
    })

    log_activity(f"[experimentation] concluded ({verdict}, conf={confidence:.2f}): {hyp[:60]}")
    return f"Experiment {verdict}: {insight[:100]}"


# ─── Entry points ─────────────────────────────────────────────────────────────

def run_experiment_cycle(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dream cycle entry point. Advances the experiment pipeline by ONE step:
    - If no pending experiments and cooldown elapsed: generate a new hypothesis
    - If proposed: design the test
    - If designed: run the test
    - If testing: consolidate
    Returns a summary dict.
    """
    global _last_hypothesis_ts

    # Hypothesis generation / experiment design is open-vocabulary (Phase 5):
    # genuinely the LLM's job. When cognition can't reach it, skip cleanly rather
    # than firing blocked round-trips. (Also tagged requires_llm for the selection
    # path; this guards the direct dream-cycle call.) The SYMBOLIC experiment
    # runner (symbolic.autonomous_experiment) covers the LLM-off case separately.
    from brain.utils.llm_gate import llm_callable_by
    if not llm_callable_by("experimentation"):
        return {"step": "skip", "reason": "llm_unavailable"}

    exps = _load_experiments()
    pending = _get_oldest_pending(exps)

    if pending is None:
        # No pending experiments: generate a new hypothesis if cooldown allows
        now = time.time()
        if now - _last_hypothesis_ts < _HYPOTHESIS_COOLDOWN:
            return {"step": "wait", "reason": "hypothesis cooldown active"}
        hyp = _generate_hypothesis(context)
        if hyp:
            exps.append(hyp)
            _save_experiments(exps)
            _last_hypothesis_ts = now
            log_activity(f"[experimentation] new hypothesis: {hyp['hypothesis'][:60]}")
            return {"step": "proposed", "hypothesis": hyp["hypothesis"], "type": hyp["type"]}
        return {"step": "no_hypothesis", "reason": "LLM returned nothing usable"}

    status = pending.get("status", "proposed")

    if status == "proposed":
        ok = _design_test(pending, context)
        _save_experiments(exps)
        return {"step": "designed", "ok": ok, "id": pending["id"]}

    elif status == "designed":
        ok = _run_test(pending, context)
        _save_experiments(exps)
        return {"step": "tested", "ok": ok, "id": pending["id"],
                "verdict_hint": "confirmed" if pending["test_results"].get("confirmed") else "not_confirmed"}

    elif status == "testing":
        summary = _consolidate(pending, context)
        _save_experiments(exps)
        return {"step": "concluded", "summary": summary, "id": pending["id"]}

    return {"step": "unknown_status", "status": status}


def run_active_experiment(context: Dict[str, Any] = None, **_) -> str:
    """
    Cognition function: advance the experimentation pipeline by one step.
    Can be selected by the bandit during autonomous operation.
    """
    context = context or {}
    try:
        result = run_experiment_cycle(context)
        step = result.get("step", "?")
        if step == "proposed":
            return f"Formed new hypothesis ({result.get('type', '?')}): {result.get('hypothesis', '')[:100]}"
        elif step == "designed":
            return f"Designed test for experiment {result.get('id', '?')}."
        elif step == "tested":
            return f"Ran experiment test ({result.get('verdict_hint', '?')}). Ready to consolidate."
        elif step == "concluded":
            return f"Experiment concluded: {result.get('summary', '')[:120]}"
        elif step == "wait":
            return f"Experimentation on cooldown: {result.get('reason', '')}."
        else:
            return f"Experimentation step: {step}"
    except Exception as e:
        log_private(f"[experimentation] run_active_experiment error: {e}")
        return f"run_active_experiment failed: {e}"
