# brain/symbolic/inference.py
#
# Symbolic inference over the world model.
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────
# Johnson-Laird Mental Models (1983):
#   People reason by building structural analogue models and querying
#   their structure directly — not by manipulating logical formulae.
#   Implemented here as forward-chaining over the relation graph.
#
# Description Logic / Subsumption (Baader et al. 2003):
#   is_a defines a subsumption hierarchy. X is_a Y → X inherits all
#   of Y's relations (properties, causes, dependencies) at discounted
#   confidence (inheritance discount = 0.80).
#
# Transitivity (classical logic):
#   leads_to, causes, depends_on are transitive over 2-hop chains.
#   Confidence degrades by 0.70 per hop (uncertainty compounds).
#
# Gärdenfors Conceptual Spaces (2000):
#   Concepts occupy regions in a quality-dimension space. Similarity
#   between two entities is the Jaccard index over their shared
#   relations — graded membership, not binary.
#   Prototype = most-mentioned entity in a class (highest mention_count).
#
# Forward chaining limit:
#   We stop at depth 2 to avoid combinatorial explosion and spurious
#   long-chain inferences (Johnson-Laird: people rarely chain >2 steps
#   spontaneously without prompting).
#
from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

_INHERIT_DISCOUNT   = 0.80  # confidence multiplier per is_a hop
_TRANSITIVE_DECAY   = 0.70  # confidence multiplier per transitive hop
_MIN_INFER_CONF     = 0.25  # below this, don't surface the inference
_TRANSITIVE_PREDS   = {"leads_to", "causes", "depends_on", "affects", "improves"}
_INHERIT_PREDS      = {"has", "leads_to", "causes", "depends_on", "affects"}
_MAX_INFERENCES     = 40    # cap to avoid bloat


# ─── helpers ──────────────────────────────────────────────────────


def _rel_key(subj: str, pred: str, obj: str) -> Tuple[str, str, str]:
    return (subj.lower(), pred.lower(), obj.lower())


def _build_index(relations: List[Dict]) -> Dict[str, List[Dict]]:
    """Index relations by subject for fast lookup."""
    idx: Dict[str, List[Dict]] = {}
    for r in relations:
        s = r.get("subject", "").lower()
        if s:
            idx.setdefault(s, []).append(r)
    return idx


# ─── subsumption / inheritance ────────────────────────────────────


def _inherit_from_supertype(
    entity: str,
    relations: List[Dict],
    subj_index: Dict[str, List[Dict]],
    existing_keys: Set[Tuple],
) -> List[Dict]:
    """
    Description Logic: X is_a Y → X inherits Y's _INHERIT_PREDS relations.
    Returns new inferred relations not already in the graph.
    """
    inferred = []
    entity_l = entity.lower()

    # Find all supertypes: X is_a ?
    supertypes = [
        r["object"].lower()
        for r in relations
        if r.get("subject", "").lower() == entity_l
        and r.get("predicate") == "is_a"
        and r.get("confidence", 0) >= 0.35
    ]

    for supertype in supertypes:
        for r in subj_index.get(supertype, []):
            if r.get("predicate") not in _INHERIT_PREDS:
                continue
            new_conf = round(
                r.get("confidence", 0.5) * _INHERIT_DISCOUNT, 3
            )
            if new_conf < _MIN_INFER_CONF:
                continue
            key = _rel_key(entity_l, r["predicate"], r.get("object", ""))
            if key not in existing_keys:
                inferred.append({
                    "subject":    entity_l,
                    "predicate":  r["predicate"],
                    "object":     r.get("object", ""),
                    "confidence": new_conf,
                    "inferred":   True,
                    "basis":      f"is_a {supertype} (description-logic inheritance)",
                })
                existing_keys.add(key)

    return inferred


# ─── transitivity ────────────────────────────────────────────────


def _transitivity_chain(
    relations: List[Dict],
    subj_index: Dict[str, List[Dict]],
    existing_keys: Set[Tuple],
) -> List[Dict]:
    """
    Classical transitivity over 2-hop chains for _TRANSITIVE_PREDS.
    X →P Y, Y →P Z  ⟹  X →P Z  (confidence decayed by _TRANSITIVE_DECAY)
    Stops at depth 2 — Johnson-Laird: >2 hops exceed working memory span.
    """
    inferred = []
    for r1 in relations:
        if r1.get("predicate") not in _TRANSITIVE_PREDS:
            continue
        if r1.get("confidence", 0) < 0.30:
            continue
        mid = r1.get("object", "").lower()
        pred = r1.get("predicate")
        for r2 in subj_index.get(mid, []):
            if r2.get("predicate") != pred:
                continue
            if r2.get("confidence", 0) < 0.30:
                continue
            new_conf = round(
                r1.get("confidence", 0.5) * r2.get("confidence", 0.5) * _TRANSITIVE_DECAY,
                3,
            )
            if new_conf < _MIN_INFER_CONF:
                continue
            subj = r1.get("subject", "").lower()
            obj  = r2.get("object", "").lower()
            if subj == obj:
                continue  # no self-loops
            key = _rel_key(subj, pred, obj)
            if key not in existing_keys:
                inferred.append({
                    "subject":    subj,
                    "predicate":  pred,
                    "object":     obj,
                    "confidence": new_conf,
                    "inferred":   True,
                    "basis":      f"transitivity via {mid} ({pred})",
                })
                existing_keys.add(key)

    return inferred


