# brain/cognition/knowledge_formation.py
#
# Converts metacognitive observations into structured causal knowledge,
# closing the gap between "observation → label" and
# "observation → abstraction → causal relation → prediction → action".
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────────────────
# Mitchell, Keller & Kedar-Cabelli (1986) Explanation-Based Learning:
#   "Learning by Explaining: A Theory of Explanation-Based Learning."
#   Cognitive Science, 10(4), 397–424.
#   The learner constructs a causal explanation for an example, then
#   generalises that explanation into a reusable rule. Storing the
#   explanation (the WHY) is what makes the rule predictive and generalisable.
#   We don't just store "goal_avoidance=True" — we store the mechanism.
#
# Pearl (2000) Causality — "Models, Reasoning, and Inference." Cambridge UP.
#   Knowledge should represent causal structure, not correlational labels.
#   A label says what happened. A causal claim says why, and predicts what
#   will happen under different conditions (counterfactual reasoning).
#
# Friston (2010) Free Energy Principle — "The free-energy principle: A unified
#   brain theory?" Nature Reviews Neuroscience, 11(2), 127–138.
#   An agent maintains a generative model that predicts future states and
#   guides action to minimise prediction error. A label cannot generate
#   predictions; a causal model can.
#
# Tulving (1972, 1983) Episodic → Semantic memory consolidation:
#   "Episodic and semantic memory." In E. Tulving & W. Donaldson (Eds.),
#   Organization of Memory. Academic Press.
#   The brain converts specific episodes (this happened to me at time T)
#   into abstracted semantic knowledge (this class of situation leads to Y).
#   This module implements that conversion step.
#
# Carver & Scheier (1982) Control Systems Theory:
#   Stored knowledge must include recommended_action so the corrective output
#   signal is ready-made, not reconstructed from scratch each cycle.
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from core.runtime_log import get_logger

from typing import Dict, Any, List, Optional

from utils.log import log_activity, log_private
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ─── Pattern templates ────────────────────────────────────────────────────────
# Each entry maps a pattern name to its structured causal model.
# Confidence starts at the template default and rises with hits (Rescorla-Wagner).
#
# Fields:
#   cause         — the driving condition (what's actually happening)
#   effect        — what it produces if unaddressed
#   mechanism     — the cognitive/affective reason this causal link operates
#   prediction    — forward-looking statement about future cycles
#   recommended_action — concrete smallest-step intervention (Carver & Scheier)
#   abstraction_level  — 2 = pattern (not specific event, not yet a principle)
#   conditions    — rule-engine keywords to match for retrieval

