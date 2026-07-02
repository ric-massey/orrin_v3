# AR6 (CODEBASE_AUDIT_2026-07-01 M3): the vector store is in-memory, so a
# restart began amnesiac. Boot now replays the tail of the memory WAL through
# the normal ingest path, so the store holds pre-restart events on the first
# cycle — and replayed events are marked so the daemon never appends them to
# the WAL a second time (no log growth per restart).
from __future__ import annotations

from pathlib import Path

import memory.wal as wal_mod
from memory.models import Event
from memory.wal import WAL


def _write_events(tmp_path: Path, n: int) -> Path:
    events_path = tmp_path / "events.jsonl"
    items_path = tmp_path / "items.jsonl"
    w = WAL(events_path, items_path, max_bytes=10_000_000, gzip_rotate=False)
    for i in range(n):
        w.append_event(Event(kind="chat:user", content=f"pre-restart fact {i}", meta={}))
    w.flush()
    return events_path


def test_replay_returns_pre_restart_events(tmp_path, monkeypatch):
    events_path = _write_events(tmp_path, 5)
    monkeypatch.setattr(wal_mod.MEMCFG, "WAL_EVENTS_PATH", events_path)

    replayed = wal_mod.replay_recent_events()
    assert [e.content for e in replayed] == [f"pre-restart fact {i}" for i in range(5)]
    assert all(e.meta.get("_replay") for e in replayed)


def test_replay_caps_to_the_tail(tmp_path, monkeypatch):
    events_path = _write_events(tmp_path, 30)
    monkeypatch.setattr(wal_mod.MEMCFG, "WAL_EVENTS_PATH", events_path)

    replayed = wal_mod.replay_recent_events(limit=10)
    assert len(replayed) == 10
    assert replayed[-1].content == "pre-restart fact 29"


def test_replay_missing_wal_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wal_mod.MEMCFG, "WAL_EVENTS_PATH", tmp_path / "absent.jsonl")
    assert wal_mod.replay_recent_events() == []


def test_daemon_does_not_rewal_replayed_events(tmp_path, monkeypatch):
    # After a simulated restart + replay + daemon tick, the store holds the
    # pre-restart events but the WAL has NOT grown.
    import memory.memory_daemon as md
    from memory.memory_daemon import MemoryDaemon
    from memory.store.inmem import InMemoryStore

    events_path = _write_events(tmp_path, 4)
    monkeypatch.setattr(wal_mod.MEMCFG, "WAL_EVENTS_PATH", events_path)

    appended = []
    monkeypatch.setattr(md, "wal_append_event", lambda ev: appended.append(ev))
    monkeypatch.setattr(md, "wal_append_items", lambda items: len(list(items)))

    store = InMemoryStore()
    daemon = MemoryDaemon(store)
    for ev in wal_mod.replay_recent_events():
        daemon.ingest(ev)
    daemon._tick()  # drain synchronously — no thread needed

    assert store.stats().get("items_total", 0) > 0, "replayed events must reach the store"
    assert appended == [], "replayed events must not be re-appended to the WAL"

    # a NEW (non-replay) event still hits the WAL
    daemon.ingest(Event(kind="chat:user", content="a genuinely new post-restart fact", meta={}))
    daemon._tick()
    assert len(appended) == 1