# ─── Gärdenfors similarity ────────────────────────────────────────


def _conceptual_similarity(
    entity_a: str,
    entity_b: str,
    relations: List[Dict],
    entities: Dict,
) -> float:
    """
    Gärdenfors (2000): similarity = Jaccard index over shared (predicate, object) pairs.
    Two entities are similar if they share relations in quality-dimension space.
    """
    a_l, b_l = entity_a.lower(), entity_b.lower()

    def rel_set(e: str) -> Set[Tuple[str, str]]:
        return {
            (r.get("predicate", ""), r.get("object", ""))
            for r in relations
            if r.get("subject", "").lower() == e
            and r.get("confidence", 0) >= 0.30
        }

    sa, sb = rel_set(a_l), rel_set(b_l)
    union = sa | sb
    if not union:
        return 0.0
    intersection = sa & sb
    return round(len(intersection) / len(union), 3)


def find_similar_entities(
    entity: str,
    model: Dict,
    *,
    top_k: int = 5,
    min_similarity: float = 0.10,
) -> List[Dict]:
    """
    Gärdenfors Conceptual Spaces: return the top_k most similar entities
    to `entity` based on shared relation structure (Jaccard index).
    """
    relations = model.get("relations", [])
    entities  = model.get("entities", {})
    entity_l  = entity.lower()

    results = []
    for key in entities:
        if key == entity_l:
            continue
        sim = _conceptual_similarity(entity_l, key, relations, entities)
        if sim >= min_similarity:
            results.append({"entity": key, "similarity": sim})

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


# ─── schema retrieval (Johnson-Laird) ─────────────────────────────


def get_entity_schema(entity: str, model: Dict) -> Dict:
    """
    Johnson-Laird Mental Models: query the world model for all structural
    properties of an entity — direct relations + inherited from supertypes.
    Returns a schema dict: {direct: [...], inherited: [...], similar: [...]}.
    """
    relations = model.get("relations", [])
    entities  = model.get("entities", {})
    entity_l  = entity.lower()
    subj_idx  = _build_index(relations)

    direct = [
        r for r in subj_index_lookup(entity_l, subj_idx)
        if r.get("confidence", 0) >= 0.25
    ]

    existing_keys: Set[Tuple] = {
        _rel_key(r.get("subject",""), r.get("predicate",""), r.get("object",""))
        for r in relations
    }

    inherited = _inherit_from_supertype(entity_l, relations, subj_idx, set(existing_keys))
    similar   = find_similar_entities(entity_l, model, top_k=3)

    entity_meta = entities.get(entity_l, {})

    return {
        "entity":    entity,
        "type":      entity_meta.get("type", "unknown"),
        "confidence": entity_meta.get("confidence", 0.0),
        "direct_relations": direct,
        "inherited_relations": inherited,
        "similar_entities": similar,
    }


def subj_index_lookup(entity: str, subj_idx: Dict) -> List[Dict]:
    return subj_idx.get(entity.lower(), [])


# ─── main entry: forward chaining ─────────────────────────────────


def run_inference(model: Dict) -> List[Dict]:
    """
    Run one pass of forward chaining over the world model:
      1. Description-logic inheritance (is_a subsumption)
      2. Transitivity (leads_to, causes, depends_on)
    Returns list of newly inferred relations (not mutating model).
    Cap at _MAX_INFERENCES to prevent explosion.

    Basis: Johnson-Laird (1983) mental model search, Description Logic
    subsumption (Baader 2003), classical transitivity chains.
    """
    relations = model.get("relations", [])
    entities  = model.get("entities", {})
    subj_idx  = _build_index(relations)

    existing_keys: Set[Tuple] = {
        _rel_key(r.get("subject",""), r.get("predicate",""), r.get("object",""))
        for r in relations
    }

    inferred: List[Dict] = []

    # 1. Inheritance for each known entity
    for entity_key in list(entities.keys()):
        new = _inherit_from_supertype(entity_key, relations, subj_idx, existing_keys)
        inferred.extend(new)
        if len(inferred) >= _MAX_INFERENCES:
            break

    # 2. Transitivity (if budget remains)
    if len(inferred) < _MAX_INFERENCES:
        new = _transitivity_chain(relations, subj_idx, existing_keys)
        inferred.extend(new[: _MAX_INFERENCES - len(inferred)])

    return inferred[:_MAX_INFERENCES]


def infer_and_explain(query: str, model: Dict) -> Optional[str]:
    """
    Given a free-text query, find the best matching inferred relation and
    return a human-readable explanation with its scientific basis.
    Used by query_world_model for richer answers.
    """
    words = set(query.lower().split())
    inferences = run_inference(model)

    best = None
    best_score = 0.0
    for inf in inferences:
        subj_hit = any(w in inf.get("subject", "") for w in words if len(w) > 3)
        obj_hit  = any(w in inf.get("object", "")  for w in words if len(w) > 3)
        if not (subj_hit or obj_hit):
            continue
        score = inf.get("confidence", 0.0) + (0.1 if subj_hit and obj_hit else 0.0)
        if score > best_score:
            best_score = score
            best = inf

    if not best:
        return None

    return (
        f"[inferred] '{best['subject']}' {best['predicate']} '{best['object']}' "
        f"(conf={best['confidence']:.2f}, basis: {best['basis']})"
    )
