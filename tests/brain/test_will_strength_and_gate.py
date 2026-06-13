# Master plan Phase 4 regression tests: differentiated commitment strength,
# the endorsement gate at the binding moment, and strength-weighted failure.
import json

import pytest

import cognition.will as W
from cognition.goal_competition import drive_pull_scores


@pytest.fixture(autouse=True)
def _isolate_will(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "_FILE", tmp_path / "commitments.json")
    # keep WM and the goal ledger out of live data
    import cog_memory.working_memory as wm_mod
    monkeypatch.setattr(wm_mod, "update_working_memory", lambda *a, **k: None)
    monkeypatch.setattr(W, "_link_commitment_to_goal", lambda intention: None)
    yield


def test_disowned_intention_forms_no_commitment(monkeypatch):
    import cog_memory.long_memory as lm_mod
    monkeypatch.setattr(lm_mod, "update_long_memory", lambda *a, **k: None)
    ctx = {}
    c = W.form_commitment(ctx, "pursue: escape this restlessness somehow")
    assert c is None
    assert "_commitment" not in ctx


def test_strength_is_differentiated_not_flat():
    ctx = {}
    c = W.form_commitment(ctx, "pursue: understand my own memory system")
    assert c is not None
    assert 0.2 <= c["strength"] <= 1.0
    assert c["initial_strength"] == c["strength"]
    assert c["stance"] in ("endorse", "ambivalent")
    assert c["wm_id"] and c["id"]
    # explicit strength bypasses the gate (caller already judged)
    c2 = W.form_commitment({}, "pursue: anything", strength=0.9)
    assert c2["strength"] == 0.9


def test_dearly_held_decays_slower_than_lightly_held():
    strong = {"_commitment": {"intention": "x", "strength": 1.0, "initial_strength": 1.0},
              "committed_goal": {"title": "x"}}
    weak = {"_commitment": {"intention": "y", "strength": 1.0, "initial_strength": 0.25},
            "committed_goal": {"title": "y"}}
    W.tick_commitment(strong)
    W.tick_commitment(weak)
    assert strong["_commitment"]["strength"] > weak["_commitment"]["strength"]


def test_follow_through_bias_scales_with_strength():
    ctx = {"_commitment": {"intention": "x", "strength": 0.5, "initial_strength": 0.5},
           "committed_goal": {"title": "x"}}
    W.tick_commitment(ctx)
    assert 0 < ctx["_commitment_bias"] < W._MAX_BIAS


def test_commitment_strength_breaks_goal_competition_ties():
    p0 = drive_pull_scores(["attend_goal", "dream_cycle"], {}, commitment_strength=0.0)
    p1 = drive_pull_scores(["attend_goal", "dream_cycle"], {}, commitment_strength=1.0)
    assert p1["attend_goal"] > p0["attend_goal"]
    assert p1["dream_cycle"] == p0["dream_cycle"]


def test_find_commitment_for_goal_matches_bare_intention(tmp_path):
    c = W.form_commitment({}, "pursue: chart the knowledge graph", strength=0.8)
    found = W.find_commitment_for_goal("chart the knowledge graph")
    assert found and found["id"] == c["id"]
    assert W.find_commitment_for_goal("some other goal") is None


def test_failed_committed_goal_costs_in_proportion(monkeypatch, tmp_path):
    """4.3: the emotional spike scales with commitment strength and the
    failure memory points back at the moment of resolve."""
    import cognition.planning.goals as G

    c = W.form_commitment({}, "pursue: finish the report", strength=1.0)
    lm_writes = []
    import cog_memory.long_memory as lm_mod
    monkeypatch.setattr(lm_mod, "update_long_memory",
                        lambda *a, **k: lm_writes.append((a, k)))
    monkeypatch.setattr(G, "update_working_memory", lambda *a, **k: None)
    monkeypatch.setattr(G, "release_reward_signal", lambda **k: None)
    monkeypatch.setattr(
        "cognition.planning.outcome_metrics.record_failure", lambda: None)

    def fail(goal_title):
        ctx = {"affect_state": {"core_signals": {
            "impasse_signal": 0.0, "negative_valence": 0.0, "confidence": 0.5}}}
        G.mark_goal_failed({"title": goal_title}, reason="test", context=ctx)
        return ctx["affect_state"]["core_signals"]

    committed = fail("finish the report")       # strength 1.0 → scale 1.5
    plain = fail("never committed goal")        # no commitment → scale 1.0
    assert committed["impasse_signal"] > plain["impasse_signal"]
    assert committed["negative_valence"] > plain["negative_valence"]
    assert committed["confidence"] < plain["confidence"]

    committed_write = lm_writes[0]
    assert committed_write[1].get("related_memory_ids") == [c["wm_id"]]
