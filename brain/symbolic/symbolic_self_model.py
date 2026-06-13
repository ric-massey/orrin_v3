# brain/symbolic/symbolic_self_model.py
# Symbolic Self-Model & Identity — reflective reasoning about the rule set itself.
#
# This is the system's ability to reason about its own knowledge at the symbolic
# level, independent of the LLM-generated identity narrative in selfhood/identity.py.
#
# What it computes (all locally, no LLM):
#
#   knowledge_domains  — which domains I have rules in, with quality metrics
#   weak_areas         — domains with low hit rates, low confidence, or high revision
#   strong_areas       — domains with high hit counts and grounding scores
#   rule_health        — overall rule set statistics
#   concept_coverage   — named concepts and their member rule counts
#   causal_coverage    — how many causal edges I have per domain
#   self_assessment    — given a query, "how confident am I I can handle this?"
#
# Self-assessment feeds back into reasoning_router:
#   If self_assessment < 0.35 → force LLM even if rules match (low self-trust)
#   If self_assessment > 0.75 → lower LLM gate threshold (high self-trust)
#
# Also generates meta-rules about the rule set itself:
#   "My TECHNICAL rules are weak — prefer LLM for technical queries"
#   "My COGNITIVE rules are strong — trust symbolic resolution"
#
# Stored in data/symbolic_self_model.json, rebuilt every dream cycle.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import DATA_DIR

SELF_MODEL_SYMBOLIC_FILE = DATA_DIR / "symbolic_self_model.json"

# Persistent per-domain action credits (BEHAVIOR_FIX_PLAN Phase 4 / audit §9):
# domain quality used to depend only on rules, so scores never moved no matter
# what Orrin DID. Completed concrete plan steps credit the matching domain.
DOMAIN_CREDITS_FILE = DATA_DIR / "domain_action_credits.json"
_CREDIT_QUALITY_BONUS_CAP = 0.15   # cap so credits refine, never dominate, quality

_DOMAIN_KW: Dict[str, List[str]] = {
    "SOCIAL":     ["user", "ric", "person", "conversation", "relationship"],
    "TECHNICAL":  ["code", "error", "system", "build", "function", "import"],
    "EMOTIONAL":  ["emotion", "mood", "exploration_drive", "risk_estimate", "resource_deficit"],
    "PLANNING":   ["goal", "plan", "step", "decision", "strategy", "milestone"],
    "COGNITIVE":  ["rule", "memory", "learn", "pattern", "concept", "reason"],
}


# ─── Domain tagging for rules ─────────────────────────────────────────────────

def _rule_domain(rule: Dict) -> str:
    text = " ".join((rule.get("conditions") or []) + [rule.get("conclusion", "")])
    lower = text.lower()
    scores = {d: sum(1 for kw in kws if kw in lower) for d, kws in _DOMAIN_KW.items()}
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "GENERAL"


def classify_domain(text: str) -> str:
    """Map free text (a plan step, a goal title) onto a knowledge domain."""
    lower = str(text or "").lower()
    scores = {d: sum(1 for kw in kws if kw in lower) for d, kws in _DOMAIN_KW.items()}
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "GENERAL"


def credit_domain_action(text: str, amount: float = 1.0) -> str:
    """
    Metric hook: a completed concrete step credits the matching knowledge
    domain, so domain scores respond to ACTION, not just rule accumulation.
    Returns the credited domain.
    """
    domain = classify_domain(text)
    try:
        credits = load_json(DOMAIN_CREDITS_FILE, default_type=dict) or {}
        credits[domain] = round(float(credits.get(domain, 0.0)) + float(amount), 2)
        save_json(DOMAIN_CREDITS_FILE, credits)
    except Exception:
        pass
    return domain


def _domain_credit_bonus() -> Dict[str, float]:
    """Per-domain quality bonus from accumulated action credits (soft-capped)."""
    try:
        credits = load_json(DOMAIN_CREDITS_FILE, default_type=dict) or {}
    except Exception:
        return {}
    return {
        d: min(_CREDIT_QUALITY_BONUS_CAP, float(c or 0.0) * 0.01)
        for d, c in credits.items() if isinstance(c, (int, float))
    }


# ─── Build model ─────────────────────────────────────────────────────────────

