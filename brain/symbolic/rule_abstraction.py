# brain/symbolic/rule_abstraction.py
# Rule Hierarchy / Abstraction Layer.
#
# Periodically clusters the rule set by condition-set similarity and merges
# similar rules into more general "parent" rules.  The parent captures what
# the cluster has in common; its children are linked for tracing.
#
# Algorithm:
#   1. Build a condition-token bitvector for each rule (bag of condition words).
#   2. Cluster greedily: pick the unassigned rule with highest total Jaccard
#      to all its neighbours; grow the cluster while Jaccard > CLUSTER_THRESH.
#   3. For each cluster of ≥ MIN_CLUSTER_SIZE rules:
#        a. Parent conditions = INTERSECTION of all condition sets (what they all share).
#        b. If intersection is empty, use the UNION of the two most-similar rules.
#        c. Parent conclusion = the most-central child conclusion (highest avg similarity
#           to the rest) — this avoids needing an LLM call.
#        d. Parent confidence = mean of child confidences, capped at 0.85.
#   4. Parent rule is added to rule_engine with source="abstraction".
#      Children get a "parent_id" annotation.
#
# Data written to data/rule_abstractions.json (parent→children map).
# Runs once per dream cycle (cadence enforced by _COOLDOWN_S).
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import time
from datetime import datetime, timezone
from typing import Dict, FrozenSet, List, Set

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

ABSTRACTIONS_FILE = DATA_DIR / "rule_abstractions.json"

_CLUSTER_THRESH  = 0.40   # minimum Jaccard for two rules to share a cluster
_MIN_CLUSTER     = 3      # minimum cluster size before we form a parent rule
_MAX_CLUSTERS    = 20     # cap to keep runtime bounded
_COOLDOWN_S      = 4 * 3600  # min 4h between abstraction runs

_last_run: float = 0.0


# ─── Token helpers ────────────────────────────────────────────────────────────

_STOPWORDS: Set[str] = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
    "from","is","are","was","were","be","been","have","has","had","do","does",
    "did","will","would","could","should","may","might","this","that","i","you",
}


def _cond_tokens(rule: Dict) -> FrozenSet[str]:
    words: Set[str] = set()
    for c in (rule.get("conditions") or []):
        words.update(w for w in re.findall(r"[a-z][a-z0-9]*", c.lower())
                     if len(w) > 2 and w not in _STOPWORDS)
    return frozenset(words)


def _conc_tokens(rule: Dict) -> FrozenSet[str]:
    text = rule.get("conclusion", "")
    words = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return frozenset(w for w in words if len(w) > 3 and w not in _STOPWORDS)


def _jaccard(a: FrozenSet, b: FrozenSet) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── Clustering ───────────────────────────────────────────────────────────────

def _cluster_rules(rules: List[Dict]) -> List[List[Dict]]:
    """
    Greedy single-linkage clustering on condition-token Jaccard.
    Returns list of clusters (each cluster is a list of rules).
    """
    # Skip rules with no conditions or tombstoned
    eligible = [r for r in rules
                if r.get("conditions") and r.get("source") != "tombstoned"
                and r.get("source") != "abstraction"]
    token_map = {r["id"]: _cond_tokens(r) for r in eligible}

    assigned: Set[str] = set()
    clusters: List[List[Dict]] = []

    for seed in eligible:
        if seed["id"] in assigned:
            continue
        cluster = [seed]
        assigned.add(seed["id"])
        seed_toks = token_map[seed["id"]]

        for candidate in eligible:
            if candidate["id"] in assigned:
                continue
            cand_toks = token_map[candidate["id"]]
            if _jaccard(seed_toks, cand_toks) >= _CLUSTER_THRESH:
                cluster.append(candidate)
                assigned.add(candidate["id"])

        if len(cluster) >= _MIN_CLUSTER:
            clusters.append(cluster)
        if len(clusters) >= _MAX_CLUSTERS:
            break

    return clusters


# ─── Parent synthesis ─────────────────────────────────────────────────────────

def _parent_conditions(cluster: List[Dict]) -> List[str]:
    """Intersection of all condition sets; fall back to pairwise-union of closest pair."""
    sets = [set(r.get("conditions") or []) for r in cluster]
    intersection = sets[0].copy()
    for s in sets[1:]:
        intersection &= s
    if intersection:
        return sorted(intersection)

    # Intersection empty — use union of two most-similar rules
    best_j, best_pair = 0.0, (cluster[0], cluster[1])
    tmap = {r["id"]: _cond_tokens(r) for r in cluster}
    for i, ra in enumerate(cluster):
        for rb in cluster[i+1:]:
            j = _jaccard(tmap[ra["id"]], tmap[rb["id"]])
            if j > best_j:
                best_j, best_pair = j, (ra, rb)
    union = set(best_pair[0].get("conditions") or []) | set(best_pair[1].get("conditions") or [])
    return sorted(union)


