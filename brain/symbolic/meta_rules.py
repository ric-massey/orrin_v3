# brain/symbolic/meta_rules.py
# Meta-rules: rules about how to apply other rules.
#
# When multiple rules match the same query, meta-rules break ties and detect
# conflicts.  They encode learned heuristics like:
#   "Prefer rules with more past hits"
#   "When confidence diverges >0.3, take the higher-confidence rule"
#   "Specific rules (more conditions) beat general rules on the same topic"
#   "If two rules contradict, flag a conflict and defer to LLM"
#
# Meta-rule schema (stored in data/meta_rules.json):
#   {
#     "id":          str,
#     "name":        str,          # human-readable
#     "condition":   str,          # "conflict" | "ambiguous" | "low_conf" | "always"
#     "action":      str,          # "prefer_hits" | "prefer_conf" | "prefer_specific"
#                                  # | "prefer_general" | "defer_llm" | "flag_conflict"
#     "priority":    int,          # lower = applied first
#     "reward":      float,        # cumulative reward from past applications
#     "applications": int,
#     "source":      str,
#   }
#
# Meta-rule resolution:
#   resolve_conflict(rules, query) → Dict with "winner" rule + "action" + "reason"
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import ContractViolation
from brain.paths import DATA_DIR

META_RULES_FILE = DATA_DIR / "meta_rules.json"

# ─── Built-in meta-rules (seeded on first load) ───────────────────────────────
_BUILTIN_META_RULES: List[Dict] = [
    {
        "id": "mr_prefer_hits",
        "name": "Prefer rules with more past hits",
        "condition": "ambiguous",
        "action": "prefer_hits",
        "priority": 10,
        "reward": 0.0,
        "applications": 0,
        "source": "builtin",
        "rationale": "Rules that have been applied more often have proven themselves in practice.",
    },
    {
        "id": "mr_prefer_high_conf",
        "name": "Prefer higher-confidence rule when confidence gap > 0.3",
        "condition": "ambiguous",
        "action": "prefer_conf",
        "priority": 20,
        "reward": 0.0,
        "applications": 0,
        "source": "builtin",
        "rationale": "Confidence tracks past penalization; low-conf rules have been wrong before.",
    },
    {
        "id": "mr_prefer_specific",
        "name": "More-specific rule beats general on same topic",
        "condition": "ambiguous",
        "action": "prefer_specific",
        "priority": 30,
        "reward": 0.0,
        "applications": 0,
        "source": "builtin",
        "rationale": "More conditions = more tightly scoped = less likely to over-generalize.",
    },
    {
        "id": "mr_defer_low_conf",
        "name": "Defer to LLM when best rule confidence < 0.4",
        "condition": "low_conf",
        "action": "defer_llm",
        "priority": 5,
        "reward": 0.0,
        "applications": 0,
        "source": "builtin",
        "rationale": "Heavily penalized rules should not drive responses — open the LLM gate.",
    },
    {
        "id": "mr_flag_contradiction",
        "name": "Flag conflict when top-2 rules contradict",
        "condition": "conflict",
        "action": "flag_conflict",
        "priority": 1,
        "reward": 0.0,
        "applications": 0,
        "source": "builtin",
        "rationale": "Contradicting rules signal a knowledge gap — surface it rather than picking arbitrarily.",
    },
]


# ─── Load / bootstrap ─────────────────────────────────────────────────────────

def _load_meta_rules() -> List[Dict]:
    raw = load_json(META_RULES_FILE, default_type=list) or []
    if not raw:
        raw = list(_BUILTIN_META_RULES)
        save_json(META_RULES_FILE, raw)
    return sorted(raw, key=lambda r: r.get("priority", 99))


def _save_meta_rules(rules: List[Dict]) -> None:
    save_json(META_RULES_FILE, sorted(rules, key=lambda r: r.get("priority", 99)))


# ─── Contradiction detection ──────────────────────────────────────────────────

