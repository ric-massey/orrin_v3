# AR2 (CODEBASE_AUDIT_2026-07-01 D5): "understand X" goals must route to the v2
# ResearchHandler — whose offline extractive synthesizer produces a sourced memo
# artifact LLM-free — instead of detouring into v1 self-report + a hollow note.
# The full circuit: generator emits kind:"research" with a handler-readable spec
# → sync routes it (research is executable) → handler plans/executes → memo
# artifact → credited effect (AR1) → P1's has_qualifying_effect closes the goal.
import queue

import pytest

from brain.agency import effect_ledger as el
from brain.cognition.intrinsic_helpers import _mk_goal
from brain.goal_io import _EXECUTABLE_KINDS
from goals.handlers.research import ResearchHandler
from goals.model import Goal, Status
from goals.runner import StepRunner

_DOC = (
    "Convection cells form when a fluid heated from below becomes unstable: warm "
    "buoyant fluid rises in plumes while cooled fluid sinks, and the competition "
    "between buoyancy and viscous dissipation settles into a regular cellular "
    "pattern. The onset is governed by the Rayleigh number; above roughly 1708 "
    "for rigid boundaries the conductive state gives way to organized rolls. "
    "The same instability appears in atmospheric cloud streets and in mantle "
    "convection, which is why the concept transfers across scales."
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def test_understand_goal_emits_research_kind_with_handler_spec():
    g = _mk_goal(
        "Understand convection more deeply", "desc",
        driven_by="world_knowledge", kind="research", requires_artifact=True,
        spec={"queries": ["convection"], "synth_kind": "memo"},
    )
    assert g["kind"] == "research"
    assert g["kind"] in _EXECUTABLE_KINDS  # sync_proposed_goals will create it in v2
    assert g["spec"]["queries"] == ["convection"]
    assert g["spec"]["synth_kind"] == "memo"
    assert g["requires_artifact"] is True
    assert g.get("deadline_cycles")  # fail-able, not immortal


def test_generators_route_web_research_not_introspection():
    # The concept-deepening generator's goals are research-kind; the introspective
    # causal-frontier goals must stay generic (their work is in his own code).
    import brain.cognition.intrinsic_generators as gen

    goal = _mk_goal("Understand emergence more deeply", "d",
                    kind="research", spec={"queries": ["emergence"]})
    assert goal["kind"] == "research"

    introspective = _mk_goal("Trace what causes impasse in my own code", "d")
    assert introspective["kind"] == "generic"
    src = open(gen.__file__).read()
    # the introspective generator (_causal_frontier_goals) passes no research kind
    frontier = src.split("def _causal_frontier_goals")[1].split("\ndef ")[0]
    assert 'kind="research"' not in frontier


class _Store:
    def __init__(self, goal):
        self._goals = {goal.id: goal}
        self._steps = {}

    def get_goal(self, gid):
        return self._goals.get(gid)

    def upsert_goal(self, goal):
        self._goals[goal.id] = goal

    def upsert_step(self, step):
        self._steps[step.id] = step

    def steps_for(self, goal_id=None):
        return [s for s in self._steps.values() if goal_id in (None, s.goal_id)]


def test_research_handler_produces_memo_and_credited_effect_llm_free(tmp_path):
    goal = Goal(
        id="g-conv", title="Understand convection more deeply", kind="research",
        spec={"queries": ["convection"], "synth_kind": "memo",
              "requires_artifact": True},
    )
    handler = ResearchHandler()
    ctx = {
        "artifacts_dir": str(tmp_path / "artifacts"),
        "web_search": lambda q, k: [
            {"title": "Convection", "url": "https://example.org/convection",
             "snippet": "cells"}],
        "web_fetch": lambda url: _DOC,
        "llm": None,  # LLM-free: forces the offline extractive synthesizer
    }
    store = _Store(goal)
    runner = StepRunner(store=store, registry={"research": handler},
                        step_queue=queue.Queue(), workers=0, ctx=ctx)

    steps = handler.plan(goal, ctx)
    # Persist the WHOLE plan before running any step, as the daemon does
    # (_plan_new_goals → _add_steps): submitting incrementally let the runner
    # finalize the goal after step 1 (only step visible, all terminal) and the
    # rest ran as zombies — the exact behavior R9-F2's terminal-goal guard kills.
    for s in steps:
        store.upsert_step(s)
    for s in steps:  # plan order respects deps for a fresh goal
        runner.submit(s)

    done = [s for s in store.steps_for(goal.id) if s.status == Status.DONE]
    assert len(done) == len(steps), [
        (s.name, s.status, s.last_error) for s in store.steps_for(goal.id)]

    synth = next(s for s in store.steps_for(goal.id) if "synthesize" in s.name)
    assert synth.artifacts, "memo path must be registered on the step (AR1/AR2)"
    memo_text = open(synth.artifacts[0]).read()
    assert "offline synthesis fallback" in memo_text.lower()

    # the memo recorded a credited effect → P1's gate can close the goal
    assert el.has_qualifying_effect("g-conv")
    assert el.has_effect_kind("g-conv", "file_write")
