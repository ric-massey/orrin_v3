# Regression test for the 2026-06-24 goal-starvation deadlock.
#
# A FAILED problem_refocus diagnosis goal (with id=None) lodged in the committed slot.
# It could not be advanced (executive queue drops terminal goals) nor closed-from-the-
# slot (the finalize path only runs while a goal is actively pursued), and while it sat
# there the action_debt gate refused to originate any new goal — permanent starvation.
# The fix: _evict_spent_committed_goal clears a terminal/orphaned goal from the slot
# before the gates, so origination can re-fill it.

from brain.cognition.intrinsic_goals import _evict_spent_committed_goal


def test_failed_goal_evicted_from_slot():
    """The exact wedge: a failed, id-less goal must be cleared from the slot."""
    ctx = {
        "committed_goal": {
            "title": "The causes of rich internal state with no environmental coupling",
            "id": None,
            "status": "failed",
        },
        "action_debt": 1,
    }
    assert _evict_spent_committed_goal(ctx) is True
    assert ctx["committed_goal"] is None


def test_completed_and_abandoned_goals_evicted():
    for status in ("completed", "abandoned"):
        ctx = {"committed_goal": {"title": "x", "id": "g_1", "status": status}}
        assert _evict_spent_committed_goal(ctx) is True
        assert ctx["committed_goal"] is None


def test_fresh_idless_pending_goal_is_kept():
    """A freshly committed intrinsic goal is legitimately id-less until the v2
    projection assigns an id. It must NOT be evicted on the missing id alone, or the
    slot would thrash a healthy goal out every cycle."""
    goal = {"title": "Understand history of written language", "id": None,
            "status": "pending"}
    ctx = {"committed_goal": goal}
    assert _evict_spent_committed_goal(ctx) is False
    assert ctx["committed_goal"] is goal


def test_active_goal_is_kept():
    """A healthy in-progress goal with an id must NOT be evicted."""
    goal = {"title": "real work", "id": "g_42", "status": "in_progress"}
    ctx = {"committed_goal": goal}
    assert _evict_spent_committed_goal(ctx) is False
    assert ctx["committed_goal"] is goal


def test_failed_goal_with_id_still_evicted():
    """Terminal status is the trigger regardless of whether an id is present."""
    ctx = {"committed_goal": {"title": "x", "id": "g_7", "status": "failed"}}
    assert _evict_spent_committed_goal(ctx) is True
    assert ctx["committed_goal"] is None


def test_empty_slot_is_noop():
    ctx = {"committed_goal": None}
    assert _evict_spent_committed_goal(ctx) is False
    assert ctx["committed_goal"] is None
