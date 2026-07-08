# Phase 2B (Grounded Cognition plan / THOUGHT_OBJECT_SPEC.md): the narrator
# captures a structured (thought_object -> narration) conditioning pair alongside
# its templated output, so the conditional-decoder training set accumulates. These
# test the capture helpers directly (the narrate_experience guards — throttle,
# perceived affect, action-phrase mapping — are exercised elsewhere).
import json

import brain.cognition.language.acquisition as acq


def test_build_thought_object_carries_structured_fields():
    context = {
        "perceived_affect_state": {"core_signals": {"impasse_signal": 0.8, "confidence": 0.2}},
    }
    thought = acq._build_thought_object(context, feel="being stuck", picked="assess_goal_progress")
    assert thought["intent"] == "narrate_experience"
    assert thought["recipient"] == "self"
    assert thought["stance"] == "first_person"
    # affect carries the felt surface AND the machine key (conditioning input, spec §5)
    assert thought["affect"]["felt"] == "being stuck"
    assert thought["affect"]["signal"] == "impasse_signal"  # argmax of perceived
    # the picked act becomes a grounded concept handle
    acts = [r for r in thought["concept_refs"] if r["type"] == "act"]
    assert acts and acts[0]["handle"] == "assess_goal_progress"


def test_build_thought_object_is_failsafe_on_empty_context():
    thought = acq._build_thought_object({}, feel="", picked="")
    assert thought["intent"] == "narrate_experience"
    assert thought["affect"]["felt"] == ""
    assert "signal" not in thought["affect"]   # no perceived affect → no key
    assert thought["concept_refs"] == []


def test_append_narration_pair_writes_roundtrippable_jsonl(tmp_path, monkeypatch):
    pairs_file = tmp_path / "narration_pairs.jsonl"
    monkeypatch.setattr(acq, "_NARRATION_PAIRS_FILE", pairs_file)
    thought = {"intent": "narrate_experience", "affect": {"felt": "being stuck"}}
    acq._append_narration_pair(thought, "Feeling being stuck, I checked my progress.")

    lines = pairs_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["thought"]["intent"] == "narrate_experience"
    assert rec["narration"] == "Feeling being stuck, I checked my progress."


def test_append_narration_pair_is_bounded(tmp_path, monkeypatch):
    pairs_file = tmp_path / "narration_pairs.jsonl"
    monkeypatch.setattr(acq, "_NARRATION_PAIRS_FILE", pairs_file)
    monkeypatch.setattr(acq, "_NARRATION_PAIRS_KEEP", 10)
    # Distinct narrations (F20 dedups repeats by digit-insensitive key, so the
    # variety must be alphabetic for this size-bound test).
    letters = "abcdefghijklmnopqrstuvwxy"
    for ch in letters:
        acq._append_narration_pair({"c": ch}, f"line about {ch}")
    lines = pairs_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10                       # capped
    assert json.loads(lines[-1])["narration"] == "line about y"   # newest retained
    assert json.loads(lines[0])["narration"] == "line about p"    # oldest dropped
