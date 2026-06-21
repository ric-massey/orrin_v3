# utils/memory_health.py
# Build a robust memory health provider bound to a daemon+store

from __future__ import annotations
from brain.core.runtime_log import get_logger
import time
from typing import Any, Dict
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

def build_memory_health_provider(daemon, store, memory_snapshot_func):
    """
    Returns a callable get_memory_health() -> dict
    that flattens snapshot and adds daemon/store hints.
    """
    def _getattr(obj, name, default=None):
        try:
            val = getattr(obj, name, default)
            return val() if callable(val) else val
        except Exception:
            return default

    def provider() -> Dict[str, Any]:
        # Daemon basics
        try:
            alive = daemon.is_alive() if hasattr(daemon, "is_alive") else bool(getattr(daemon, "thread", None) and daemon.thread.is_alive())
        except Exception:
            alive = False

        working_cache_size = int(_getattr(daemon, "working_cache_size", 0) or 0)
        last_compaction_ts = float(_getattr(daemon, "last_compaction_ts", 0.0) or 0.0)
        flush_failures     = int(_getattr(daemon, "flush_failures", 0) or 0)

        snap = {}
        try:
            snap = memory_snapshot_func(
                store,
                working_cache_size=working_cache_size,
                last_compaction_ts=last_compaction_ts,
                flush_failures=flush_failures,
            ) or {}
        except Exception as e:
            snap = {"status": "snapshot_error", "error": str(e)}

        ss = snap.get("store_stats")
        if ss is not None:
            try:
                if hasattr(ss, "__dict__"):
                    snap["store_stats"] = ss.__dict__
                elif hasattr(ss, "_asdict"):
                    snap["store_stats"] = ss._asdict()
            except Exception as _e:
                record_failure("memory_health.build_memory_health_provider.provider", _e)

        items = None
        bytes_total = None
        if isinstance(snap.get("store_stats"), dict):
            items = snap["store_stats"].get("items_total")
            for key in ("vector_bytes_total", "bytes_total", "approx_bytes", "mem_bytes"):
                if key in snap["store_stats"] and isinstance(snap["store_stats"][key], (int, float)):
                    bytes_total = int(snap["store_stats"][key])
                    break

        wal_enabled = bool(_getattr(store, "wal_enabled", False) or _getattr(daemon, "wal_enabled", False) or False)
        wal_queue   = _getattr(store, "wal_queue", None)
        if isinstance(wal_queue, bool):
            wal_queue = None
        try:
            wal_queue = int(wal_queue) if wal_queue is not None else None
        except Exception:
            wal_queue = None

        wal_lag_s = _getattr(store, "wal_last_flush_age_s", None)
        if wal_lag_s is None:
            ts = _getattr(store, "wal_last_flush_ts", None)
            if ts:
                try:
                    wal_lag_s = max(0.0, time.time() - float(ts))
                except Exception:
                    wal_lag_s = None

        out = {
            "daemon_alive": bool(alive),
            "store_type": type(store).__name__,
            "items": items,
            "bytes": bytes_total,
            "wal_enabled": wal_enabled,
            "wal_queue": wal_queue,
            "wal_lag_s": wal_lag_s,
            **snap,
        }
        return out

    return provider
