# brain/symbolic/rule_engine.py
# Structured if→then inference engine.
#
# Rules are stored in data/symbolic_rules.json.  The casual_rules.txt file
# (natural-language heuristics) is imported on first load and converted to
# structured rules automatically.
#
# SCIENTIFIC BASIS:
#   Newell & Simon (1972) — "Human Problem Solving." Prentice-Hall.
#   Classical forward-chaining production system: match condition patterns
#   against working memory, fire the highest-priority matching rule.
#   Minsky (1975) — "A framework for representing knowledge." In P. H. Winston
#   (Ed.), The Psychology of Computer Vision. McGraw-Hill.
#   Frame-based knowledge: each rule bundles conditions, conclusions, and
#   metadata into a self-contained unit.
#   Anderson (1983) ACT-R — "The Architecture of Cognition." Harvard UP.
#   Production rules carry not just condition→action but declarative knowledge
#   about WHY the rule fires (causal claim) and WHAT to expect (prediction).
#   Schank (1982), Kolodner (1993) Case-Based Reasoning — cases store
#   situation + outcome + lesson + adaptation, not just observation labels.
#   Mitchell, Keller & Kedar-Cabelli (1986) Explanation-Based Learning —
#   store the causal explanation, not just the surface outcome.
#
# Rule schema (all new fields optional — fully backward-compatible):
#   {
#     "id":                str,        # unique slug
#     "conditions":        [str],      # keyword / pattern strings (AND-matched)
#     "negations":         [str],      # must NOT appear (optional)
#     "conclusion":        str,        # what to conclude / answer
#     "action":            str|None,   # optional fn_name to call
#     "confidence":        float,      # 0–1, decays if wrong
#     "hits":              int,        # times successfully applied
#     "source":            str,        # "casual_rules"|"crystallization"|"user"|"knowledge_formation"
#     "created_at":        str,        # ISO timestamp
#     # ── Knowledge structure fields (Layer 1) ──────────────────────────────
#     "causal_claim":      {           # structured causal relationship (Pearl 2000)
#       "cause": str,                  #   what drives this situation
#       "effect": str,                 #   what it produces
#       "mechanism": str               #   why / how the causal link operates
#     } | None,
#     "prediction":        str|None,   # what will happen if the rule fires and is unaddressed
#     "recommended_action": str|None,  # concrete intervention to reduce the error (Carver & Scheier 1982)
#     "abstraction_level": int,        # 1=specific event, 2=pattern, 3=principle, 4=meta-principle
#     "evidence_ids":      [str],      # IDs of child rules / observations this was synthesised from
#     "parent_id":         str|None,   # ID of a higher-level rule that subsumes this one
#   }
#
# The match() function returns the best-matching rule or None.
# apply() returns the conclusion string and optionally logs a hit.
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import CASUAL_RULES, DATA_DIR

SYMBOLIC_RULES_FILE = DATA_DIR / "symbolic_rules.json"

_rules_cache: List[Dict] = []
_cache_ts: float = 0.0
_CACHE_TTL: float = 120.0  # reload rules every 2 min


# ─── Load / bootstrap ─────────────────────────────────────────────────────────

def _load_rules(force: bool = False) -> List[Dict]:
    global _rules_cache, _cache_ts
    if not force and _rules_cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _rules_cache
    raw = load_json(SYMBOLIC_RULES_FILE, default_type=list) or []
    if not raw:
        raw = _import_casual_rules()
        save_json(SYMBOLIC_RULES_FILE, raw)
    _rules_cache = raw
    _cache_ts = time.time()
    return _rules_cache


def _import_casual_rules() -> List[Dict]:
    """Convert casual_rules.txt into structured rule dicts."""
    rules: List[Dict] = []
    try:
        text = CASUAL_RULES.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return rules
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Try "IF … THEN …" or "if … then …"
        m = re.match(r"(?:if|IF)\s+(.+?)\s+(?:then|THEN)\s+(.+)", line, re.IGNORECASE)
        if m:
            cond_text, conclusion = m.group(1).strip(), m.group(2).strip()
            conditions = [c.strip() for c in re.split(r"\band\b", cond_text, flags=re.IGNORECASE) if c.strip()]
        else:
            # plain sentence → treat whole line as a conclusion with no conditions
            conditions, conclusion = [], line
        rid = hashlib.md5(line.encode()).hexdigest()[:10]
        rules.append(_make_rule(rid, conditions, conclusion, source="casual_rules"))
    log_activity(f"[rule_engine] Imported {len(rules)} rules from casual_rules.txt")
    return rules


def _make_rule(
    rid: str,
    conditions: List[str],
    conclusion: str,
    *,
    negations: Optional[List[str]] = None,
    action: Optional[str] = None,
    confidence: float = 0.75,
    source: str = "unknown",
    causal_claim: Optional[Dict] = None,
    prediction: Optional[str] = None,
    recommended_action: Optional[str] = None,
    abstraction_level: int = 1,
    evidence_ids: Optional[List[str]] = None,
    parent_id: Optional[str] = None,
) -> Dict:
    return {
        "id":                 rid,
        "conditions":         conditions,
        "negations":          negations or [],
        "conclusion":         conclusion,
        "action":             action,
        "confidence":         confidence,
        "hits":               0,
        "source":             source,
        "created_at":         datetime.now(timezone.utc).isoformat(),
        # Knowledge structure fields — Anderson (1983) ACT-R, Schank (1982) CBR
        "causal_claim":       causal_claim,
        "prediction":         prediction,
        "recommended_action": recommended_action,
        "abstraction_level":  abstraction_level,
        "evidence_ids":       evidence_ids or [],
        "parent_id":          parent_id,
    }


