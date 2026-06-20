# brain/symbolic/prediction_engine.py
# Stronger world-model prediction engine.
#
# Augments the existing LLM-based prediction.py with:
#
#   1. Symbolic predictions (zero LLM):
#      When a high-confidence rule fires, its conclusion becomes a prediction
#      about what will happen if the same conditions re-occur.
#      These are typed and domain-tagged.
#
#   2. Domain-specific accuracy tracking:
#      Each prediction carries a domain tag (SOCIAL, TECHNICAL, EMOTIONAL,
#      PLANNING, COGNITIVE).  Accuracy is tracked per domain so
#      intrinsic_motivation.uncertainty() can use domain-weighted error
#      rates instead of a single global miss-rate.
#
#   3. Structured prediction schema:
#      Extends existing schema with: domain, basis (symbolic|llm), rule_id,
#      confidence_interval, and resolution fields.
#
#   4. Prediction chains:
#      When prediction P comes true, check if P's conclusion matches any
#      rule condition → generate chained prediction P2 from that rule.
#      This gives the system "if A then B then C" world-model chains.
#
# Data: data/predictions.json (extends existing schema — backward compat)
#       data/prediction_domain_stats.json (domain accuracy ledger)
from __future__ import annotations
from core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import PREDICTIONS_FILE, DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

DOMAIN_STATS_FILE = DATA_DIR / "prediction_domain_stats.json"

# ─── Domain classification ────────────────────────────────────────────────────

_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "SOCIAL":     ["user", "ric", "person", "conversation", "talk", "ask", "feel",
                   "relationship", "trust", "respond"],
    "TECHNICAL":  ["code", "error", "bug", "system", "file", "process", "build",
                   "function", "module", "import", "data"],
    "EMOTIONAL":  ["emotion", "mood", "exploration_drive", "risk_estimate", "stagnation_signal", "resource_deficit",
                   "wonder", "stress", "calm", "feeling"],
    "PLANNING":   ["goal", "plan", "step", "milestone", "decision", "strategy",
                   "objective", "approach", "task", "next"],
    "COGNITIVE":  ["rule", "memory", "learn", "pattern", "insight", "concept",
                   "analogy", "abstract", "reason", "predict"],
}


def classify_domain(text: str) -> str:
    lower = text.lower()
    scores = {d: sum(1 for kw in kws if kw in lower)
              for d, kws in _DOMAIN_KEYWORDS.items()}
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "GENERAL"


# ─── Symbolic prediction generation ──────────────────────────────────────────

def make_symbolic_prediction(
    query: str,
    rule_id: str,
    conclusion: str,
    confidence: float,
    *,
    horizon: str = "short",
    context: Optional[Dict] = None,
) -> Dict:
    """
    Turn a fired rule's conclusion into a structured future prediction.
    The prediction: "If similar conditions recur, expect: <conclusion>."
    """
    domain = classify_domain(query + " " + conclusion)
    pred_text = f"If '{query[:60]}' recurs: {conclusion[:150]}"
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "prediction":         pred_text,
        "horizon":            horizon,
        "confidence":         round(min(confidence * 0.9, 0.90), 3),
        "confidence_interval": [round(max(0, confidence - 0.15), 3),
                                 round(min(1, confidence + 0.10), 3)],
        "created_ts":         ts,
        "status":             "pending",
        "checked_ts":         None,
        "outcome":            None,
        "domain":             domain,
        "basis":              "symbolic",
        "rule_id":            rule_id,
        "resolved":           False,
        "correct":            None,
    }


def save_symbolic_predictions(preds: List[Dict]) -> None:
    """Append symbolic predictions to PREDICTIONS_FILE."""
    if not preds:
        return
    existing = load_json(PREDICTIONS_FILE, default_type=list) or []
    existing.extend(preds)
    save_json(PREDICTIONS_FILE, existing[-150:])
    log_activity(f"[prediction_engine] Saved {len(preds)} symbolic prediction(s).")


# ─── Domain accuracy tracking ────────────────────────────────────────────────

