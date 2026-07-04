# brain/cognition/idle_consolidation/semantic_extractor.py
# Episodic → semantic extractor: condense recent cognition_history entries into
# structured (action, context, outcome) facts with counts and confidence.
#
# Runs during the dream cycle after the LLM consolidation prose has been
# generated. No additional LLM call — patterns are extracted from the
# existing episode/event data (reward, dominant emotion, goal presence).
#
# Output schema (data/semantic_facts.json), one entry per (action, context, outcome) triple:
#   {
#     "action":     "speak",
#     "context":    "goalless",
#     "outcome":    "failure",
#     "count":      12,
#     "confidence": 0.74,
#     "first_seen": iso8601,
#     "last_seen":  iso8601
#   }
#
# Confidence is the share of (action, context) episodes that resulted in this
# outcome — i.e. P(outcome | action, context). It's a frequentist estimate
# bounded to [0, 1] with a small Laplace prior so single-observation facts
# don't have confidence=1.0.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
from brain.paths import DATA_DIR

try:
    from brain.paths import COGNITION_HISTORY_FILE
except Exception:
    COGNITION_HISTORY_FILE = DATA_DIR / "cognition_history.json"

SEMANTIC_FACTS_FILE = DATA_DIR / "semantic_facts.json"

# How many recent cognition_history entries to scan per dream cycle.
_SCAN_WINDOW = 200

# Reward thresholds for bucketing outcomes.
_REWARD_SUCCESS = 0.55
_REWARD_FAILURE = 0.10  # below this is a failure (rewards are typically [-0.3, 1.0])


def _classify_outcome(reward: float) -> str:
    try:
        r = float(reward)
    except (ValueError, TypeError):  # intentional: non-numeric reward → neutral
        return "neutral"
    if r >= _REWARD_SUCCESS:
        return "success"
    if r <= _REWARD_FAILURE:
        return "failure"
    return "neutral"


def _classify_context(entry: Dict[str, Any]) -> str:
    """
    Derive a coarse context label from the entry's reason features.
    Layered so we capture the most informative dimension available:
      - goal presence vs. absence (most decision-relevant)
      - high-distress vs. low-distress vs. stagnation_signal
      - falls back to dominant emotion bucket
    """
    reason = entry.get("reason") or {}
    if not isinstance(reason, dict):
        reason = {}

    feats = reason.get("features_on") or {}
    if not isinstance(feats, dict):
        feats = {}

    # Goal context — "committed_goal" feature is set when a goal was active.
    has_goal = bool(feats.get("committed_goal_active") or feats.get("has_goal"))
    # Heuristic fallback: any goal-related feature flag
    if not has_goal:
        has_goal = any(
            k.startswith("goal_") and float(v or 0.0) > 0.0
            for k, v in feats.items()
            if isinstance(v, (int, float))
        )

    distress = float(feats.get("distress_present") or 0.0)
    stagnation_signal_val = reason.get("stagnation_signal")
    try:
        stagnation_signal = float(stagnation_signal_val) if stagnation_signal_val is not None else 0.0
    except Exception:
        stagnation_signal = 0.0

    dom = str(reason.get("dominant_affect") or "").lower() or "neutral"

    if has_goal and distress >= 0.5:
        return "goal_under_distress"
    if has_goal:
        return "goal_active"
    if stagnation_signal >= 0.5:
        return "bored"
    if distress >= 0.5:
        return "distressed"
    return f"emo_{dom}"


def _scan_episodes(history: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str]]:
    """
    Return list of (action, context, outcome, timestamp) tuples extracted
    from the recent slice of cognition_history.
    """
    out: List[Tuple[str, str, str, str]] = []
    if not isinstance(history, list):
        return out

    window = history[-_SCAN_WINDOW:]
    for entry in window:
        if not isinstance(entry, dict):
            continue
        action = entry.get("choice") or entry.get("action")
        if not action or not isinstance(action, str):
            continue
        outcome = _classify_outcome(entry.get("reward", 0.0))
        ctx_label = _classify_context(entry)
        ts = entry.get("timestamp") or datetime.now(timezone.utc).isoformat()
        out.append((action, ctx_label, outcome, str(ts)))
    return out


def _key(action: str, context: str, outcome: str) -> str:
    return f"{action}|{context}|{outcome}"


