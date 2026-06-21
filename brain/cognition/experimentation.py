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
    EXPERIMENTS_FILE, WORKING_MEMORY_FILE, COGNITION_HISTORY_FILE, COGNITIVE_FUNCTIONS_LIST_FILE,
    SELF_MODEL_FILE, PREDICTIONS_FILE,
)
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_MAX_EXPERIMENTS     = 30    # rolling cap on experiment history
_HYPOTHESIS_COOLDOWN = 4 * 3600   # generate a new hypothesis at most every 4h
_BEHAVIORAL_REPS     = 5          # how many simulated selections to run per test
_PATTERN_WINDOW      = 120        # WM entries to scan for pattern tests
_CONFIRMED_THRESHOLD = 0.65       # hit rate above this = confirmed
_REFUTED_THRESHOLD   = 0.25       # hit rate below this = refuted (else: inconclusive)

# Function classification for behavioral tests
_OUTWARD_FNS = frozenset({
    "look_outward", "look_around", "search_own_files", "grep_files",
    "search_files", "seek_novelty", "pursue_committed_goal",
    "plan_next_step", "assess_goal_progress", "thread_continue",
})
_INWARD_FNS = frozenset({
    "reflection", "reflect_on_directive", "dream_cycle", "narrative_update",
    "propose_value_revision", "metacog_flush", "self_review",
    "reflect_on_internal_agents",
})

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


# ─── Phase 2: Test design ─────────────────────────────────────────────────────

def _design_test(experiment: Dict, context: Dict[str, Any]) -> bool:
    """
    Build a concrete test plan for the hypothesis. Returns True on success.
    Writes the plan into experiment["test_plan"] in-place.
    """
    hyp = experiment["hypothesis"]
    htype = experiment["type"]

    if htype == "behavioral":
        experiment["test_plan"] = _design_behavioral_test(hyp, context)
    elif htype == "pattern":
        experiment["test_plan"] = _design_pattern_test(hyp, context)
    else:
        experiment["test_plan"] = _design_capability_test(hyp, context)

    if not experiment["test_plan"]:
        return False
    experiment["status"] = "designed"
    experiment["designed_at"] = now_iso_z()
    return True


def _design_behavioral_test(hyp: str, context: Dict) -> Dict:
    """
    Parse the hypothesis for emotional state conditions and expected function class.
    Build a list of simulated contexts to test.
    """
    # Ask LLM to extract the test parameters
    prompt = (
        f"Parse this behavioral hypothesis into test parameters:\n\"{hyp}\"\n\n"
        "Extract the key variables for simulation:\n"
        '{"trigger_emotion": "impasse_signal|risk_estimate|stagnation_signal|exploration_drive|...", '
        '"trigger_level": 0.0-1.0, '
        '"expected_class": "outward|inward|either", '
        '"attention_mode": "alert|wandering|neutral", '
        '"has_goal": true|false, '
        '"user_present": false}'
        "\nReturn ONLY the JSON."
    )
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="experimentation/design_behavioral"), "experimentation") or ""
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return {}
        params = json.loads(m.group(0))
        return {
            "method": "behavioral_simulation",
            "trigger_emotion": str(params.get("trigger_emotion", "risk_estimate")),
            "trigger_level": float(params.get("trigger_level", 0.65)),
            "expected_class": str(params.get("expected_class", "inward")),
            "attention_mode": str(params.get("attention_mode", "neutral")),
            "has_goal": bool(params.get("has_goal", False)),
            "user_present": bool(params.get("user_present", False)),
            "reps": _BEHAVIORAL_REPS,
            "success_criterion": f"≥ {int(_CONFIRMED_THRESHOLD * 100)}% of selections match expected_class",
        }
    except Exception:
        return {}


def _design_pattern_test(hyp: str, context: Dict) -> Dict:
    """Extract signal name and expected outcome for a pattern hypothesis."""
    prompt = (
        f"Parse this pattern hypothesis into measurable variables:\n\"{hyp}\"\n\n"
        '{"antecedent_keyword": "keyword to look for in WM entry content", '
        '"consequent_keyword": "keyword to look for in next WM entry", '
        '"window": 3}'
        "\nReturn ONLY the JSON."
    )
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="experimentation/design_pattern"), "experimentation") or ""
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return {}
        params = json.loads(m.group(0))
        return {
            "method": "pattern_check",
            "antecedent_keyword": str(params.get("antecedent_keyword", "")).lower()[:40],
            "consequent_keyword": str(params.get("consequent_keyword", "")).lower()[:40],
            "window": min(5, max(1, int(params.get("window", 3)))),
            "success_criterion": f"conditional hit rate ≥ {_CONFIRMED_THRESHOLD:.0%}",
        }
    except Exception:
        return {}