def update_domain_stats(
    domain: str,
    correct: bool,
    *,
    basis: str = "symbolic",
    mismatch_score: Optional[float] = None,
    weight: float = 1.0,
) -> None:
    """
    Called when a prediction is resolved.  Updates running accuracy per domain.
    Uses exponential moving average (α=0.15) so old errors fade.
    mismatch_score: 0.0 = perfect match, 1.0 = complete miss (overrides binary correct).
    weight: evidence weight in (0, 1] — inner predictions graded by self-report
    alone (no behavioral receipt) pass 0.5, so a feeling that nothing outside
    him confirmed moves the ledger at half strength (master plan Phase 1.3).
    """
    weight = max(0.0, min(1.0, float(weight))) or 1.0
    stats = load_json(DOMAIN_STATS_FILE, default_type=dict) or {}
    if domain not in stats:
        stats[domain] = {"accuracy": 0.50, "total": 0, "correct": 0, "symbolic_total": 0}

    entry = stats[domain]
    entry["total"] = round(entry.get("total", 0) + weight, 2)
    if correct:
        entry["correct"] = round(entry.get("correct", 0) + weight, 2)
    if basis == "symbolic":
        entry["symbolic_total"] = round(entry.get("symbolic_total", 0) + weight, 2)

    # Graded accuracy signal: use mismatch_score if provided, else binary
    alpha = 0.15 * weight
    old_acc = float(entry.get("accuracy", 0.5))
    if mismatch_score is not None:
        accuracy_signal = max(0.0, 1.0 - float(mismatch_score))
    else:
        accuracy_signal = 1.0 if correct else 0.0
    new_acc = old_acc * (1 - alpha) + accuracy_signal * alpha
    entry["accuracy"] = round(new_acc, 4)
    # Reconciled reliability: the graded EMA above and the binary correct/total
    # ledger drifted far apart (COGNITIVE: EMA 0.97 vs 1117/1734 = 0.64), and
    # routers were trusting the inflated one. Export a conservative blend —
    # never higher than the Laplace-smoothed binary rate.
    _binary = (entry.get("correct", 0) + 1) / (entry.get("total", 0) + 2)
    entry["reliability"] = round(min(new_acc, _binary), 4)
    entry["last_updated"] = datetime.now(timezone.utc).isoformat()

    stats[domain] = entry
    save_json(DOMAIN_STATS_FILE, stats)


def get_domain_error_rates() -> Dict[str, float]:
    """
    Return per-domain prediction error rate (1 - accuracy).
    Used by intrinsic_motivation to weight uncertainty by domain.
    """
    stats = load_json(DOMAIN_STATS_FILE, default_type=dict) or {}
    # Prefer the reconciled reliability (conservative blend of graded EMA and
    # binary hit rate); fall back to the raw EMA for entries written before
    # the reliability field existed.
    return {
        domain: round(1.0 - float(entry.get("reliability", entry.get("accuracy", 0.5))), 4)
        for domain, entry in stats.items()
    }


def domain_weighted_prediction_error(query: str) -> float:
    """
    Returns the error rate for the most likely domain of `query`.
    Falls back to global average if domain stats unavailable.
    """
    domain = classify_domain(query)
    rates = get_domain_error_rates()
    if domain in rates:
        return rates[domain]
    if rates:
        return round(sum(rates.values()) / len(rates), 4)
    return 0.40  # prior: 40% error rate before any data


# ─── Prediction resolution hook ──────────────────────────────────────────────

