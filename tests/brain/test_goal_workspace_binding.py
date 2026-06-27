# Part II / Option D, D3 — bind the committed goal through the global workspace.
#
# The goal Orrin is AWARE of and the goal he's PURSUING must be the same object,
# bound by id (one goal, many views), not two text copies that can drift. These
# tests pin: the conscious goal-moment carries the committed goal's id; bound_goal
# returns the one authoritative object; goal_in_focus reflects the binding; and a
# bound situation references the same goal id.
from typing import Any, Dict

import brain.cognition.global_workspace as gw
import brain.cognition.binding as binding


def _ctx_with_goal(gid="g-42", title="make a synthesis") -> Dict[str, Any]:
    return {"committed_goal": {"id": gid, "title": title, "name": title,
                               "tier": "core", "driven_by": "output_producing"}}


# ── the conscious goal-moment is bound to the goal object by id ─────────────────

def test_goal_moment_carries_committed_goal_id():
    ctx = _ctx_with_goal("g-42")
    # nothing else competing → the goal wins the workspace
    moment = gw.update_workspace(ctx)
    assert moment is not None and moment["source"] == "goal"
    assert moment.get("goal_id") == "g-42"
    # and it equals the authoritative committed goal's id (they can't be two goals)
    assert moment["goal_id"] == ctx["committed_goal"]["id"]


def test_goal_in_focus_true_when_goal_is_conscious():
    ctx = _ctx_with_goal("g-42")
    gw.update_workspace(ctx)
    assert gw.goal_in_focus(ctx) is True


def test_goal_in_focus_false_when_something_else_is_conscious():
    ctx = _ctx_with_goal("g-42")
    # a present user dominates salience (0.95 > goal's 0.55)
    ctx["latest_user_input"] = "hey Orrin, what are you up to?"
    moment = gw.update_workspace(ctx)
    assert moment["source"] == "user"
    assert gw.goal_in_focus(ctx) is False     # goal committed, but not in the spotlight


# ── the single accessor: one authoritative object ──────────────────────────────

def test_bound_goal_returns_authoritative_object():
    ctx = _ctx_with_goal("g-42")
    g = gw.bound_goal(ctx)
    assert g is ctx["committed_goal"]          # the same object, not a copy
    assert g["tier"] == "core" and g["driven_by"] == "output_producing"


def test_bound_goal_none_when_uncommitted():
    assert gw.bound_goal({}) is None
    assert gw.bound_goal({"committed_goal": {}}) is None


# ── a bound situation references the same goal id ───────────────────────────────

def test_bound_situation_carries_goal_id():
    # goal + a goal-relevant signal sharing tokens → they bind into one situation
    ctx = {
        "committed_goal": {"id": "g-7", "title": "study migratory birds",
                           "name": "study migratory birds"},
        "top_signals": [{"content": "a fact about migratory birds surfaced",
                         "signal_strength": 0.6, "tags": ["goal"]}],
    }
    composites = binding.bind_situation(ctx)
    bound_with_goal = [c for c in composites if (c.get("facets") or {}).get("goal_id")]
    assert bound_with_goal, "expected a bound situation that references the goal"
    assert bound_with_goal[0]["facets"]["goal_id"] == "g-7"
