# brain/symbolic/rule_forgetting.py
# Active forgetting system — demotes, prunes, and retires stale symbolic knowledge.
#
# Three mechanisms:
#
#   1. Idle decay — rules with no WAL firing in N days lose confidence at
#      _DECAY_RATE_PER_WEEK per week of inactivity above the threshold.
#      A rule that reaches _TOMBSTONE_THRESH is soft-deleted.
#
#   2. Overfit pruning — rules with >_MAX_CONDITIONS conditions AND <_MIN_HITS
#      hits have their least-frequent condition dropped, making them more general.
#      A slight confidence bump rewards the simplification.
#
#   3. Concept retirement — concept nodes in the KG whose backing rules are all
#      tombstoned get tagged "retired" so analogy/search stops surfacing them.
#
# Entry point: run_forgetting_cycle(context) → {decayed, pruned, retired, total_changes}
# Called from dream_cycle at each dream pass.
#
# SCIENTIFIC BASIS:
#   Ebbinghaus (1885) — "Über das Gedächtnis." The forgetting curve: unused
#   memories decay exponentially with time. Idle decay here operationalizes this
#   as weekly confidence loss on rules that fire below threshold frequency.
#   Bjork (1994) — "Memory and metamemory considerations in the training of human
#   beings." In J. Metcalfe & A. Shimamura (Eds.), Metacognition. MIT Press.
#   Desirable difficulties: infrequently-fired rules lose confidence, but can
#   recover if re-encountered — mirroring spaced-repetition consolidation.
from __future__ import annotations
from core.runtime_log import get_logger

import json
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Optional

from utils.json_utils import load_json, save_json
from utils.log import log_activity
from brain.paths import DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_IDLE_DAYS_THRESH    = 21          # no firing in this many days → start decay
_DECAY_RATE_PER_WEEK = 0.012       # confidence reduction per idle week
_MAX_CONDITIONS      = 5           # over-specific threshold
_MIN_HITS_PRUNE      = 3           # only prune if hits below this
_TOMBSTONE_THRESH    = 0.20        # mirrors rule_verifier
_WAL_FILE            = DATA_DIR / "rule_firings.jsonl"
_FORGETTING_LOG      = DATA_DIR / "forgetting_log.json"


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_forgetting_cycle(context: Optional[Dict] = None) -> Dict:
    decayed  = decay_idle_rules()
    pruned   = prune_overfitted_rules()
    retired  = retire_stale_concepts()

    # Decay signal_score pattern weights in sync with rule forgetting
    patterns_pruned = 0
    try:
        from symbolic.pattern_scorer import decay_patterns as _dp
        patterns_pruned = _dp()
        if patterns_pruned:
            log_activity(f"[forgetting] Intuition: {patterns_pruned} pattern tokens pruned")
    except Exception as _e:
        record_failure("rule_forgetting.run_forgetting_cycle", _e)

    total = decayed + pruned + retired
    if total:
        log_activity(
            f"[forgetting] Cycle complete: {decayed} decayed, "
            f"{pruned} pruned, {retired} retired."
        )
    _append_forgetting_log({"decayed": decayed, "pruned": pruned, "retired": retired})
    return {"decayed": decayed, "pruned": pruned, "retired": retired, "total_changes": total}


# ─── 1. Idle decay ────────────────────────────────────────────────────────────

def _last_firing_times() -> Dict[str, float]:
    """Read WAL and return {rule_id: last_ts} for all rules that have fired."""
    if not _WAL_FILE.exists():
        return {}
    last: Dict[str, float] = {}
    try:
        for line in _WAL_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                rid = e.get("rule_id", "")
                ts  = float(e.get("ts", 0))
                if rid and ts > last.get(rid, 0):
                    last[rid] = ts
            except Exception as _e:
                record_failure("rule_forgetting._last_firing_times", _e)
    except Exception as _e:
        record_failure("rule_forgetting._last_firing_times.2", _e)
    return last


def decay_idle_rules(days_threshold: int = _IDLE_DAYS_THRESH) -> int:
    try:
        from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
    except Exception:
        return 0

    rules = get_all_rules()
    now   = time.time()
    idle_cutoff_s = days_threshold * 86400
    firing_times  = _last_firing_times()
    decay_count   = 0

    for rule in rules:
        if rule.get("source") == "tombstoned":
            continue

        rid = rule.get("id", "")
        if rid in firing_times:
            last_ts = firing_times[rid]
        else:
            created = rule.get("created_at", "")
            try:
                last_ts = datetime.fromisoformat(created).timestamp() if created else now
            except Exception:
                last_ts = now

        idle_secs = now - last_ts
        if idle_secs < idle_cutoff_s:
            continue

        idle_weeks = idle_secs / (7 * 86400)
        decay      = round(_DECAY_RATE_PER_WEEK * idle_weeks, 4)
        old_conf   = float(rule.get("confidence", 0.75))
        new_conf   = round(max(_TOMBSTONE_THRESH + 0.01, old_conf - decay), 4)
        if new_conf == old_conf:
            continue

        rule["confidence"] = new_conf
        decay_count += 1
        log_activity(
            f"[forgetting] Idle decay '{rid}': "
            f"conf {old_conf:.3f}→{new_conf:.3f} ({idle_weeks:.1f}wk idle)"
        )

        if new_conf <= _TOMBSTONE_THRESH:
            rule["source"] = "tombstoned"
            log_activity(f"[forgetting] '{rid}' tombstoned via idle decay.")

    if decay_count:
        save_json(SYMBOLIC_RULES_FILE, rules)
        _invalidate_rule_cache()

    return decay_count


