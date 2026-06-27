# brain/cognition/experiment_tests.py
#
# Experiment test design + execution for experimentation.py
# (CODEBASE_CLEANUP_PLAN 4.5C), lifted verbatim to bring that module under the
# 600-line soft limit. Phase 2 (design a behavioral / pattern / capability test
# for a hypothesis, incl. the simulated-selection context builder) and Phase 3
# (run that test and return the confirmed / refuted / inconclusive verdict).
# experimentation.py re-imports _design_test / _run_test for its public cycle.
from __future__ import annotations

import json
import re
from typing import Any, Dict

from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_private
from brain.paths import (
    COGNITIVE_FUNCTIONS_LIST_FILE, WORKING_MEMORY_FILE,
    COGNITION_HISTORY_FILE, SELF_MODEL_FILE,
)
from brain.utils.timeutils import now_iso_z

# ─── Test thresholds + function classification ───────────────────────────────
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
    except Exception as exc:  # test design failed — record, no design
        record_failure("experiment_tests._design_behavioral_test", exc)
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
    except Exception as exc:  # test design failed — record, no design
        record_failure("experiment_tests._design_pattern_test", exc)
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
    except Exception as exc:  # test design failed — record, no design
        record_failure("experiment_tests._design_capability_test", exc)
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
        record_failure("experiment_tests.run_behavioral", e)
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
        record_failure("experiment_tests.run_capability", e)
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
