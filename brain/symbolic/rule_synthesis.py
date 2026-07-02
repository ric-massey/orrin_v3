# brain/symbolic/rule_synthesis.py
#
# Builds the abstraction hierarchy from specific patterns upward to principles
# and meta-principles. Called from the dream cycle after rule_abstraction runs.
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────────────────
# Chase & Simon (1973) Chunking:
#   "Perception in chess." Cognitive Psychology, 4(1), 55–81.
#   Expert cognition works by aggregating specific patterns into higher-level
#   chunks. Chess masters don't see individual pieces — they see configurations.
#   This module implements the chunking pass: specific rules → patterns →
#   principles → meta-principles.
#
# Bartlett (1932) Schema theory:
#   "Remembering: A Study in Experimental and Social Psychology." Cambridge UP.
#   Schemas are abstracted knowledge structures with slots, defaults, and
#   inheritance. They generalize across specific events and enable inference
#   by slot-filling. Parent rules here are schemas.
#
# Gentner (1983) Structure-Mapping / Analogical Reasoning:
#   "Structure-mapping: A theoretical framework for analogy." Cognitive Science.
#   Abstraction finds structural commonalities across surface-different situations.
#   Two rules fire in different contexts but share the same causal structure →
#   they reveal a common principle.
#
# Quinlan (1986) Inductive Learning / ID3:
#   "Induction of Decision Trees." Machine Learning, 1(1), 81–106.
#   Generalisation: find the minimal description that covers all positive
#   examples (child rules) without overfitting to surface differences.
#
# Anderson (1982) Procedural Learning / Compilation:
#   "Acquisition of cognitive skill." Psychological Review, 89(4), 369–406.
#   Skills move from declarative (rule-list) to compiled (principle): the
#   compiled form carries the general structure, not specific instances.
#
# Hierarchy levels:
#   L1 — specific event  ("this cycle I avoided this task")
#   L2 — pattern        ("goal avoidance recurs when uncertainty > confidence")
#   L3 — principle      ("high uncertainty suppresses action across domains")
#   L4 — meta-principle ("reduce task size when uncertainty exceeds confidence")
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, FrozenSet, List, Optional, Set

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

SYNTHESIS_FILE = DATA_DIR / "rule_synthesis.json"

_COOLDOWN_S    = 6 * 3600   # run at most once per 6 hours (dream cycle cadence)
_MIN_CLUSTER   = 2           # minimum L2 rules to synthesise an L3 principle
_last_run: float = 0.0

_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "is", "are", "was", "were", "be", "been", "have",
    "has", "had", "this", "that", "i", "it", "if", "not", "no", "so",
}


# ─── Token helpers ────────────────────────────────────────────────────────────

def _tokens(text: str) -> FrozenSet[str]:
    words = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return frozenset(w for w in words if len(w) > 3 and w not in _STOPWORDS)


def _jaccard(a: FrozenSet, b: FrozenSet) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── Causal claim generalisation ─────────────────────────────────────────────

def _generalise_causal_claims(rules: List[Dict]) -> Optional[Dict]:
    """
    Gentner (1983): abstraction = structural commonality across surface-different instances.
    Find what all the causal claims share in their cause/effect/mechanism tokens.
    Returns a generalised causal claim dict, or None if no shared structure.
    """
    claims = [r.get("causal_claim") for r in rules if isinstance(r.get("causal_claim"), dict)]
    if not claims:
        return None

    cause_tokens   = [_tokens(c.get("cause", ""))     for c in claims]
    effect_tokens  = [_tokens(c.get("effect", ""))    for c in claims]
    mech_tokens    = [_tokens(c.get("mechanism", "")) for c in claims]

    def common_words(token_sets: List[FrozenSet]) -> str:
        if not token_sets:
            return ""
        intersection = token_sets[0]
        for s in token_sets[1:]:
            intersection = intersection & s
        # Fall back to union of two most-similar if intersection is too small
        if len(intersection) < 2 and len(token_sets) >= 2:
            best_j, best_union = 0.0, frozenset()
            for i, a in enumerate(token_sets):
                for b in token_sets[i + 1:]:
                    j = _jaccard(a, b)
                    if j > best_j:
                        best_j = j
                        best_union = a | b
            intersection = best_union
        return " ".join(sorted(intersection)[:8]) if intersection else ""

    cause_phrase  = common_words(cause_tokens)
    effect_phrase = common_words(effect_tokens)
    mech_phrase   = common_words(mech_tokens)

    if not cause_phrase and not effect_phrase:
        return None

    return {
        "cause":     cause_phrase or "unresolved internal conflict",
        "effect":    effect_phrase or "degraded cognitive performance",
        "mechanism": mech_phrase or "shared structural pattern across multiple instances",
    }


