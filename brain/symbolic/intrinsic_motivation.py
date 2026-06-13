# brain/symbolic/intrinsic_motivation.py
# Information-theoretic intrinsic motivation: novelty, uncertainty, prediction error.
#
# Drives the main loop autonomously — when exploration_drive exceeds thresholds, the
# system spawns investigation sub-goals without waiting for user input.
#
#   novelty(query)          — how unlike anything in long memory (0–1)
#   uncertainty(query)      — inverse of rule + kg coverage (0–1)
#   prediction_error()      — recent prediction miss rate (0–1)
#   exploration_drive_score(query)  — weighted sum (0–1)
#
# Drive levels:
#   score ≥ 0.70 → "explore" : spawn sub-goal, lower LLM gate threshold
#   score ≥ 0.45 → "investigate" : note anomaly, worth follow-up
#   score < 0.25 → "exploit" : familiar territory, prefer symbolic resolution
#
# Sub-goal spawning:
#   maybe_spawn_subgoal(query, context) injects into context["proposed_goals"]
#   when exploration_drive ≥ 0.70 AND the same topic hasn't been spawned recently
#   (cooldown: 30 min per topic hash). goal_io.sync_proposed_goals picks these up and
#   creates real goals in the goal system next cycle.
from __future__ import annotations
from core.runtime_log import get_logger

import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import PREDICTIONS_FILE, DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ─── Spawn cooldown state ─────────────────────────────────────────────────────
_SPAWN_LOG_FILE  = DATA_DIR / "intrinsic_spawns.json"
_SPAWN_COOLDOWN  = 1800.0   # 30 min per topic before re-spawning
_EXPLORE_THRESH  = 0.70
_INVEST_THRESH   = 0.45


# ─── Novelty ──────────────────────────────────────────────────────────────────

def novelty(query: str) -> float:
    """0 = seen before, 1 = completely new. Inverted structural analogy score."""
    from symbolic.analogy_engine import find_analogues
    analogues = find_analogues(query, top_n=3, min_score=0.0)
    if not analogues:
        return 1.0
    max_sim = max(a["score"] for a in analogues)
    return round(1.0 - min(max_sim, 1.0), 3)


# ─── Uncertainty ──────────────────────────────────────────────────────────────

def uncertainty(query: str) -> float:
    """0 = fully covered, 1 = completely unknown."""
    from symbolic.rule_engine import match_all
    from symbolic.symbolic_search import can_answer_symbolically

    rules_hit = match_all(query, threshold=0.30)
    rule_cov = min(len(rules_hit) / 3.0, 1.0)
    kg_cov = 1.0 if can_answer_symbolically(query) else 0.0
    coverage = max(rule_cov, kg_cov * 0.8)
    return round(1.0 - coverage, 3)


# ─── Prediction error ─────────────────────────────────────────────────────────

def prediction_error(context: Optional[Dict] = None) -> float:
    """
    Domain-weighted prediction miss rate.
    Uses prediction_engine's per-domain accuracy when available;
    falls back to raw global miss rate.
    """
    query = (context or {}).get("user_input", "") if context else ""
    # Try domain-weighted error first (more precise signal)
    if query:
        try:
            from symbolic.prediction_engine import domain_weighted_prediction_error
            return domain_weighted_prediction_error(query)
        except Exception as _e:
            record_failure("intrinsic_motivation.prediction_error", _e)
    # Global miss rate fallback
    try:
        preds = load_json(PREDICTIONS_FILE, default_type=list) or []
        if not preds:
            return 0.5
        recent = preds[-20:]
        resolved = [p for p in recent if p.get("resolved")]
        if not resolved:
            return 0.5
        # correct=True → 0 error, correct=False → 1 error, None (partial) → 0.5 error.
        # Treating None as a hard miss would punish ambiguous outcomes too harshly
        # and inflate the exploration_drive signal artificially.
        def _err(p):
            c = p.get("correct")
            if c is True:
                return 0.0
            if c is False:
                return 1.0
            return 0.5
        return round(sum(_err(p) for p in resolved) / len(resolved), 3)
    except Exception:
        return 0.3


# ─── Unified exploration_drive score ──────────────────────────────────────────────────

def exploration_drive_score(query: str, context: Optional[Dict] = None) -> float:
    n = novelty(query)
    u = uncertainty(query)
    pe = prediction_error(context)
    return round(min(0.45 * n + 0.35 * u + 0.20 * pe, 1.0), 3)


def drive_label(score: float) -> str:
    if score >= _EXPLORE_THRESH:
        return "explore"
    if score >= _INVEST_THRESH:
        return "investigate"
    return "exploit"


def get_drive(query: str, context: Optional[Dict] = None) -> Dict:
    n = novelty(query)
    u = uncertainty(query)
    pe = prediction_error(context)
    score = round(min(0.45 * n + 0.35 * u + 0.20 * pe, 1.0), 3)
    label = drive_label(score)
    log_activity(f"[intrinsic] {label} score={score} (novelty={n} uncertainty={u} pred_err={pe})")
    return {
        "score": score,
        "label": label,
        "novelty": n,
        "uncertainty": u,
        "prediction_error": pe,
    }


# ─── Sub-goal spawning ───────────────────────────────────────────────────────

def _topic_hash(query: str) -> str:
    return hashlib.md5(query.lower().strip()[:80].encode()).hexdigest()[:12]


def _load_spawn_log() -> Dict:
    return load_json(_SPAWN_LOG_FILE, default_type=dict) or {}