def _design_capability_test(hyp: str, context: Dict) -> Dict:
    """Generate a concrete task and rubric for testing a capability claim."""
    prompt = (
        f"Design a test for this capability hypothesis:\n\"{hyp}\"\n\n"
        "Create:\n"
        '{"task_prompt": "specific concrete task to give Orrin", '
        '"rubric": "how to evaluate the output (2-3 criteria)", '
        '"pass_threshold": 7}'
        "\nReturn ONLY the JSON. Keep task_prompt under 150 words."
    )
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="experimentation/design_capability"), "experimentation") or ""
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return {}
        params = json.loads(m.group(0))
        return {
            "method": "capability_run",
            "task_prompt": str(params.get("task_prompt", ""))[:400],
            "rubric": str(params.get("rubric", ""))[:300],
            "pass_threshold": int(params.get("pass_threshold", 7)),
            "success_criterion": f"LLM rating ≥ {params.get('pass_threshold', 7)}/10 on rubric",
        }
    except Exception:
        return {}


# ─── Phase 3: Test execution ──────────────────────────────────────────────────

def _build_sim_context(emotion: str, level: float, attention: str,
                        has_goal: bool, user_present: bool, noise: float = 0.0) -> Dict:
    """
    Construct a minimal context dict for select_function simulation.
    noise adds small random variation so repeated runs aren't identical.
    """
    import random
    base_emo = {e: 0.05 for e in
                ["positive_valence", "negative_valence", "conflict_signal", "threat_level", "exploration_drive", "stagnation_signal",
                 "impasse_signal", "risk_estimate", "motivation", "excitement"]}
    base_emo[emotion] = max(0.0, min(1.0, level + random.uniform(-noise, noise)))

    fns_raw = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
    available = [
        (f["name"] if isinstance(f, dict) else str(f))
        for f in fns_raw if f
    ]
    if not available:
        available = list(_OUTWARD_FNS | _INWARD_FNS)

    return {
        "affect_state": {"core_signals": base_emo},
        "attention_mode": attention,
        "committed_goal": {"title": "test goal"} if has_goal else None,
        "latest_user_input": "hello" if user_present else "",
        "available_functions": available,
        "_rest_mode": False,
        "energy_mode": "neutral",
        "energy_state": "medium",
        "action_vs_reflect_bias": 0.5,
        "working_memory": [],
        "recent_picks": [],
        "act_now": False,
        "action_debt": 0,
        "reflection_budget_exhausted": False,
        "_experiment_sim": True,   # flag so downstream knows this is a simulation
    }


def _run_behavioral_test(experiment: Dict, context: Dict[str, Any]) -> Dict:
    """
    Run select_function N times with the simulated context.
    Returns {"picks": [...], "hit_rate": float, "confirmed": bool}.
    """
    plan = experiment["test_plan"]
    emotion = plan.get("trigger_emotion", "risk_estimate")
    level   = float(plan.get("trigger_level", 0.65))
    attn    = plan.get("attention_mode", "neutral")
    has_goal = bool(plan.get("has_goal", False))
    user_present = bool(plan.get("user_present", False))
    expected = plan.get("expected_class", "inward")
    reps = int(plan.get("reps", _BEHAVIORAL_REPS))

    picks = []
    classifications = []
    try:
        from brain.think.think_utils.select_function import select_function as _sel
        for _ in range(reps):
            sim_ctx = _build_sim_context(emotion, level, attn, has_goal, user_present, noise=0.08)
            try:
                result = _sel(sim_ctx)
                fn_name = (result[0] if isinstance(result, tuple) else result) or ""
                fn_name = fn_name if isinstance(fn_name, str) else str(fn_name)
            except Exception:
                fn_name = ""
            picks.append(fn_name)
            if fn_name in _OUTWARD_FNS:
                classifications.append("outward")
            elif fn_name in _INWARD_FNS:
                classifications.append("inward")
            else:
                classifications.append("other")
    except Exception as e:
        return {"error": str(e), "picks": [], "hit_rate": 0.0, "confirmed": False}

    if expected == "either":
        hit_rate = 1.0  # trivially satisfied
    else:
        hits = sum(1 for c in classifications if c == expected)
        hit_rate = hits / len(classifications) if classifications else 0.0

    confirmed = hit_rate >= _CONFIRMED_THRESHOLD
    refuted   = hit_rate <= _REFUTED_THRESHOLD

    return {
        "picks": picks,
        "classifications": classifications,
        "expected_class": expected,
        "hit_rate": round(hit_rate, 3),
        "confirmed": confirmed,
        "refuted": refuted,
        "inconclusive": not confirmed and not refuted,
    }


