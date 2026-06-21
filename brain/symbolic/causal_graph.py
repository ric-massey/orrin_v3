# brain/symbolic/causal_graph.py
#
# Causal structure grounded in Pearl (2000, 2018) and Granger (1969).
#
# SCIENTIFIC BASIS
# ──────────────────────────────────────────────────────────────────
# Pearl's Ladder of Causation (2018):
#   Level 1 — Association:    P(Y | X)       — temporal co-occurrence
#   Level 2 — Intervention:   P(Y | do(X))   — Orrin deliberately took action X
#   Level 3 — Counterfactual: P(Y | ~X, ~X)  — would Y have happened without X?
#
# Granger causality (Granger 1969):
#   X Granger-causes Y if past X improves prediction of Y beyond Y's own history.
#   Implemented here as: X→Y strengthens only when X precedes Y AND X is NOT
#   reliably preceded by a third variable Z that also precedes Y (confound check).
#
# Confounding (Pearl 2000, Chapter 3):
#   If Z → X and Z → Y both exist with high confidence, X→Y is likely confounded.
#   We weaken the X→Y edge's causal_score when a common cause Z is detected.
#
# Edge schema:
#   cause, effect, strength (EMA-updated), evidence_count, counterfactual_count,
#   intervention_count (Level 2 evidence — strongest), confound_score (0-1, reduces
#   causal_score), causal_score (final credibility), source, layer (1/2/3).
#
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR

CAUSAL_GRAPH_FILE = DATA_DIR / "causal_graph.json"

_EMA_ALPHA          = 0.20  # learning rate for strength updates
_MIN_EVIDENCE       = 5     # minimum confirmed observations to trust an edge (was 2 — too low)
_MIN_CAUSAL_SCR     = 0.30  # minimum causal_score for query results
_WM_SEQ_MIN_FREQ    = 3     # X→Y must co-occur this many times before a temporal edge is added
_CONFOUND_THRESHOLD = 0.55  # common-cause score above this weakens causal_score

# Lock/commit thresholds: once an edge is this credible AND has this much
# intervention (Pearl Level 2) evidence, treat it as established ground truth and
# STOP re-intervening on it — Orrin no longer burns cycles re-testing what he
# already knows. Falsifiable: a counterfactual that drops strength re-opens it.
_ESTABLISH_SCORE    = 0.80
_ESTABLISH_IV       = 6
_REOPEN_STRENGTH    = 0.60


def _load_edges() -> List[Dict]:
    return load_json(CAUSAL_GRAPH_FILE, default_type=list) or []


def _save_edges(edges: List[Dict]) -> None:
    save_json(CAUSAL_GRAPH_FILE, edges[-500:])


def _edge_id(cause: str, effect: str) -> str:
    return hashlib.md5(f"{cause.lower()}→{effect.lower()}".encode()).hexdigest()[:12]


def _compute_causal_score(edge: Dict) -> float:
    """
    causal_score integrates three Pearl levels:
      - Level 1 (observation): base EMA strength
      - Level 2 (intervention): boosts score — do(X) evidence is stronger than P(Y|X)
      - Level 3 (counterfactual): penalizes score
    Plus confound penalty: if a common cause Z→X and Z→Y is known, score drops.
    Rescorla-Wagner sample penalty: ramps from 0→1 as evidence grows to _MIN_EVIDENCE.
    """
    ev   = int(edge.get("evidence_count", 0))
    cf   = int(edge.get("counterfactual_count", 0))
    iv   = int(edge.get("intervention_count", 0))
    conf = float(edge.get("confound_score", 0.0))
    total = ev + cf
    cf_ratio = cf / total if total else 0.0

    # Intervention evidence counts double (Pearl Level 2 > Level 1)
    effective_ev = ev + iv * 2
    sample_penalty = min(1.0, effective_ev / _MIN_EVIDENCE)
    strength = float(edge.get("strength", 0.5))
    confound_penalty = 1.0 - (conf * 0.4)  # confounding reduces score up to 40%
    return round(strength * (1.0 - cf_ratio) * sample_penalty * confound_penalty, 4)


def _maybe_establish(edge: Dict) -> None:
    """Promote a well-supported edge to 'established' (locked) ground truth."""
    if (not edge.get("established")
            and edge.get("causal_score", 0.0) >= _ESTABLISH_SCORE
            and int(edge.get("intervention_count", 0)) >= _ESTABLISH_IV):
        edge["established"] = True
        log_activity(f"[causal] Established (locked): "
                     f"'{edge['cause'][:40]}' → '{edge['effect'][:40]}'")


def is_established(cause: str, effect: str) -> bool:
    """True if the cause→effect edge is locked as established ground truth."""
    eid = _edge_id(cause, effect)
    return any(e.get("id") == eid and e.get("established") for e in _load_edges())


