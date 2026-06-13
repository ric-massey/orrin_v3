# brain/symbolic/rule_verifier.py
# Rule Execution + Verification Loop.
#
# Every time a rule fires in reasoning_router, the firing is written to a WAL
# (rule_firings.jsonl).  At cycle finalization, apply_outcome() looks up the
# most recent firing that matches the current context and adjusts the rule's
# confidence based on the actual outcome score.
#
# Confidence adjustment:
#   outcome ≥ 0.65  → +REWARD  (rule was right)
#   outcome ≤ 0.30  → −PENALTY (rule misled; heavy enough to matter)
#   0.30 < outcome < 0.65 → no change (ambiguous)
#
# When confidence falls below REVISION_THRESHOLD, the rule is copied to
# data/rule_revisions.json for inspection / dream-cycle review.
# When confidence falls below TOMBSTONE_THRESHOLD, the rule is soft-deleted
# (confidence pinned to 0.10 and source marked "tombstoned") to prevent
# further firings without removing historical data.
#
# Integration points:
#   reasoning_router.route()  → record_firing() after a rule resolves
#   think/think_utils/finalize.py → apply_outcome() at cycle end
from __future__ import annotations
from core.runtime_log import get_logger

import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

FIRINGS_WAL     = DATA_DIR / "rule_firings.jsonl"
REVISIONS_FILE  = DATA_DIR / "rule_revisions.json"

_REWARD          =  0.025   # confidence bump on good outcome
_PENALTY         = -0.040   # confidence hit on bad outcome
_REVISION_THRESH =  0.45    # flag for human review below this
_TOMBSTONE_THRESH = 0.20    # soft-delete below this
_WAL_WINDOW      = 300      # seconds to look back when matching outcome to firing
_WAL_MAX_LINES   = 5_000    # hard cap before rotation


# ─── WAL helpers ──────────────────────────────────────────────────────────────

def _query_hash(query: str) -> str:
    return hashlib.md5(query.lower().strip()[:120].encode()).hexdigest()[:12]


