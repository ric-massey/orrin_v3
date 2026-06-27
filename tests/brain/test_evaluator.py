# tests/brain/test_evaluator.py
from __future__ import annotations

from unittest.mock import patch, MagicMock


# WAL tests

def test_wal_append_and_load(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all
        append_pending("did-1", "reflect", {"a": 1.0}, cycle=5)
        append_pending("did-2", "dream", {"b": 0.5}, cycle=6)
        entries = load_all()
    assert len(entries) == 2
    assert entries[0]["decision_id"] == "did-1"
    assert entries[0]["action"] == "reflect"
    assert entries[0]["resolved"] is False
    assert entries[1]["decision_id"] == "did-2"


def test_wal_rewrite(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all, rewrite
        append_pending("did-1", "reflect", {}, cycle=1)
        append_pending("did-2", "dream", {}, cycle=2)
        entries = load_all()
        entries[0]["resolved"] = True
        rewrite(entries)
        reloaded = load_all()
    assert len(reloaded) == 2
    assert reloaded[0]["resolved"] is True
    assert reloaded[1]["resolved"] is False


def test_wal_appends_goal_id(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all
        append_pending("did-3", "plan", {"x": 1.0}, cycle=10, committed_goal_id="goal-abc")
        entries = load_all()
    assert entries[0]["committed_goal_id"] == "goal-abc"


# EvaluatorDaemon Signal A (retrieval)

def _make_retrieved_item(decision_id: str):
    item = MagicMock()
    item.meta = {"decision_id": decision_id}
    return item


def test_signal_a_fires_when_memory_retrieved(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all
        from brain.eval.evaluator_daemon import EvaluatorDaemon

        append_pending("did-x", "reflect", {"a": 0.5}, cycle=1)
        ctx = {"retrieved_memories": [_make_retrieved_item("did-x")]}

        ev = EvaluatorDaemon()
        with patch("brain.think.bandit.contextual_bandit.update_delayed"), \
             patch("brain.think.loop_helpers.emit_trace"):
            ev.tick(ctx, cycle=3)

        entries = load_all()
    resolved = [e for e in entries if e["resolved"]]
    assert len(resolved) == 1
    assert resolved[0]["resolved_by"] == "retrieval_A"
    assert resolved[0]["reward"] > 0.5  # age=2 still high


def test_signal_a_does_not_fire_when_no_match(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all
        from brain.eval.evaluator_daemon import EvaluatorDaemon

        append_pending("did-y", "dream", {}, cycle=1)
        ctx = {"retrieved_memories": [_make_retrieved_item("did-z")]}  # different id

        ev = EvaluatorDaemon()
        ev.tick(ctx, cycle=2)

        entries = load_all()
    assert all(not e["resolved"] for e in entries)


def test_old_entries_pruned(tmp_path):
    wal_file = tmp_path / "test_wal.jsonl"
    with patch("brain.eval.evaluator_wal.EVALUATOR_WAL", wal_file):
        from brain.eval.evaluator_wal import append_pending, load_all
        from brain.eval.evaluator_daemon import EvaluatorDaemon

        append_pending("did-old", "reflect", {}, cycle=1)
        ctx = {"retrieved_memories": []}

        ev = EvaluatorDaemon()
        # Age = 501 > AGE_TIMEOUT=500 -> prune
        ev.tick(ctx, cycle=502)

        entries = load_all()
    resolved = [e for e in entries if e["resolved"]]
    assert len(resolved) == 1
    assert resolved[0]["resolved_by"] == "pruned"
    assert resolved[0]["reward"] == 0.0


# update_delayed wiring

def test_update_delayed_calls_bandit_update(tmp_path):
    from brain.think.bandit.contextual_bandit import update_delayed
    with patch("brain.think.bandit.contextual_bandit.update") as mock_update, \
         patch("brain.think.loop_helpers.emit_trace"):
        update_delayed("reflect", {"a": 1.0}, 0.75, decision_id="did-test")
        # Delayed rewards use the default (None → UCB1 sample-mean), not a forced rate.
        mock_update.assert_called_once_with("reflect", {"a": 1.0}, 0.75, lr=None, l2=0.001)
