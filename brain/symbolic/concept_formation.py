# brain/symbolic/concept_formation.py
# Concept formation: turn clusters of rules into named higher-level abstractions.
#
# A "concept" is a named, typed abstraction over a cluster of rules that share
# a common theme.  Concepts bridge the gap between raw rules ("when X then Y")
# and knowledge graph entities ("exploration_drive: concept").
#
# Formation algorithm:
#   1. Cluster rules by condition-token Jaccard (reuses rule_abstraction logic).
#   2. Name the concept from the cluster's dominant condition tokens.
#   3. Classify the concept type (PROCESS | STATE | RELATIONSHIP | PROPERTY | PRINCIPLE).
#   4. Write a one-sentence definition by composing the most-central conclusion
#      and the shared conditions.
#   5. Add the concept as a node in the knowledge graph (type="concept").
#   6. Link each member rule to the concept via a "part_of" relation.
#   7. Store the concept record in data/symbolic_concepts.json.
#
# Runs at most once per 8h (concept formation is slower than rule abstraction).
# Wire into dream_cycle every 2nd cycle.
from __future__ import annotations
from core.runtime_log import get_logger

import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, FrozenSet, List, Optional, Set

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

CONCEPTS_SYMBOLIC_FILE = DATA_DIR / "symbolic_concepts.json"

_CLUSTER_THRESH  = 0.35   # slightly looser than rule_abstraction
_MIN_CLUSTER     = 3
_MAX_CONCEPTS    = 30
_COOLDOWN_S      = 8 * 3600
_last_run: float = 0.0

# Concept type vocabulary — classified from dominant condition tokens
_TYPE_SEEDS: Dict[str, List[str]] = {
    "PROCESS":      ["process", "step", "cycle", "loop", "run", "execute", "flow", "pipeline"],
    "STATE":        ["state", "mode", "status", "condition", "level", "phase", "stage"],
    "RELATIONSHIP": ["relation", "link", "connect", "between", "cause", "effect", "depend"],
    "PROPERTY":     ["quality", "value", "score", "measure", "ratio", "confidence", "rate"],
    "PRINCIPLE":    ["rule", "principle", "always", "never", "prefer", "avoid", "ensure"],
}

_STOPWORDS: Set[str] = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
    "from","is","are","was","were","be","been","have","has","had","do","does",
    "did","will","would","could","should","may","might","this","that","i","you",
}


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return [w for w in words if len(w) > 2 and w not in _STOPWORDS]


def _dominant_tokens(cluster: List[Dict]) -> List[str]:
    counts: Counter = Counter()
    for rule in cluster:
        for c in (rule.get("conditions") or []):
            counts.update(_tokenize(c))
    return [tok for tok, _ in counts.most_common(6)]


def _classify_type(dominant: List[str]) -> str:
    dom_set = set(dominant)
    best_type, best_count = "PRINCIPLE", 0
    for ctype, seeds in _TYPE_SEEDS.items():
        count = len(dom_set & set(seeds))
        if count > best_count:
            best_count, best_type = count, ctype
    return best_type


def _concept_name(dominant: List[str]) -> str:
    """Two or three dominant tokens → title-cased concept name."""
    return "_".join(dominant[:3]).replace("-", "_")


def _concept_definition(conditions: List[str], conclusion: str) -> str:
    cond_str = ", ".join(conditions[:4]) if conditions else "various factors"
    return f"When {cond_str}: {conclusion[:150]}"


# ─── Clustering (mirrors rule_abstraction, tuned for concept level) ───────────

def _cluster_rules_for_concepts(rules: List[Dict]) -> List[List[Dict]]:
    eligible = [r for r in rules
                if r.get("conditions") and r.get("source") not in ("tombstoned",)]
    tmap: Dict[str, FrozenSet] = {}
    for r in eligible:
        words: Set[str] = set()
        for c in (r.get("conditions") or []):
            words.update(w for w in _tokenize(c) if len(w) > 3)
        tmap[r["id"]] = frozenset(words)

    def jaccard(a, b):
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    assigned: Set[str] = set()
    clusters: List[List[Dict]] = []
    for seed in eligible:
        if seed["id"] in assigned:
            continue
        cluster = [seed]
        assigned.add(seed["id"])
        for candidate in eligible:
            if candidate["id"] in assigned:
                continue
            if jaccard(tmap[seed["id"]], tmap[candidate["id"]]) >= _CLUSTER_THRESH:
                cluster.append(candidate)
                assigned.add(candidate["id"])
        if len(cluster) >= _MIN_CLUSTER:
            clusters.append(cluster)
        if len(clusters) >= _MAX_CONCEPTS:
            break
    return clusters