def _are_contradictory(r1: Dict, r2: Dict) -> bool:
    """
    Heuristic contradiction check.
    Two conclusions contradict if one contains negation words and both share
    most content words.
    """
    from brain.symbolic.analogy_engine import _tokenize, _jaccard
    c1 = r1.get("conclusion", "").lower()
    c2 = r2.get("conclusion", "").lower()
    t1 = _tokenize(c1)
    t2 = _tokenize(c2)
    overlap = _jaccard(t1, t2)
    if overlap < 0.25:
        return False
    _NEG = {"not", "never", "cannot", "no", "without", "avoid", "don't", "doesn't",
            "failed", "incorrect", "wrong", "false", "unlike"}
    neg1 = bool(_NEG & set(c1.split()))
    neg2 = bool(_NEG & set(c2.split()))
    return neg1 != neg2  # one negates, the other doesn't — likely contradictory


# ─── Core resolver ────────────────────────────────────────────────────────────

def resolve_conflict(
    matched_rules: List[Tuple[Dict, float]],
    *,
    query: str = "",
) -> Dict:
    """
    Given a list of (rule, score) pairs from rule_engine.match_all(),
    apply meta-rules to pick the best one or flag a conflict.

    Returns:
      {
        "winner":   rule_dict | None,
        "score":    float,
        "action":   str,          # what the meta-rule did
        "reason":   str,          # human-readable rationale
        "conflict": bool,         # True if contradicting rules detected
        "meta_rule_id": str,
      }
    """
    # Boundary contract (master plan 5.1): this seam crashed silently for
    # months when a bare rule-dict list arrived instead of (rule, score)
    # pairs and the ValueError vanished into a catch-all. A wrong shape now
    # raises a NAMED error that record_failure re-raises under any strict
    # mode regardless of exception type.
    for item in matched_rules or []:
        if not (
            isinstance(item, (tuple, list)) and len(item) == 2
            and isinstance(item[0], dict) and isinstance(item[1], (int, float))
        ):
            raise ContractViolation(
                "resolve_conflict expects List[Tuple[rule_dict, score]]; got "
                f"{type(item).__name__}: {str(item)[:80]}"
            )

    if not matched_rules:
        return {"winner": None, "score": 0.0, "action": "no_match",
                "reason": "No rules matched.", "conflict": False, "meta_rule_id": ""}

    if len(matched_rules) == 1:
        rule, score = matched_rules[0]
        if rule.get("confidence", 1.0) < 0.4:
            _record_application("mr_defer_low_conf")
            return {"winner": None, "score": score, "action": "defer_llm",
                    "reason": f"Only rule has confidence={rule['confidence']:.2f} < 0.4",
                    "conflict": False, "meta_rule_id": "mr_defer_low_conf"}
        return {"winner": rule, "score": score, "action": "only_match",
                "reason": "Single rule matched.", "conflict": False, "meta_rule_id": ""}

    top_rule, top_score = matched_rules[0]
    second_rule, second_score = matched_rules[1]

    # ── Gate: low confidence on the best rule ──────────────────────────────
    if top_rule.get("confidence", 1.0) < 0.4:
        _record_application("mr_defer_low_conf")
        return {"winner": None, "score": top_score, "action": "defer_llm",
                "reason": f"Best rule confidence={top_rule['confidence']:.2f} < 0.4",
                "conflict": False, "meta_rule_id": "mr_defer_low_conf"}

    # ── Contradiction check ────────────────────────────────────────────────
    if _are_contradictory(top_rule, second_rule):
        _record_application("mr_flag_contradiction")
        log_activity(
            f"[meta_rules] Contradiction: '{top_rule['id']}' vs '{second_rule['id']}' — deferring to LLM"
        )
        return {"winner": None, "score": top_score, "action": "flag_conflict",
                "reason": (f"Rules '{top_rule['id']}' and '{second_rule['id']}' contradict — "
                            "deferring to LLM for resolution"),
                "conflict": True, "meta_rule_id": "mr_flag_contradiction"}

    # ── Ambiguity resolution (scores close) ───────────────────────────────
    if abs(top_score - second_score) < 0.10:
        winner, reason, mr_id = _resolve_ambiguous(top_rule, second_rule, top_score, second_score)
        return {"winner": winner, "score": top_score, "action": mr_id,
                "reason": reason, "conflict": False, "meta_rule_id": mr_id}

    # ── Clear winner ──────────────────────────────────────────────────────
    return {"winner": top_rule, "score": top_score, "action": "highest_score",
            "reason": f"Score gap={top_score - second_score:.3f} — top rule wins clearly",
            "conflict": False, "meta_rule_id": ""}


