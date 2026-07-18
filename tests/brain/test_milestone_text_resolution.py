# R10-4: a milestone's criterion text resolves regardless of which key its
# writer used. goal_comprehension writes {"milestone": criterion}; a single-key
# read (ms.get("text")) dropped those — rendering failure reasons as ['?', '?']
# and deriving empty plans from comprehension-built goals.

from brain.cognition.planning.goal_plan_ops import milestone_text, unmet_milestone_texts


def test_milestone_text_resolves_each_writer_key():
    assert milestone_text({"text": "wrote a memo"}) == "wrote a memo"
    assert milestone_text({"milestone": "answered the question"}) == "answered the question"
    assert milestone_text({"label": "L"}) == "L"
    assert milestone_text({"criterion": "C"}) == "C"
    assert milestone_text({"description": "D"}) == "D"
    assert milestone_text({"name": "N"}) == "N"
    assert milestone_text({"met": True}) == ""       # no criterion key → empty, not "?"
    assert milestone_text("not a dict") == ""


def test_unmet_texts_includes_comprehension_keyed_milestones():
    goal = {"milestones": [
        {"milestone": "produce a synthesis", "met": False},
        {"text": "read a source", "met": True},
        {"milestone": "answer the question", "met": False},
    ]}
    unmet = unmet_milestone_texts(goal)
    assert "produce a synthesis" in unmet
    assert "answer the question" in unmet
    assert "read a source" not in unmet   # met → excluded
    assert "?" not in unmet               # never the placeholder
