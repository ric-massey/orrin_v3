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
from brain.core.runtime_log import get_logger

import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

FIRINGS_WAL     = DATA_DIR / "rule_firings.jsonl"
REVISIONS_FILE  = DATA_DIR / "rule_revisions.json"

_REWARD          =  0.025   # confidence bump on good outcome
_PENALTY         = -0.040   # confidence hit on bad outcome
_REVISION_THRESH =  0.45    # flag for human review below this
_TOMBSTONE_THRESH = 0.20    # soft-delete below this
_WAL_WINDOW      = 300      # seconds to look back when matching outcome to firing
_WAL_MAX_LINES   = 5_000    # hard cap before rotation

# ── Outcome-based authority (Core Architecture Master Plan T1.2) ──────────────
# A rule that mispredicts N times in a row loses firing priority WITHOUT human
# action — the run had PLANNING wrong 893/893 yet still firing heavily because
# nothing decayed a rule's authority on sustained error. Two guards keep decay
# from becoming deletion (an under-learned domain needs acquisition, not having
# its last rule stripped — SOCIAL already sits at 0 learned rules):
#   • MIN_SAMPLE — a rule must have enough resolved outcomes before retirement.
#   • domain floor — never tombstone the LAST usable rule in a domain.
_MISS_STREAK_N   = 4        # consecutive mispredictions that trip authority loss
_MIN_SAMPLE      = 5        # resolved outcomes before a rule may be retired
_AUTHORITY_DECAY = 0.15     # extra confidence cut once the miss streak trips
_AUTHORITY_FLOOR = 0.15     # decay priority TOWARD this, never to zero


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
        from brain.symbolic.ground_truth import grounding_multiplier as _gm
        delta = round(delta * _gm(rule_id), 5)
    except Exception as _e:
        record_failure("rule_verifier.apply_outcome", _e)

    _adjust_confidence(rule_id, delta, verdict, entry, outcome_score)
    updated.append(rule_id)

    # Update signal_score pattern weights from this outcome
    try:
        from brain.symbolic.pattern_scorer import update_pattern_weights, update_world_model, tokenize_query
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
    from brain.symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
    from brain.utils.json_utils import save_json

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

        # T1.2 — outcome-based authority. Track resolved-outcome count and the
        # consecutive-misprediction streak so a rule that is *sustainedly* wrong
        # loses firing priority on its own. A reward clears the streak.
        rule["outcome_count"] = int(rule.get("outcome_count", 0)) + 1
        if verdict in ("penalty", "prediction_miss"):
            rule["consecutive_misses"] = int(rule.get("consecutive_misses", 0)) + 1
        else:
            rule["consecutive_misses"] = 0

        authority_lost = False
        if (rule["consecutive_misses"] >= _MISS_STREAK_N
                and rule["outcome_count"] >= _MIN_SAMPLE):
            # Sustained error → strip priority toward the floor (never to zero):
            # a rule pinned at 0 is as broken as one pinned at 1.0.
            new_conf = round(max(_AUTHORITY_FLOOR, new_conf - _AUTHORITY_DECAY), 4)
            authority_lost = True

        rule["confidence"] = new_conf

        log_activity(
            f"[rule_verifier] Rule '{rule_id}' {verdict}: "
            f"conf {old_conf:.3f} → {new_conf:.3f} (outcome={outcome_score:.2f}"
            f"{', authority-stripped' if authority_lost else ''})"
        )

        # Flag for revision if confidence fell below threshold
        if new_conf < _REVISION_THRESH and old_conf >= _REVISION_THRESH:
            _flag_for_revision(rule, outcome_score, firing_entry)

        # Soft-delete if below tombstone threshold — but never RETIRE past the
        # over-retirement guard: an under-learned rule (too few samples) or the
        # last usable rule in its domain is floored, not tombstoned, so decay
        # can't leave a domain with zero usable rules.
        if new_conf <= _TOMBSTONE_THRESH:
            if _retirement_allowed(rule, rules):
                rule["source"] = "tombstoned"
                log_activity(f"[rule_verifier] Rule '{rule_id}' tombstoned (conf={new_conf:.3f})")
            else:
                rule["confidence"] = max(new_conf, _AUTHORITY_FLOOR)
                log_activity(
                    f"[rule_verifier] Rule '{rule_id}' retirement-exempt "
                    f"(samples={rule['outcome_count']}, last-in-domain guard) — "
                    f"floored at {rule['confidence']:.3f}, not tombstoned."
                )

        save_json(SYMBOLIC_RULES_FILE, rules)
        # Invalidate cache
        try:
            from brain.symbolic import rule_engine as _re
            _re._rules_cache = []
        except Exception as _e:
            record_failure("rule_verifier._adjust_confidence", _e)
        break


