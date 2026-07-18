# Run 9 fixes R9-F1/F2/F4 (RUN9_DEEP_ANALYSIS_2026-07-15 Finding 1): the daemon
# re-collected READY steps every tick while a worker was still executing them,
# so the same step ran concurrently on the 3-worker pool; racers upserted stale
# private copies (attempts reached 9/3, DONE overwrote FAILED), a zombie
# synthesize ran on an already-FAILED goal, and finalization clobbered the real
# failure reason with the last step's None. Every "failed" research goal in the
# Run 8 life was manufactured this way — the work had succeeded on disk.

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from goals.goals_daemon import GoalsDaemon
from goals.registry import GoalRegistry
from goals.runner import StepRunner
from goals.store import FileGoalsStore
from goals.handlers.base import BaseGoalHandler, HandlerContext
from goals.model import Goal, Step, Status


def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)


def wait_until(pred, *, timeout: float = 15.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


class _SlowPipelineHandler(BaseGoalHandler):
    """search → fetch → synthesize, where fetch spans many daemon pulses (the
    Run 8 fetch took 5.7 s while the scheduler ticked every 0.5 s). Records how
    many times each step executed and the max concurrency per step id."""
    kind = "research"

    def __init__(self, fetch_sleep_s: float = 0.4):
        self._sleep = fetch_sleep_s
        self._mu = threading.Lock()
        self.exec_counts: dict[str, int] = {}
        self.max_concurrent: dict[str, int] = {}
        self._live: dict[str, int] = {}

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        s1 = Step(id=f"{goal.id}-search", goal_id=goal.id, name="search",
                  action={"op": "search"}, status=Status.READY)
        s2 = Step(id=f"{goal.id}-fetch", goal_id=goal.id, name="fetch",
                  action={"op": "fetch"}, status=Status.READY, deps=[s1.id])
        s3 = Step(id=f"{goal.id}-synth", goal_id=goal.id, name="synthesize",
                  action={"op": "synth"}, status=Status.READY, deps=[s2.id])
        return [s1, s2, s3]

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        return False, None

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        with self._mu:
            self.exec_counts[step.id] = self.exec_counts.get(step.id, 0) + 1
            self._live[step.id] = self._live.get(step.id, 0) + 1
            self.max_concurrent[step.id] = max(
                self.max_concurrent.get(step.id, 0), self._live[step.id])
        try:
            if (step.action or {}).get("op") == "fetch":
                time.sleep(self._sleep)
            step.status = Status.DONE
            step.finished_at = UTCNOW()
            step.last_error = None
            return step
        finally:
            with self._mu:
                self._live[step.id] -= 1


class _AlwaysBoomHandler(BaseGoalHandler):
    kind = "boom"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        return []

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        return False, None

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        raise RuntimeError("boom")


class _CountingHandler(BaseGoalHandler):
    kind = "dummy"

    def __init__(self):
        self.calls = 0

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        return []

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        return False, None

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        self.calls += 1
        step.status = Status.DONE
        step.finished_at = UTCNOW()
        return step


# ── R9-F1: the WAL race trace, reproduced with workers=3 + a slow handler ─────

def test_slow_step_executes_exactly_once_under_three_workers(tmp_path):
    store = FileGoalsStore(tmp_path)
    handler = _SlowPipelineHandler(fetch_sleep_s=0.4)
    reg = GoalRegistry([handler])
    goal = Goal(id="g_race", title="raced research goal", kind="research", spec={})
    store.upsert_goal(goal)

    daemon = GoalsDaemon(store, reg, workers=3, tick_seconds=0.03)
    daemon.start()
    try:
        assert wait_until(
            lambda: (store.get_goal("g_race") or goal).is_terminal(), timeout=15.0)
    finally:
        daemon.stop()
        daemon.join(timeout=5.0)

    final = store.get_goal("g_race")
    assert final is not None and final.status == Status.DONE
    assert final.last_error is None

    # The fetch step spanned ~13 scheduler pulses while READY in the store;
    # pre-fix it was re-enqueued and ran concurrently (att climbed to 9/3).
    fetch_id = "g_race-fetch"
    assert handler.exec_counts.get(fetch_id) == 1
    assert handler.max_concurrent.get(fetch_id) == 1
    for s in store.steps_for("g_race"):
        assert s.status == Status.DONE
        assert int(s.attempts or 0) <= int(s.max_attempts or 3)


# ── R9-F2: a worker re-reads the step fresh and skips non-READY copies ────────

def test_stale_copy_of_done_step_is_skipped(tmp_path):
    store = FileGoalsStore(tmp_path)
    handler = _CountingHandler()
    reg = GoalRegistry([handler])
    goal = Goal(id="g1", title="t", kind="dummy", spec={}, status=Status.RUNNING)
    store.upsert_goal(goal)
    done = Step(id="s1", goal_id="g1", name="n", action={"op": "x"},
                status=Status.DONE, finished_at=UTCNOW())
    store.upsert_step(done)

    runner = StepRunner(store=store, registry=reg, step_queue=__import__("queue").Queue(),
                        workers=0)
    stale_ready_copy = Step(id="s1", goal_id="g1", name="n", action={"op": "x"},
                            status=Status.READY)
    runner.submit(stale_ready_copy)

    assert handler.calls == 0
    assert store.get_step("s1").status == Status.DONE


# ── R9-F2 (zombie guard): steps of a terminal goal are cancelled, not run ─────

def test_step_of_failed_goal_is_cancelled_not_run(tmp_path):
    store = FileGoalsStore(tmp_path)
    handler = _CountingHandler()
    reg = GoalRegistry([handler])
    goal = Goal(id="g1", title="t", kind="dummy", spec={}, status=Status.FAILED,
                last_error="no URLs to fetch")
    store.upsert_goal(goal)
    step = Step(id="s_zombie", goal_id="g1", name="synthesize",
                action={"op": "synth"}, status=Status.READY)
    store.upsert_step(step)

    runner = StepRunner(store=store, registry=reg, step_queue=__import__("queue").Queue(),
                        workers=0)
    runner.submit(step)

    assert handler.calls == 0
    assert store.get_step("s_zombie").status == Status.CANCELLED
    # The failure reason survives (pre-fix the zombie's None clobbered it).
    assert store.get_goal("g1").last_error == "no URLs to fetch"


# ── R9-F4: attempts never pass max; goal error comes from the FAILED step ─────

def test_attempts_never_exceed_max(tmp_path):
    store = FileGoalsStore(tmp_path)
    reg = GoalRegistry([_AlwaysBoomHandler()])
    goal = Goal(id="g1", title="t", kind="boom", spec={}, status=Status.RUNNING)
    store.upsert_goal(goal)
    step = Step(id="s1", goal_id="g1", name="n", action={"op": "x"},
                status=Status.READY, max_attempts=3)
    store.upsert_step(step)

    runner = StepRunner(store=store, registry=reg, step_queue=__import__("queue").Queue(),
                        workers=0)
    for _ in range(6):  # twice the budget; extra submits must not push past max
        s = store.get_step("s1")
        runner.submit(s)

    final = store.get_step("s1")
    assert final.status == Status.FAILED
    assert int(final.attempts) == 3


def test_goal_last_error_comes_from_failed_step_not_last_step(tmp_path):
    store = FileGoalsStore(tmp_path)
    reg = GoalRegistry([_CountingHandler()])
    goal = Goal(id="g1", title="t", kind="dummy", spec={}, status=Status.RUNNING)
    store.upsert_goal(goal)
    failed = Step(id="s_fetch", goal_id="g1", name="fetch", action={"op": "f"},
                  status=Status.FAILED, attempts=3, max_attempts=3,
                  last_error="ValueError: no URLs to fetch", finished_at=UTCNOW())
    zombie_done = Step(id="s_synth", goal_id="g1", name="synthesize",
                       action={"op": "s"}, status=Status.DONE, last_error=None,
                       finished_at=UTCNOW())
    store.upsert_step(failed)
    store.upsert_step(zombie_done)

    runner = StepRunner(store=store, registry=reg, step_queue=__import__("queue").Queue(),
                        workers=0)
    assert runner._maybe_finalize_goal(goal, zombie_done) is True
    final = store.get_goal("g1")
    assert final.status == Status.FAILED
    assert final.last_error == "ValueError: no URLs to fetch"