# ─── 2. Overfit pruning ───────────────────────────────────────────────────────

def prune_overfitted_rules(
    max_conditions: int = _MAX_CONDITIONS,
    min_hits: int = _MIN_HITS_PRUNE,
) -> int:
    try:
        from symbolic.rule_engine import get_all_rules, SYMBOLIC_RULES_FILE
    except Exception:
        return 0

    rules = get_all_rules()

    # Build condition frequency map across all non-tombstoned rules
    cond_freq: Counter = Counter()
    for r in rules:
        if r.get("source") != "tombstoned":
            for c in (r.get("conditions") or []):
                cond_freq[str(c).lower()] += 1

    pruned_count = 0
    for rule in rules:
        if rule.get("source") in ("tombstoned", "abstraction"):
            continue
        conditions = rule.get("conditions") or []
        hits = int(rule.get("hits", 0))
        if len(conditions) <= max_conditions or hits >= min_hits:
            continue

        # Drop the condition that appears least frequently across all rules
        rarest = min(conditions, key=lambda c: cond_freq.get(str(c).lower(), 0))
        new_conditions = [c for c in conditions if c != rarest]
        if not new_conditions:
            continue

        old_conf = float(rule.get("confidence", 0.75))
        rule["conditions"] = new_conditions
        rule["confidence"] = round(min(old_conf + 0.005, 0.95), 4)
        pruned_count += 1
        log_activity(
            f"[forgetting] Pruned '{str(rarest)[:40]}' from rule '{rule.get('id')}' "
            f"({len(conditions)}→{len(new_conditions)} conds, {hits} hits)"
        )

    if pruned_count:
        save_json(SYMBOLIC_RULES_FILE, rules)
        _invalidate_rule_cache()

    return pruned_count


# ─── 3. Concept retirement ────────────────────────────────────────────────────

def retire_stale_concepts() -> int:
    """
    Mark concept KG nodes as retired when no active rule references them.
    Uses add_entity with a 'retired' tag rather than deletion to preserve history.
    """
    try:
        from symbolic.rule_engine import get_all_rules
        from cognition.knowledge_graph import add_entity
    except Exception:
        return 0

    rules = get_all_rules()
    active_text = " ".join(
        " ".join(r.get("conditions") or []) + " " + r.get("conclusion", "")
        for r in rules
        if r.get("source") != "tombstoned"
        and float(r.get("confidence", 0)) > _TOMBSTONE_THRESH
    ).lower()

    # Query KG for concept-type entities
    try:
        from cognition.knowledge_graph import _load_graph
        g = _load_graph()
        entities = [
            e for e in g.get("entities", {}).values()
            if e.get("type") == "concept"
            and "retired" not in (e.get("tags") or [])
        ]
    except Exception:
        return 0

    retired_count = 0
    for entity in entities:
        name = entity.get("name", "").lower()
        if not name:
            continue
        # Check if any active rule mentions this concept
        if name in active_text:
            continue
        # Retire: re-add with "retired" tag
        try:
            existing_tags = list(entity.get("tags") or [])
            existing_tags.append("retired")
            add_entity(
                name=entity["name"],
                entity_type="concept",
                properties={"description": entity.get("description", "")},
                extra_tags=existing_tags,
            )
            retired_count += 1
            log_activity(f"[forgetting] Concept '{entity['name']}' retired (no active rule refs).")
        except Exception as _e:
            record_failure("rule_forgetting.retire_stale_concepts", _e)

    return retired_count


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _invalidate_rule_cache() -> None:
    try:
        from symbolic import rule_engine as _re
        _re._rules_cache = []
    except Exception as _e:
        record_failure("rule_forgetting._invalidate_rule_cache", _e)


def _append_forgetting_log(entry: Dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        existing = load_json(_FORGETTING_LOG, default_type=list) or []
        existing.append(entry)
        save_json(_FORGETTING_LOG, existing[-90:])
    except Exception as _e:
        record_failure("rule_forgetting._append_forgetting_log", _e)


def get_forgetting_stats(days: int = 7) -> Dict:
    """Return aggregate forgetting stats for the last N days."""
    entries = load_json(_FORGETTING_LOG, default_type=list) or []
    cutoff_ts = time.time() - days * 86400
    recent = []
    for e in entries:
        try:
            ts = datetime.fromisoformat(e.get("timestamp", "")).timestamp()
            if ts >= cutoff_ts:
                recent.append(e)
        except Exception as _e:
            record_failure("rule_forgetting.get_forgetting_stats", _e)
    return {
        "total_decayed":  sum(e.get("decayed", 0) for e in recent),
        "total_pruned":   sum(e.get("pruned", 0) for e in recent),
        "total_retired":  sum(e.get("retired", 0) for e in recent),
        "cycles":         len(recent),
    }
