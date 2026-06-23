# brain/cognition/novelty_memory.py
#
# Fix 4 (explore_loop_fix_plan.md §5) — cross-call novelty memory for exploration
# actions. The exploration tools (search_own_files, grep_files, survey_environment…)
# dedup WITHIN one call but kept no memory ACROSS calls, so every invocation
# re-surfaced the same matches and reported false novelty — feeding a no-progress
# loop that nothing could detect (E3).
#
# This module gives each (goal, action) pair a small, aged, capped "already
# surfaced" set. It answers two questions the rest of the system needs:
#   • observe(...)        → was anything NEW surfaced this call?  (false-novelty fix)
#   • novel_count(...)    → monotonic count of distinct things ever surfaced
#                           (Fix 3 reads this so step-completion churn isn't
#                            mistaken for progress).
#   • barren_streak / is_exhausted(...) → the *satiety* signal for bounded-corpus
#                           exploration (Fix 1 §4.3 — a filesystem-exploration goal
#                           is "done" when repeated searching stops finding anything
#                           new, NOT when one action was logged).
#
# Scope is per-(goal_id, action) and AGED — never global+permanent — because the
# corpus genuinely grows (Orrin writes files), so "exhausted" must be able to
# lapse back to "novel" when the world changes (§5 Fix 4 scope/decay).
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import DATA_DIR

_STORE_FILE = DATA_DIR / "novelty_memory.json"

# Caps & decay (mirror the WM/inbox age+cap pattern already in the codebase).
_MAX_HASHES_PER_KEY = 256      # bound the seen-set per (goal, action)
_KEY_TTL_S          = 24 * 3600  # forget a (goal, action) record after a day idle
_BARREN_EXHAUSTED   = 3        # consecutive 0-new calls ⇒ this exploration is sated
# Diminishing-returns (habituation) satiety: a brain doesn't need ZERO new — it
# habituates when the RATE of new information falls. A call where < this fraction of
# results are new counts as "low novelty"; this many in a row ⇒ sated. This is the
# robust signal in a live system where the corpus (Orrin's own growing files) keeps
# emitting the occasional new match so the strict barren streak rarely lands.
_LOW_NOVELTY_RATIO  = 0.15
_LOW_NOVELTY_LIMIT  = 4


def _now() -> float:
    return time.time()


def _key(goal_id: str, action: str) -> str:
    return f"{str(goal_id or 'nogoal')}::{str(action or 'noaction')}"


def _load() -> Dict[str, Any]:
    try:
        store = load_json(_STORE_FILE, default_type=dict)
        return store if isinstance(store, dict) else {}
    except (OSError, ValueError):  # intentional: missing/malformed store → {}
        return {}


def _prune(store: Dict[str, Any]) -> Dict[str, Any]:
    """Drop records untouched for longer than the TTL (decay, not just cap)."""
    cutoff = _now() - _KEY_TTL_S
    return {
        k: v for k, v in store.items()
        if isinstance(v, dict) and float(v.get("ts", 0) or 0) >= cutoff
    }


def _save(store: Dict[str, Any]) -> None:
    try:
        save_json(_STORE_FILE, store)
    except Exception as _e:
        log_private(f"[novelty_memory] save failed: {_e}")


def _hash(item: str) -> str:
    return hashlib.sha1(str(item).strip().lower().encode("utf-8", "ignore")).hexdigest()[:16]


def observe(goal_id: str, action: str, items: List[str]) -> Dict[str, Any]:
    """Record the items an exploration call surfaced; report what was NEW.

    Returns a dict:
      novel         — bool, did this call surface at least one unseen item?
      new           — int,  count of unseen items this call
      total         — int,  monotonic distinct items ever surfaced for this (goal, action)
      barren_streak — int,  consecutive calls (incl. this) that surfaced nothing new
      exhausted     — bool, barren_streak ≥ threshold ⇒ satiety for bounded-corpus search
    """
    store = _prune(_load())
    k = _key(goal_id, action)
    rec = store.get(k) if isinstance(store.get(k), dict) else None
    if rec is None:
        rec = {"hashes": [], "count": 0, "barren_streak": 0, "low_streak": 0, "ts": _now()}

    seen = set(rec.get("hashes") or [])
    new_hashes = []
    n_items = 0
    for it in (items or []):
        if not it:
            continue
        n_items += 1
        h = _hash(it)
        if h not in seen:
            seen.add(h)
            new_hashes.append(h)

    new_n = len(new_hashes)
    new_ratio = (new_n / n_items) if n_items else 0.0
    if new_n:
        rec["count"] = int(rec.get("count", 0)) + new_n
        rec["barren_streak"] = 0
        # Keep the most-recent hashes (cap → age the set, newest retained).
        merged = (rec.get("hashes") or []) + new_hashes
        rec["hashes"] = merged[-_MAX_HASHES_PER_KEY:]
    else:
        rec["barren_streak"] = int(rec.get("barren_streak", 0)) + 1
    # Diminishing-returns streak: a call that surfaced mostly-already-seen results
    # (or nothing) counts toward habituation, even if 1 new thing slipped in.
    if new_ratio <= _LOW_NOVELTY_RATIO:
        rec["low_streak"] = int(rec.get("low_streak", 0)) + 1
    else:
        rec["low_streak"] = 0
    rec["ts"] = _now()

    store[k] = rec
    _save(store)

    barren = int(rec.get("barren_streak", 0))
    low = int(rec.get("low_streak", 0))
    return {
        "novel": new_n > 0,
        "new": new_n,
        "total": int(rec.get("count", 0)),
        "barren_streak": barren,
        "low_streak": low,
        "exhausted": barren >= _BARREN_EXHAUSTED or low >= _LOW_NOVELTY_LIMIT,
    }


def novel_count(goal_id: str, action: Optional[str] = None) -> int:
    """Monotonic count of distinct items surfaced for this goal (Fix 3 reads this).
    When `action` is None, sums across all actions recorded for the goal."""
    store = _load()
    if action is not None:
        rec = store.get(_key(goal_id, action))
        return int(rec.get("count", 0)) if isinstance(rec, dict) else 0
    gid = str(goal_id or "nogoal")
    total = 0
    for k, v in store.items():
        if isinstance(v, dict) and k.startswith(f"{gid}::"):
            total += int(v.get("count", 0))
    return total


def is_exhausted(goal_id: str) -> Tuple[bool, str]:
    """Satiety signal for bounded-corpus exploration: True when at least one of the
    goal's exploration actions has gone barren for ≥ threshold consecutive calls.
    Returns (exhausted, reason)."""
    store = _load()
    gid = str(goal_id or "nogoal")
    for k, v in store.items():
        if not (isinstance(v, dict) and k.startswith(f"{gid}::")):
            continue
        action = k.split("::", 1)[1] if "::" in k else "?"
        if int(v.get("barren_streak", 0)) >= _BARREN_EXHAUSTED:
            return True, f"{action} barren×{v.get('barren_streak')}"
        if int(v.get("low_streak", 0)) >= _LOW_NOVELTY_LIMIT:
            return True, f"{action} diminishing×{v.get('low_streak')}"
    return False, ""
