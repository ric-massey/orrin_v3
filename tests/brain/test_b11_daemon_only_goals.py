"""B11 (Run 13 verdict §4b A) — daemon-owned waiting goals are not brain goals.

A characterize goal waits up to 6 h for fresh telemetry. Run 13 committed it as a
brain goal, closed it within minutes, "repaired" the still-running daemon copy and
re-absorbed it every ~15 min: all 18 desyncs, 53–78 % of focus, and 67,884 of the
daemon's 72,010 WAL rows (identical rewrites of the deferring check step).
Fixtures are excerpts of the Run 13 capture (tests/fixtures/run13/).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import brain.goal_io as gio
from goals.model import step_from_dict
from goals.store import FileGoalsStore

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"


def _characterize_node(status: str = "in_progress") -> dict:
    node = json.loads((FIX / "characterize_v1_node.json").read_text())
    node["status"] = status
    return node


def test_characterize_goal_is_never_committable(monkeypatch):
    other = {"name": "Understand tides", "title": "Understand tides", "kind": "research",
             "tier": "growth", "status": "in_progress", "priority": "NORMAL", "id": "g_x"}
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: [_characterize_node(), other])
    names = [g.get("name") for g in gio._committable_from_v1_tree(limit=10)]
    assert names == ["Understand tides"]


def test_v1_close_does_not_cancel_running_characterization(monkeypatch):
    node = _characterize_node(status="completed")
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: [node])
    monkeypatch.setattr(gio, "_goal_to_v1", lambda g: dict(g.as_v1))
    closed: list = []
    monkeypatch.setattr(gio, "close_goal_v2", lambda vid, **k: closed.append(vid) or True)
    running = SimpleNamespace(as_v1={**node, "status": "in_progress"})
    api = SimpleNamespace(list_goals=lambda **k: [running])
    gio._reconcile_open_v2_into_v1(api)
    assert closed == []


def test_reconcile_skips_orphan_repair_for_characterize(monkeypatch):
    from brain.cognition.planning import goal_reconcile as gr
    from goals.model import Status
    node = _characterize_node(status="completed")
    v2 = SimpleNamespace(id=node["id"], title=node["title"], kind="characterize",
                         status=Status.RUNNING)
    monkeypatch.setattr(gio, "_api_ref", SimpleNamespace(list_goals=lambda **k: [v2]))
    monkeypatch.setattr("brain.cognition.planning.goals.load_goals", lambda: [node])
    closed: list = []
    monkeypatch.setattr(gio, "close_goal_v2", lambda vid, **k: closed.append(vid) or True)
    assert gr.reconcile_goal_stores() == 0
    assert closed == []


def test_unchanged_step_upserts_write_one_wal_row(tmp_path):
    """Replays the first 120 Run-13 step upserts (3 distinct states)."""
    store = FileGoalsStore(tmp_path / "goals")
    rows = [json.loads(line)["step"]
            for line in (FIX / "characterize_wal_excerpt.jsonl").read_text().splitlines()]
    for r in rows:
        store.upsert_step(step_from_dict(r))
    wal = [json.loads(line) for line in (tmp_path / "goals" / "wal.log").read_text().splitlines()]
    assert len(rows) == 120
    assert len(wal) == 3
    # The in-memory step still reflects the last write.
    last = rows[-1]
    assert store.get_step(last["id"]).last_error == last["last_error"]


def test_changed_step_is_still_written(tmp_path):
    store = FileGoalsStore(tmp_path / "goals")
    row = json.loads((FIX / "characterize_wal_excerpt.jsonl").read_text().splitlines()[0])["step"]
    s = step_from_dict(row)
    store.upsert_step(s)
    s.last_error = "DEFERRED: 12 fresh rows; driver not yet recurred enough"
    store.upsert_step(s)   # same object mutated in place — must still persist
    wal = (tmp_path / "goals" / "wal.log").read_text().splitlines()
    assert len(wal) == 2