def _resolve_ambiguous(
    r1: Dict, r2: Dict, s1: float, s2: float
) -> Tuple[Dict, str, str]:
    """Apply priority-ordered meta-rules to pick between two close-scoring rules."""

    # mr_prefer_hits: more hits → proven in practice
    h1, h2 = r1.get("hits", 0), r2.get("hits", 0)
    if abs(h1 - h2) >= 3:
        winner = r1 if h1 > h2 else r2
        _record_application("mr_prefer_hits")
        return winner, f"Hit count: {h1} vs {h2}", "mr_prefer_hits"

    # mr_prefer_high_conf: confidence gap > 0.3
    c1, c2 = r1.get("confidence", 0.75), r2.get("confidence", 0.75)
    if abs(c1 - c2) >= 0.30:
        winner = r1 if c1 > c2 else r2
        _record_application("mr_prefer_high_conf")
        return winner, f"Confidence gap: {c1:.2f} vs {c2:.2f}", "mr_prefer_high_conf"

    # mr_prefer_specific: more conditions = more specific
    n1, n2 = len(r1.get("conditions") or []), len(r2.get("conditions") or [])
    if n1 != n2:
        winner = r1 if n1 > n2 else r2
        _record_application("mr_prefer_specific")
        return winner, f"Specificity: {n1} vs {n2} conditions", "mr_prefer_specific"

    # Default: take highest raw score
    return r1, "No meta-rule differentiated — took highest raw score", ""


def _record_application(meta_rule_id: str) -> None:
    rules = _load_meta_rules()
    for r in rules:
        if r["id"] == meta_rule_id:
            r["applications"] = r.get("applications", 0) + 1
            break
    _save_meta_rules(rules)


# ─── Reward / learning ───────────────────────────────────────────────────────

def reward_meta_rule(meta_rule_id: str, delta: float) -> None:
    """
    Called when a meta-rule-selected answer receives outcome feedback.
    Positive delta → rule was a good choice; negative → consider re-ordering.
    """
    if not meta_rule_id:
        return
    rules = _load_meta_rules()
    for r in rules:
        if r["id"] == meta_rule_id:
            r["reward"] = round(r.get("reward", 0.0) + delta, 4)
            break
    _save_meta_rules(rules)
    log_activity(f"[meta_rules] Reward {delta:+.3f} → '{meta_rule_id}'")


def add_meta_rule(
    name: str,
    condition: str,
    action: str,
    *,
    priority: int = 50,
    rationale: str = "",
    source: str = "crystallization",
) -> Dict:
    """Add a new learned meta-rule. Used by crystallization when it detects patterns."""
    mid = hashlib.md5(name.encode()).hexdigest()[:10]
    rules = _load_meta_rules()
    for r in rules:
        if r["id"] == mid:
            return r
    mr = {
        "id": mid,
        "name": name,
        "condition": condition,
        "action": action,
        "priority": priority,
        "reward": 0.0,
        "applications": 0,
        "source": source,
        "rationale": rationale,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    rules.append(mr)
    _save_meta_rules(rules)
    log_activity(f"[meta_rules] New meta-rule '{mid}': {name}")
    return mr


def get_meta_rule_stats() -> List[Dict]:
    """Return meta-rule performance summary for the progress tracker."""
    rules = _load_meta_rules()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "applications": r.get("applications", 0),
            "reward": r.get("reward", 0.0),
            "priority": r.get("priority", 99),
        }
        for r in rules
    ]
