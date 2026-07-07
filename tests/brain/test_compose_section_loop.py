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


def _goal():
    return {
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


_MATERIAL = [
    ("note_novel (2026-07-05)",
     "Emergence arises when many local interactions between simple parts produce "
     "global order that none of the parts encodes on its own — ant colonies and "
     "market prices both show this signature clearly.", ""),
    ("long memory",
     "I noticed that removing the central controller from the simulation did not "
     "destroy the pattern; the order re-formed from the local rules alone.", ""),
]


def test_one_section_writes_file_effect_and_completes_step(_isolate, monkeypatch):
    # F1a: sections are grounded in real material and drafted by a real writer;
    # this test covers the file/effect/step mechanics, so both are stubbed.
    monkeypatch.setattr(cs, "_gather_material", lambda goal, section: list(_MATERIAL))
    monkeypatch.setattr(
        cs, "_draft",
        lambda goal, section, material: (
            "The thesis is that order can arise without a controller. "
            + " ".join(body for _, body, _ in material)
        ),
    )
    goal = _goal()
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


def test_empty_material_pool_is_an_honest_step_failure(_isolate):
    # F1a (2026-07-05 findings): "nothing to synthesize" is a legitimate step
    # failure — no template, no manuscript write, no completed step.
    goal = _goal()
    result = cs.compose_section({"committed_goal": goal})
    assert result["success"] is False
    assert "nothing to synthesize" in result["result"]
    assert not (cs.TRACKED_WORK_DIR / "synthesis-emergence.md").exists()
    assert [p["status"] for p in goal["plan"]] == ["pending", "pending"]

    # And the step-runner's perceptual-control test reads it as no-effect, so
    # the durable attempt counter (F1b) can see the retries.
    from brain.cognition.planning.step_execution import _result_is_real
    assert _result_is_real(result) is False


def test_deduped_draft_appends_nothing_and_fails(_isolate, monkeypatch):
    # F1a: the ledger's novelty verdict comes BEFORE the manuscript is touched —
    # a repeated draft cannot grow the file (the 07-05 treadmill: 166 sections,
    # 156 uncredited, file still 197 KB).
    monkeypatch.setattr(cs, "_gather_material", lambda goal, section: list(_MATERIAL))
    monkeypatch.setattr(
        cs, "_draft",
        lambda goal, section, material: (
            "The thesis is that order can arise without a controller, and this "
            "exact draft repeats verbatim on every retry of the same step, which "
            "must be credited exactly once by the content-addressed ledger."
        ),
    )
    first = cs.compose_section({"committed_goal": _goal()})
    assert first["success"] is True
    from pathlib import Path
    size_after_first = Path(first["path"]).stat().st_size

    second = cs.compose_section({"committed_goal": _goal()})
    assert second["success"] is False
    assert "nothing to add" in second["result"]
    assert Path(first["path"]).stat().st_size == size_after_first
