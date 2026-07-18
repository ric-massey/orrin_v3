# R10-12: understanding goals close on an EPISTEMIC event, not satiety. Every
# completed understanding goal must carry `question` + `answered: true/false`,
# scored by whether the produced artifact answers the question — not by effort.

from brain.cognition import epistemic_closeout as ec
from brain.paths import GOALS_DIR


def _write_memo(gid: str, body: str) -> None:
    d = GOALS_DIR / "artifacts" / gid
    d.mkdir(parents=True, exist_ok=True)
    (d / "memo_finding.md").write_text(body, encoding="utf-8")


def test_question_derived_from_title_when_absent():
    q = ec.question_for({"title": "Understand black holes more deeply"})
    assert q == "What is not obvious about black holes?"


def test_answered_when_artifact_addresses_the_subject():
    gid = "g_answered"
    _write_memo(gid, "Black holes bend spacetime so steeply that not even light "
                     "escapes past the event horizon. A surprising, non-obvious "
                     "fact is that their entropy scales with surface area, not "
                     "volume — the holographic bound. This reframes information.")
    goal = {"id": gid, "driven_by": "world_knowledge",
            "title": "Understand black holes more deeply",
            "question": "What is not obvious about black holes?"}
    answered = ec.stamp_closeout(goal)
    assert answered is True
    assert goal["answered"] is True
    assert goal["question"] == "What is not obvious about black holes?"
    assert goal.get("answer")


def test_not_answered_when_artifact_is_empty_or_off_topic():
    gid = "g_unanswered"
    _write_memo(gid, "short")   # below the substantive-prose floor
    goal = {"id": gid, "driven_by": "world_knowledge",
            "title": "Understand quantum entanglement more deeply",
            "question": "What is not obvious about quantum entanglement?"}
    answered = ec.stamp_closeout(goal)
    assert answered is False
    assert goal["answered"] is False


def test_non_understanding_goal_is_untouched():
    goal = {"id": "g_other", "driven_by": "usefulness", "title": "Fix the parser"}
    assert ec.stamp_closeout(goal) is None
    assert "answered" not in goal
