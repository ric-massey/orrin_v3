# brain/symbolic/crystallization.py
# Knowledge crystallization: turn successful LLM responses into reusable rules.
#
# Compression test (the key gate):
#   A candidate rule must pass three checks before being stored.
#   1. Not subsumed — no existing rule with the same/superset conditions already
#      covers this conclusion (prevents duplicate/narrow rules).
#   2. Generality score — rules with fewer conditions score higher; a new rule
#      must be at least as general as the weakest existing rule in the same cluster.
#   3. Informativeness — the conclusion must carry content not already in the
#      existing rule set (measured by token novelty against stored conclusions).
#
# Only rules that pass all three are added. This keeps the rule set lean and
# prevents the common failure mode where every LLM call dumps 4 near-identical
# micro-rules that match nothing useful.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.symbolic.rule_engine import add_rule, get_all_rules
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

CRYSTALLIZED_SKILLS_FILE = DATA_DIR / "crystallized_skills.json"

_MIN_OUTCOME        = 0.55   # only crystallize high-quality responses
_MAX_RULES_PER_CALL = 4      # cap rules extracted from one response
_MIN_GENERALITY     = 0.30   # rules with generality below this are too narrow
_MIN_TOKEN_NOVELTY  = 0.25   # conclusion must share < 75% tokens with existing conclusions

_STOPWORDS: Set[str] = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
    "from","is","are","was","were","be","been","have","has","had","do","does",
    "did","will","would","could","should","may","might","this","that","i","you",
    "we","it","its","he","she","they","what","which","who","how","when","where",
}

_META_SKIP = frozenset({
    "i am not sure", "i don't know", "as an ai", "i cannot", "i'm unable",
    "please note", "it's important", "it is important", "keep in mind",
    "you should note", "remember that",
})


# ─── Token helpers ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> Set[str]:
    words = re.findall(r"[a-z][a-z0-9]*", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ─── Condition extraction ────────────────────────────────────────────────────

def _extract_conditions(query: str) -> List[str]:
    words = re.findall(r"[a-z][a-z0-9_-]*", query.lower())
    return [w for w in words if len(w) > 3 and w not in _STOPWORDS][:8]


def _split_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 20]


# ─── Compression test ─────────────────────────────────────────────────────────

def _generality_score(conditions: List[str]) -> float:
    """
    Fewer conditions = more general = higher score.
    0 conditions → 1.0; 8+ conditions → near 0.
    """
    n = len(conditions)
    if n == 0:
        return 1.0
    return round(1.0 / (1.0 + n * 0.25), 3)


def _is_subsumed(
    candidate_conditions: List[str],
    candidate_conclusion: str,
    existing_rules: List[Dict],
) -> bool:
    """
    True if an existing rule already covers this candidate.
    Subsumed = existing conditions are a subset of candidate conditions
    AND existing conclusion overlaps heavily with candidate conclusion.
    """
    cand_cond_set = set(c.lower() for c in candidate_conditions)
    cand_conc_toks = _tokenize(candidate_conclusion)

    for rule in existing_rules:
        exist_cond_set = set(c.lower() for c in (rule.get("conditions") or []))
        # Existing conditions are a subset (existing rule is more general)
        if exist_cond_set <= cand_cond_set:
            exist_conc_toks = _tokenize(rule.get("conclusion", ""))
            overlap = _jaccard(cand_conc_toks, exist_conc_toks)
            if overlap >= 0.65:
                return True
    return False


def _conclusion_token_novelty(conclusion: str, existing_rules: List[Dict]) -> float:
    """
    How novel is this conclusion relative to what's already stored?
    Returns 0–1; 1 = completely new vocabulary.
    """
    cand_toks = _tokenize(conclusion)
    if not cand_toks:
        return 0.0
    max_overlap = max(
        (_jaccard(cand_toks, _tokenize(r.get("conclusion", ""))) for r in existing_rules),
        default=0.0,
    )
    return round(1.0 - max_overlap, 3)


def _passes_compression_test(
    conditions: List[str],
    conclusion: str,
    existing_rules: List[Dict],
) -> Tuple[bool, str]:
    """
    Returns (passes, reason_string).
    Three gates: subsumed check, generality, token novelty.
    """
    gen = _generality_score(conditions)
    if gen < _MIN_GENERALITY:
        return False, f"too_narrow (generality={gen}, conditions={len(conditions)})"

    if _is_subsumed(conditions, conclusion, existing_rules):
        return False, "subsumed_by_existing_rule"

    novelty = _conclusion_token_novelty(conclusion, existing_rules)
    if novelty < _MIN_TOKEN_NOVELTY:
        return False, f"low_novelty (token_novelty={novelty})"

    return True, "ok"


