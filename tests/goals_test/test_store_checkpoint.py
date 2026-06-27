# T0.4 — the goals store must compact its append-only state.jsonl + WAL so a
# long / multi-day run can't grow them without bound.
from pathlib import Path

from goals.store import FileGoalsStore
from goals.model import Goal, Status


def _wal_lines(p: Path) -> int:
    return len(p.read_text(encoding="utf-8").splitlines()) if p.exists() else 0


def _goal(i: int) -> Goal:
    return Goal(id=f"g{i % 5}", title=f"goal {i % 5}", kind="generic",
                spec={}, status=Status.NEW)


def test_checkpoint_compacts_wal_and_preserves_goals(tmp_path):
    store = FileGoalsStore(tmp_path)
    # Many upserts of a handful of goals → the WAL accrues a line per upsert.
    for i in range(50):
        store.upsert_goal(_goal(i))
    wal = Path(store.paths()["wal"])
    before = _wal_lines(wal)
    assert before >= 50  # append-only: one line per upsert

    report = store.checkpoint(keep_tail_lines=5)
    assert isinstance(report, dict)

    after = _wal_lines(wal)
    assert after < before  # WAL was compacted
    # The compaction loses no live goals: the 5 distinct goals survive.
    assert store.counts()["goals"] == 5
    # A fresh store reloading from the compacted state.jsonl sees the same goals.
    reloaded = FileGoalsStore(tmp_path)
    assert reloaded.counts()["goals"] == 5
    assert _wal_lines(wal) == after
