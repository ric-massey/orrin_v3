# brain/symbolic/symbolic_search.py
# BFS / beam search over the knowledge graph + rule engine.
#
# Given a query, explore the knowledge graph outward from the most relevant
# entities, collecting facts and rule-based conclusions along the way.
# Returns a structured answer if the graph coverage is sufficient, else None.
#
# This replaces "ask the LLM what it knows" for questions that are answerable
# from Orrin's local symbolic world model.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Dict, List, Optional, Set

from brain.utils.log import log_activity
from brain.symbolic.rule_engine import match_all
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_MAX_DEPTH   = 3    # BFS hops from seed entities
_BEAM_WIDTH  = 8    # max entities kept per BFS level
_MIN_CONF    = 0.35  # minimum entity confidence to include


def search(query: str, *, context: Optional[Dict] = None) -> Optional[str]:
    """
    Perform symbolic BFS search over the knowledge graph for `query`.
    Returns a compact answer string if sufficient coverage found, else None.
    """
    try:
        from brain.cognition.knowledge_graph import query_relevant, get_neighbors
    except Exception as e:
        log_activity(f"[symbolic_search] kg import failed: {e}")
        return None

    # Seed: top-N entities matching the query
    seeds = query_relevant(query, limit=4)
    seeds = [e for e in seeds if e.get("confidence", 1.0) >= _MIN_CONF]
    if not seeds:
        return None

    visited: Set[str] = set()
    frontier: List[Dict] = seeds
    facts: List[str] = []

    for depth in range(_MAX_DEPTH):
        next_frontier: List[Dict] = []
        for entity in frontier[:_BEAM_WIDTH]:
            name = entity.get("name", "")
            if name in visited:
                continue
            visited.add(name)

            # Collect entity facts
            etype = entity.get("type", "")
            props = entity.get("properties") or {}
            tags = entity.get("tags") or []

            fact = f"{name} ({etype})"
            if props:
                prop_str = "; ".join(f"{k}={v}" for k, v in list(props.items())[:4])
                fact += f": {prop_str}"
            if tags:
                fact += f" [{', '.join(tags[:5])}]"
            facts.append(fact)

            # Follow relations one hop out
            try:
                neighbors = get_neighbors(name) or []
                for nb in neighbors[:4]:
                    target_name = nb.get("target", nb.get("name", ""))
                    if target_name and target_name not in visited:
                        next_frontier.append({"name": target_name, "type": "unknown",
                                              "properties": {}, "tags": [], "confidence": 0.5})
            except Exception as _e:
                record_failure("symbolic_search.search", _e)

        frontier = next_frontier
        if not frontier:
            break

    if not facts:
        return None

    # Apply rule engine to the collected facts + query
    combined_text = query + " " + " ".join(facts)
    rules_matched = match_all(combined_text, threshold=0.3)
    rule_conclusions = [r["conclusion"] for r, _ in rules_matched[:3]]

    # Build compact answer
    answer_parts = [f"[symbolic] {f}" for f in facts[:6]]
    answer_parts += [f"[rule] {c}" for c in rule_conclusions]

    if not answer_parts:
        return None

    log_activity(f"[symbolic_search] {len(facts)} facts + {len(rule_conclusions)} rules for '{query[:60]}'")
    return "\n".join(answer_parts)


def can_answer_symbolically(query: str, *, min_facts: int = 2) -> bool:
    """Quick check: does the knowledge graph have enough coverage for this query?"""
    try:
        from brain.cognition.knowledge_graph import query_relevant
        seeds = query_relevant(query, limit=min_facts)
        seeds = [e for e in seeds if e.get("confidence", 1.0) >= _MIN_CONF]
        return len(seeds) >= min_facts
    except Exception:
        return False