def _run_pattern_test(experiment: Dict, context: Dict[str, Any]) -> Dict:
    """
    Scan WM history for antecedent→consequent patterns within a sliding window.
    Returns conditional hit rate and a verdict.
    """
    plan = experiment["test_plan"]
    ante_kw = plan.get("antecedent_keyword", "").lower()
    cons_kw = plan.get("consequent_keyword", "").lower()
    window  = int(plan.get("window", 3))

    if not ante_kw or not cons_kw:
        return {"error": "missing keywords", "hit_rate": 0.0, "confirmed": False}

    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    entries = [str(e.get("content", "") if isinstance(e, dict) else e).lower()
               for e in wm[-_PATTERN_WINDOW:]]

    # Also pull from cognition history for function-level patterns
    cog_log = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    cog_entries = [str(e.get("choice", "") if isinstance(e, dict) else e).lower()
                   for e in cog_log[-_PATTERN_WINDOW:]]

    antecedent_count = 0
    hit_count = 0
    baseline_count = 0

    combined = entries + cog_entries
    for i, entry in enumerate(combined):
        if ante_kw in entry:
            antecedent_count += 1
            # Check if consequent appears within the window
            lookahead = combined[i+1: i+1+window]
            if any(cons_kw in la for la in lookahead):
                hit_count += 1

        if cons_kw in entry:
            baseline_count += 1

    baseline_rate = baseline_count / len(combined) if combined else 0.0
    hit_rate      = hit_count / antecedent_count if antecedent_count > 0 else 0.0
    lift          = (hit_rate / baseline_rate) if baseline_rate > 0.01 else None

    confirmed = hit_rate >= _CONFIRMED_THRESHOLD and antecedent_count >= 3
    refuted   = antecedent_count >= 5 and hit_rate <= _REFUTED_THRESHOLD

    return {
        "antecedent_count": antecedent_count,
        "hit_count": hit_count,
        "baseline_rate": round(baseline_rate, 3),
        "hit_rate": round(hit_rate, 3),
        "lift": round(lift, 2) if lift is not None else None,
        "confirmed": confirmed,
        "refuted": refuted,
        "inconclusive": not confirmed and not refuted,
        "note": ("too few antecedent examples for reliable result" if antecedent_count < 3 else ""),
    }


def _run_capability_test(experiment: Dict, context: Dict[str, Any]) -> Dict:
    """
    Run the task_prompt through LLM, then rate the output against the rubric.
    Returns rating (0-10) and a verdict.
    """
    plan = experiment["test_plan"]
    task_prompt = plan.get("task_prompt", "")
    rubric      = plan.get("rubric", "quality, relevance, depth")
    threshold   = int(plan.get("pass_threshold", 7))

    if not task_prompt:
        return {"error": "no task prompt", "rating": 0, "confirmed": False}

    try:
        from brain.utils.generate_response import generate_response, llm_ok
        sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
        identity = sm.get("identity_story", "an evolving reflective AI")
        task_with_identity = f"You are Orrin — {identity}.\n\n{task_prompt}"
        output = llm_ok(generate_response(task_with_identity, caller="experimentation/capability_task"), "experimentation") or ""
    except Exception as e:
        return {"error": str(e), "rating": 0, "confirmed": False}

    # Rate the output
    rate_prompt = (
        f"Rate this response against the rubric on a scale of 0-10.\n\n"
        f"Task: {task_prompt[:200]}\n\n"
        f"Response:\n{output[:600]}\n\n"
        f"Rubric: {rubric}\n\n"
        f"Reply as JSON: {{\"rating\": 0-10, \"rationale\": \"one sentence\"}}"
    )
    try:
        rate_raw = llm_ok(generate_response(rate_prompt, caller="experimentation/capability_rate"), "experimentation") or ""
        m = re.search(r'\{.*\}', rate_raw, re.DOTALL)
        rating = 5
        rationale = ""
        if m:
            data = json.loads(m.group(0))
            rating = int(data.get("rating", 5))
            rationale = str(data.get("rationale", "")).strip()
    except Exception:
        rating = 5
        rationale = "rating parse failed"

    confirmed = rating >= threshold

    return {
        "task_output": output[:300],
        "rating": rating,
        "rationale": rationale,
        "threshold": threshold,
        "confirmed": confirmed,
        "refuted": not confirmed and rating <= threshold - 3,
        "inconclusive": not confirmed and rating > threshold - 3,
    }


def _run_test(experiment: Dict, context: Dict[str, Any]) -> bool:
    """Dispatch to the right test runner. Updates experiment["test_results"] in-place."""
    htype = experiment.get("type", "behavioral")
    try:
        if htype == "behavioral":
            results = _run_behavioral_test(experiment, context)
        elif htype == "pattern":
            results = _run_pattern_test(experiment, context)
        else:
            results = _run_capability_test(experiment, context)
    except Exception as e:
        log_private(f"[experimentation] test execution error: {e}")
        results = {"error": str(e)}

    experiment["test_results"] = results
    experiment["status"] = "testing"
    experiment["tested_at"] = now_iso_z()
    return bool(results) and "error" not in results


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
        emotion="exploration_drive" if confirmed else ("surprise" if refuted else "stagnation_signal"),
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