_PATTERN_MODELS: Dict[str, Dict] = {
    "rut": {
        "conditions": ["repeated", "function", "cycles", "rut", "stuck"],
        "conclusion": "Repeated execution of the same cognitive function indicates a rut: "
                      "the selected action is no longer reducing the underlying error signal.",
        "causal_claim": {
            "cause":     "habitual function selection without observable outcome change",
            "effect":    "stagnation — error signal remains high, reward drops",
            "mechanism": "Hebbian reinforcement of the dominant path crowds out exploration; "
                         "the bandit over-exploits a locally rewarded action "
                         "(Agrawal & Goyal, 2012: Thompson sampling requires exploration to avoid local optima)",
        },
        "prediction":         "Without intervention, rut deepens over next 5–10 cycles and "
                              "goal progress stalls further.",
        "recommended_action": "Suppress the dominant function for 10–15 cycles; "
                              "inject novelty pressure; select a function from a different "
                              "cognitive category (action vs reflection, internal vs external).",
        "abstraction_level":  2,
    },
    "oscillation": {
        "conditions": ["alternating", "oscillation", "between", "cycles", "unresolved"],
        "conclusion": "Alternation between two functions without resolution indicates an "
                      "unresolved tension that neither function is equipped to dissolve alone.",
        "causal_claim": {
            "cause":     "two competing drives or goals of similar strength, each partially "
                         "satisfied by different functions",
            "effect":    "no net progress on either goal; oscillation persists indefinitely",
            "mechanism": "Action-selection instability: the bandit can't find a stable policy "
                         "because neither function fully resolves the underlying conflict "
                         "(Powers, 1973: competing control loops produce behavioural oscillation)",
        },
        "prediction":         "Oscillation will continue until the underlying tension is "
                              "explicitly named and one function given priority.",
        "recommended_action": "Detect the tension explicitly; create a sub-goal that resolves "
                              "it; or deliberately suppress one of the two functions for a "
                              "full exploration pass.",
        "abstraction_level":  2,
    },
    "goal_avoidance": {
        "conditions": ["goal", "avoidance", "thinking", "not doing", "action_debt", "cycles"],
        "conclusion": "Sustained reflection without goal-directed action predicts continued "
                      "stagnation. Thinking about a goal is not the same as pursuing it.",
        "causal_claim": {
            "cause":     "high uncertainty or task complexity triggers analysis paralysis: "
                         "reflection is cognitively safer than action (Bandura, 1977: "
                         "low self-efficacy predicts avoidance of challenging tasks)",
            "effect":    "action_debt accumulates; goal recedes; impasse_signal rises",
            "mechanism": "Avoidance is negatively reinforced — it temporarily reduces risk_estimate "
                         "without actually reducing the goal gap. The bandit learns to "
                         "select comfortable functions because they avoid the aversive "
                         "experience of potentially failing at the goal.",
        },
        "prediction":         "If action_debt exceeds 8 cycles, the pattern becomes "
                              "self-reinforcing and requires stronger intervention to break.",
        "recommended_action": "Decompose the goal into the smallest executable action — "
                              "one concrete step that takes ≤1 cognitive cycle. Attempt that "
                              "step before any further reflection. Reduce task size, not effort.",
        "abstraction_level":  2,
    },
    "reflection_imbalance": {
        "conditions": ["reflection", "action", "imbalance", "over-processing", "outward"],
        "conclusion": "Excess reflection without outward action indicates the cognitive system "
                      "is generating information it is not using.",
        "causal_claim": {
            "cause":     "high exploration_drive and analytical drive with low action_vs_reflect_bias "
                         "and no committed external goal",
            "effect":    "rich internal state with no environmental coupling; "
                         "knowledge accumulates but is not tested against reality",
            "mechanism": "Situated cognition (Lave, 1988): cognition is embedded in action. "
                         "Reflection that never feeds action is not integrated knowledge — "
                         "it is unverified belief. Without grounding in outcome, "
                         "confidence calibration degrades.",
        },
        "prediction":         "Continued reflection-only cycles will produce increasingly "
                              "abstract beliefs with lower predictive validity, as there is "
                              "no error signal from reality to correct them.",
        "recommended_action": "Force at least one external action per 3 reflective cycles. "
                              "Preferred: look_outward, seek_novelty, or any goal-directed "
                              "function. The action does not need to be large — any "
                              "environmental coupling resets the loop.",
        "abstraction_level":  2,
    },
    "emotional_stagnation": {
        "conditions": ["dominant", "emotion", "stagnation", "consecutive", "cycles"],
        "conclusion": "A dominant affect signal persisting across many cycles without "
                      "environmental change indicates an attractor state rather than "
                      "genuine emotional response to current conditions.",
        "causal_claim": {
            "cause":     "homeostatic drift: the affect system has settled at a stable "
                         "attractor value rather than tracking external events",
            "effect":    "cognitive bias — all new information is processed through the "
                         "lens of the dominant affect, distorting salience and selection",
            "mechanism": "Russell & Barrett (2000) core affect: affect should vary with "
                         "events. Absence of variation means the signal is decoupled from "
                         "its environmental causes — the thermostat is stuck.",
        },
        "prediction":         "Decision quality degrades as affect-derived scores become "
                              "unreliable predictors of actual outcome value.",
        "recommended_action": "Seek novelty to introduce variability; attempt regulation "
                              "strategy (Gross, 1998); if impasse_signal/risk_estimate is the "
                              "attractor, check whether an unresolved goal is driving it.",
        "abstraction_level":  2,
    },
}


# ─── Pattern classifier ───────────────────────────────────────────────────────

def _classify_observation(observation: str) -> Optional[str]:
    """Map a metacognitive observation string to one of the pattern keys."""
    obs = observation.lower()
    if "rut" in obs and "oscillat" not in obs:
        return "rut"
    if "oscillat" in obs or "alternating" in obs:
        return "oscillation"
    if "avoidance" in obs or "thinking but not doing" in obs or "action_debt" in obs:
        return "goal_avoidance"
    if "imbalance" in obs or "over-processing" in obs:
        return "reflection_imbalance"
    if "stagnation" in obs and "emotion" in obs:
        return "emotional_stagnation"
    return None


# ─── Causal query ─────────────────────────────────────────────────────────────

def _query_causal_context(pattern_key: str) -> List[str]:
    """
    Query the causal graph for existing evidence about this pattern.
    Returns a list of supporting evidence strings for the confidence estimate.
    """
    try:
        from symbolic.causal_graph import get_causes, get_effects
        causes  = get_causes(pattern_key)[:2]
        effects = get_effects(pattern_key)[:2]
        evidence = []
        for e in causes:
            evidence.append(f"causal: '{e['cause']}' leads to {pattern_key} "
                            f"(score={e.get('causal_score', 0):.2f}, n={e.get('evidence_count', 0)})")
        for e in effects:
            evidence.append(f"causal: {pattern_key} leads to '{e['effect']}' "
                            f"(score={e.get('causal_score', 0):.2f}, n={e.get('evidence_count', 0)})")
        return evidence
    except Exception:
        return []


# ─── Confidence estimator ─────────────────────────────────────────────────────

def _estimate_confidence(pattern_key: str, causal_evidence: List[str], hits: int) -> float:
    """
    Estimate confidence using Rescorla-Wagner style accumulation:
    base from template, + causal graph evidence, + prior hit count.
    """
    base = 0.60
    causal_boost = min(0.20, len(causal_evidence) * 0.05)
    hit_boost = min(0.15, hits * 0.01)
    return round(min(0.92, base + causal_boost + hit_boost), 3)


# ─── Main entry ───────────────────────────────────────────────────────────────

