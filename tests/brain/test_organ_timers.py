# Run 4 fix B2 (RUN4_FIX_PLAN_2026-07-04 §B2): timer-protect the consolidation
# organs. Under an ignition monopoly the integrative organs went dark by hour 3
# while the dream (its own timer) never missed. These assert the timer fallback
# runs an organ ignition hasn't, and that an ignition run resets its timer.

import time

import brain.loop.organ_timers as ot


def test_organ_is_due_after_interval(monkeypatch):
    ot.reset_for_tests(now=0.0)
    # Nothing due right at reset.
    assert ot.due_organs(now=1.0) == []
    # Everything due once the interval elapses.
    due = ot.due_organs(now=ot._ORGAN_INTERVAL_S + 1.0)
    assert set(due) == set(ot._PROTECTED_ORGANS)


def test_run_due_organs_invokes_and_marks(monkeypatch):
    ot.reset_for_tests()
    # Age every organ past the interval.
    with ot._lock:
        for k in ot._last_ran:
            ot._last_ran[k] = time.time() - (ot._ORGAN_INTERVAL_S + 10)

    calls = []
    fake_registry = {name: {"function": (lambda ctx=None, n=name: calls.append(n))}
                     for name in ot._PROTECTED_ORGANS}
    monkeypatch.setattr("brain.registry.cognition_registry.COGNITIVE_FUNCTIONS",
                        fake_registry, raising=False)

    # One organ per protected slot (default limit=1).
    ran = ot.run_due_organs({})
    assert len(ran) == 1
    assert ran[0] in ot._PROTECTED_ORGANS
    assert calls == ran
    # The organ it ran is no longer due; the rest still are.
    assert ran[0] not in ot.due_organs()


def test_ignition_run_resets_the_timer():
    ot.reset_for_tests()
    name = ot._PROTECTED_ORGANS[0]
    with ot._lock:
        ot._last_ran[name] = time.time() - (ot._ORGAN_INTERVAL_S + 10)
    assert name in ot.due_organs()
    ot.mark_ran(name)          # an ignition-driven run
    assert name not in ot.due_organs()


def test_failing_organ_does_not_retry_every_cycle(monkeypatch):
    ot.reset_for_tests()
    with ot._lock:
        for k in ot._last_ran:
            ot._last_ran[k] = time.time() - (ot._ORGAN_INTERVAL_S + 10)

    def _boom(ctx=None):
        raise RuntimeError("organ blew up")

    monkeypatch.setattr(
        "brain.registry.cognition_registry.COGNITIVE_FUNCTIONS",
        {name: {"function": _boom} for name in ot._PROTECTED_ORGANS}, raising=False)

    ran = ot.run_due_organs({})      # crashes internally, but the timer is stamped
    assert ran == []                  # nothing counted as run
    # The organ it attempted is no longer due (stamped before running).
    assert len(ot.due_organs()) < len(ot._PROTECTED_ORGANS)
