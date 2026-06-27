# brain/cognition/reflection/review_failures.py
#
# The failure ledger (master plan Phase 2.2): nineteen failures become one story.
#
# mark_goal_failed writes one durable long-memory entry per failure, but nothing
# ever read the failures *together* — so "failed nineteen times" never became
# "here is the kind of thing I keep getting wrong." This module clusters
# goal_failure memories by failure-reason + goal-kind tokens (symbolic, no LLM)
# and emits failure_pattern memories whose related_memory_ids point back at the
# clustered failures.
#
# Patterns feed:
#   (a) narrative pressure (+0.25, the same scale as a thread pivot) so repeated
#       failure becomes autobiography material;
#   (b) a planning prior — failure_pattern_discount() gives goals matching an
#       active pattern a strength discount at commitment time (Phase 4.3).
#
# Trigger: event-driven, not a timer — the review runs only when the durable
# failure count has risen by >= _TRIGGER_DELTA since the last review.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity
from brain.paths import DATA_DIR, LONG_MEMORY_FILE
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_REVIEW_STATE_FILE = DATA_DIR / "failure_review_state.json"
_TRIGGER_DELTA = 3          # new failures needed since last review
_CLUSTER_MIN = 2            # smallest cluster worth calling a pattern
_JACCARD_MIN = 0.4          # token overlap for two failures to share a cluster
_SCAN_LIMIT = 100           # most recent failures considered

_STOP = frozenset(
    "the and for are was with this that have from its not failed goal reason "
    "recorded unknown none could".split()
)


def _tok(text: str) -> Set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", str(text).lower()) if w not in _STOP}


def _failure_entries(long_mem: List[Dict]) -> List[Dict]:
    return [
        e for e in long_mem
        if isinstance(e, dict) and e.get("event_type") == "goal_failure" and e.get("content")
    ]


def _cluster(failures: List[Dict]) -> List[List[Dict]]:
    """Greedy token-overlap clustering: each failure joins the first cluster
    whose seed it overlaps by >= _JACCARD_MIN, else starts its own."""
    clusters: List[Dict[str, Any]] = []   # {"toks": set, "members": [entries]}
    for f in failures:
        toks = _tok(f.get("content", ""))
        if not toks:
            continue
        placed = False
        for c in clusters:
            union = toks | c["toks"]
            if union and len(toks & c["toks"]) / len(union) >= _JACCARD_MIN:
                c["members"].append(f)
                c["toks"] |= toks
                placed = True
                break
        if not placed:
            clusters.append({"toks": set(toks), "members": [f]})
    return [c["members"] for c in clusters]


def _digest(cluster: List[Dict]) -> str:
    """Shared-token description of what keeps going wrong — symbolic, no LLM."""
    common = _tok(cluster[0].get("content", ""))
    for f in cluster[1:]:
        common &= _tok(f.get("content", ""))
    theme = ", ".join(sorted(common)[:6]) or "similar circumstances"
    example = str(cluster[-1].get("content", ""))[:100]
    return f"recurring theme: {theme}. Most recent: {example}"


def review_failures(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Cognition function. Reads goal_failure long-memory entries, clusters them,
    and writes failure_pattern memories (importance 4, related_memory_ids = the
    clustered failures' UUIDs). Runs only when >= _TRIGGER_DELTA new failures
    have accumulated since the last review.
    """
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    failures = _failure_entries(long_mem)
    state = load_json(_REVIEW_STATE_FILE, default_type=dict) or {}
    last_count = int(state.get("last_count") or 0)
    if len(failures) < last_count:
        last_count = 0   # ledger shrank (pruning) — re-baseline

    new_failures = len(failures) - last_count
    if new_failures < _TRIGGER_DELTA:
        return (
            f"Failure review: {new_failures} new failure(s) since last review "
            f"(< {_TRIGGER_DELTA}) — nothing to consolidate yet."
        )

    # Don't re-emit patterns for failures already woven into one.
    already_patterned: Set[str] = set()
    for e in long_mem:
        if isinstance(e, dict) and e.get("event_type") == "failure_pattern":
            already_patterned.update(e.get("related_memory_ids") or [])

    candidates = [f for f in failures[-_SCAN_LIMIT:]
                  if f.get("id") and f["id"] not in already_patterned]
    clusters = [c for c in _cluster(candidates) if len(c) >= _CLUSTER_MIN]

    emitted = 0
    try:
        from brain.cog_memory.long_memory import update_long_memory
        for cluster in clusters:
            ids = [f["id"] for f in cluster if f.get("id")]
            content = (
                f"Failure pattern: {len(cluster)} similar goal failures — "
                f"{_digest(cluster)}. This is the kind of thing I keep getting wrong."
            )
            update_long_memory(
                content,
                emotion="impasse_signal",
                event_type="failure_pattern",
                importance=4,
                priority=3,
                related_memory_ids=ids,
                context=context,
            )
            emitted += 1
    except Exception as e:
        record_failure("review_failures.emit", e)

    if emitted:
        try:
            from brain.cognition.self_state.autobiography import add_narrative_pressure
            add_narrative_pressure(0.25, f"{emitted} failure pattern(s) consolidated")
        except Exception as e:
            record_failure("review_failures.pressure", e)

    state["last_count"] = len(failures)
    state["last_review_ts"] = datetime.now(timezone.utc).isoformat()
    state["patterns_emitted_total"] = int(state.get("patterns_emitted_total") or 0) + emitted
    try:
        save_json(_REVIEW_STATE_FILE, state)
    except Exception as e:
        record_failure("review_failures.state", e)

    msg = (
        f"Failure review: {new_failures} new failure(s), "
        f"{emitted} pattern(s) consolidated from {len(candidates)} unwoven failures."
    )
    log_activity(f"[review_failures] {msg}")
    return msg


def failure_pattern_discount(intention_text: str) -> float:
    """
    Planning prior (feeds Phase 4.3): how much to discount commitment strength
    for an intention that matches an active failure pattern. Returns 0.0–0.30.
    A vow on ground where vows keep breaking starts appropriately humbler.
    """
    try:
        toks = _tok(intention_text)
        if not toks:
            return 0.0
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        patterns = [
            e for e in long_mem
            if isinstance(e, dict) and e.get("event_type") == "failure_pattern"
        ][-10:]
        discount = 0.0
        for p in patterns:
            p_toks = _tok(p.get("content", ""))
            # Containment, not symmetric jaccard: the pattern text carries
            # boilerplate that would dilute the overlap. What matters is how
            # much of the INTENTION falls on patterned ground.
            if p_toks and len(toks & p_toks) / len(toks) >= 0.5:
                discount += 0.15
        return min(0.30, discount)
    except Exception as e:
        record_failure("review_failures.discount", e)
        return 0.0
