# Default-mode stage (brain/cognition/default_mode.py).
#
# Ambient thought and rumination used to write context keys nothing read, so the
# DMN never reached awareness or the action pick. These tests pin the wiring:
# surfaced content is offered to the Global Workspace, can win it on a quiet
# cycle, loses to a present user, routes the action prior to inward work, and
# reaches the LLM draft prompt. Run 12.5 checks the same chain on a live life.
from typing import Any, Dict

import pytest

import brain.cognition.ambient_thought as ambient
import brain.cognition.default_mode as dm
import brain.cognition.global_workspace as gw
import brain.cognition.rumination as rumination
from brain.think.think_utils.selection.boosts import compute_workspace_prior
from brain.think.think_utils.selection.routing import _workspace_routes_for

_FRAG = {"id": "f1", "content": "Something unfinished is still pulling at the edges.",
         "fragment_type": "zeigarnik", "intensity": 0.9}
_LOOP = {"id": "r1", "content": "the refusal earlier did not sit right",
         "mode": "brooding", "charge": 0.6, "return_count": 2}


@pytest.fixture
def stub_dmn(monkeypatch):
    state: Dict[str, Any] = {"frags": [_FRAG], "loop": _LOOP, "resolved": []}
    monkeypatch.setattr(ambient, "update_ambient",
                        lambda ctx: {"surfaced": list(state["frags"]), "active": []})
    monkeypatch.setattr(rumination, "update_rumination",
                        lambda ctx: {"surfaced": state["loop"], "active": []})
    monkeypatch.setattr(rumination, "mark_resolved", lambda lid: state["resolved"].append(lid))
    monkeypatch.delenv("ORRIN_DMN_WORKSPACE", raising=False)
    return state


def test_sets_surface_keys_and_offers_both(stub_dmn):
    ctx: Dict[str, Any] = {"_cycle_index": 7}
    dm.run_default_mode(ctx)
    assert ctx["_ambient_surface_text"].startswith("Background: ")
    assert ctx["_rumination_text"].startswith("Recurring: ")
    offers = {o["source"]: o for o in ctx["_workspace_offers"]}
    assert offers["ambient"]["salience"] == pytest.approx(0.15 + 0.35 * 0.9)
    assert offers["rumination"]["salience"] == pytest.approx(0.25 + 0.45 * 0.6)
    assert offers["rumination"]["kind"] == "brooding"


def test_idempotent_within_a_cycle(stub_dmn):
    ctx: Dict[str, Any] = {"_cycle_index": 3}
    dm.run_default_mode(ctx)
    dm.run_default_mode(ctx)          # think() fallback call after prepare_workspace
    assert len(ctx["_workspace_offers"]) == 2
    ctx["_cycle_index"] = 4
    dm.run_default_mode(ctx)
    assert len(ctx["_workspace_offers"]) == 4


def test_flag_off_generates_but_does_not_offer(stub_dmn, monkeypatch):
    monkeypatch.setenv("ORRIN_DMN_WORKSPACE", "0")
    ctx: Dict[str, Any] = {"_cycle_index": 1}
    dm.run_default_mode(ctx)
    assert ctx["_ambient_surface_text"]
    assert not ctx.get("_workspace_offers")


def test_stuck_brood_is_shifted_to_reflective(stub_dmn):
    stub_dmn["loop"] = dict(_LOOP, return_count=8)
    dm.run_default_mode({"_cycle_index": 1})
    assert stub_dmn["resolved"] == ["r1"]


def test_rumination_wins_quiet_workspace_and_routes_inward(stub_dmn):
    stub_dmn["frags"] = []
    ctx: Dict[str, Any] = {"_cycle_index": 1}
    dm.run_default_mode(ctx)
    moment = gw.update_workspace(ctx)
    assert moment is not None and moment["source"] == "rumination"
    prior = compute_workspace_prior(ctx, ["reflect_on_self_beliefs", "reflection", "attend_goal"])
    assert prior.get("reflect_on_self_beliefs", 0) > 0 and "attend_goal" not in prior


def test_ambient_wins_quiet_workspace(stub_dmn):
    stub_dmn["loop"] = None
    ctx: Dict[str, Any] = {"_cycle_index": 1}
    dm.run_default_mode(ctx)
    moment = gw.update_workspace(ctx)
    assert moment is not None and moment["source"] == "ambient"


def test_present_user_suppresses_dmn_in_workspace(stub_dmn):
    ctx: Dict[str, Any] = {"_cycle_index": 1, "latest_user_input": "hey Orrin"}
    dm.run_default_mode(ctx)
    assert gw.update_workspace(ctx)["source"] == "user"


def test_dmn_sources_have_routes():
    assert _workspace_routes_for({"source": "ambient"})
    assert _workspace_routes_for({"source": "rumination"})


def test_surface_lines_reach_llm_draft_prompt():
    from brain.think.inner_loop import _draft_prompt
    ctx = {"_ambient_surface_text": "Background: a quiet hum",
           "_rumination_text": "Recurring: the refusal"}
    prompt = _draft_prompt("topic", "", ctx, 1)
    assert "Background: a quiet hum" in prompt and "Recurring: the refusal" in prompt
