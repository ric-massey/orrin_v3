# brain/cognition/entropy_budget.py
#
# C9 (Run 11 §6.1b, with §8-E1) — the GLOBAL entropy budget.
#
# Local decay organs exist everywhere (memory strength, rule forgetting, WAL
# trims, salience decay, consolidation) but nothing accounts globally — the
# rising RSS floor is unaudited accumulation with no knowledge-vs-cruft split.
# This is the one ledgered view: what GREW, what was COMPRESSED (many memos →
# one principle), what was FORGOTTEN, bucketed per life-quarter, so the §10
# gate can read "≥1 measured consolidation-compression event" and the 20k
# memory ceiling has an audit trail instead of a mystery floor.
#
# Writers: update_long_memory (grew), prune_long_memory (forgotten), the
# memory daemon's compact_and_promote (compressed), effect-artifact capture
# (grew). Cheap counters; never block the writer's path.
from __future__ import annotations

import threading
import time
from typing import Any, Dict

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json

_FILE = DATA_DIR / "entropy_budget.json"
_KINDS = ("grew", "compressed", "forgotten")
_QUARTER_CYCLES = 5000    # a 20k-cycle life = 4 quarters

_lock = threading.Lock()
# Growth events fire many times per cycle — buffer in memory and flush in
# batches so the ledger never becomes per-write disk churn on the hot path.
_pending: Dict[str, Dict[str, Dict[str, int]]] = {}
_pending_n = 0
_last_flush = 0.0
_FLUSH_EVERY_N = 20
_FLUSH_EVERY_S = 60.0


def _quarter() -> str:
    try:
        from brain.utils.get_cycle_count import get_cycle_count
        return f"q{int(get_cycle_count()) // _QUARTER_CYCLES}"
    except Exception:  # intentional: cycle counter unavailable → unbucketed quarter
        return "q?"


def note(kind: str, channel: str, n: int = 1) -> None:
    """Count `n` items that grew / were compressed / were forgotten on
    `channel` (e.g. long_memory, memory_store, effect_artifacts)."""
    global _pending_n, _last_flush
    if kind not in _KINDS or not channel or n <= 0:
        return
    try:
        now = time.time()
        with _lock:
            q = _pending.setdefault(_quarter(), {k: {} for k in _KINDS})
            bucket = q.setdefault(kind, {})
            bucket[str(channel)] = int(bucket.get(str(channel), 0) or 0) + int(n)
            _pending_n += 1
            if _pending_n >= _FLUSH_EVERY_N or (now - _last_flush) >= _FLUSH_EVERY_S:
                _flush_locked(now)
    except Exception as exc:
        record_failure("entropy_budget.note", exc)


def _flush_locked(now: float) -> None:
    global _pending_n, _last_flush
    if not _pending:
        _pending_n = 0
        _last_flush = now
        return
    d = load_json(_FILE, default_type=dict) or {}
    if not isinstance(d, dict):
        d = {}
    for qk, q in _pending.items():
        dq = d.setdefault(qk, {k: {} for k in _KINDS})
        for kind, chans in q.items():
            if kind not in _KINDS:
                continue
            db = dq.setdefault(kind, {})
            for ch, n in chans.items():
                db[ch] = int(db.get(ch, 0) or 0) + int(n)
    d["updated"] = round(now, 1)
    save_json(_FILE, d)
    _pending.clear()
    _pending_n = 0
    _last_flush = now


def flush() -> None:
    """Force the buffered counts to disk (tests / shutdown)."""
    try:
        with _lock:
            _flush_locked(time.time())
    except Exception as exc:
        record_failure("entropy_budget.flush", exc)


def snapshot() -> Dict[str, Any]:
    """The full per-quarter ledger (run analysis / §10 gate)."""
    flush()
    d = load_json(_FILE, default_type=dict) or {}
    return d if isinstance(d, dict) else {}


def compression_events() -> int:
    """Total measured compression events this life — the E1 gate readout."""
    total = 0
    for qk, q in snapshot().items():
        if isinstance(q, dict):
            total += sum(int(v or 0) for v in (q.get("compressed") or {}).values())
    return total
