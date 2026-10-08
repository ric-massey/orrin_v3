"""B20 (Run 13 verdict §4b C) — "Answer:" follow-ups must reach the daemon.

Run 13 added follow-ups straight to the v1 tree, so none passed
sync_proposed_goals: 0 hand-offs, 51 failed at the 3-attempt cap. Parents are
real Run 13 goals (tests/fixtures/run13/followup_parents.json).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import brain.goal_io as gio
from brain.cognition import epistemic_closeout as ec

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"


def _parents():
    return {p["id"]: p for p in json.loads((FIX / "followup_parents.json").read_text())}


def _drain():
    ctx: dict = {}
    gio._drain_pending_proposals(ctx)
    return ctx.get("proposed_goals", [])


def test_research_followup_is_handed_to_the_daemon(monkeypatch):
    _drain()
    parent = _parents()["g_72c5f00bc1"]
    tree_adds: list = []
    monkeypatch.setattr("brain.cognition.planning.goal_store.add_goal",
                        lambda g: tree_adds.append(g) or g)
    assert ec.spawn_followup_goal(parent) is True
    assert tree_adds == []

    created: list = []
    api = SimpleNamespace(
        list_goals=lambda **k: [],
        create_goal=lambda **k: created.append(k) or SimpleNamespace(id="g_new"))
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: [])
    ctx: dict = {}
    gio.sync_proposed_goals(api, ctx)
    assert len(created) == 1
    g = created[0]
    assert g["kind"] == "research"
    assert g["title"].startswith("Answer: What is there about The Daily Stoic")
    assert g["spec"]["queries"][0] == "The Daily Stoic"
    assert g["spec"]["question"] == parent["question"]


def test_aspiration_question_spawns_nothing():
    _drain()
    assert ec.spawn_followup_goal(_parents()["g_0abd3dd3521c"]) is False
    assert _drain() == []


def test_followup_query_unwraps_templates():
    assert ec.followup_query({}, "What actually is emergence, beyond the mentions I keep seeing?") \
        == "emergence"
    assert ec.followup_query({}, "What about tidal locking do I still not understand?") \
        == "tidal locking"
    assert ec.followup_query({"spec": {"queries": ["Ostrom commons"]}}, "Why did it fail?") \
        == "Ostrom commons"