def resolve_prediction(
    pred_id_or_text: str,
    *,
    correct: bool,
    outcome: str = "",
    mismatch_score: Optional[float] = None,
) -> None:
    """
    Mark a prediction resolved and update domain stats.
    `pred_id_or_text`: match by prediction text prefix.
    `mismatch_score`: 0.0 = perfect, 1.0 = complete miss. Enables graded surprise.
    """
    preds = load_json(PREDICTIONS_FILE, default_type=list) or []
    matched_pred = None
    for pred in preds:
        text = pred.get("prediction", "")
        if not text.startswith(pred_id_or_text[:40]):
            continue
        if pred.get("status") == "pending":
            pred["status"] = "resolved"
            pred["resolved"] = True
            pred["correct"] = correct
            pred["mismatch_score"] = round(mismatch_score, 3) if mismatch_score is not None else (0.0 if correct else 1.0)
            pred["checked_ts"] = datetime.now(timezone.utc).isoformat()
            pred["outcome"] = outcome[:200] if outcome else ("correct" if correct else "incorrect")
            domain = pred.get("domain", classify_domain(text))
            basis  = pred.get("basis", "llm")
            update_domain_stats(domain, correct, basis=basis, mismatch_score=mismatch_score)
            matched_pred = pred
            # Feed prediction failure back to the generating rule's confidence
            rule_id = pred.get("rule_id")
            if rule_id and mismatch_score is not None and mismatch_score > 0.4:
                try:
                    from symbolic.rule_verifier import weaken_rule_confidence as _wrc
                    _wrc(rule_id, amount=mismatch_score * 0.05)
                except Exception as _e:
                    record_failure("prediction_engine.resolve_prediction", _e)
            break
    save_json(PREDICTIONS_FILE, preds[-150:])

    # Feed outcome into causal graph and signal_score world model
    if matched_pred:
        try:
            from symbolic.causal_graph import update_from_prediction_outcome as _ucpo
            _ucpo(matched_pred, correct)
        except Exception as _e:
            record_failure("prediction_engine.resolve_prediction.2", _e)
        try:
            from symbolic.pattern_scorer import update_pattern_weights, update_world_model, tokenize_query
            _text = matched_pred.get("text", "")
            _tokens, _domain = tokenize_query(_text)
            update_pattern_weights(_domain, _tokens, 1.0 if correct else 0.0)
            update_world_model(_domain, "prediction", correct)
        except Exception as _e:
            record_failure("prediction_engine.resolve_prediction.3", _e)


# ─── Prediction chaining ─────────────────────────────────────────────────────

def chain_from_verified_prediction(pred: Dict) -> Optional[Dict]:
    """
    When prediction P came true, try to chain: does P's conclusion match any rule?
    If yes, create a chained prediction from that rule's conclusion.
    """
    if not pred.get("correct"):
        return None
    conclusion_text = pred.get("outcome", pred.get("prediction", ""))
    if not conclusion_text:
        return None

    try:
        from symbolic.rule_engine import match
        chained_rule = match(conclusion_text, threshold=0.40)
        if not chained_rule or chained_rule.get("confidence", 0) < 0.55:
            return None
        chained_pred = make_symbolic_prediction(
            query=conclusion_text,
            rule_id=chained_rule["id"],
            conclusion=chained_rule["conclusion"],
            confidence=chained_rule["confidence"] * 0.85,  # decay confidence
            horizon="medium",
        )
        chained_pred["chained_from"] = pred.get("prediction", "")[:80]
        return chained_pred
    except Exception:
        return None


# ─── Batch check (called from prediction.check_predictions) ──────────────────

def run_symbolic_prediction_cycle(context: Optional[Dict] = None) -> Dict:
    """
    Full cycle:
      1. Check recently fired rules and generate symbolic predictions.
      2. Resolve any pending symbolic predictions that are now evaluable.
      3. Chain from verified predictions.
    Returns summary.
    """
    new_preds: List[Dict] = []
    chained: int = 0

    # Generate predictions from recently fired rules (read from WM context)
    try:
        recent_firings = (context or {}).get("_recent_rule_firings") or []
        for firing in recent_firings[-5:]:
            rule_id   = firing.get("rule_id", "")
            query     = firing.get("query_head", "")
            answer    = firing.get("answer_head", "")
            confidence = firing.get("confidence", 0.72)
            if rule_id and query and answer:
                pred = make_symbolic_prediction(query, rule_id, answer, confidence)
                new_preds.append(pred)
    except Exception as _e:
        record_failure("prediction_engine.run_symbolic_prediction_cycle", _e)

    # Chain from recently verified predictions
    try:
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        verified = [p for p in preds[-30:]
                    if p.get("correct") and not p.get("chained_from")]
        for pred in verified[:5]:
            chained_pred = chain_from_verified_prediction(pred)
            if chained_pred:
                new_preds.append(chained_pred)
                chained += 1
    except Exception as _e:
        record_failure("prediction_engine.run_symbolic_prediction_cycle.2", _e)

    if new_preds:
        save_symbolic_predictions(new_preds)

    return {
        "new_predictions": len(new_preds),
        "chained": chained,
        "domain_error_rates": get_domain_error_rates(),
    }
