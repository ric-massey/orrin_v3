# brain/symbolic/symbolic_dictionary.py
# Self-updatable English vocabulary owned by the symbolic layer.
from __future__ import annotations

import re
from typing import Dict, List, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import DATA_DIR
from utils.timeutils import now_iso_z

DICT_FILE = DATA_DIR / "symbolic_dictionary.json"

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "this", "that", "it", "its", "i", "you",
    "we", "he", "she", "they", "what", "which", "who", "how", "when",
    "where", "if", "then", "not", "no", "so", "as",
}

_populated: bool = False


# ─── Load / save ─────────────────────────────────────────────────────────────

def _load() -> Dict[str, Dict]:
    raw = load_json(DICT_FILE, default_type=dict)
    return {k.lower(): v for k, v in raw.items()} if raw else {}


def _save(d: Dict[str, Dict]) -> None:
    save_json(DICT_FILE, d)



# ─── Lazy auto-populate guard ────────────────────────────────────────────────

def _ensure_populated() -> None:
    global _populated
    if _populated:
        return
    _populated = True
    d = _load()
    if not d:
        auto_populate_from_rules()


# ─── Public API ──────────────────────────────────────────────────────────────

def define(word: str) -> Optional[str]:
    """Return the definition for word (case-insensitive) or None."""
    _ensure_populated()
    entry = _load().get(word.lower())
    if entry:
        return entry.get("definition")
    return None


def add_word(
    word: str,
    definition: str,
    examples: Optional[List[str]] = None,
    domain: str = "GENERAL",
    source: str = "user",
) -> None:
    """
    Persist a new word. No-op if the word already exists with uses > 0
    (an actively-used definition is treated as authoritative).
    """
    if not word or not definition:
        return
    key = word.lower().strip()
    d = _load()
    existing = d.get(key)
    if existing and existing.get("uses", 0) > 0:
        return
    d[key] = {
        "word":       key,
        "definition": definition.strip(),
        "examples":   examples or [],
        "domain":     domain.upper(),
        "source":     source,
        "created_at": existing.get("created_at", now_iso_z()) if existing else now_iso_z(),
        "uses":       existing.get("uses", 0) if existing else 0,
    }
    _save(d)


def learn_from_rule(rule: Dict) -> None:
    """
    Extract key noun/verb tokens from a rule's conclusion and add them
    with auto-generated definitions.
    """
    conclusion = rule.get("conclusion", "")
    domain = _rule_domain(rule)
    if not conclusion:
        return

    tokens = re.findall(r"[a-z][a-z0-9]*", conclusion.lower())
    candidates = [t for t in tokens if len(t) > 3 and t not in _STOPWORDS]

    for token in candidates[:4]:
        definition = f"A {domain} concept: {conclusion[:100]}"
        add_word(token, definition, domain=domain, source="rule_engine")


def enrich_explanation(text: str) -> str:
    """
    Scan text for tokens that appear in the dictionary and append a
    'Terms: word=definition' footnote for any matches.
    """
    _ensure_populated()
    d = _load()
    if not d:
        return text

    tokens = set(re.findall(r"[a-z][a-z0-9]*", text.lower()))
    matched = []
    for token in sorted(tokens):
        if len(token) <= 3:
            continue
        entry = d.get(token)
        if entry:
            entry["uses"] = entry.get("uses", 0) + 1
            matched.append(f"{token}={entry['definition'][:80]}")

    if not matched:
        return text

    # Persist updated use counts
    _save(d)
    return text + "\n\nTerms: " + "; ".join(matched)


def auto_populate_from_rules() -> None:
    """
    Call learn_from_rule for all active rules.
    Skips if the dictionary already has more than 50 entries.
    """
    d = _load()
    if len(d) > 50:
        return
    try:
        from symbolic.rule_engine import get_all_rules
        rules = get_all_rules()
        for rule in rules:
            if rule.get("source") != "tombstoned":
                learn_from_rule(rule)
        log_activity(f"[sym_dict] auto_populate: {len(_load())} words after processing {len(rules)} rules")
    except Exception as e:
        log_activity(f"[sym_dict] auto_populate error: {e}")


def get_stats() -> Dict:
    """Return {total_words, domains, most_used}."""
    d = _load()
    domain_counts: Dict[str, int] = {}
    most_used = ("", 0)
    for entry in d.values():
        dom = entry.get("domain", "GENERAL")
        domain_counts[dom] = domain_counts.get(dom, 0) + 1
        uses = entry.get("uses", 0)
        if uses > most_used[1]:
            most_used = (entry.get("word", ""), uses)
    return {
        "total_words": len(d),
        "domains":     domain_counts,
        "most_used":   {"word": most_used[0], "uses": most_used[1]},
    }


# ─── Internal helpers ────────────────────────────────────────────────────────

_DOMAIN_KW: Dict[str, List[str]] = {
    "SOCIAL":    ["user", "ric", "person", "conversation", "relationship"],
    "TECHNICAL": ["code", "error", "system", "build", "function", "import"],
    "EMOTIONAL": ["emotion", "mood", "exploration_drive", "risk_estimate", "resource_deficit"],
    "PLANNING":  ["goal", "plan", "step", "decision", "strategy", "milestone"],
    "COGNITIVE": ["rule", "memory", "learn", "pattern", "concept", "reason"],
}


def _rule_domain(rule: Dict) -> str:
    text = " ".join((rule.get("conditions") or []) + [rule.get("conclusion", "")])
    lower = text.lower()
    scores = {d: sum(1 for kw in kws if kw in lower) for d, kws in _DOMAIN_KW.items()}
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "GENERAL"