# ─── Main entry point ─────────────────────────────────────────────────────────

def form_concepts(*, force: bool = False) -> Dict:
    """
    Cluster rules into named concepts and register them in the knowledge graph.
    Returns summary dict.
    """
    global _last_run
    now = time.time()
    if not force and (now - _last_run) < _COOLDOWN_S:
        return {"skipped": True, "reason": "cooldown"}
    _last_run = now

    from symbolic.rule_engine import get_all_rules
    rules = get_all_rules()
    if not rules:
        return {"concepts_formed": 0}

    clusters = _cluster_rules_for_concepts(rules)
    existing = load_json(CONCEPTS_SYMBOLIC_FILE, default_type=list) or []
    existing_names = {c["name"] for c in existing}

    formed = 0
    for cluster in clusters:
        dominant = _dominant_tokens(cluster)
        if not dominant:
            continue
        name = _concept_name(dominant)
        if name in existing_names:
            continue

        ctype = _classify_type(dominant)
        # Pull best conditions and conclusion from cluster
        from symbolic.rule_abstraction import _parent_conditions, _parent_conclusion
        conditions = _parent_conditions(cluster)
        conclusion = _parent_conclusion(cluster)
        definition = _concept_definition(conditions, conclusion)

        concept = {
            "name":        name,
            "type":        ctype,
            "definition":  definition,
            "conditions":  conditions,
            "member_rules": [r["id"] for r in cluster],
            "dominant_tokens": dominant,
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }
        existing.append(concept)
        existing_names.add(name)
        formed += 1

        # Register in knowledge graph
        _register_in_kg(concept)
        log_activity(f"[concept_formation] Concept '{name}' ({ctype}): {definition[:80]}")

    save_json(CONCEPTS_SYMBOLIC_FILE, existing[-_MAX_CONCEPTS:])
    log_activity(f"[concept_formation] {formed} concept(s) formed from {len(clusters)} cluster(s).")
    return {"concepts_formed": formed, "total_concepts": len(existing)}


def _register_in_kg(concept: Dict) -> None:
    try:
        from cognition.knowledge_graph import add_entity, add_relation
        add_entity(
            name=concept["name"],
            entity_type="concept",
            tags=concept.get("dominant_tokens", [])[:6],
            properties={
                "definition": concept["definition"][:200],
                "concept_type": concept["type"],
                "member_count": len(concept.get("member_rules", [])),
            },
            confidence=0.80,
        )
        # Link each member rule concept to the parent concept via "part_of"
        for rule_id in concept.get("member_rules", [])[:5]:
            try:
                add_relation(
                    source=rule_id,
                    relation="part_of",
                    target=concept["name"],
                )
            except Exception as _e:
                record_failure("concept_formation._register_in_kg", _e)
    except Exception as e:
        log_activity(f"[concept_formation] KG registration failed: {e}")


def get_concepts() -> List[Dict]:
    return load_json(CONCEPTS_SYMBOLIC_FILE, default_type=list) or []


def get_concept_for_query(query: str) -> Optional[Dict]:
    """Return the most relevant concept for a query string."""
    concepts = get_concepts()
    if not concepts:
        return None
    q_toks = set(_tokenize(query))
    best_c, best_score = None, 0.0
    for c in concepts:
        dom = set(c.get("dominant_tokens") or [])
        if not dom:
            continue
        score = len(q_toks & dom) / len(q_toks | dom) if (q_toks | dom) else 0.0
        if score > best_score:
            best_score, best_c = score, c
    return best_c if best_score >= 0.15 else None
