# brain/symbolic/symbolic_fluency.py
# Natural language generation from symbolic structures.
#
# When the reasoning_router resolves a query without LLM (rule, analogy,
# symbolic search), this module converts the bare structured result into
# a coherent, Orrin-voiced response rather than returning raw rule text.
#
# generate_symbolic_response(router_result, query, context) is called from
# generate_response.py when source in {"rule", "analogy", "symbolic_search"}.
#
# Output style: concise and direct; includes the source of confidence;
# never sounds robotic ("According to rule R-42…"); sounds like Orrin reasoning.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
from typing import Dict, List, Optional
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)


# ─── Main entry point ─────────────────────────────────────────────────────────

def generate_symbolic_response(
    router_result: Dict,
    query: str,
    context: Optional[Dict] = None,
) -> str:
    """
    Convert a resolved router_result into natural language.
    Returns a string ready to send to the user (or to cache as a symbolic answer).
    """
    source  = router_result.get("source", "")
    answer  = (router_result.get("answer") or "").strip()
    rule_id = router_result.get("rule_id", "")

    if source == "rule":
        raw = _explain_from_rule(query, answer, rule_id, router_result, context)
    elif source == "analogy":
        raw = _explain_from_analogy(query, answer, context)
    elif source in ("symbolic_search", "causal_graph"):
        raw = _explain_from_search(query, answer, context)
    else:
        raw = answer

    # Enrich with dictionary definitions for any domain terms found in the response
    try:
        from brain.symbolic.symbolic_dictionary import enrich_explanation as _enrich
        raw = _enrich(raw)
    except Exception as _e:
        record_failure("symbolic_fluency.generate_symbolic_response", _e)

    return raw


# ─── Per-source renderers ─────────────────────────────────────────────────────

def _explain_from_rule(
    query: str,
    answer: str,
    rule_id: str,
    router_result: Dict,
    context: Optional[Dict],
) -> str:
    """
    Render a rule-resolved answer with:
      - The conclusion in plain language
      - A confidence qualifier based on rule.confidence
      - An optional causal explanation if the graph has one
    """
    # Fetch rule confidence for qualifier
    conf_qualifier = ""
    try:
        from brain.symbolic.rule_engine import get_all_rules
        for r in get_all_rules():
            if r.get("id") == rule_id:
                conf = float(r.get("confidence", 0.75))
                if conf >= 0.85:
                    conf_qualifier = "I'm quite confident: "
                elif conf >= 0.65:
                    conf_qualifier = "Based on what I know: "
                else:
                    conf_qualifier = "My best read, though uncertain: "
                break
    except Exception:
        conf_qualifier = ""

    # Try causal enrichment
    causal_note = ""
    try:
        from brain.symbolic.causal_graph import causal_explanation
        causal_raw = causal_explanation(query)
        if causal_raw:
            # Extract the cause→effect text from the bracketed format
            m = re.search(r"'(.+?)' causes '(.+?)'", causal_raw)
            if m:
                causal_note = f" This traces back to the link between {m.group(1)} and {m.group(2)}."
    except Exception as _e:
        record_failure("symbolic_fluency._explain_from_rule", _e)

    # Check for conflicts that fell through — soften the tone
    if router_result.get("conflict"):
        return (
            f"There's some tension in what I know here. "
            f"{answer}{causal_note}"
        )

    return f"{conf_qualifier}{answer}{causal_note}"


def _explain_from_analogy(
    query: str,
    answer: str,
    context: Optional[Dict],
) -> str:
    """
    Render an analogy-resolved answer, framing it as a transfer from a past case.
    """
    # The answer from analogy_engine is already the mapped_solution text.
    # Add a framing sentence that signals it's analogical reasoning.
    intro = _analogy_intro(query)
    return f"{intro} {answer}"


def _explain_from_search(
    query: str,
    answer: str,
    context: Optional[Dict],
) -> str:
    """
    Render a knowledge-graph BFS answer, noting the graph as the source
    and enriching with any causal context.
    """
    causal_note = ""
    try:
        from brain.symbolic.causal_graph import causal_explanation
        causal_raw = causal_explanation(query)
        if causal_raw:
            m = re.search(r"'(.+?)' causes '(.+?)'", causal_raw)
            if m:
                causal_note = f" Causally, {m.group(1)} tends to drive {m.group(2)}."
    except Exception as _e:
        record_failure("symbolic_fluency._explain_from_search", _e)

    return f"{answer}{causal_note}"


# ─── Standalone explanation helpers (importable by other modules) ─────────────

def explain_rule(rule: Dict, query: str = "") -> str:
    """
    Turn a rule dict into a single readable sentence.
    Useful for surfacing rule content in WM or dream logs.
    """
    conditions = rule.get("conditions") or []
    conclusion = rule.get("conclusion", "")
    conf       = float(rule.get("confidence", 0.75))

    cond_text = _join_conditions(conditions)
    conf_pct  = int(conf * 100)

    if cond_text:
        return f"When {cond_text}, then {conclusion} (confidence: {conf_pct}%)."
    return f"{conclusion} (confidence: {conf_pct}%)."


def explain_causal_chain(query: str, max_hops: int = 3) -> str:
    """
    Build a multi-hop causal narrative for a query.
    Follows cause→effect chains up to max_hops deep.
    """
    try:
        from brain.symbolic.causal_graph import get_causes, get_effects
    except Exception:
        return ""

    effects = get_effects(query)
    if not effects:
        causes = get_causes(query)
        if not causes:
            return ""
        best = causes[0]
        return f"{best['cause']} causes {query} (causal score: {best['causal_score']:.2f})."

    best = effects[0]
    chain = [f"{best['cause']} → {best['effect']}"]
    next_query = best["effect"]
    for _ in range(max_hops - 1):
        downstream = get_effects(next_query)
        if not downstream:
            break
        d = downstream[0]
        chain.append(d["effect"])
        next_query = d["effect"]

    return "Causal chain: " + " → ".join(chain) + "."


def explain_analogy(analogy: Dict, query: str = "") -> str:
    """
    Convert an analogy result (from analogy_engine.find_analogues) into prose.
    """
    score       = analogy.get("score", 0)
    solution    = analogy.get("mapped_solution", "")
    intent_type = analogy.get("intent_type", "")
    intro       = _analogy_intro(query)
    return f"{intro} ({intent_type}, similarity {score:.0%}): {solution}"


# ─── Private utilities ────────────────────────────────────────────────────────

def _join_conditions(conditions: List) -> str:
    if not conditions:
        return ""
    parts = [str(c).strip() for c in conditions if str(c).strip()]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _analogy_intro(query: str) -> str:
    words = query.lower().split()
    if any(w in words for w in ("how", "why", "explain")):
        return "A similar situation suggests"
    if any(w in words for w in ("what", "is", "are")):
        return "By analogy"
    return "Drawing from a past case"
