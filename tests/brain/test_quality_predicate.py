# T0.5 — the shared real-content / quality predicate.
#
# This test IS the operational definition of "high quality": the predicate must
# PASS every exemplar (work that meets Ric's standard) and REJECT every
# anti-exemplar (the 2026-06-23 run's on-disk slop shapes). When a future run
# leaks slop, add it under anti_exemplars/ and the bar ratchets up.
from pathlib import Path

import pytest

from brain.cognition.quality_predicate import assess_quality, is_real_work

_GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "quality_golden"
_IGNORE = {"README.md", "PLACEHOLDER.md"}


def _golden_files(kind: str):
    d = _GOLDEN / kind
    if not d.is_dir():
        return []
    return [p for p in sorted(d.iterdir())
            if p.is_file() and p.name not in _IGNORE and not p.name.startswith("_")]


@pytest.mark.parametrize("path", _golden_files("anti_exemplars"),
                         ids=lambda p: p.name)
def test_anti_exemplars_are_rejected(path):
    verdict = assess_quality(path.read_text(encoding="utf-8"))
    assert not verdict.ok, f"{path.name} should be rejected but passed ({verdict.reason})"


@pytest.mark.parametrize("path", _golden_files("exemplars"),
                         ids=lambda p: p.name)
def test_exemplars_pass(path):
    verdict = assess_quality(path.read_text(encoding="utf-8"))
    assert verdict.ok, f"{path.name} should pass but was rejected ({verdict.reason})"


def test_golden_set_is_non_vacuous():
    # A calibration set with no anti-exemplars (or no exemplars) proves nothing.
    assert _golden_files("anti_exemplars"), "no anti-exemplars — predicate is uncalibrated"
    assert _golden_files("exemplars"), "no exemplars — predicate has no positive standard"


# ── Direct shape checks (independent of the on-disk fixtures) ──────────────────

def test_stub_machine_log_rejected():
    v = assess_quality("snapshot_goals → goals_state_20260622-004100.jsonl (lines=0)")
    assert not v.ok and v.reason.startswith("stub")


def test_template_skeleton_rejected_even_without_a_goal():
    note = ("what I actually know about emergence: question or desired change; "
            "relevant evidence; reasoned conclusion")
    assert not is_real_work(note)


def test_grounded_body_passes_when_evidence_present():
    goal = {
        "title": "what I already know about emergence",
        "grounded_parts": ["question or desired change", "relevant evidence",
                            "reasoned conclusion"],
        "definition_of_done": [{"criterion": "a reasoned conclusion answers the goal",
                                "met": False}],
    }
    # A real finding: tokens drawn from evidence, absent from the template.
    evidence = ("convection cells and starling flocks show that local feedback "
                "coupling produces a measurable global polarization pattern")
    body = ("Local feedback coupling between units and a shared field produces a "
            "measurable global polarization pattern, as in convection cells and "
            "starling flocks — the coupling is the mechanism and the lever.")
    v = assess_quality(body, goal=goal, evidence=evidence)
    assert v.ok, v.reason


def test_ungrounded_body_rejected_when_evidence_present():
    goal = {"title": "explain emergence"}
    evidence = "convection cells starling flocks polarization coupling field"
    # Body shares nothing with the evidence — not traceable to inputs.
    body = ("I spent some time thinking and feel that things generally come "
            "together somehow when many pieces move around together over time.")
    v = assess_quality(body, goal=goal, evidence=evidence)
    assert not v.ok and v.reason == "ungrounded"


def test_near_duplicate_rejected():
    prior = ("Local feedback coupling between units and a shared field produces a "
             "measurable global polarization pattern in flocks and convection.")
    nearly = ("Local feedback coupling between units and a shared field produces a "
              "measurable global polarization pattern in flocks and convection!!")
    v = assess_quality(nearly, prior_outputs=[prior])
    assert not v.ok and v.reason == "near_duplicate"