# ─── Matching ─────────────────────────────────────────────────────────────────

def _score_rule(rule: Dict, text: str) -> float:
    """Return match score 0–1; 0 means no match."""
    lowered = text.lower()
    conditions = rule.get("conditions") or []
    negations = rule.get("negations") or []

    if negations and any(n.lower() in lowered for n in negations):
        return 0.0

    if not conditions:
        return rule.get("confidence", 0.5) * 0.2  # unconditional rules score low

    matched = sum(1 for c in conditions if c.lower() in lowered)
    if matched == 0:
        return 0.0
    ratio = matched / len(conditions)
    return ratio * rule.get("confidence", 0.75)


def match(text: str, threshold: float = 0.4) -> Optional[Dict]:
    """Return the best-matching rule for `text`, or None."""
    rules = _load_rules()
    best: Optional[Dict] = None
    best_score = threshold
    for rule in rules:
        s = _score_rule(rule, text)
        if s > best_score:
            best_score = s
            best = rule
    return best


def match_all(text: str, threshold: float = 0.35) -> List[Tuple[Dict, float]]:
    """Return all matching rules sorted by score descending."""
    rules = _load_rules()
    results = []
    for rule in rules:
        s = _score_rule(rule, text)
        if s >= threshold:
            results.append((rule, s))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ─── Apply ────────────────────────────────────────────────────────────────────

def apply(rule: Dict, *, log: bool = True) -> str:
    """Return the rule's conclusion and bump hit count."""
    rule["hits"] = rule.get("hits", 0) + 1
    if log:
        log_activity(f"[rule_engine] Applied rule '{rule['id']}': {rule['conclusion'][:80]}")
    _flush_hit(rule)
    return rule["conclusion"]


def _flush_hit(rule: Dict) -> None:
    rules = _load_rules()
    for i, r in enumerate(rules):
        if r["id"] == rule["id"]:
            rules[i] = rule
            break
    save_json(SYMBOLIC_RULES_FILE, rules)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def add_rule(
    conditions: List[str],
    conclusion: str,
    *,
    negations: Optional[List[str]] = None,
    action: Optional[str] = None,
    confidence: float = 0.80,
    source: str = "crystallization",
    causal_claim: Optional[Dict] = None,
    prediction: Optional[str] = None,
    recommended_action: Optional[str] = None,
    abstraction_level: int = 1,
    evidence_ids: Optional[List[str]] = None,
    parent_id: Optional[str] = None,
) -> Dict:
    rid = hashlib.md5(conclusion.encode()).hexdigest()[:10]
    rules = _load_rules(force=True)
    for r in rules:
        if r["id"] == rid:
            # Update knowledge fields on existing rule if the caller provides them
            changed = False
            if causal_claim and not r.get("causal_claim"):
                r["causal_claim"] = causal_claim; changed = True
            if prediction and not r.get("prediction"):
                r["prediction"] = prediction; changed = True
            if recommended_action and not r.get("recommended_action"):
                r["recommended_action"] = recommended_action; changed = True
            if abstraction_level > r.get("abstraction_level", 1):
                r["abstraction_level"] = abstraction_level; changed = True
            if changed:
                save_json(SYMBOLIC_RULES_FILE, rules)
                _load_rules(force=True)
            return r
    rule = _make_rule(
        rid, conditions, conclusion,
        negations=negations, action=action,
        confidence=confidence, source=source,
        causal_claim=causal_claim, prediction=prediction,
        recommended_action=recommended_action,
        abstraction_level=abstraction_level,
        evidence_ids=evidence_ids, parent_id=parent_id,
    )
    rules.append(rule)
    save_json(SYMBOLIC_RULES_FILE, rules)
    _load_rules(force=True)
    log_activity(f"[rule_engine] New rule '{rid}' (L{abstraction_level}) from {source}: {conclusion[:80]}")
    return rule


def reinforce_rule(rule_id: str, confidence: Optional[float] = None) -> Optional[Dict]:
    """Strengthen an existing rule in place: bump hits (a re-observation is
    evidence) and ratchet confidence upward, never down. Returns the rule, or
    None if the id is unknown."""
    rules = _load_rules(force=True)
    for r in rules:
        if r["id"] == rule_id:
            r["hits"] = r.get("hits", 0) + 1
            if confidence is not None and confidence > r.get("confidence", 0.0):
                r["confidence"] = confidence
            save_json(SYMBOLIC_RULES_FILE, rules)
            _load_rules(force=True)
            return r
    return None


def penalize(rule_id: str, amount: float = 0.05) -> None:
    """Reduce confidence when a rule produced a wrong answer."""
    rules = _load_rules(force=True)
    for r in rules:
        if r["id"] == rule_id:
            r["confidence"] = max(0.1, r["confidence"] - amount)
            break
    save_json(SYMBOLIC_RULES_FILE, rules)
    _load_rules(force=True)


def get_all_rules() -> List[Dict]:
    return list(_load_rules())
