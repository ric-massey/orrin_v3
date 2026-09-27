# Default-mode stage (brain/cognition/default_mode.py).
#
# Ambient thought and rumination used to write context keys nothing read, so the
# DMN never reached awareness or the action pick. These tests pin the wiring:
# surfaced content is offered to the Global Workspace, can win it on a quiet
# cycle, loses to a present user, and routes the action prior to inward work —
# all symbolic, with no LLM in the chain. Run 12.5 checks the same on a live life.
import re
from pathlib import Path
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
    assert ctx["ambient_texture"] == [_FRAG]
    assert ctx["ruminative_loop"] == _LOOP
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
    assert ctx["ambient_texture"]
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


def test_dmn_chain_needs_no_llm(stub_dmn, monkeypatch):
    # Default deployment: the LLM is a tool, never a reader of Orrin's state.
    import brain.utils.llm_gate as gate
    monkeypatch.setattr(gate, "llm_available", lambda: False)
    ctx: Dict[str, Any] = {"_cycle_index": 1}
    dm.run_default_mode(ctx)
    assert gw.update_workspace(ctx)["source"] in ("ambient", "rumination")
    assert compute_workspace_prior(ctx, ["reflection", "reflect_on_self_beliefs"])


def test_inner_loop_llm_path_is_not_a_default_caller(monkeypatch):
    # inner_loop's LLM draft prompt only runs if tool-only mode is switched off;
    # cognition must never depend on it.
    monkeypatch.delenv("ORRIN_LLM_TOOL_ONLY", raising=False)
    from brain.utils.generate_response import _LLM_TOOL_CALLERS
    assert "inner_loop" not in _LLM_TOOL_CALLERS


# ── guard: every per-cycle surface line written to context has a reader ─────────

_BRAIN = Path(__file__).resolve().parents[2] / "brain"
_WRITE = re.compile(r'context\["(_[a-z_]+_text)"\]\s*=(?!=)')

# Prose lines built for the (tool-gated, default-off) LLM inner-loop prompt. Their
# structured siblings (theory_of_mind, temporal_state, energy_mode) already drive
# speech/selection symbolically. Known and deliberate until decided; do not add
# to this set — wire a new line to a symbolic reader instead.
_KNOWN_UNREAD = {"_tom_text", "_ftime_text", "_energy_mode_text"}


def test_every_context_surface_text_has_a_reader():
    sources = {p: p.read_text(encoding="utf-8") for p in _BRAIN.rglob("*.py")}
    written = {k for src in sources.values() for k in _WRITE.findall(src)}
    orphans = []
    for key in sorted(written - _KNOWN_UNREAD):
        read = re.compile(rf'\.get\(\s*"{key}"|\["{key}"\](?!\s*=[^=])')
        if not any(read.search(src) for src in sources.values()):
            orphans.append(key)
    assert not orphans, f"context keys written but never read: {orphans}"
