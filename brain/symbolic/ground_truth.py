# brain/symbolic/ground_truth.py
# Grounding & Reality Testing — couples rule quality to real-world action outcomes.
#
# The core problem with purely internal reward: a rule can score well because
# the LLM *says* its answer is good, not because anything in the world actually
# changed.  This module intercepts actual action execution outcomes and feeds
# them back to rule confidence independently of LLM-graded quality.
#
# Integration points:
#   action_gate._stamp_outcome  → record_action_result() called after every action
#   rule_verifier.apply_outcome → grounding_multiplier() adjusts the delta
#   dream_cycle                 → audit_grounding_health() for dashboard
#
# Data written to data/ground_truth.jsonl (append-only execution trace)
#             and data/rule_grounding.json  (per-rule grounding stats)
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import DATA_DIR

GROUND_TRUTH_WAL  = DATA_DIR / "ground_truth.jsonl"
GROUNDING_STATS   = DATA_DIR / "rule_grounding.json"

_EMA_ALPHA   = 0.20
_WAL_MAX     = 3_000
_MIN_SAMPLES = 3      # need this many executions before grounding_score is trusted


# ─── WAL helpers ──────────────────────────────────────────────────────────────

def _append_wal(entry: Dict) -> None:
    try:
        GROUND_TRUTH_WAL.parent.mkdir(parents=True, exist_ok=True)
        if GROUND_TRUTH_WAL.exists():
            lines = GROUND_TRUTH_WAL.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > _WAL_MAX:
                GROUND_TRUTH_WAL.write_text(
                    "\n".join(lines[-(_WAL_MAX // 2):]) + "\n", encoding="utf-8"
                )
        with GROUND_TRUTH_WAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_activity(f"[ground_truth] WAL write failed: {e}")


# ─── Public API ───────────────────────────────────────────────────────────────

def record_action_result(
    action_type: str,
    success: bool,
    *,
    rule_id: str = "",
    context: Optional[Dict] = None,
    output_snippet: str = "",
) -> None:
    """
    Call this after any real action completes.
    `rule_id` links the action back to the rule that suggested it (if known).
    Called from action_gate after _stamp_outcome.
    """
    entry = {
        "ts":          time.time(),
        "action_type": action_type,
        "success":     success,
        "rule_id":     rule_id,
        "output":      output_snippet[:200],
    }
    _append_wal(entry)

    if rule_id:
        _update_grounding_stats(rule_id, success)
        log_activity(
            f"[ground_truth] rule='{rule_id}' action={action_type} "
            f"success={success}"
        )


def _update_grounding_stats(rule_id: str, success: bool) -> None:
    stats = load_json(GROUNDING_STATS, default_type=dict) or {}
    entry = stats.get(rule_id, {"grounding_score": 0.50, "total": 0, "successes": 0})
    entry["total"] = entry.get("total", 0) + 1
    if success:
        entry["successes"] = entry.get("successes", 0) + 1
    # EMA update
    old = float(entry.get("grounding_score", 0.5))
    target = 1.0 if success else 0.0
    entry["grounding_score"] = round(old + _EMA_ALPHA * (target - old), 4)
    entry["last_updated"] = datetime.now(timezone.utc).isoformat()
    stats[rule_id] = entry
    save_json(GROUNDING_STATS, stats)


def grounding_score(rule_id: str) -> float:
    """
    Return the real-world grounding score for a rule (0–1).
    Returns 0.5 (neutral) when fewer than _MIN_SAMPLES executions have been recorded.
    """
    if not rule_id:
        return 0.5
    stats = load_json(GROUNDING_STATS, default_type=dict) or {}
    entry = stats.get(rule_id)
    if not entry or entry.get("total", 0) < _MIN_SAMPLES:
        return 0.5  # not enough data — neutral
    return float(entry.get("grounding_score", 0.5))


def grounding_multiplier(rule_id: str) -> float:
    """
    Multiplier for confidence delta in rule_verifier:
      grounding_score 0.8 → multiplier 1.4 (amplify reward for grounded rules)
      grounding_score 0.5 → multiplier 1.0 (neutral)
      grounding_score 0.2 → multiplier 0.6 (dampen reward for ungrounded rules)
    Linear: multiplier = 0.6 + 0.8 × grounding_score
    """
    gs = grounding_score(rule_id)
    return round(0.6 + 0.8 * gs, 3)


def get_grounding_stats() -> Dict:
    return load_json(GROUNDING_STATS, default_type=dict) or {}


def audit_grounding_health() -> Dict:
    """
    Summary of rule grounding for the dashboard / dream log.
    Returns: total_tracked, mean_grounding, well_grounded, poorly_grounded.
    """
    stats = get_grounding_stats()
    if not stats:
        return {"total_tracked": 0, "mean_grounding": 0.5,
                "well_grounded": 0, "poorly_grounded": 0}
    scores = [e.get("grounding_score", 0.5) for e in stats.values()]
    return {
        "total_tracked":   len(scores),
        "mean_grounding":  round(sum(scores) / len(scores), 3),
        "well_grounded":   sum(1 for s in scores if s >= 0.70),
        "poorly_grounded": sum(1 for s in scores if s < 0.35),
    }