def update_edge(
    cause: str,
    effect: str,
    *,
    confirmed: bool = True,
    counterfactual: bool = False,
    intervention: bool = False,   # Pearl Level 2: Orrin deliberately did this
    source: str = "rule_chain",
) -> Dict:
    """
    Add evidence to a causal edge.
    intervention=True marks Pearl Level 2 evidence (do(X)) — worth double.
    """
    edges = _load_edges()
    eid = _edge_id(cause, effect)
    ts = datetime.now(timezone.utc).isoformat()

    for edge in edges:
        if edge["id"] == eid:
            if confirmed:
                edge["evidence_count"] = edge.get("evidence_count", 0) + 1
                old = float(edge.get("strength", 0.5))
                edge["strength"] = round(old + _EMA_ALPHA * (1.0 - old), 4)
            if intervention:
                edge["intervention_count"] = edge.get("intervention_count", 0) + 1
                edge.setdefault("layer", 1)
                edge["layer"] = max(edge["layer"], 2)
            if counterfactual:
                edge["counterfactual_count"] = edge.get("counterfactual_count", 0) + 1
                old = float(edge.get("strength", 0.5))
                edge["strength"] = round(old + _EMA_ALPHA * (0.0 - old), 4)
                edge["layer"] = max(edge.get("layer", 1), 3)
            edge["causal_score"] = _compute_causal_score(edge)
            # Lock when credible enough; a contradicting counterfactual that drops
            # strength below the floor re-opens a locked-but-wrong edge for revision.
            if counterfactual and float(edge.get("strength", 0.0)) < _REOPEN_STRENGTH:
                edge["established"] = False
            else:
                _maybe_establish(edge)
            edge["last_updated"] = ts
            _save_edges(edges)
            return edge

    # New edge
    edge = {
        "id":                   eid,
        "cause":                cause,
        "effect":               effect,
        "strength":             0.60 if confirmed else 0.30,
        "evidence_count":       1 if confirmed else 0,
        "counterfactual_count": 1 if counterfactual else 0,
        "intervention_count":   1 if intervention else 0,
        "confound_score":       0.0,
        "causal_score":         0.0,
        "layer":                2 if intervention else (3 if counterfactual else 1),
        "source":               source,
        "created_at":           ts,
        "last_updated":         ts,
    }
    edge["causal_score"] = _compute_causal_score(edge)
    _maybe_establish(edge)
    edges.append(edge)
    _save_edges(edges)
    log_activity(f"[causal] New edge (L{edge['layer']}): '{cause[:40]}' → '{effect[:40]}' ({source})")
    return edge


def _check_confounders(cause: str, effect: str, edges: List[Dict]) -> float:
    """
    Look for common causes Z such that Z→cause and Z→effect both exist.
    Returns confound_score 0.0–1.0.  Higher = more likely confounded.
    Pearl (2000): confounding bias = P(Y|X) - P(Y|do(X)).
    """
    cause_l  = cause.lower()
    effect_l = effect.lower()

    # Find all nodes that point TO cause
    causes_of_cause = {
        e["cause"].lower() for e in edges
        if cause_l in e.get("effect", "").lower()
        and e.get("causal_score", 0) >= _MIN_CAUSAL_SCR
    }
    if not causes_of_cause:
        return 0.0

    # Among those, find how many also point TO effect
    confounder_strength = 0.0
    for e in edges:
        if e.get("cause", "").lower() in causes_of_cause:
            if effect_l in e.get("effect", "").lower():
                confounder_strength = max(confounder_strength, float(e.get("causal_score", 0)))

    return round(confounder_strength, 3)


def check_and_update_confounding() -> None:
    """
    Run confound detection on all edges and update their confound_score.
    Called periodically (e.g., once per dream cycle) not every edge update.
    """
    edges = _load_edges()
    changed = False
    for edge in edges:
        old_cs = float(edge.get("confound_score", 0.0))
        new_cs = _check_confounders(edge["cause"], edge["effect"], edges)
        if abs(new_cs - old_cs) > 0.05:
            edge["confound_score"] = new_cs
            edge["causal_score"] = _compute_causal_score(edge)
            changed = True
    if changed:
        _save_edges(edges)


def get_causes(effect: str, *, min_score: float = _MIN_CAUSAL_SCR) -> List[Dict]:
    edges = _load_edges()
    eff_l = effect.lower()
    results = [e for e in edges
               if eff_l in e.get("effect", "").lower()
               and e.get("causal_score", 0) >= min_score]
    return sorted(results, key=lambda e: e["causal_score"], reverse=True)


def get_effects(cause: str, *, min_score: float = _MIN_CAUSAL_SCR) -> List[Dict]:
    edges = _load_edges()
    cau_l = cause.lower()
    results = [e for e in edges
               if cau_l in e.get("cause", "").lower()
               and e.get("causal_score", 0) >= min_score]
    return sorted(results, key=lambda e: e["causal_score"], reverse=True)


def get_causal_effects(query: str) -> List[str]:
    effects = get_effects(query)
    return [e["effect"] for e in effects[:3]]