def _mark_spawned(topic_hash: str) -> None:
    log = _load_spawn_log()
    log[topic_hash] = time.time()
    # Prune old entries
    cutoff = time.time() - _SPAWN_COOLDOWN * 4
    log = {k: v for k, v in log.items() if v > cutoff}
    save_json(_SPAWN_LOG_FILE, log)


def _recently_spawned(topic_hash: str) -> bool:
    log = _load_spawn_log()
    last = log.get(topic_hash, 0.0)
    return (time.time() - last) < _SPAWN_COOLDOWN


def maybe_spawn_subgoal(query: str, context: Dict) -> Optional[Dict]:
    """
    If exploration_drive ≥ 0.70 and this topic hasn't been spawned recently,
    inject an investigation sub-goal into context["proposed_goals"].
    Returns the spawned goal dict, or None if not spawned.

    goal_io.sync_proposed_goals will pick up proposed_goals and register them in the
    goal system next cycle.
    """
    drive = get_drive(query, context=context)
    if drive["score"] < _EXPLORE_THRESH:
        return None

    th = _topic_hash(query)
    if _recently_spawned(th):
        return None

    # Build investigation goal
    title = f"Investigate: {query[:60]}"
    goal = {
        "title": title,
        "description": (
            f"Autonomously triggered by high exploration_drive (score={drive['score']}, "
            f"novelty={drive['novelty']}, uncertainty={drive['uncertainty']}). "
            f"Original query: {query[:200]}"
        ),
        "source": "intrinsic_motivation",
        "priority": "medium",
        "milestones": [
            {"title": "Gather symbolic facts from knowledge graph"},
            {"title": "Check rule base for relevant patterns"},
            {"title": "Form and test a hypothesis"},
            {"title": "Crystallize findings into new rules"},
        ],
        "exploration_drive_score": drive["score"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    proposed = context.get("proposed_goals") or []
    proposed.append(goal)
    context["proposed_goals"] = proposed

    _mark_spawned(th)
    log_activity(
        f"[intrinsic] Sub-goal spawned: '{title}' "
        f"(score={drive['score']}, novelty={drive['novelty']})"
    )

    # Decompose into a multi-step causal plan for longer-horizon tracking
    try:
        from symbolic.temporal_planner import integrate_goal_plan as _igp
        _igp(goal, context=context)
    except Exception as _e:
        record_failure("intrinsic_motivation.maybe_spawn_subgoal", _e)

    return goal


def run_intrinsic_motivation(context: Dict) -> Dict:
    """
    Cognitive-loop entry point — called from ORRIN_loop as a registered
    cognitive function.  Checks exploration_drive on the current user input (if any)
    and spawns sub-goals when warranted.  Returns a summary dict.
    """
    user_input = (context or {}).get("user_input", "")
    if not user_input:
        # No active query — compute background exploration_drive from recent WM
        try:
            from utils.json_utils import load_json as _lj
            from paths import WORKING_MEMORY_FILE as _WMF
            wm = _lj(_WMF, default_type=list) or []
            recent_texts = [
                e.get("content", "") for e in wm[-5:] if isinstance(e, dict)
            ]
            user_input = " ".join(recent_texts)[:300]
        except Exception:
            return {"spawned": None, "drive": {}}

    if not user_input.strip():
        return {"spawned": None, "drive": {}}

    drive = get_drive(user_input, context=context)
    spawned = None
    if drive["score"] >= _EXPLORE_THRESH:
        spawned = maybe_spawn_subgoal(user_input, context)

    # Domain-error driven goal spawning:
    # If any prediction domain has error > 0.65, spawn a targeted investigation
    # goal regardless of exploration_drive score — high error = the world model is wrong there.
    domain_spawned: List[Optional[Dict]] = []
    try:
        from symbolic.prediction_engine import get_domain_error_rates
        error_rates = get_domain_error_rates()
        for domain, err_rate in error_rates.items():
            if err_rate >= 0.65:
                th = _topic_hash(f"domain_error_{domain}")
                if not _recently_spawned(th):
                    goal = {
                        "title": f"Resolve prediction failures: {domain}",
                        "description": (
                            f"Prediction error rate in {domain} domain is {err_rate:.0%}. "
                            f"Investigate what's causing consistent mispredictions and "
                            f"revise or delete the relevant rules/predictions."
                        ),
                        "source": "domain_error_intrinsic",
                        "priority": "high",
                        "milestones": [
                            {"title": f"Audit {domain} rules for low grounding scores"},
                            {"title": f"Review {domain} prediction history for patterns"},
                            {"title": "Identify root cause of mispredictions"},
                            {"title": "Revise or tombstone failing rules"},
                            {"title": "Crystallize corrected rules"},
                        ],
                        "domain": domain,
                        "error_rate": err_rate,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    proposed = context.get("proposed_goals") or []
                    proposed.append(goal)
                    context["proposed_goals"] = proposed
                    _mark_spawned(th)
                    domain_spawned.append(goal)
                    log_activity(
                        f"[intrinsic] Domain-error goal spawned: {domain} ({err_rate:.0%} error)"
                    )
    except Exception as _de:
        log_activity(f"[intrinsic] domain error goal spawn failed: {_de}")

    return {
        "spawned":        spawned.get("title") if spawned else None,
        "domain_spawned": [g["title"] for g in domain_spawned if g],
        "drive":          drive,
    }
