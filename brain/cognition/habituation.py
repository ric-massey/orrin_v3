# brain/cognition/habituation.py
#
# Repeated exposure reduces affective salience.
#
# Orrin has been staring at the same goal for 40 cycles.
# It's still there, still real — but the affective punch per cycle diminishes.
# The temporal_pressure impasse_signal bump scales down. The WM entries
# feel familiar rather than urgent. Eventually, genuine novelty stands out
# by contrast, and stagnation_signal accumulates from the monotony of recognition.
#
# Tracked per content-hash: WM entries, goal ids, function picks.
#
# Effects:
#   - Habituated goal → context["_goal_habituation_factor"] < 1.0
#     temporal_pressure uses this to scale down age impasse_signal bumps
#   - High overall WM familiarity → stagnation_signal accumulation
#   - Does NOT erase memories — just dampens their affective response
#
# SCIENTIFIC BASIS:
#   Thompson & Spencer (1966) — "Habituation: A model phenomenon for the study
#   of neuronal substrates of behavior." Psychological Review, 173(1), 16–43.
#   The factor curve (count → multiplier) operationalizes parametric feature 1:
#   the strength and/or probability of the response decreases as stimulation
#   is repeated.

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.log import log_private
from brain.utils.json_utils import load_json, save_json
from brain.paths import HABITUATION_FILE, WORKING_MEMORY_FILE


_SAVE_EVERY_N = 6    # save habituation counts every N cycles to avoid per-cycle I/O
_PRUNE_EVERY_N = 250 # prune stale entries every N cycles

_cycle_counter = 0
_store_cache: Optional[Dict] = None   # in-memory cache; flushed every _SAVE_EVERY_N cycles


# ── Factor curve ───────────────────────────────────────────────────────────────
# count → multiplier for emotional responses
#   count=0:  1.00 (first time, full impact)
#   count=5:  0.76
#   count=15: 0.57
#   count=30: 0.45
#   count=60: 0.36 (approaching floor)

def get_factor(key: str, store: Optional[Dict] = None) -> float:
    """
    Habituation multiplier [0.30..1.00] for emotional responses to this key.
    1.0 = completely fresh; 0.30 = seen so often it barely registers.
    """
    s = store if store is not None else _get_store()
    entry = s.get(key)
    if not entry:
        return 1.0
    count = int(entry.get("count") or 0)
    return round(max(0.30, 0.30 + 0.70 / (1.0 + count / 10.0)), 3)


# ── Store management ───────────────────────────────────────────────────────────

def _get_store() -> Dict:
    global _store_cache
    if _store_cache is None:
        _store_cache = _load_store()
    return _store_cache


def _load_store() -> Dict:
    data = load_json(HABITUATION_FILE, default_type=dict) or {}
    return data if isinstance(data, dict) else {}


def _flush_store() -> None:
    global _store_cache
    if _store_cache is not None:
        save_json(HABITUATION_FILE, _store_cache)


def _record(store: Dict, key: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if key not in store:
        store[key] = {"count": 1, "first_seen": now, "last_seen": now}
    else:
        store[key]["count"] = int(store[key].get("count") or 0) + 1
        store[key]["last_seen"] = now


def _content_hash(text: str) -> str:
    """12-char hash of content, ignoring leading system tags like [memory]."""
    clean = text.strip()
    # Strip leading tags: "[memory] ..." → "..."
    if clean.startswith("[") and "]" in clean:
        clean = clean[clean.index("]") + 1:].strip()
    return hashlib.md5(clean[:200].encode("utf-8", errors="replace")).hexdigest()[:12]


# ── Main per-cycle entry point ─────────────────────────────────────────────────

def apply_habituation(context: Dict[str, Any]) -> Dict:
    """
    Called each cycle from finalize.py.
    Returns summary dict and sets context["_habituation"] and
    context["_goal_habituation_factor"].
    """
    global _cycle_counter
    _cycle_counter += 1
    try:
        return _apply(context)
    except Exception as e:
        log_private(f"[habituation] error: {e}")
        return {}


def _apply(context: Dict[str, Any]) -> Dict:
    store = _get_store()

    # ── 1. WM entries ──────────────────────────────────────────────────────────
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    wm_factors: List[float] = []

    for entry in (wm[-14:] if len(wm) > 14 else wm):
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content") or "")
        if not content or len(content) < 8:
            continue
        key = f"wm:{_content_hash(content)}"
        _record(store, key)
        wm_factors.append(get_factor(key, store))

    # ── 2. Active goal ─────────────────────────────────────────────────────────
    goal = context.get("committed_goal") or {}
    goal_factor = 1.0
    if isinstance(goal, dict) and (goal.get("title") or goal.get("id")):
        goal_key = f"goal:{goal.get('id') or goal.get('title')}"
        _record(store, goal_key)
        goal_factor = get_factor(goal_key, store)

    context["_goal_habituation_factor"] = goal_factor

    # ── 3. Recent function picks ───────────────────────────────────────────────
    for fn in (context.get("recent_picks") or [])[-6:]:
        if fn:
            _record(store, f"fn:{fn}")

    # ── 4. stagnation_signal from familiarity ────────────────────────────────────────────
    # When WM is mostly familiar (all habituated), genuine novelty is scarce.
    # stagnation_signal accumulates until something new breaks through.
    stagnation_signal_bump = 0.0
    if wm_factors:
        avg_factor = sum(wm_factors) / len(wm_factors)
        familiarity = 1.0 - avg_factor   # 0 = fresh, 1 = all habituated
        if familiarity > 0.60:
            stagnation_signal_bump = (familiarity - 0.60) * 0.07  # max ~0.028 per cycle

        if stagnation_signal_bump > 0:
            emo = context.get("affect_state") or {}
            core = emo.get("core_signals") or emo
            if isinstance(core, dict):
                core["stagnation_signal"] = min(1.0, float(core.get("stagnation_signal") or 0.0) + stagnation_signal_bump)
                if isinstance(emo.get("core_signals"), dict):
                    emo["core_signals"] = core
                else:
                    emo.update(core)
                context["affect_state"] = emo

    # ── 5. Periodic maintenance ────────────────────────────────────────────────
    if _cycle_counter % _PRUNE_EVERY_N == 0:
        _prune_store(store)

    if _cycle_counter % _SAVE_EVERY_N == 0:
        _flush_store()

    summary = {
        "wm_avg_factor": round(sum(wm_factors) / len(wm_factors), 3) if wm_factors else 1.0,
        "goal_factor":   round(goal_factor, 3),
        "stagnation_signal_bump":  round(stagnation_signal_bump, 4),
    }
    context["_habituation"] = summary
    return summary


def _prune_store(store: Dict) -> None:
    """Remove entries older than 30 days with count < 3 (noise, not signal)."""
    now = datetime.now(timezone.utc)
    stale = []
    for key, entry in store.items():
        if not isinstance(entry, dict):
            stale.append(key)
            continue
        count = int(entry.get("count") or 0)
        if count >= 3:
            continue
        last_str = entry.get("last_seen")
        if not last_str:
            stale.append(key)
            continue
        try:
            dt = datetime.fromisoformat(str(last_str))
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() > 30 * 86400:
                stale.append(key)
        except Exception:
            stale.append(key)
    for key in stale:
        store.pop(key, None)