def _parent_conclusion(cluster: List[Dict]) -> str:
    """
    Most-central conclusion: highest average Jaccard to all other conclusions.
    Falls back to longest conclusion.
    """
    tmap = {r["id"]: _conc_tokens(r) for r in cluster}
    best_id, best_avg = cluster[0]["id"], -1.0
    for ra in cluster:
        others = [tmap[rb["id"]] for rb in cluster if rb["id"] != ra["id"]]
        avg = sum(_jaccard(tmap[ra["id"]], o) for o in others) / max(len(others), 1)
        if avg > best_avg:
            best_avg, best_id = avg, ra["id"]

    for r in cluster:
        if r["id"] == best_id:
            return r["conclusion"]
    return cluster[0]["conclusion"]


def _name_cluster(conditions: List[str]) -> str:
    """Human-readable cluster name from dominant condition tokens."""
    return "When " + ", ".join(conditions[:4]) if conditions else "General rule"


# ─── Main entry point ─────────────────────────────────────────────────────────

def abstract_rules(*, force: bool = False) -> Dict:
    """
    Run one abstraction pass.  Returns summary dict.
    Enforces _COOLDOWN_S unless force=True.
    """
    global _last_run
    now = time.time()
    if not force and (now - _last_run) < _COOLDOWN_S:
        return {"skipped": True, "reason": "cooldown"}
    _last_run = now

    from brain.symbolic.rule_engine import get_all_rules, add_rule, SYMBOLIC_RULES_FILE
    from brain.utils.json_utils import save_json as _sj

    rules = get_all_rules()
    clusters = _cluster_rules(rules)

    if not clusters:
        log_activity("[rule_abstraction] No clusters found.")
        return {"clusters": 0, "parents_added": 0}

    existing_abstractions = load_json(ABSTRACTIONS_FILE, default_type=list) or []
    existing_parent_ids = {a["parent_id"] for a in existing_abstractions}

    parents_added = 0

    for cluster in clusters:
        conditions = _parent_conditions(cluster)
        conclusion = _parent_conclusion(cluster)
        cluster_name = _name_cluster(conditions)

        # Check if an equivalent parent already exists
        import hashlib as _hl
        parent_key = _hl.md5(conclusion.encode()).hexdigest()[:10]
        if parent_key in existing_parent_ids:
            continue

        mean_conf = round(
            min(sum(r.get("confidence", 0.75) for r in cluster) / len(cluster), 0.85),
            3,
        )

        # Carry forward knowledge structure fields from children.
        # Bartlett (1932): parent schema inherits the richest knowledge of its children.
        child_causal = next((r.get("causal_claim") for r in cluster
                             if isinstance(r.get("causal_claim"), dict)), None)
        child_pred   = next((r.get("prediction") for r in cluster
                             if r.get("prediction")), None)
        child_action = next((r.get("recommended_action") for r in cluster
                             if r.get("recommended_action")), None)
        child_levels = [r.get("abstraction_level", 1) for r in cluster]
        parent_level = max(child_levels) + 1

        parent_rule = add_rule(
            conditions=conditions,
            conclusion=conclusion,
            confidence=mean_conf,
            source="abstraction",
            causal_claim=child_causal,
            prediction=child_pred,
            recommended_action=child_action,
            abstraction_level=parent_level,
            evidence_ids=[r["id"] for r in cluster],
        )

        child_ids = [r["id"] for r in cluster]
        # Annotate children with parent_id (best-effort)
        all_rules = get_all_rules()
        modified = False
        for rule in all_rules:
            if rule["id"] in child_ids and "parent_id" not in rule:
                rule["parent_id"] = parent_rule["id"]
                modified = True
        if modified:
            _sj(SYMBOLIC_RULES_FILE, all_rules)
            try:
                from brain.symbolic import rule_engine as _re
                _re._rules_cache = []
            except Exception as _e:
                record_failure("rule_abstraction.abstract_rules", _e)

        existing_abstractions.append({
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "parent_id":   parent_rule["id"],
            "parent_name": cluster_name,
            "child_ids":   child_ids,
            "conditions":  conditions,
            "conclusion":  conclusion[:200],
        })
        parents_added += 1
        log_activity(
            f"[rule_abstraction] Parent '{parent_rule['id']}' formed from "
            f"{len(cluster)} rules: {cluster_name[:60]}"
        )

    save_json(ABSTRACTIONS_FILE, existing_abstractions[-200:])
    log_activity(f"[rule_abstraction] {len(clusters)} cluster(s) → {parents_added} new parent(s).")
    return {"clusters": len(clusters), "parents_added": parents_added}


def get_abstraction_tree() -> List[Dict]:
    """Return the current parent→children map for inspection."""
    return load_json(ABSTRACTIONS_FILE, default_type=list) or []
