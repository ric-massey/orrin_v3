"""T1.P — forced-production test (Core Architecture Master Plan, Phase 1).

The plan's bet "production is downstream of closure" was untestable because the
producer was only ever exercised by the slow autonomous run, which can't tell
"producer broken" from "producer never invoked." This deterministic harness
removes that ambiguity BEFORE the expensive T1.G run: inject a committed
output_producing / requires_artifact making-goal, FORCE the producer path
(compose_section) with the LLM unavailable (worst case — the offline draft), and
assert that

  (a) a REAL-content artifact lands on disk, judged by the SAME T0.5 quality
      predicate the closure gate uses (not a stub, not a grounded_parts template
      skeleton), and
  (b) the making-goal is DONE-able through the strengthened artifact_satisfied
      gate once that produced file is its artifact —

with no dependence on the autonomous loop choosing to route there. After this is
green the only open variable left for T1.G is routing.
"""
from pathlib import Path

import pytest

from brain.agency import compose_section as cs
from brain.agency import effect_ledger as el
from brain.cognition.quality_predicate import assess_artifact_file
from goals.model import Goal, Step, Status, artifact_satisfied


# A machine-log stub — the run's slop shape the gate must reject (negative control).
_STUB = "snapshot_goals → goals_state_20260622-004100.jsonl (lines=0)"


@pytest.fixture
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl")
    monkeypatch.setattr(cs, "TRACKED_WORK_DIR", tmp_path / "tracked_work")
    # Force the OFFLINE producer path (no LLM): the deterministic _draft fallback
    # is the worst case — if even that makes real work, production-on-demand holds.
    monkeypatch.setattr(cs, "llm_callable_by", lambda *_a, **_k: False)
    el.reset_for_tests()
    yield tmp_path
    el.reset_for_tests()


def _making_goal():
    return {
        "id": "make-emergence-synthesis",
        "title": "Write a synthesis of emergence",
        "driven_by": "output_producing",
        "requires_artifact": True,
        "grounded_parts": ["local interactions", "global order", "no central controller"],
        "definition_of_done": [{"criterion": "A clear thesis exists", "kind": "artifact", "met": False}],
        "tracked_work": True,
        "plan": [
            {"step": "Draft the thesis", "status": "pending",
             "action": {"function": "compose_section", "section": "Thesis"}},
        ],
    }


def test_producer_makes_real_work_on_demand(_isolate):
    """The forced producer writes a durable artifact that passes the T0.5 predicate."""
    goal = _making_goal()
    result = cs.compose_section({"committed_goal": goal})

    assert result["success"] is True
    path = Path(result["path"])
    assert path.exists() and path.parent == cs.TRACKED_WORK_DIR
    assert result["effect"] is not None and result["effect"]["significance"] > 0.0

    # Judged by the SAME predicate the closure gate uses (goal=None, exactly how
    # artifact_satisfied calls it): real content, not a stub/template skeleton.
    verdict = assess_artifact_file(str(path))
    assert verdict.ok, f"producer output rejected by T0.5: {verdict.reason}"


def test_making_goal_is_done_able_through_artifact_gate(_isolate):
    """Once the produced file is the goal's artifact, the v2 gate allows DONE."""
    goal = _making_goal()
    result = cs.compose_section({"committed_goal": goal})
    produced = str(Path(result["path"]))

    v2 = Goal(id=goal["id"], title=goal["title"], kind="generic",
              spec={"requires_artifact": True})
    step = Step(id="s1", goal_id=goal["id"], name="compose_section", action={},
                status=Status.DONE, artifacts=[produced])
    assert artifact_satisfied(v2, [step]) is True


def test_stub_artifact_is_not_done_able(_isolate, tmp_path):
    """Negative control: a stub artifact passes neither T0.5 nor the gate, so the
    gate isn't trivially green — DONE genuinely requires real production."""
    stub = tmp_path / "s_abc_ok.txt"
    stub.write_text(_STUB, encoding="utf-8")
    assert assess_artifact_file(str(stub)).ok is False

    v2 = Goal(id="g_stub", title="Write something", kind="generic",
              spec={"requires_artifact": True})
    step = Step(id="s1", goal_id="g_stub", name="x", action={},
                status=Status.DONE, artifacts=[str(stub)])
    assert artifact_satisfied(v2, [step]) is False
