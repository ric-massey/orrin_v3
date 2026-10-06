"""Run 13 item 5 (DEMO_RUN_2026-08-19 §4.2): a host suspension mid-life is credited
as sleep, not lived. Run 12 slept 12.4 h, woke, and died of old age 17 s later."""
from datetime import datetime, timedelta, timezone

from brain.cognition import runtime_lifetime as rl
from brain.utils.json_utils import load_json, save_json


def _roll(started_hours_ago: float, lifespan_days: float) -> None:
    start = datetime.now(timezone.utc) - timedelta(hours=started_hours_ago)
    save_json(rl.LIFESPAN_FILE, {"start_time": start.isoformat(), "lifespan_days": lifespan_days,
                                 "noise_days": 0.0, "slept_seconds": 0.0})


def test_short_gap_is_not_a_suspension(monkeypatch):
    _roll(1, 1.0)
    monkeypatch.setattr(rl, "_clock_ref", None)
    assert rl.detect_suspension(wall=1000.0, mono=50.0) == 0.0
    assert rl.detect_suspension(wall=1030.0, mono=75.0) == 0.0   # 5 s drift, not sleep
    assert load_json(rl.LIFESPAN_FILE, default_type=dict)["slept_seconds"] == 0.0


def test_suspension_is_credited_and_counted(monkeypatch):
    _roll(1, 1.0)
    monkeypatch.setattr(rl, "_clock_ref", None)
    rl.detect_suspension(wall=1000.0, mono=50.0)
    gap = rl.detect_suspension(wall=1000.0 + 12.4 * 3600 + 4, mono=54.0)
    assert round(gap) == round(12.4 * 3600)
    data = load_json(rl.LIFESPAN_FILE, default_type=dict)
    assert round(data["slept_seconds"]) == round(12.4 * 3600)
    assert data["suspension_count"] == 1


def test_run12_shape_no_longer_dies_on_waking(monkeypatch):
    # 28 h since birth on a 1.16-day (27.8 h) lifespan: dead by wall clock. With
    # 12.4 h of that spent suspended, only ~15.6 h were lived.
    _roll(28, 1.16)
    assert rl.real_deadline_passed() is True
    monkeypatch.setattr(rl, "_clock_ref", None)
    rl.detect_suspension(wall=0.0, mono=0.0)
    rl.detect_suspension(wall=12.4 * 3600, mono=0.0)
    assert rl.real_deadline_passed() is False