def build_symbolic_self_model() -> Dict:
    """
    Compute the full symbolic self-model from current state.
    Writes to data/symbolic_self_model.json and returns the dict.
    """
    from symbolic.rule_engine import get_all_rules
    from symbolic.concept_formation import get_concepts
    from symbolic.causal_graph import get_all_edges
    from symbolic.ground_truth import audit_grounding_health
    from symbolic.prediction_engine import get_domain_error_rates
    from symbolic.rule_verifier import get_pending_revisions

    rules = get_all_rules()
    concepts = get_concepts()
    causal_edges = get_all_edges()
    grounding = audit_grounding_health()
    domain_errors = get_domain_error_rates()
    pending_revisions = len(get_pending_revisions())

    # ── Per-domain rule stats ─────────────────────────────────────────────────
    domain_stats: Dict[str, Dict] = {}
    for rule in rules:
        if rule.get("source") == "tombstoned":
            continue
        domain = _rule_domain(rule)
        if domain not in domain_stats:
            domain_stats[domain] = {
                "count": 0, "total_hits": 0, "total_conf": 0.0,
                "revisions": 0, "abstraction_count": 0,
            }
        ds = domain_stats[domain]
        ds["count"] += 1
        ds["total_hits"] += rule.get("hits", 0)
        ds["total_conf"] += rule.get("confidence", 0.75)
        if rule.get("source") == "abstraction":
            ds["abstraction_count"] += 1

    _credit_bonus = _domain_credit_bonus()
    knowledge_domains: Dict[str, Dict] = {}
    for domain, ds in domain_stats.items():
        n = ds["count"]
        mean_conf = round(ds["total_conf"] / n, 3) if n else 0.0
        mean_hits = round(ds["total_hits"] / n, 2) if n else 0.0
        pred_error = domain_errors.get(domain, 0.5)
        # pred_factor: pred_error=0.5 is the default when no prediction data exists —
        # treat it as mild uncertainty (0.25 error) rather than penalising by 50%.
        _pred_adj = 0.25 if 0.49 < pred_error < 0.51 else pred_error
        # hits_factor: floor at 0.35 — untested rules aren't proven bad, just new.
        _hits_factor = max(0.35, min(mean_hits / 5.0, 1.0))
        knowledge_domains[domain] = {
            "rule_count":     n,
            "mean_confidence": mean_conf,
            "mean_hits":       mean_hits,
            "prediction_error": pred_error,
            "abstraction_count": ds["abstraction_count"],
            "action_credit_bonus": _credit_bonus.get(domain, 0.0),
            # quality = conf × (1 − pred_adj) × hits_factor + action credits
            # (completed concrete steps move the score — audit §9)
            "quality": round(
                mean_conf * (1 - _pred_adj) * _hits_factor + _credit_bonus.get(domain, 0.0),
                3),
        }
    # Domains with action credits but no rules yet still appear (and can move).
    for domain, bonus in _credit_bonus.items():
        if domain not in knowledge_domains and bonus > 0:
            knowledge_domains[domain] = {
                "rule_count": 0, "mean_confidence": 0.0, "mean_hits": 0.0,
                "prediction_error": 0.5, "abstraction_count": 0,
                "action_credit_bonus": bonus, "quality": round(bonus, 3),
            }

    # ── Causal edges per domain ────────────────────────────────────────────────
    causal_by_domain: Dict[str, int] = {}
    for edge in causal_edges:
        cause_text = edge.get("cause", "")
        lower = cause_text.lower()
        domain = "GENERAL"
        for d, kws in _DOMAIN_KW.items():
            if any(kw in lower for kw in kws):
                domain = d
                break
        causal_by_domain[domain] = causal_by_domain.get(domain, 0) + 1

    # ── Weak / strong areas ──────────────────────────────────────────────────
    sorted_domains = sorted(knowledge_domains.items(), key=lambda x: x[1]["quality"])
    weak_areas  = [d for d, stats in sorted_domains if stats["quality"] < 0.35]
    strong_areas = [d for d, stats in sorted_domains if stats["quality"] >= 0.65]

    # ── Overall rule health ──────────────────────────────────────────────────
    active_rules = [r for r in rules if r.get("source") != "tombstoned"]
    tombstoned   = [r for r in rules if r.get("source") == "tombstoned"]
    mean_conf_all = round(
        sum(r.get("confidence", 0.75) for r in active_rules) / max(len(active_rules), 1),
        3
    )

    rule_health = {
        "total_rules":      len(rules),
        "active_rules":     len(active_rules),
        "tombstoned_rules": len(tombstoned),
        "mean_confidence":  mean_conf_all,
        "pending_revisions": pending_revisions,
        "grounding":        grounding,
    }

    # ── Concept coverage ─────────────────────────────────────────────────────
    concept_coverage = [
        {
            "name":         c["name"],
            "type":         c["type"],
            "member_count": len(c.get("member_rules", [])),
            "dominant":     c.get("dominant_tokens", [])[:3],
        }
        for c in concepts
    ]

    model = {
        "built_at":          datetime.now(timezone.utc).isoformat(),
        "knowledge_domains": knowledge_domains,
        "weak_areas":        weak_areas,
        "strong_areas":      strong_areas,
        "rule_health":       rule_health,
        "concept_coverage":  concept_coverage,
        "causal_edges_total": len(causal_edges),
        "causal_by_domain":  causal_by_domain,
        "domain_error_rates": domain_errors,
    }

    save_json(SELF_MODEL_SYMBOLIC_FILE, model)
    log_activity(
        f"[sym_self] Model built: {len(active_rules)} rules, "
        f"strong={strong_areas}, weak={weak_areas}, "
        f"causal_edges={len(causal_edges)}"
    )
    return model


