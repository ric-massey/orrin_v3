"""Run 13 gate-passer 4 (DEMO_RUN_2026-08-19 §4.1): Run 12's daemon lane went silent
at 04:23Z because every re-proposed topic matched an already-DONE v2 goal and sync
`adopted_existing` it — a no-op. A finished goal is never adopted; the proposal
becomes a distinct round-k follow-on with fresh search angles."""
from types import SimpleNamespace

import brain.goal_io as goal_io


class _Api:
    def __init__(self, goals):
        self.goals = goals
        self.created = []

    def list_goals(self, **_kw):
        return self.goals

    def create_goal(self, **kw):
        self.created.append(kw)
        return SimpleNamespace(id=f"new{len(self.created)}", **kw)


def _g(gid, title, status):
    return SimpleNamespace(id=gid, title=title, kind="research", status=SimpleNamespace(value=status))


def _proposal(title):
    return {"title": title, "kind": "research", "driven_by": "world_knowledge",
            "milestones": [{"text": "learned", "met": False}],
            "spec": {"queries": ["mathematics", "mathematics explained"]},
            "question": "What is there about mathematics that my earlier notes on it are missing?"}


def test_done_title_becomes_round_two_not_adopted():
    api = _Api([_g("g_old", "Understand mathematics more deeply", "DONE")])
    ctx = {"proposed_goals": [_proposal("Understand mathematics more deeply")]}
    goal_io.sync_proposed_goals(api, ctx)
    assert len(api.created) == 1, "a finished title must yield NEW work, not adopt the DONE goal"
    kw = api.created[0]
    assert kw["title"] == "Understand mathematics more deeply — round 2"
    assert kw["spec"]["followon_of"] == "g_old"
    assert kw["spec"]["queries"] == ["mathematics open problems", "mathematics criticism and debate"]
    assert kw.get("id") is None, "the follow-on must not reuse the finished goal's id"


def test_round_counter_and_angles_advance():
    api = _Api([_g("g1", "Understand mathematics more deeply", "DONE"),
                _g("g2", "Understand mathematics more deeply — round 2", "FAILED")])
    ctx = {"proposed_goals": [_proposal("Understand mathematics more deeply")]}
    goal_io.sync_proposed_goals(api, ctx)
    kw = api.created[0]
    assert kw["title"].endswith("— round 3")
    assert kw["spec"]["queries"][0] == "mathematics history and development"


def test_live_goal_still_adopted():
    api = _Api([_g("g_live", "Understand mathematics more deeply", "RUNNING")])
    ctx = {"proposed_goals": [_proposal("Understand mathematics more deeply")]}
    goal_io.sync_proposed_goals(api, ctx)
    assert api.created == []