def causal_explanation(query: str) -> Optional[str]:
    words = set(re.findall(r"[a-z][a-z0-9]*", query.lower()))
    edges = _load_edges()
    relevant = [e for e in edges
                if e.get("causal_score", 0) >= _MIN_CAUSAL_SCR
                and (words & set(re.findall(r"[a-z][a-z0-9]*", e.get("cause","").lower()))
                     or words & set(re.findall(r"[a-z][a-z0-9]*", e.get("effect","").lower())))]
    if not relevant:
        return None
    best = max(relevant, key=lambda e: e["causal_score"])
    layer_label = {1: "associated with", 2: "causes (intervention)", 3: "counterfactually causes"}
    pred = layer_label.get(best.get("layer", 1), "associated with")
    return (f"[causal] '{best['cause'][:60]}' {pred} '{best['effect'][:60]}' "
            f"(score={best['causal_score']:.2f}, n={best['evidence_count']}, L{best.get('layer',1)})")


def discover_from_rule_chain(chain: List[Dict]) -> List[Dict]:
    new_edges = []
    for i in range(len(chain) - 1):
        r1, r2 = chain[i], chain[i + 1]
        if r1.get("hits", 0) < _MIN_EVIDENCE or r2.get("hits", 0) < _MIN_EVIDENCE:
            continue
        cause  = r1.get("conclusion", "")[:80]
        effect = r2.get("conclusion", "")[:80]
        if cause and effect and cause != effect:
            e = update_edge(cause, effect, confirmed=True, source="rule_chain")
            new_edges.append(e)
    return new_edges


def discover_from_wm_sequence(wm_entries: List[Dict]) -> List[Dict]:
    """
    Granger-style temporal discovery: X→Y only proposed when X precedes Y
    at least _WM_SEQ_MIN_FREQ times in this window. Single occurrences are noise.
    """
    event_types = [
        e.get("event_type", "")
        for e in wm_entries
        if isinstance(e, dict) and e.get("event_type")
    ]

    # Count consecutive pair frequencies across the window
    pair_counts: defaultdict = defaultdict(int)
    for i in range(len(event_types) - 1):
        et1, et2 = event_types[i], event_types[i + 1]
        if et1 and et2 and et1 != et2:
            pair_counts[f"{et1}→{et2}"] += 1

    new_edges = []
    for pair_key, count in pair_counts.items():
        if count < _WM_SEQ_MIN_FREQ:
            continue
        et1, et2 = pair_key.split("→", 1)
        e = update_edge(et1, et2, confirmed=True, source="temporal")
        new_edges.append(e)
    return new_edges


def record_intervention(action: str, observed_effect: str) -> Dict:
    """
    Pearl Level 2: Orrin deliberately executed `action` and observed `effect`.
    do(action) evidence is causally stronger than passive observation.
    """
    return update_edge(action, observed_effect, confirmed=True, intervention=True, source="intervention")


def get_all_edges() -> List[Dict]:
    return _load_edges()


def update_from_prediction_outcome(pred: Dict, correct: bool) -> Optional[Dict]:
    rule_id = pred.get("rule_id", "")
    if not rule_id:
        return None
    pred_text = pred.get("prediction", "")
    m = re.search(r"If '(.+?)' recurs", pred_text)
    cause = m.group(1)[:80] if m else pred_text[:60]
    effect = (pred.get("outcome") or pred.get("prediction", ""))[:80]
    if not cause or not effect or cause == effect:
        return None
    return update_edge(
        cause, effect,
        confirmed=correct,
        counterfactual=(not correct),
        source="prediction_outcome",
    )


def simulate_counterfactual(cause: str, effect: str, *, context: Optional[Dict] = None) -> Dict:
    """
    Pearl Level 3: estimate whether effect would occur without cause.
    Searches for alternative rules producing effect without cause in conditions.
    """
    try:
        from brain.symbolic.rule_engine import get_all_rules
    except Exception:
        return {"counterfactual_likely": False, "alternative_rules": [], "action_taken": "skipped"}

    cause_tokens  = set(re.findall(r"[a-z][a-z0-9]+", cause.lower()))
    effect_tokens = set(re.findall(r"[a-z][a-z0-9]+", effect.lower()))
    rules = get_all_rules()
    alternatives: List[str] = []
    for r in rules:
        if r.get("source") == "tombstoned":
            continue
        conc_tokens = set(re.findall(r"[a-z][a-z0-9]+", r.get("conclusion", "").lower()))
        if not (conc_tokens & effect_tokens):
            continue
        cond_tokens = set(re.findall(r"[a-z][a-z0-9]+", str(r.get("conditions", "")).lower()))
        if cause_tokens & cond_tokens:
            continue
        if float(r.get("confidence", 0)) >= 0.45 and int(r.get("hits", 0)) >= 1:
            alternatives.append(r.get("id", ""))

    counterfactual_likely = len(alternatives) >= 2
    action = "none"
    if counterfactual_likely:
        update_edge(cause, effect, confirmed=False, counterfactual=True, source="simulation")
        action = "cf_registered"

    return {
        "counterfactual_likely": counterfactual_likely,
        "alternative_rules":     alternatives,
        "action_taken":          action,
    }
