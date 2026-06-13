# Invariant test (Finding 11): replaying a WAL is idempotent — re-applying the
# same goal_upsert/step_upsert records to a store must leave it in the same
# state (and report the same counts) as the first replay. Complements
# test_wal.py::test_replay_to_store_applies_wal, which only checks a single
# replay.
from pathlib import Path

from goals import wal as W
from goals.store import FileGoalsStore


def test_replay_to_store_is_idempotent(tmp_path: Path):
    wal = tmp_path / "external.wal.log"
    store = FileGoalsStore(data_dir=tmp_path / "store")

    fixed_ts = "2026-01-01T00:00:00+00:00"
    W.append(wal, {
        "type": "goal_upsert",
        "goal": {
            "id": "g1", "title": "T", "kind": "research", "spec": {},
            "status": "NEW", "priority": "NORMAL",
            "created_at": fixed_ts, "updated_at": fixed_ts,
        },
    })
    W.append(wal, {
        "type": "step_upsert",
        "step": {
            "id": "s1", "goal_id": "g1", "name": "N", "action": {"op": "noop"},
            "status": "READY",
        },
    })

    report1 = W.replay_to_store(store, wal)
    g1_after_1 = store.get_goal("g1")
    s1_after_1 = store.get_step("s1")
    steps_after_1 = {s.id for s in store.steps_for("g1")}

    report2 = W.replay_to_store(store, wal)
    g1_after_2 = store.get_goal("g1")
    s1_after_2 = store.get_step("s1")
    steps_after_2 = {s.id for s in store.steps_for("g1")}

    assert report1 == report2 == {"goals": 1, "steps": 1, "skipped": 0}
    assert g1_after_1 == g1_after_2
    assert s1_after_1 == s1_after_2
    assert steps_after_1 == steps_after_2 == {"s1"}


def test_replay_to_store_repeated_full_replays_stable(tmp_path: Path):
    # A WAL with several upserts to the same goal/step (as would accumulate
    # over a real session) replayed multiple times must converge to the same
    # final state each time, with no duplicate steps appearing.
    wal = tmp_path / "external.wal.log"
    store = FileGoalsStore(data_dir=tmp_path / "store")

    for status in ("NEW", "READY", "RUNNING", "DONE"):
        W.append(wal, {
            "type": "goal_upsert",
            "goal": {
                "id": "g1", "title": "T", "kind": "research", "spec": {},
                "status": status, "priority": "NORMAL",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        })
    for status in ("READY", "RUNNING", "DONE"):
        W.append(wal, {
            "type": "step_upsert",
            "step": {
                "id": "s1", "goal_id": "g1", "name": "N", "action": {"op": "noop"},
                "status": status,
            },
        })

    W.replay_to_store(store, wal)
    snapshot1 = (store.get_goal("g1"), {s.id: s.status for s in store.steps_for("g1")})

    W.replay_to_store(store, wal)
    snapshot2 = (store.get_goal("g1"), {s.id: s.status for s in store.steps_for("g1")})

    assert snapshot1 == snapshot2
    # Final state reflects the LAST record for each id, not an accumulation.
    assert snapshot1[0].status == "DONE"
    assert snapshot1[1] == {"s1": "DONE"}
