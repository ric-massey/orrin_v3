# Cycle-stall tripwire (Run 8 §0 owed item): the pulse-based heartbeat missed a
# dead brain thread for 6.5 h because surviving threads kept feeding the pulse.
# CycleStallGuard keys on the production_loop cycle stamp instead and triggers
# the Supervisor when it stops advancing while the process lives.

import supervisor.cycle_stall as cs
from supervisor.cycle_stall import CycleStallGuard


def _guard(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(cs.time, "monotonic", lambda: clock["now"])
    cycle = {"v": -1}
    trips: list[str] = []
    guard = CycleStallGuard(
        get_cycle=lambda: cycle["v"],
        on_violation=trips.append,
        max_stall_s=100.0,
        poll_interval_s=1.0,
    )
    return guard, clock, cycle, trips


def test_unarmed_until_first_stamp(monkeypatch):
    guard, clock, _cycle, trips = _guard(monkeypatch)
    for _ in range(10):  # provider says "no stamp yet" (fresh boot, reset file)
        clock["now"] += 60.0
        guard.step()
    assert trips == []


def test_trips_after_stall_and_is_one_shot(monkeypatch):
    guard, clock, cycle, trips = _guard(monkeypatch)
    cycle["v"] = 4417
    clock["now"] += 1.0
    guard.step()  # arm
    cycle["v"] = 4418
    clock["now"] += 1.0
    guard.step()  # advance — the last stamp the Run 8 crash ever wrote

    clock["now"] += 99.0
    guard.step()
    assert trips == []  # under the limit: no trip

    clock["now"] += 2.0
    guard.step()
    assert len(trips) == 1
    assert "cycle_stall" in trips[0] and "4418" in trips[0]

    clock["now"] += 500.0
    guard.step()
    assert len(trips) == 1  # one-shot while the stamp stays frozen


def test_advance_resets_and_can_trip_again(monkeypatch):
    guard, clock, cycle, trips = _guard(monkeypatch)
    cycle["v"] = 10
    clock["now"] += 1.0
    guard.step()
    clock["now"] += 101.0
    guard.step()
    assert len(trips) == 1

    cycle["v"] = 11  # loop came back: any CHANGE is progress
    clock["now"] += 1.0
    guard.step()
    clock["now"] += 101.0
    guard.step()
    assert len(trips) == 2


def test_new_life_reset_to_lower_cycle_counts_as_progress(monkeypatch):
    guard, clock, cycle, trips = _guard(monkeypatch)
    cycle["v"] = 9000
    clock["now"] += 1.0
    guard.step()
    cycle["v"] = 3  # reset_orrin → new life stamps restart low
    clock["now"] += 99.0
    guard.step()
    clock["now"] += 99.0
    guard.step()
    assert trips == []  # change was progress; timer restarted
