# brain/symbolic/rule_compressor.py
# Abstraction / compression: scan all active rules for shared condition tokens.
# When ≥3 rules share ≥2 common condition tokens, synthesize a general meta-rule
# covering the group and tombstone the specific rules it generalizes.
#
# Analogy: how the prefrontal cortex extracts abstract schemas from repeated
# specific experiences — chunking specific episodes into reusable rules.
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private

try:
    from brain.paths import SYMBOLIC_RULES_FILE
except Exception:
    from pathlib import Path
    SYMBOLIC_RULES_FILE = Path(__file__).resolve().parents[1] / "data" / "symbolic_rules.json"

_MIN_RULES_IN_CLUSTER = 3   # minimum rules needed to trigger compression
_MIN_SHARED_TOKENS    = 2   # minimum shared condition tokens to count as related
_MIN_CONFIDENCE       = 0.40  # only consider rules that aren't completely degraded
_MAX_COMPRESSIONS     = 5   # cap per run to keep the cycle fast


def _tokenize(condition: str) -> Set[str]:
    """Extract meaningful tokens from a condition string."""
    words = re.findall(r'\b[a-z]{3,}\b', condition.lower())
    stopwords = {"the", "and", "not", "for", "are", "was", "has", "its", "this", "that", "with", "from", "have"}
    return {w for w in words if w not in stopwords}


def _rule_id(conditions: List[str], conclusion: str) -> str:
    key = "|".join(sorted(conditions)) + conclusion
    return "meta_" + hashlib.md5(key.encode()).hexdigest()[:10]


def _build_meta_rule(cluster: List[Dict], shared_tokens: Set[str]) -> Dict:
    """Synthesize a meta-rule that generalizes a cluster of specific rules."""
    ts = datetime.now(timezone.utc).isoformat()
    conditions = sorted(shared_tokens)
    # Conclusion: find the most common conclusion keyword across the cluster
    all_conclusions = [str(r.get("conclusion") or "") for r in cluster]
    all_words = []
    for c in all_conclusions:
        all_words.extend(re.findall(r'\b[a-z]{4,}\b', c.lower()))
    conclusion_counter = Counter(all_words)
    top_word = conclusion_counter.most_common(1)[0][0] if conclusion_counter else "respond"
    conclusion = f"[meta] When {', '.join(conditions)}: consider {top_word}"

    avg_confidence = sum(float(r.get("confidence", 0.5)) for r in cluster) / len(cluster)
    avg_hits = sum(int(r.get("hits", 0)) for r in cluster) // len(cluster)

    return {
        "id": _rule_id(conditions, conclusion),
        "conditions": conditions,
        "negations": [],
        "conclusion": conclusion,
        "action": None,
        "confidence": round(min(0.85, avg_confidence + 0.1), 3),
        "hits": avg_hits,
        "source": "rule_compressor",
        "created_at": ts,
        "compressed_from": [r["id"] for r in cluster],
    }


def run_rule_compression() -> Dict[str, Any]:
    """
    Main entry point, called during dream cycle.

    Scans symbolic_rules.json for clusters of specific rules with shared condition
    tokens. Generates a meta-rule per cluster and tombstones the source rules.

    Returns a summary dict.
    """
    rules: List[Dict] = load_json(SYMBOLIC_RULES_FILE, default_type=list) or []
    if not isinstance(rules, list):
        return {"skipped": True, "reason": "rules_not_list"}

    # Only consider active (non-tombstoned), sufficiently confident rules
    active = [
        r for r in rules
        if isinstance(r, dict)
        and not r.get("tombstoned")
        and float(r.get("confidence", 0.5)) >= _MIN_CONFIDENCE
        and r.get("source") != "rule_compressor"  # don't compress already-abstract rules
    ]

    if len(active) < _MIN_RULES_IN_CLUSTER:
        return {"skipped": True, "reason": "insufficient_active_rules", "count": len(active)}

    # Build token sets for each rule
    token_sets: List[Tuple[Dict, Set[str]]] = []
    for r in active:
        cond_tokens: Set[str] = set()
        for cond in (r.get("conditions") or []):
            cond_tokens.update(_tokenize(str(cond)))
        if cond_tokens:
            token_sets.append((r, cond_tokens))

    # Find clusters: group rules that share ≥ _MIN_SHARED_TOKENS tokens
    used_ids: Set[str] = set()
    clusters: List[List[Dict]] = []

    for i, (rule_i, tokens_i) in enumerate(token_sets):
        if rule_i["id"] in used_ids:
            continue
        cluster = [rule_i]
        shared = set(tokens_i)
        for j, (rule_j, tokens_j) in enumerate(token_sets):
            if j <= i or rule_j["id"] in used_ids:
                continue
            intersection = tokens_i & tokens_j
            if len(intersection) >= _MIN_SHARED_TOKENS:
                cluster.append(rule_j)
                shared &= tokens_j

        if len(cluster) >= _MIN_RULES_IN_CLUSTER and len(shared) >= _MIN_SHARED_TOKENS:
            clusters.append(cluster)
            for r in cluster:
                used_ids.add(r["id"])

    if not clusters:
        return {"skipped": False, "clusters": 0, "meta_rules_added": 0}

    # Apply compressions (capped)
    meta_rules_added = 0
    tombstoned = 0
    existing_ids = {r.get("id") for r in rules if isinstance(r, dict)}

    for cluster in clusters[:_MAX_COMPRESSIONS]:
        # Compute final shared token set across whole cluster
        shared_tokens: Set[str] = set()
        for idx, r in enumerate(cluster):
            r_tokens: Set[str] = set()
            for cond in (r.get("conditions") or []):
                r_tokens.update(_tokenize(str(cond)))
            if idx == 0:
                shared_tokens = r_tokens
            else:
                shared_tokens &= r_tokens

        if len(shared_tokens) < _MIN_SHARED_TOKENS:
            continue

        meta = _build_meta_rule(cluster, shared_tokens)
        if meta["id"] not in existing_ids:
            rules.append(meta)
            existing_ids.add(meta["id"])
            meta_rules_added += 1
            log_private(f"[rule_compressor] meta rule: {meta['conclusion'][:100]}")

        # Tombstone the specific rules subsumed by the meta-rule
        for r in cluster:
            for existing_rule in rules:
                if isinstance(existing_rule, dict) and existing_rule.get("id") == r["id"]:
                    existing_rule["tombstoned"] = True
                    existing_rule["tombstoned_by"] = meta["id"]
                    tombstoned += 1
                    break

    try:
        save_json(SYMBOLIC_RULES_FILE, rules)
    except Exception as e:
        log_activity(f"[rule_compressor] save failed: {e}")
        return {"skipped": False, "error": str(e)}

    log_activity(
        f"[rule_compressor] {len(clusters[:_MAX_COMPRESSIONS])} cluster(s) → "
        f"{meta_rules_added} meta rule(s), {tombstoned} rules tombstoned"
    )
    return {
        "skipped": False,
        "clusters": len(clusters),
        "meta_rules_added": meta_rules_added,
        "tombstoned": tombstoned,
    }
