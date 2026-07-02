# AR7 (CODEBASE_AUDIT_2026-07-01 G3/G4/G5): honest goal closure.
# G3 — a research/finding milestone is met by a real ledger effect for the goal,
#      not by keyword-matching the milestone prose against working memory.
# G4 — a felt-state-fallback note is delivered but earns NO effect credit.
# G5 — internal diagnostic strings can't become goal subjects.
import pytest

from brain.agency import effect_ledger as el

_LONG = ("Convection cells form because buoyant plumes and cooled downdrafts "
         "settle into the packing that moves the most heat for the least viscous "
         "dissipation; onset is governed by the Rayleigh number crossing about "
         "seventeen hundred for rigid plates, and the same structure appears in "
         "cloud streets and mantle convection.")


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def test_research_milestone_met_by_ledger_effect():
    from brain.cognition.planning.env_snapshot import _milestone_met

    ms = {"text": "A finding was written to long memory.", "met": False}
    # no effect, no WM evidence → unmet
    assert not _milestone_met(ms, {"working_memory": [], "_goal_has_effect": False})
    # a real credited effect for the goal → met, regardless of keyword echoes
    assert _milestone_met(ms, {"working_memory": [], "_goal_has_effect": True})


def test_apply_milestone_updates_grounds_on_effect(monkeypatch):
    from brain.cognition.planning import env_snapshot as es

    el.record_effect("note_novel", _LONG, goal_id="g-ms")
    goal = {"id": "g-ms", "title": "understand convection",
            "milestones": [{"text": "A summary of findings was written to long memory.",
                            "met": False}]}
    ctx = {"committed_goal": goal, "working_memory": []}
    ticked = es.apply_milestone_updates(ctx)
    assert ticked == 1
    assert goal["milestones"][0]["met"] is True


def test_ungrounded_note_is_delivered_but_not_credited(monkeypatch):
    import brain.behavior.express_to_user as ex

    delivered = []
    monkeypatch.setitem(ex._ROUTES, "note", lambda text, artifact, ctx: delivered.append(text) or True)
    monkeypatch.setattr(ex, "compose_from_motive", lambda motive, ctx: _LONG)

    m = ex.build_motive({}, intent="leave_note", recipient="Ric", seed=None)
    out = ex.express_to_user(m, "note", {}, credit=False)
    assert out["success"] and delivered
    assert el.effects_for_goal(m.goal_id or "") == []
    # ledger has no credited note at all
    assert not el.credited_goal_ids()


def test_grounded_note_still_credits(monkeypatch):
    import brain.behavior.express_to_user as ex

    monkeypatch.setitem(ex._ROUTES, "note", lambda text, artifact, ctx: True)
    monkeypatch.setattr(ex, "compose_from_motive", lambda motive, ctx: _LONG)

    m = ex.build_motive({}, intent="leave_note", recipient="Ric", seed="a real finding")
    m.goal_id = "g-note"
    out = ex.express_to_user(m, "note", {})
    assert out["success"]
    assert el.has_qualifying_effect("g-note")


@pytest.mark.parametrize("bad", [
    "effect_ledger.gate.rejected",
    "brain.cognition.leave_note",
    "record_failure category spike",
    "goal_io.no_milestones",
    "_check_passed",
])
def test_internal_strings_rejected_as_goal_subjects(bad):
    from brain.cognition.intrinsic_helpers import _acceptable_goal_subject
    assert not _acceptable_goal_subject(bad)


@pytest.mark.parametrize("good", [
    "convection cells",
    "the history of writing systems",
    "Open question: why do starlings flock at dusk?",
])
def test_real_topics_still_accepted(good):
    from brain.cognition.intrinsic_helpers import _acceptable_goal_subject
    assert _acceptable_goal_subject(good)