def _append_wal(entry: Dict) -> None:
    import json
    try:
        FIRINGS_WAL.parent.mkdir(parents=True, exist_ok=True)
        # Rotate if too large
        if FIRINGS_WAL.exists():
            lines = FIRINGS_WAL.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) > _WAL_MAX_LINES:
                FIRINGS_WAL.write_text(
                    "\n".join(lines[-(_WAL_MAX_LINES // 2):]) + "\n",
                    encoding="utf-8",
                )
        with FIRINGS_WAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        log_activity(f"[rule_verifier] WAL write failed: {e}")


def _read_wal_recent(window_s: float = _WAL_WINDOW) -> List[Dict]:
    import json
    if not FIRINGS_WAL.exists():
        return []
    cutoff = time.time() - window_s
    entries = []
    try:
        for line in FIRINGS_WAL.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("ts", 0) >= cutoff:
                    entries.append(e)
            except Exception as _e:
                record_failure("rule_verifier._read_wal_recent", _e)
    except Exception as _e:
        record_failure("rule_verifier._read_wal_recent.2", _e)
    return entries


# ─── Public API ───────────────────────────────────────────────────────────────

def record_firing(
    rule_id: str,
    query: str,
    answer: str,
    *,
    meta_rule_id: str = "",
    context: Optional[Dict] = None,
) -> None:
    """
    Write one WAL entry for a rule that just fired.
    Call this from reasoning_router immediately after a rule resolves.
    """
    _append_wal({
        "ts":           time.time(),
        "rule_id":      rule_id,
        "query_hash":   _query_hash(query),
        "query_head":   query[:80],
        "answer_head":  answer[:80],
        "meta_rule_id": meta_rule_id,
        "outcome":      None,   # filled in by apply_outcome()
    })


def apply_outcome(
    outcome_score: float,
    *,
    query: str = "",
    context: Optional[Dict] = None,
) -> List[str]:
    """
    Match a just-completed cycle's outcome_score to the most recent rule
    firing(s) within the WAL window.  Adjust rule confidence accordingly.
    Returns list of rule_ids that were updated.
    """
    updated: List[str] = []
    recent = _read_wal_recent()
    if not recent:
        return updated

    q_hash = _query_hash(query) if query else ""
    # Find matching entries (prefer exact query hash, fall back to any recent)
    candidates = [e for e in recent if e.get("outcome") is None]
    if q_hash:
        exact = [e for e in candidates if e.get("query_hash") == q_hash]
        if exact:
            candidates = exact

    # Process the last matching entry
    if not candidates:
        return updated
    entry = candidates[-1]

    rule_id = entry.get("rule_id", "")
    if not rule_id:
        return updated

    if outcome_score >= 0.65:
        delta = _REWARD
        verdict = "reward"
    elif outcome_score <= 0.30:
        delta = _PENALTY
        verdict = "penalty"
    else:
        return updated  # ambiguous outcome — no adjustment

    # Scale delta by real-world grounding score
    try:
        from symbolic.ground_truth import grounding_multiplier as _gm
        delta = round(delta * _gm(rule_id), 5)
    except Exception as _e:
        record_failure("rule_verifier.apply_outcome", _e)

    _adjust_confidence(rule_id, delta, verdict, entry, outcome_score)
    updated.append(rule_id)

    # Update signal_score pattern weights from this outcome
    try:
        from symbolic.pattern_scorer import update_pattern_weights, update_world_model, tokenize_query
        q_text = entry.get("query_head", query)
        tokens, domain = tokenize_query(q_text)
        update_pattern_weights(domain, tokens, outcome_score)
        update_world_model(domain, "rule", outcome_score >= 0.65)
    except Exception as _e:
        record_failure("rule_verifier.apply_outcome.2", _e)

    return updated


# ─── Confidence adjustment ────────────────────────────────────────────────────

def _adjust_confidence(
    rule_id: str,
    delta: float,
    verdict: str,
    firing_entry: Dict,
    outcome_score: float,
) -> None:
    from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
    from utils.json_utils import save_json

    rules = get_all_rules()
    for rule in rules:
        if rule.get("id") != rule_id:
            continue

        old_conf = float(rule.get("confidence", 0.75))
        # Ceiling 0.98, not 1.0: a rule pinned at exactly 1.0 made the verifier
        # a permanent no-op for it ("conf 1.000 → 1.000" every cycle) — no
        # evidence could ever move it again. Below-ceiling confidence keeps
        # every rule revisable.
        new_conf = round(max(0.10, min(0.98, old_conf + delta)), 4)
        rule["confidence"] = new_conf

        log_activity(
            f"[rule_verifier] Rule '{rule_id}' {verdict}: "
            f"conf {old_conf:.3f} → {new_conf:.3f} (outcome={outcome_score:.2f})"
        )

        # Flag for revision if confidence fell below threshold
        if new_conf < _REVISION_THRESH and old_conf >= _REVISION_THRESH:
            _flag_for_revision(rule, outcome_score, firing_entry)

        # Soft-delete if below tombstone threshold
        if new_conf <= _TOMBSTONE_THRESH:
            rule["source"] = "tombstoned"
            log_activity(f"[rule_verifier] Rule '{rule_id}' tombstoned (conf={new_conf:.3f})")

        save_json(SYMBOLIC_RULES_FILE, rules)
        # Invalidate cache
        try:
            from symbolic import rule_engine as _re
            _re._rules_cache = []
        except Exception as _e:
            record_failure("rule_verifier._adjust_confidence", _e)
        break


def weaken_rule_confidence(rule_id: str, *, amount: float = 0.03) -> None:
    """Directly weaken a rule's confidence by `amount`. Used by prediction failure feedback."""
    _adjust_confidence(
        rule_id,
        delta=-abs(amount),
        verdict="prediction_miss",
        firing_entry={"query_head": ""},
        outcome_score=0.0,
    )


def _flag_for_revision(rule: Dict, outcome: float, firing: Dict) -> None:
    existing = load_json(REVISIONS_FILE, default_type=list) or []
    existing.append({
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "rule_id":     rule.get("id"),
        "rule_conclusion": rule.get("conclusion", "")[:200],
        "confidence":  rule.get("confidence"),
        "outcome":     outcome,
        "query":       firing.get("query_head", ""),
        "status":      "pending",
    })
    save_json(REVISIONS_FILE, existing[-100:])
    log_activity(f"[rule_verifier] Rule '{rule.get('id')}' flagged for revision.")


# ─── Dream-cycle review ───────────────────────────────────────────────────────

def get_pending_revisions() -> List[Dict]:
    """Return rules that need human/LLM review."""
    return [r for r in (load_json(REVISIONS_FILE, default_type=list) or [])
            if r.get("status") == "pending"]


def mark_revision_resolved(rule_id: str, *, action: str = "keep") -> None:
    revisions = load_json(REVISIONS_FILE, default_type=list) or []
    for r in revisions:
        if r.get("rule_id") == rule_id and r.get("status") == "pending":
            r["status"] = action
    save_json(REVISIONS_FILE, revisions)
