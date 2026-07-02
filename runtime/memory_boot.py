"""Memory-subsystem boot (extracted from main.py to keep it under the size gate).

Builds the in-memory vector store + daemon and performs the AR6 (audit M3) WAL
boot replay: the store is in-memory, so every restart began amnesiac — semantic
recall stayed empty until new events accumulated. The tail of the memory WAL is
re-ingested through the normal path (re-embedded, novelty-scored) BEFORE the
daemon starts; replayed events carry meta._replay so the daemon does not append
them to the WAL a second time (which would grow the log every restart).
"""
from __future__ import annotations

from typing import Tuple

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)


def start_memory() -> Tuple[object, object]:
    """Build store + daemon, queue the WAL replay, start the daemon.

    Returns (store, daemon). Replay is best-effort: a broken WAL must never
    block boot.
    """
    from memory.store.inmem import InMemoryStore
    from memory.memory_daemon import MemoryDaemon

    store = InMemoryStore()
    daemon = MemoryDaemon(store)
    try:
        from memory.wal import replay_recent_events
        replayed = replay_recent_events()
        for ev in replayed:
            daemon.ingest(ev)
        if replayed:
            print(f"[memory] queued {len(replayed)} WAL events for boot replay")
    except Exception as e:
        _log.warning("WAL boot replay failed: %s", e)
    daemon.start()
    print("[memory] MemoryDaemon started with InMemoryStore")
    return store, daemon