def _rule_domain(rule: Dict) -> str:
    """Best-effort domain of a rule, from its conclusion + conditions text."""
    try:
        from brain.symbolic.prediction_engine import classify_domain
        text = " ".join([str(rule.get("conclusion") or "")]
                        + [str(c) for c in (rule.get("conditions") or [])])
        return classify_domain(text)
    except Exception as _e:
        record_failure("rule_verifier._rule_domain", _e)
        return "GENERAL"


def _is_usable(rule: Dict) -> bool:
    """A rule still able to fire: not tombstoned and above the tombstone floor."""
    return (rule.get("source") != "tombstoned"
            and float(rule.get("confidence", 0.0) or 0.0) > _TOMBSTONE_THRESH)


def _retirement_allowed(rule: Dict, rules: List[Dict]) -> bool:
    """Over-retirement guard. Refuse to tombstone a rule when (a) it has too few
    resolved outcomes to judge (under-learned → needs acquisition, not deletion),
    or (b) it is the last usable rule in its domain (a domain must never be left
    with zero usable rules purely by retirement — SOCIAL already sits at 0)."""
    if int(rule.get("outcome_count", 0)) < _MIN_SAMPLE:
        return False
    domain = _rule_domain(rule)
    siblings = sum(1 for r in rules
                   if r.get("id") != rule.get("id")
                   and _is_usable(r) and _rule_domain(r) == domain)
    return siblings > 0


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


def drain_revisions() -> Dict[str, int]:
    """Resolve every PENDING rule revision against the rule's current state, so a
    flagged revision never sits 'pending' forever (the run had 37 stuck). Decided
    by outcome, not by hand (T1.2 — "applied/rejected within a bounded window";
    called each dream cycle, so the window is one consolidation):

      • rule gone / already tombstoned     → "retired"
      • confidence recovered ≥ revision thr → "kept"   (it earned its way back)
      • still degraded, retirement allowed  → "retired" (tombstone the persistent
                                                          mispredictor)
      • still degraded, retirement guarded  → "weakened" (under-learned / last in
                                                          domain — keep, don't strip)

    Returns a small tally for the dream-cycle log. Fail-safe."""
    tally = {"kept": 0, "weakened": 0, "retired": 0}
    try:
        revisions = load_json(REVISIONS_FILE, default_type=list) or []
        pending = [r for r in revisions if r.get("status") == "pending"]
        if not pending:
            return tally

        from brain.symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
        rules = get_all_rules()
        by_id = {r.get("id"): r for r in rules}
        rules_changed = False

        for rev in pending:
            rid = rev.get("rule_id")
            rule = by_id.get(rid)
            if rule is None or rule.get("source") == "tombstoned":
                rev["status"] = "retired"
                tally["retired"] += 1
                continue
            conf = float(rule.get("confidence", 0.0) or 0.0)
            if conf >= _REVISION_THRESH:
                rev["status"] = "kept"
                tally["kept"] += 1
            elif _retirement_allowed(rule, rules):
                rule["source"] = "tombstoned"
                rules_changed = True
                rev["status"] = "retired"
                tally["retired"] += 1
            else:
                # Under-learned or last-in-domain: don't strip it, keep it
                # revisable. Resolve the revision so it stops blocking the queue.
                rev["status"] = "weakened"
                tally["weakened"] += 1

        save_json(REVISIONS_FILE, revisions)
        if rules_changed:
            save_json(SYMBOLIC_RULES_FILE, rules)
            try:
                from brain.symbolic import rule_engine as _re
                _re._rules_cache = []
            except Exception as _e:
                record_failure("rule_verifier.drain_revisions.cache", _e)
        if any(tally.values()):
            log_activity(f"[rule_verifier] Drained revisions: {tally}")
    except Exception as _e:
        record_failure("rule_verifier.drain_revisions", _e)
    return tally