def form_structured_knowledge(
    observation: str,
    context: Dict[str, Any],
) -> Optional[Dict]:
    """
    Run the full chain for a single metacognitive observation:
      1. Classify what type of pattern this is
      2. Retrieve the causal model template for that pattern
      3. Query the causal graph for supporting evidence
      4. Estimate confidence from evidence + prior hits
      5. Write a structured rule to the rule engine (not just prose to WM)
      6. Feed the causal claim back into the causal graph

    Returns the created/updated rule, or None if the observation couldn't be
    mapped to a known pattern.

    Mitchell et al. (1986) EBL: store the explanation, not the surface outcome.
    Tulving (1972): convert episode → semantic, structured, predictive knowledge.
    """
    pattern_key = _classify_observation(observation)
    if not pattern_key:
        return None

    template = _PATTERN_MODELS.get(pattern_key)
    if not template:
        return None

    causal_evidence = _query_causal_context(pattern_key)

    # Match against existing rules BEFORE creating (FINDINGS 2026-06-12 §3.4: the
    # same goal_avoidance rule was "formed" 349× — the old pattern_key-in-conclusion
    # match never hit, so every call re-ran the full formation chain). The
    # template's causal claim is the stable identity of a pattern's rule.
    existing: List[Dict] = []
    prior_hits = 0
    try:
        from symbolic.rule_engine import get_all_rules
        _claim = template["causal_claim"]
        existing = [r for r in get_all_rules()
                    if r.get("source") == "knowledge_formation"
                    and (r.get("causal_claim") == _claim
                         or pattern_key in r.get("conclusion", "").lower())]
        prior_hits = sum(r.get("hits", 0) for r in existing)
    except Exception as _e:
        record_failure("knowledge_formation.form_structured_knowledge", _e)

    confidence = _estimate_confidence(pattern_key, causal_evidence, prior_hits)

    if existing:
        # Re-observation of a known pattern reinforces the existing rule — it
        # does not re-form it (no duplicate causal-graph confirmation, no
        # "rule formed" log spam).
        rule = existing[0]
        try:
            from symbolic.rule_engine import reinforce_rule
            rule = reinforce_rule(rule["id"], confidence=confidence) or rule
        except Exception as _e:
            record_failure("knowledge_formation.form_structured_knowledge.reinforce", _e)
        log_private(
            f"[knowledge_formation] Reinforced existing rule '{rule.get('id')}' for "
            f"'{pattern_key}' (conf={rule.get('confidence', confidence):.2f}, "
            f"hits={rule.get('hits', prior_hits)})"
        )
        return rule

    # Enrich the conclusion with evidence summary
    conclusion = template["conclusion"]
    if causal_evidence:
        conclusion += f" [Evidence: {'; '.join(causal_evidence[:2])}]"

    # Write the structured rule — this is the EBL output
    try:
        from symbolic.rule_engine import add_rule
        rule = add_rule(
            conditions=template["conditions"],
            conclusion=conclusion[:500],
            confidence=confidence,
            source="knowledge_formation",
            causal_claim=template["causal_claim"],
            prediction=template["prediction"],
            recommended_action=template["recommended_action"],
            abstraction_level=template["abstraction_level"],
        )
    except Exception as e:
        log_private(f"[knowledge_formation] rule write failed: {e}")
        return None

    # Feed causal claim back into the causal graph so it accumulates evidence
    try:
        from symbolic.causal_graph import update_edge
        cc = template["causal_claim"]
        update_edge(
            cc["cause"][:80], cc["effect"][:80],
            confirmed=True, source="knowledge_formation",
        )
    except Exception as _e:
        record_failure("knowledge_formation.form_structured_knowledge.2", _e)

    log_activity(
        f"[knowledge_formation] Structured rule formed for '{pattern_key}' "
        f"(conf={confidence:.2f}, prior_hits={prior_hits}, "
        f"causal_evidence={len(causal_evidence)})"
    )
    return rule


def form_from_observations(
    observations: List[str],
    context: Dict[str, Any],
) -> List[Dict]:
    """
    Process a list of metacognitive observations and form structured knowledge
    for each one that can be classified.
    Called from metacog_flush after apply_behavioral_adaptations.
    """
    formed = []
    for obs in observations:
        rule = form_structured_knowledge(obs, context)
        if rule:
            formed.append(rule)
    return formed


def get_recommendation_for_pattern(pattern_key: str) -> Optional[str]:
    """
    Return the recommended_action string for a named pattern.
    Used by planning and goal-pursuit functions to get concrete next steps.
    """
    template = _PATTERN_MODELS.get(pattern_key)
    if not template:
        # Check the rule engine for a stored rule
        try:
            from symbolic.rule_engine import get_all_rules
            rules = [r for r in get_all_rules()
                     if r.get("source") == "knowledge_formation"
                     and pattern_key in r.get("conclusion", "").lower()
                     and r.get("recommended_action")]
            if rules:
                best = max(rules, key=lambda r: r.get("confidence", 0))
                return best["recommended_action"]
        except Exception as _e:
            record_failure("knowledge_formation.get_recommendation_for_pattern", _e)
        return None
    return template.get("recommended_action")
