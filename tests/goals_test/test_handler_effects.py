# AR1 (CODEBASE_AUDIT_2026-07-01 D7): a v2 handler step that reaches DONE with a
# written artifact records a file_write effect via the runner chokepoint, so
# daemon production (research memos, housekeeping reports) is visible to the
# goal/production/reward system. Fetched source material never enters
# Step.artifacts, so intake can't masquerade as production.
import queue

import pytest

from brain.agency import effect_ledger as el
from goals.model import Goal, Step, Status
from goals.runner import StepRunner

_MEMO = (
    "# Research memo: how convection cells form\n\n"
    "TL;DR: a fluid heated from below self-organizes into hexagonal cells because "
    "buoyant plumes and cooled downdrafts settle into the packing that moves the "
    "most heat for the least viscous dissipation. Key findings: onset is governed "
    "by the Rayleigh number crossing ~1708 for rigid plates; pattern wavelength "
    "tracks layer depth; the same instability structure appears in atmospheric "
    "cloud streets and in mantle convection, which is why the concept transfers."
)


class _MemoHandler:
    """Writes a real artifact and registers it on the step, like research/coding do."""

    def __init__(self, path):
        self.path = path

    def tick(self, goal, step, ctx):
        self.path.write_text(_MEMO, encoding="utf-8")
        step.artifacts.append(str(self.path))
        step.status = Status.DONE
        return step


class _NoArtifactHandler:
    def tick(self, goal, step, ctx):
        step.status = Status.DONE
        return step


class _Store:
    def __init__(self, goal, step):
        self._goals = {goal.id: goal}
        self._steps = {step.id: step}

    def get_goal(self, gid):
        return self._goals.get(gid)

    def upsert_goal(self, goal):
        self._goals[goal.id] = goal

    def upsert_step(self, step):
        self._steps[step.id] = step

    def steps_for(self, goal_id=None):
        return [s for s in self._steps.values() if goal_id in (None, s.goal_id)]


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def _run(goal, step, handler):
    store = _Store(goal, step)
    runner = StepRunner(
        store=store, registry={goal.kind: handler},
        step_queue=queue.Queue(), workers=0,
    )
    runner.submit(step)


def test_done_step_with_artifact_records_file_write_effect(tmp_path):
    goal = Goal(id="g-research", title="research convection", kind="research",
                spec={"requires_artifact": True})
    step = Step(id="s1", goal_id=goal.id, name="synthesize", action={})
    _run(goal, step, _MemoHandler(tmp_path / "research_memo.md"))

    assert el.has_qualifying_effect("g-research")
    assert el.has_effect_kind("g-research", "file_write")
    assert el.significance_for_goal("g-research") > 0.0


def test_done_step_without_artifact_records_nothing():
    goal = Goal(id="g-empty", title="reflect", kind="generic", spec={})
    step = Step(id="s1", goal_id=goal.id, name="reflect", action={})
    _run(goal, step, _NoArtifactHandler())

    assert not el.has_qualifying_effect("g-empty")


def test_rerun_of_same_artifact_dedupes(tmp_path):
    goal = Goal(id="g-dup", title="research convection", kind="research", spec={})
    handler = _MemoHandler(tmp_path / "research_memo.md")
    _run(goal, Step(id="s1", goal_id=goal.id, name="synthesize", action={}), handler)
    _run(goal, Step(id="s2", goal_id=goal.id, name="synthesize", action={}), handler)

    # both runs recorded, but the identical content credits exactly once
    assert len(el.effects_for_goal("g-dup")) == 1