def get_symbolic_self_model() -> Dict:
    """Load the last-built model (or build now if stale/missing)."""
    model = load_json(SELF_MODEL_SYMBOLIC_FILE, default_type=dict)
    if not model:
        return build_symbolic_self_model()
    return model


# ─── Self-assessment ─────────────────────────────────────────────────────────

def self_assess(query: str) -> Dict:
    """
    Given a query, return a self-assessment dict:
      {
        "confidence": float,   # 0–1 how confident I am I can answer symbolically
        "domain":     str,
        "reason":     str,
        "trust_symbolic": bool,  # True → trust symbolic resolution
      }
    """
    model = get_symbolic_self_model()
    query_lower = query.lower()

    # Best-match domain classification: count keyword hits per domain and pick
    # the winner. SOCIAL requires ≥2 matches to prevent "user" (ubiquitous in
    # internal prompts) from swamping every query into a zero-rule domain.
    _DOMAIN_MIN_HITS = {"SOCIAL": 2}
    _scores = {d: sum(1 for kw in kws if kw in query_lower) for d, kws in _DOMAIN_KW.items()}
    _eligible = {d: s for d, s in _scores.items() if s >= _DOMAIN_MIN_HITS.get(d, 1)}
    domain = max(_eligible, key=lambda d: _eligible[d]) if _eligible else "GENERAL"

    kd = (model.get("knowledge_domains") or {}).get(domain, {})
    quality = kd.get("quality", 0.3)
    rule_count = kd.get("rule_count", 0)
    pred_error = kd.get("prediction_error", 0.5)

    # Self-confidence: quality + rule density bonus (caps at 0.25 for 15+ rules).
    # Divisor=15 means 3 rules → 0.20, 5 rules → 0.25 (capped), giving 3-rule
    # domains slightly too little confidence to trust on their own.
    density_bonus = min(rule_count / 15.0, 0.25)
    confidence = round(min(quality + density_bonus, 1.0), 3)

    weak_areas   = model.get("weak_areas", [])
    strong_areas = model.get("strong_areas", [])

    if domain in strong_areas:
        reason = f"Strong domain: {rule_count} rules, quality={quality:.2f}"
    elif domain in weak_areas:
        reason = f"Weak domain: low quality ({quality:.2f}), pred_error={pred_error:.2f}"
    else:
        reason = f"Moderate domain: {rule_count} rules, quality={quality:.2f}"

    # 0.40: a domain with 5+ rules passes; 3 rules does not (0.391 < 0.40).
    # Prevents domains with almost no rules from trusting their own coverage.
    trust = confidence >= 0.40

    return {
        "confidence":     confidence,
        "domain":         domain,
        "reason":         reason,
        "trust_symbolic": trust,
        "rule_count":     rule_count,
        "quality":        quality,
    }


# ─── Meta-rules from self-model ──────────────────────────────────────────────

def generate_self_meta_rules() -> List[Dict]:
    """
    Inspect the symbolic self-model and generate meta-rules about which
    domains to trust symbolically vs defer to LLM.
    Only generates rules when there's enough evidence (>= 5 rules in domain).
    Returns list of newly added meta-rule dicts.
    """
    model = get_symbolic_self_model()
    kd = model.get("knowledge_domains", {})
    added = []

    try:
        from symbolic.meta_rules import add_meta_rule
        for domain, stats in kd.items():
            if stats.get("rule_count", 0) < 5:
                continue
            quality = stats.get("quality", 0.5)
            if quality >= 0.65:
                mr = add_meta_rule(
                    name=f"Trust symbolic for {domain} queries",
                    condition="ambiguous",
                    action="prefer_specific",
                    priority=15,
                    rationale=f"{domain} domain has quality={quality:.2f} — symbolic resolution preferred",
                    source="symbolic_self_model",
                )
                added.append(mr)
            elif quality < 0.30:
                mr = add_meta_rule(
                    name=f"Defer LLM for weak {domain} queries",
                    condition="low_conf",
                    action="defer_llm",
                    priority=4,
                    rationale=f"{domain} domain has quality={quality:.2f} — LLM preferred",
                    source="symbolic_self_model",
                )
                added.append(mr)
    except Exception as e:
        log_activity(f"[sym_self] meta-rule generation failed: {e}")

    return added
