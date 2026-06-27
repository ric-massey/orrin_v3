"""Unit tests for reaper.trend — the shared (t, v) time-series helpers extracted
from host_resources.py / memory.py (structure audit §8)."""
from collections import deque

from reaper.trend import slope, trim, window_ok


def _series(points):
    return deque(points)


def test_trim_drops_stale_left():
    dq = _series([(0.0, 1.0), (1.0, 2.0), (5.0, 3.0)])
    trim(dq, cutoff=2.0)
    assert list(dq) == [(5.0, 3.0)]


def test_window_ok_requires_two_points_and_span():
    assert window_ok(_series([(0.0, 1.0)]), need_s=10.0) is False
    # span 9.6 >= 10 * 0.95 (9.5) → ok with the jitter slack
    assert window_ok(_series([(0.0, 1.0), (9.6, 1.0)]), need_s=10.0) is True
    # span 9.0 < 9.5 → not enough window yet
    assert window_ok(_series([(0.0, 1.0), (9.0, 1.0)]), need_s=10.0) is False


def test_slope_none_when_insufficient_or_degenerate():
    assert slope(_series([])) is None
    assert slope(_series([(1.0, 5.0)])) is None
    # all samples at the same timestamp → degenerate denominator
    assert slope(_series([(2.0, 1.0), (2.0, 9.0)])) is None


def test_slope_recovers_linear_rate():
    # v = 3 * t  → slope 3.0
    dq = _series([(0.0, 0.0), (1.0, 3.0), (2.0, 6.0), (3.0, 9.0)])
    assert abs(slope(dq) - 3.0) < 1e-9
    # flat series → 0.0
    assert abs(slope(_series([(0.0, 5.0), (1.0, 5.0), (2.0, 5.0)]))) < 1e-9
