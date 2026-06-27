"""PRODUCTION_LOOP_CLOSURE verification tests #5 and #7.

#5 — the background Executive defers compose_section to the deliberate lane.
#7 — one successful section writes one tracked file, one non-zero effect, and
     marks one plan step complete.
"""

import pytest

from brain.agency import compose_section as cs
from brain.agency import effect_ledger as el
from brain.cognition.planning.step_execution import execute_step_action, is_procedural


def test_compose_section_is_not_procedural_and_is_deferred_off_the_executive():
    # F3: compose_section is a deliberate (conscious) act, never run on the
    # background procedural lane.
    assert is_procedural("compose_section") is False
    executed, msg = execute_step_action(
        "compose_section", {"_procedural_only": True}, step_text="Draft the thesis",
        goal={"title": "Write a synthesis"},
    )
    assert executed is False
    assert "deferred" in msg.lower()


@pytest.fixture
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl")
    monkeypatch.setattr(cs, "TRACKED_WORK_DIR", tmp_path / "tracked_work")
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def test_one_section_writes_file_effect_and_completes_step(_isolate):
    goal = {
        "id": "synthesis-emergence",
        "title": "Write a synthesis of emergence",
        "grounded_parts": ["local interactions", "global order", "no central controller"],
        "definition_of_done": [{"criterion": "A clear thesis exists", "met": False}],
        "tracked_work": True,
        "plan": [
            {"step": "Draft the thesis section", "status": "pending",
             "action": {"function": "compose_section", "section": "Thesis"}},
            {"step": "Draft the evidence section", "status": "pending",
             "action": {"function": "compose_section", "section": "Evidence"}},
        ],
    }
    result = cs.compose_section({"committed_goal": goal})

    # one tracked file
    from pathlib import Path
    assert result["success"] is True
    assert Path(result["path"]).exists()
    assert Path(result["path"]).parent == (cs.TRACKED_WORK_DIR)

    # one non-zero effect
    assert result["effect"] is not None
    assert result["effect"]["significance"] > 0.0
    assert result["effect"]["novelty"] > 0.0

    # exactly one plan step advanced to completed (the multi-section completion
    # gate itself is covered by test_effect_ledger's required-sections test, #9)
    statuses = [p["status"] for p in goal["plan"]]
    assert statuses == ["completed", "pending"]