# ─── Principle synthesis ──────────────────────────────────────────────────────

def _synthesise_principle(rules: List[Dict], level: int) -> Optional[Dict]:
    """
    Synthesise a parent rule at `level` from a cluster of child rules.
    Returns the fields dict to pass to add_rule, or None if synthesis fails.

    Anderson (1982) procedural compilation: the general form captures what
    all the instances have in common, discarding surface-specific detail.
    """
    # Conditions: intersection of condition tokens (Quinlan 1986 generalisation)
    cond_sets = [set(r.get("conditions") or []) for r in rules]
    shared_conds = set(cond_sets[0])
    for s in cond_sets[1:]:
        shared_conds &= s
    if not shared_conds:
        # Fall back: union of two most-overlapping rules' conditions
        best_j, best_conds = 0.0, set()
        for i, ra in enumerate(rules):
            for rb in rules[i + 1:]:
                ta = _tokens(" ".join(ra.get("conditions") or []))
                tb = _tokens(" ".join(rb.get("conditions") or []))
                j = _jaccard(ta, tb)
                if j > best_j:
                    best_j = j
                    best_conds = set(ra.get("conditions") or []) | set(rb.get("conditions") or [])
        shared_conds = best_conds

    if not shared_conds:
        return None

    # Generalise causal claim (Gentner, 1983)
    causal_claim = _generalise_causal_claims(rules)

    # Conclusion: most-central child conclusion
    conc_tokens = {r["id"]: _tokens(r.get("conclusion", "")) for r in rules}
    best_id, best_avg = rules[0]["id"], -1.0
    for ra in rules:
        others = [conc_tokens[rb["id"]] for rb in rules if rb["id"] != ra["id"]]
        avg = sum(_jaccard(conc_tokens[ra["id"]], o) for o in others) / max(len(others), 1)
        if avg > best_avg:
            best_avg, best_id = avg, ra["id"]
    base_conclusion = next((r["conclusion"] for r in rules if r["id"] == best_id),
                           rules[0]["conclusion"])

    level_label = {2: "Pattern", 3: "Principle", 4: "Meta-principle"}.get(level, "Abstraction")
    conclusion = (
        f"[L{level} {level_label}] {base_conclusion[:200]} "
        f"— generalised from {len(rules)} instances"
    )

    # Prediction: synthesise from child predictions if available
    child_preds = [r.get("prediction") for r in rules if r.get("prediction")]
    prediction = child_preds[0] if child_preds else None

    # Recommended action: most specific (highest-confidence) child's action
    actioned = sorted(
        [r for r in rules if r.get("recommended_action")],
        key=lambda r: r.get("confidence", 0), reverse=True,
    )
    recommended_action = actioned[0]["recommended_action"] if actioned else None

    mean_conf = round(
        min(sum(r.get("confidence", 0.75) for r in rules) / len(rules), 0.88), 3
    )

    return {
        "conditions":         sorted(shared_conds),
        "conclusion":         conclusion[:500],
        "confidence":         mean_conf,
        "source":             "rule_synthesis",
        "causal_claim":       causal_claim,
        "prediction":         prediction,
        "recommended_action": recommended_action,
        "abstraction_level":  level,
        "evidence_ids":       [r["id"] for r in rules],
    }


# ─── Cluster rules by level ───────────────────────────────────────────────────

def _cluster_by_level(rules: List[Dict], target_level: int) -> List[List[Dict]]:
    """
    Greedy single-linkage clustering of rules at `target_level` by condition-token
    Jaccard. Returns list of clusters (each ≥ _MIN_CLUSTER rules).
    Chase & Simon (1973): chunk when Jaccard threshold exceeded.
    """
    eligible = [
        r for r in rules
        if r.get("abstraction_level", 1) == target_level
        and r.get("source") not in ("tombstoned", "rule_synthesis")
        and r.get("conditions")
    ]
    if len(eligible) < _MIN_CLUSTER:
        return []

    tok_map = {r["id"]: _tokens(" ".join(r.get("conditions") or [])) for r in eligible}
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
            j = _jaccard(tok_map[seed["id"]], tok_map[candidate["id"]])
            if j >= 0.30:
                cluster.append(candidate)
                assigned.add(candidate["id"])
        if len(cluster) >= _MIN_CLUSTER:
            clusters.append(cluster)

    return clusters


# ─── Main entry ───────────────────────────────────────────────────────────────