# ─── Crystallize ─────────────────────────────────────────────────────────────

def crystallize(
    query: str,
    response: str,
    *,
    outcome: float = 0.6,
    caller: str = "unknown",
) -> List[Dict]:
    """
    Extract rules from a successful LLM response and register them.
    Applies compression test: only adds rules that are genuinely new and general.
    Returns list of newly added rule dicts (may be empty).
    """
    if outcome < _MIN_OUTCOME:
        return []
    if not query.strip() or not response.strip():
        return []

    # Quarantine, don't crystallize, garbage (Phase 1.4): corrupted memory text
    # (nested chunk headers, unbalanced brackets, mid-word truncations) must
    # never be minted into symbolic rules.
    try:
        from brain.utils.text_sanity import is_corrupt_text
        if is_corrupt_text(query) or is_corrupt_text(response):
            log_activity(f"[crystallization] Quarantined corrupt source text from '{caller}'")
            return []
    except Exception as _e:
        record_failure("crystallization.crystallize", _e)

    conditions = _extract_conditions(query)
    if not conditions:
        return []

    sentences = _split_sentences(response)
    existing_rules = get_all_rules()
    added: List[Dict] = []
    rejected = 0

    for sentence in sentences[:_MAX_RULES_PER_CALL]:
        lower = sentence.lower()
        if any(skip in lower for skip in _META_SKIP):
            rejected += 1
            continue

        passes, reason = _passes_compression_test(conditions, sentence, existing_rules)
        if not passes:
            log_activity(f"[crystallization] Skipped (compression: {reason}): {sentence[:60]}")
            rejected += 1
            continue

        rule = add_rule(
            conditions=conditions,
            conclusion=sentence,
            confidence=0.72,
            source="crystallization",
        )
        added.append(rule)
        existing_rules.append(rule)  # update local copy for subsequent checks

    if added or rejected:
        log_activity(
            f"[crystallization] {len(added)} rule(s) added, {rejected} rejected "
            f"(compression) from '{caller}'"
        )
    if added:
        _log_crystallization(query, response, added, caller, rejected)

    return added


def _log_crystallization(
    query: str, response: str, rules: List[Dict], caller: str, rejected: int
) -> None:
    try:
        existing = load_json(CRYSTALLIZED_SKILLS_FILE, default_type=list) or []
        existing.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "caller": caller,
            "query": query[:200],
            "response_snippet": response[:300],
            "rules_added": [r["id"] for r in rules],
            "rules_rejected_compression": rejected,
        })
        save_json(CRYSTALLIZED_SKILLS_FILE, existing[-200:])
    except Exception as _e:
        record_failure("crystallization._log_crystallization", _e)


# ─── Dream-cycle hook ────────────────────────────────────────────────────────

def crystallize_idle_insights(dream_entry: Dict) -> int:
    """
    Call from idle_consolidation_cycle.py after a completed cycle.
    Crystallizes consolidation + processing insights into permanent rules.
    Returns count of new rules added.
    """
    total = 0
    for kind in ("consolidation", "processing"):
        text = dream_entry.get(kind, "")
        if not text:
            continue
        rules = crystallize(
            query=f"dream {kind}",
            response=text,
            outcome=0.80,
            caller=f"idle_consolidation_cycle/{kind}",
        )
        total += len(rules)
    return total


# ─── Generality audit ────────────────────────────────────────────────────────

def audit_rule_set() -> Dict:
    """
    Scan the full rule set for redundancy and return a health report.
    Call from idle_consolidation_cycle or diagnostics.
    """
    rules = get_all_rules()
    total = len(rules)
    subsumed_count = 0
    low_gen = 0
    stale = 0  # hits==0 and older than 7 days

    now_ts = time.time()
    for i, rule in enumerate(rules):
        gen = _generality_score(rule.get("conditions") or [])
        if gen < _MIN_GENERALITY:
            low_gen += 1
        if rule.get("hits", 0) == 0:
            try:
                from datetime import datetime
                age_s = now_ts - datetime.fromisoformat(
                    rule["created_at"].replace("Z", "+00:00")
                ).timestamp()
                if age_s > 7 * 86400:
                    stale += 1
            except Exception as _e:
                record_failure("crystallization.audit_rule_set", _e)
        # Subsumed check against all other rules
        others = rules[:i] + rules[i+1:]
        cond = rule.get("conditions") or []
        conc = rule.get("conclusion", "")
        if _is_subsumed(cond, conc, others):
            subsumed_count += 1

    return {
        "total": total,
        "subsumed": subsumed_count,
        "low_generality": low_gen,
        "stale_zero_hits": stale,
        "health_ratio": round(
            (total - subsumed_count - low_gen) / max(total, 1), 3
        ),
    }
