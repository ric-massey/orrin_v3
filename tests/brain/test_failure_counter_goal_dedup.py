"""Run 13 item 10: one failures.jsonl row per goal failure. Run 12 logged all three
failed goals twice — once by the daemon runner, once by the brain's GoalFailed
handler (DEMO_RUN_2026-08-19 §4.7)."""
import json

from brain.utils import failure_counter as fc


def _rows():
    p = fc._data_dir() / "failures.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_same_goal_logged_once_across_lanes(monkeypatch):
    monkeypatch.setattr(fc, "_GOAL_FAILURES_SEEN", set())
    fc.record_goal_failure("g_dup_1", "Understand time", "ValueError: no URLs to fetch")
    fc.record_goal_failure("g_dup_1", "Understand time", "ValueError: no URLs to fetch")
    assert sum(1 for r in _rows() if r.get("goal_id") == "g_dup_1") == 1


def test_dedup_survives_restart_via_file_tail(monkeypatch):
    monkeypatch.setattr(fc, "_GOAL_FAILURES_SEEN", set())
    fc.record_goal_failure("g_dup_2", "t", "r")
    monkeypatch.setattr(fc, "_GOAL_FAILURES_SEEN", set())   # a fresh process
    fc.record_goal_failure("g_dup_2", "t", "r")
    assert sum(1 for r in _rows() if r.get("goal_id") == "g_dup_2") == 1


def test_distinct_goals_both_logged(monkeypatch):
    monkeypatch.setattr(fc, "_GOAL_FAILURES_SEEN", set())
    fc.record_goal_failure("g_a", "a", "r")
    fc.record_goal_failure("g_b", "b", "r")
    ids = {r.get("goal_id") for r in _rows()}
    assert {"g_a", "g_b"} <= ids