def synthesise_rules(*, force: bool = False) -> Dict:
    """
    Run one synthesis pass:
      1. Cluster L2 rules → synthesise L3 principle rules
      2. Cluster L3 rules → synthesise L4 meta-principle rules

    Called from the dream cycle. Returns summary dict.

    Basis: Chase & Simon (1973) chunking, Bartlett (1932) schema,
    Gentner (1983) structure-mapping, Quinlan (1986) induction.
    """
    global _last_run
    now = time.time()
    if not force and (now - _last_run) < _COOLDOWN_S:
        return {"skipped": True, "reason": "cooldown"}
    _last_run = now

    try:
        from brain.symbolic.rule_engine import get_all_rules, add_rule, SYMBOLIC_RULES_FILE
        from brain.utils.json_utils import save_json as _sj
    except ImportError as e:  # intentional: rule_engine optional → report, no synthesis
        return {"error": str(e)}

    all_rules   = get_all_rules()
    synthesis_log = load_json(SYNTHESIS_FILE, default_type=list) or []
    existing_ids  = {s["parent_id"] for s in synthesis_log}

    total_new = 0

    for child_level, parent_level in [(2, 3), (3, 4)]:
        clusters = _cluster_by_level(all_rules, child_level)
        for cluster in clusters:
            fields = _synthesise_principle(cluster, parent_level)
            if not fields:
                continue

            # Deduplicate by conclusion hash
            rid = hashlib.md5(fields["conclusion"].encode()).hexdigest()[:10]
            if rid in existing_ids:
                continue

            parent_rule = add_rule(**fields)
            if not parent_rule:
                continue

            # Annotate children with parent_id
            modified = False
            fresh_rules = get_all_rules()
            for rule in fresh_rules:
                if rule["id"] in fields["evidence_ids"] and not rule.get("parent_id"):
                    rule["parent_id"] = parent_rule["id"]
                    modified = True
            if modified:
                _sj(SYMBOLIC_RULES_FILE, fresh_rules)
                try:
                    from brain.symbolic import rule_engine as _re
                    _re._rules_cache = []
                except Exception as _e:
                    record_failure("rule_synthesis.synthesise_rules", _e)

            synthesis_log.append({
                "timestamp":    datetime.now(timezone.utc).isoformat(),
                "parent_id":    parent_rule["id"],
                "parent_level": parent_level,
                "child_ids":    fields["evidence_ids"],
                "conclusion":   fields["conclusion"][:200],
                "causal_claim": fields.get("causal_claim"),
            })
            existing_ids.add(parent_rule["id"])
            total_new += 1

            # AR1: a synthesized principle is produced structure — record it on
            # the effect ledger so the production system can see it.
            try:
                from brain.symbolic.symbolic_effects import record_symbolic_effect
                claim = fields.get("causal_claim") or {}
                record_symbolic_effect(
                    "rule",
                    (f"[synthesized L{parent_level} principle] "
                     f"conditions: {', '.join(fields['conditions'])}; "
                     f"conclusion: {fields['conclusion']}; "
                     f"causal: {claim.get('cause', '')} -> {claim.get('effect', '')} "
                     f"({claim.get('mechanism', '')}); "
                     f"generalised from {len(cluster)} L{child_level} rules"),
                    metadata={"rule_id": parent_rule["id"], "level": parent_level},
                )
            except Exception as _e:
                record_failure("rule_synthesis.record_effect", _e)

            log_activity(
                f"[rule_synthesis] L{parent_level} rule '{parent_rule['id']}' "
                f"from {len(cluster)} L{child_level} rules: "
                f"{fields['conclusion'][:80]}"
            )

    save_json(SYNTHESIS_FILE, synthesis_log[-200:])
    log_activity(f"[rule_synthesis] Synthesis complete: {total_new} new principle rules.")
    return {"principles_added": total_new}


def get_synthesis_tree() -> List[Dict]:
    """Return the full synthesis log (parent→children map) for inspection."""
    return load_json(SYNTHESIS_FILE, default_type=list) or []


def get_principle_for(query: str) -> Optional[Dict]:
    """
    Find the highest-abstraction-level rule matching a query.
    Used by planning and reflection to retrieve principles, not just patterns.
    """
    try:
        from brain.symbolic.rule_engine import get_all_rules
        rules = [r for r in get_all_rules()
                 if r.get("abstraction_level", 1) >= 3
                 and r.get("source") == "rule_synthesis"]
        if not rules:
            return None
        q_toks = _tokens(query)
        scored = []
        for r in rules:
            cond_toks = _tokens(" ".join(r.get("conditions") or []))
            conc_toks = _tokens(r.get("conclusion", ""))
            score = _jaccard(q_toks, cond_toks) + _jaccard(q_toks, conc_toks) * 0.5
            score *= r.get("confidence", 0.5)
            if score > 0.05:
                scored.append((r, score))
        if not scored:
            return None
        return max(scored, key=lambda x: x[1])[0]
    except Exception as _e:
        record_failure("rule_synthesis.get_principle_for", _e)
        return None
