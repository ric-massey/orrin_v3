"""P2b — feed corrections of PRODUCED WORK into the person model (ToM), with higher
weight than a conversational cue; write the corrected effect's significance down; and
re-aim the owning goal (the scripted correct→retry loop).
"""
import pytest

import brain.cognition.theory_of_mind as tom
from brain.agency import effect_ledger


# ── ToM belief model: artifact correction shifts predicted preference ────────────

def _base_belief():
    return {"feels_understood": None, "in_alignment": None, "satisfied_last": None,
            "consecutive_misalignments": 0, "belief_discordance": False}


def test_artifact_correction_weighs_more_than_conversational():
    sig = {"is_artifact_correction": True, "correction_note": "too formal",
           "is_affirming": False, "has_neg_words": False, "is_frustrated": False,
           "is_correction": True, "is_question": False, "is_personal": False}
    b = tom._update_belief_model(_base_belief(), sig, "", "")
    assert b["in_alignment"] is False
    assert b["belief_discordance"] is True
    assert b["consecutive_misalignments"] == 2          # ~2× a conversational correction (+1)
    assert b["preference_alignment"] == pytest.approx(-0.4)
    assert b["last_artifact_correction"] == "too formal"


def test_conversational_correction_is_plus_one_only():
    sig = {"is_affirming": False, "has_neg_words": False, "is_frustrated": False,
           "is_correction": True, "is_question": False, "is_personal": False}
    b = tom._update_belief_model(_base_belief(), sig, "", "")
    assert b["consecutive_misalignments"] == 1          # weaker than the artifact channel


def test_affirmation_nudges_preference_positive():
    sig = {"is_affirming": True, "has_neg_words": False, "is_frustrated": False,
           "is_correction": False, "is_question": False, "is_personal": False}
    b = tom._update_belief_model(_base_belief(), sig, "", "")
    assert b["preference_alignment"] == pytest.approx(0.2)


def test_register_artifact_correction_persists_shift():
    """register_artifact_correction updates and persists the belief model in
    relationships.json (isolated tmp under test)."""
    belief = tom.register_artifact_correction("person_x", "you were too verbose",
                                              goal_id="g1", content_hash="h1")
    assert belief.get("preference_alignment") == pytest.approx(-0.4)
    assert tom._is_misaligned(belief) is True
    # persisted
    reloaded = tom._load_tom_state("person_x").get("belief_model") or {}
    assert reloaded.get("preference_alignment") == pytest.approx(-0.4)
    assert reloaded.get("last_corrected_goal") == "g1"

    # a second correction accumulates the shift (bounded at -1.0)
    belief2 = tom.register_artifact_correction("person_x", "still too verbose", goal_id="g1")
    assert belief2["preference_alignment"] == pytest.approx(-0.8)


# ── effect-ledger significance write-down (mirror of mark_reused) ────────────────

def test_mark_corrected_writes_significance_down():
    effect_ledger.reset_for_tests()
    row = effect_ledger.record_effect(
        "note_novel", "a substantial produced answer that is well formed and varied " * 4,
        goal_id="gc1")
    assert row is not None
    before = effect_ledger.significance_for_goal("gc1")
    assert before > 0.0
    n = effect_ledger.mark_corrected(row.content_hash)
    assert n == 1
    assert effect_ledger.correction_count(row.content_hash) == 1
    after = effect_ledger.significance_for_goal("gc1")
    assert after < before                                 # corrected work loses significance


# ── log_correction closes the loop end-to-end ────────────────────────────────────

def test_log_correction_closes_the_loop(monkeypatch):
    import brain.control_signals.feedback_log as fl
    effect_ledger.reset_for_tests()
    row = effect_ledger.record_effect(
        "note_novel", "another substantial well-formed produced answer with varied words " * 4,
        goal_id="gL")
    assert row is not None

    # capture the goal reopen without touching the real goal store
    reopened = {}
    monkeypatch.setattr(fl, "_reopen_goal_for_correction",
                        lambda gid, note: reopened.setdefault("gid", gid) is None or True)

    out = fl.log_correction(goal_id="gL", content_hash=row.content_hash,
                            note="the tone was wrong", person_id="person_y")
    assert out["logged"] is True
    assert out["significance_written_down"] is True
    assert out["belief_updated"] is True
    assert out["goal_reopened"] is True
    assert reopened.get("gid") == "gL"
    # the correction actually wrote significance down and shifted the person model
    assert effect_ledger.correction_count(row.content_hash) == 1
    assert out.get("preference_alignment") == pytest.approx(-0.4)


def test_reopen_goal_for_correction_reopens_and_aims(monkeypatch):
    import brain.control_signals.feedback_log as fl
    tree = [{"id": "gR", "title": "make a thing", "status": "completed", "subgoals": []}]
    saved = {}
    monkeypatch.setattr("brain.cognition.planning.goal_store.load_goals", lambda: tree)
    monkeypatch.setattr("brain.cognition.planning.goal_store.save_goals",
                        lambda g: saved.setdefault("tree", g))
    ok = fl._reopen_goal_for_correction("gR", "fix the ending")
    assert ok is True
    assert tree[0]["status"] == "in_progress"             # reopened
    assert tree[0]["_correction_gap"] == "fix the ending"  # aimed
    assert saved.get("tree") is tree