def extract_semantic_facts() -> Dict[str, Any]:
    """
    Read cognition_history, derive structured facts, merge with the existing
    semantic_facts file (updating counts and confidence rather than duplicating).

    Returns a summary dict:
      {"scanned": N, "new_facts": M, "updated_facts": K, "total_facts": T}
    """
    history = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    if not isinstance(history, list):
        history = []

    episodes = _scan_episodes(history)
    if not episodes:
        return {"scanned": 0, "new_facts": 0, "updated_facts": 0, "total_facts": 0}

    # Count by (action, context, outcome) and by (action, context) totals
    by_triple: Dict[str, int] = {}
    by_pair: Dict[Tuple[str, str], int] = {}
    first_seen: Dict[str, str] = {}
    last_seen: Dict[str, str] = {}
    for action, ctx, outcome, ts in episodes:
        k = _key(action, ctx, outcome)
        by_triple[k] = by_triple.get(k, 0) + 1
        by_pair[(action, ctx)] = by_pair.get((action, ctx), 0) + 1
        if k not in first_seen or ts < first_seen[k]:
            first_seen[k] = ts
        if k not in last_seen or ts > last_seen[k]:
            last_seen[k] = ts

    # Load existing facts and index by key
    existing: List[Dict[str, Any]] = load_json(SEMANTIC_FACTS_FILE, default_type=list) or []
    if not isinstance(existing, list):
        existing = []
    index: Dict[str, Dict[str, Any]] = {}
    for fact in existing:
        if not isinstance(fact, dict):
            continue
        k = _key(str(fact.get("action") or ""),
                 str(fact.get("context") or ""),
                 str(fact.get("outcome") or ""))
        index[k] = fact

    new_count = 0
    updated_count = 0

    # Confidence uses Laplace smoothing over the (action, context) total in this
    # scan window. Combined counts (existing + new) drive the long-running estimate.
    for k, fresh_n in by_triple.items():
        action, ctx, outcome = k.split("|", 2)
        pair_total_window = by_pair[(action, ctx)]

        if k in index:
            fact = index[k]
            old_count = int(fact.get("count") or 0)
            new_total_count = old_count + fresh_n
            # Update last_seen
            if last_seen.get(k):
                fact["last_seen"] = last_seen[k]
            fact["count"] = new_total_count
            # Confidence: weighted blend of prior confidence and the fresh window
            # share, weighted by sample counts (so a single new sample doesn't
            # whipsaw a fact with 100 prior observations).
            fresh_share = (fresh_n + 1.0) / (pair_total_window + 2.0)
            prior_conf = float(fact.get("confidence") or 0.5)
            w_prior = old_count / max(old_count + fresh_n, 1)
            w_fresh = fresh_n / max(old_count + fresh_n, 1)
            fact["confidence"] = round(prior_conf * w_prior + fresh_share * w_fresh, 3)
            updated_count += 1
        else:
            # Laplace-smoothed initial confidence: (k+1)/(n+2)
            init_conf = (fresh_n + 1.0) / (pair_total_window + 2.0)
            index[k] = {
                "action":     action,
                "context":    ctx,
                "outcome":    outcome,
                "count":      fresh_n,
                "confidence": round(init_conf, 3),
                "first_seen": first_seen.get(k, ""),
                "last_seen":  last_seen.get(k, ""),
            }
            new_count += 1

    # RUN4_FIX_PLAN §3.10 — decay/re-test facts NOT re-observed this scan. A
    # high-confidence fact learned from a source lane that has since changed or
    # been removed (2026-07-03: produce_and_check neutral, n=228, conf 0.979,
    # learned from the removed stuck loop) otherwise stays pinned forever. A fact
    # not seen this pass loses a little confidence; if the pattern is still real
    # it gets re-observed above and recovers, if the lane is gone it fades and
    # stops dominating. A well-supported fact decays slower (count-scaled floor).
    _observed = set(by_triple.keys())
    _STALE_DECAY = 0.03
    for k, fact in index.items():
        if k in _observed:
            continue
        try:
            n = int(fact.get("count") or 0)
            floor = max(0.1, 0.5 - min(0.3, n / 1000.0))   # strong facts settle higher, not to 0
            conf = float(fact.get("confidence") or 0.5)
            new_conf = max(floor, round(conf - _STALE_DECAY, 3))
            if new_conf != conf:
                fact["confidence"] = new_conf
                fact["stale_decayed"] = True
        except Exception as exc:
            record_failure("semantic_extractor.stale_decay", exc)

    # Save back as a flat list sorted by count (most-supported facts first).
    merged = sorted(index.values(), key=lambda f: -int(f.get("count") or 0))
    # Bound the file size so it doesn't grow without limit; keep top 500 facts.
    merged = merged[:500]
    try:
        save_json(SEMANTIC_FACTS_FILE, merged)
    except Exception as e:
        log_activity(f"[semantic_extractor] save failed: {e}")

    summary = {
        "scanned":       len(episodes),
        "new_facts":     new_count,
        "updated_facts": updated_count,
        "total_facts":   len(merged),
    }
    return summary
