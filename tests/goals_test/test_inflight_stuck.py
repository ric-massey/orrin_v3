# R10-6: the R9-F1 in-flight guard must not silently wedge dispatch. A step
# stuck inflight far past any sane execution time (a hung worker) is reported by
# stuck_inflight() so the daemon can log it loudly — but never reaped, because a
# live worker still owns the id and reaping re-opens the R9-F1 double-run race.

from __future__ import annotations

import queue
import time

from goals.runner import StepRunner
from goals.registry import GoalRegistry
from goals.store import FileGoalsStore


def _runner(tmp_path):
    store = FileGoalsStore(str(tmp_path / "goals.json"))
    return StepRunner(store=store, registry=GoalRegistry(), step_queue=queue.Queue(),
                      workers=0, ctx={}, reaper_sink=lambda e: None)


def test_stuck_inflight_reports_only_aged_ids(tmp_path):
    r = _runner(tmp_path)
    assert r._inflight_add("s_fresh") is True
    assert r._inflight_add("s_old") is True
    # Backdate s_old so it looks like it's been running a long time.
    r._inflight_since["s_old"] = time.monotonic() - 400.0

    stuck = r.stuck_inflight(older_than_s=300.0)
    ids = {sid for sid, _age in stuck}
    assert ids == {"s_old"}
    assert stuck[0][1] >= 300.0


def test_remove_clears_timestamp_and_unsticks(tmp_path):
    r = _runner(tmp_path)
    r._inflight_add("s1")
    r._inflight_since["s1"] = time.monotonic() - 999.0
    assert r.stuck_inflight(300.0)          # is stuck
    r._inflight_remove("s1")
    assert r.stuck_inflight(300.0) == []    # completion clears it
    assert "s1" not in r._inflight_since
    # And the id can be re-dispatched afterwards (not permanently wedged).
    assert r._inflight_add("s1") is True
