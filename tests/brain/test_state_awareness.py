# State → awareness (brain/cognition/state_awareness.py).
#
# Energy mode, felt time, and theory of mind already steer speech/selection
# through their structured fields. These tests pin the salient-moment path added
# on top: a shift (energy), a newly felt absence (waiting phase), or a persistent
# misalignment (ToM) is offered to the Global Workspace, can win it, and routes
# the action prior to real, selectable, LLM-free functions. Run 12.5 D9–D12.
import json
from pathlib import Path
from typing import Any, Dict

import pytest

import brain.cognition.global_workspace as gw
import brain.cognition.state_awareness as sa
import brain.cognition.temporal_state as ts
import brain.motivation.energy_orientation as eo
from brain.cognition.binding import bind_situation
from brain.think.think_utils.selection.routing import _workspace_routes_for

_REPO = Path(__file__).resolve().parents[2]


# ── energy: shift recording + consumption ──────────────────────────────────────

def test_energy_shift_recorded_once_and_consumed():
    state: Dict[str, Any] = {}
    eo._record_shift(state, "neutral", "rest")
    eo._save(state)
    assert eo.consume_pending_shift()["to"] == "rest"
    assert eo.consume_pending_shift() is None


def test_energy_shifts_collapse_and_round_trip_cancels():
    state: Dict[str, Any] = {}
    eo._record_shift(state, "neutral", "rest")
    eo._record_shift(state, "rest", "reactive")
    assert (state["pending_shift"]["from"], state["pending_shift"]["to"]) == ("neutral", "reactive")
    eo._record_shift(state, "reactive", "neutral")
    assert "pending_shift" not in state


def test_smoothed_orientation_records_a_real_mode_change():
    eo._save({"mode": "neutral", "ema": {"active": 0.0, "rest": 0.9, "reactive": 0.0}})
    ctx = {"affect_state": {"core_signals": {"resource_deficit": 1.0, "motivation": 0.0}}}
    mode = eo.get_smoothed_orientation(ctx).mode
    pending = eo.consume_pending_shift()
    assert mode != "neutral" and pending == {**pending, "from": "neutral", "to": mode}


# ── felt time: waiting-phase entry recording ───────────────────────────────────

def test_waiting_phase_entry_is_recorded_once():
    ts._save({"cycles_since_contact": 28, "session_cycles": 100, "time_texture": "waiting_fresh"})
    ctx: Dict[str, Any] = {"affect_state": {"core_signals": {}}, "working_memory": []}
    ts.update_temporal_state(ctx)            # 29 → still waiting_fresh
    assert ts.consume_pending_phase() is None
    ts.update_temporal_state(ctx)            # 30 → waiting_wondering
    assert ts.consume_pending_phase()["phase"] == "waiting_wondering"
    ts.update_temporal_state(ctx)            # 31 → same phase, nothing new
    assert ts.consume_pending_phase() is None


def test_contact_clears_an_unconsumed_phase():
    ts._save({"cycles_since_contact": 29, "session_cycles": 10, "time_texture": "waiting_fresh"})
    ts.update_temporal_state({"affect_state": {"core_signals": {}}, "working_memory": []})
    ts.update_temporal_state({"affect_state": {"core_signals": {}}, "working_memory": [],
                              "latest_user_input": "hi"})
    assert ts.consume_pending_phase() is None


# ── offers ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def pending(monkeypatch):
    box: Dict[str, Any] = {"shift": None, "phase": None}
    monkeypatch.setattr(eo, "consume_pending_shift", lambda: box["shift"])
    monkeypatch.setattr(ts, "consume_pending_phase", lambda: box["phase"])
    monkeypatch.delenv("ORRIN_STATE_AWARENESS", raising=False)
    return box


def test_energy_shift_is_offered_and_wins_a_quiet_workspace(pending):
    pending["shift"] = {"from": "neutral", "to": "rest"}
    ctx: Dict[str, Any] = {}
    sa.offer_state_awareness(ctx)
    moment = gw.update_workspace(ctx)
    assert moment["source"] == "energy" and moment["kind"] == "rest"
    assert _workspace_routes_for(moment)["idle_consolidation_cycle"] > 0


def test_shift_back_to_neutral_is_not_offered(pending):
    pending["shift"] = {"from": "rest", "to": "neutral"}
    ctx: Dict[str, Any] = {}
    sa.offer_state_awareness(ctx)
    assert not ctx.get("_workspace_offers")


def test_waiting_phase_is_offered(pending):
    pending["phase"] = {"phase": "waiting_extended"}
    ctx: Dict[str, Any] = {}
    sa.offer_state_awareness(ctx)
    (offer,) = ctx["_workspace_offers"]
    assert offer["source"] == "felt_time" and offer["salience"] == 0.50


def test_state_offers_lose_to_a_present_user(pending):
    pending["shift"] = {"from": "neutral", "to": "reactive"}
    pending["phase"] = {"phase": "waiting_long_absence"}
    ctx: Dict[str, Any] = {"latest_user_input": "hey"}
    sa.offer_state_awareness(ctx)
    assert gw.update_workspace(ctx)["source"] == "user"


def test_flag_off_still_consumes(monkeypatch):
    consumed = []
    monkeypatch.setattr(eo, "consume_pending_shift", lambda: consumed.append(1) or {"to": "rest"})
    monkeypatch.setattr(ts, "consume_pending_phase", lambda: consumed.append(2) or None)
    monkeypatch.setenv("ORRIN_STATE_AWARENESS", "0")
    ctx: Dict[str, Any] = {}
    sa.offer_state_awareness(ctx)
    assert consumed == [1, 2] and not ctx.get("_workspace_offers")


# ── theory of mind ─────────────────────────────────────────────────────────────

def test_theory_of_mind_runs_once_per_cycle(monkeypatch):
    import brain.cognition.theory_of_mind as tom_mod
    calls = []
    monkeypatch.setattr(tom_mod, "simulate", lambda ctx: calls.append(1) or {"surface_text": "x"})
    ctx: Dict[str, Any] = {}
    sa.run_theory_of_mind(ctx)     # sense
    sa.run_theory_of_mind(ctx)     # think fallback
    assert calls == [1] and ctx["theory_of_mind"] == {"surface_text": "x"}


def test_tom_marker_is_never_persisted():
    src = (_REPO / "brain/loop/finalize.py").read_text(encoding="utf-8")
    assert f'"{sa.TOM_RAN_KEY}"' in src


def _misaligned(n: int) -> Dict[str, Any]:
    return {"misaligned": True, "belief_model": {"consecutive_misalignments": n}}


def test_tom_item_only_for_persistent_misalignment_with_user_present():
    assert sa.tom_binding_item({"latest_user_input": "no", "theory_of_mind": {"misaligned": False}}) is None
    assert sa.tom_binding_item({"theory_of_mind": _misaligned(3)}) is None
    assert sa.tom_binding_item({"latest_user_input": "no", "theory_of_mind": _misaligned(2)})["salience"] == 0.60
    assert sa.tom_binding_item({"latest_user_input": "no", "theory_of_mind": _misaligned(4)})["salience"] == 0.70


def test_misalignment_binds_with_the_user_and_wins_awareness():
    ctx: Dict[str, Any] = {"latest_user_input": "no, that's not what I meant",
                           "theory_of_mind": _misaligned(3)}
    bind_situation(ctx)
    (situation,) = [c for c in ctx["_bound_candidates"] if "read" in (c.get("facets") or {})]
    assert set(situation["members"]) == {"user", "tom"}
    assert "interlocutor_read" in situation["referent_links"]
    moment = gw.update_workspace(ctx)
    assert moment["source"] == "binding" and "don't feel understood" in moment["content"]
    assert _workspace_routes_for(moment)["reflect_on_conversation_patterns"] > 0


def test_no_misalignment_leaves_the_user_message_alone():
    ctx: Dict[str, Any] = {"latest_user_input": "thanks, that helps",
                           "theory_of_mind": {"misaligned": False}}
    bind_situation(ctx)
    assert gw.update_workspace(ctx)["source"] == "user"


# ── every new route targets a real, selectable, LLM-free function ──────────────

def test_new_routes_target_registered_functions():
    seed = json.loads((_REPO / "brain/data/cognitive_functions.json").read_text(encoding="utf-8"))
    names = {e["name"] if isinstance(e, dict) else e for e in seed}
    targets = set()
    for source in ("ambient", "rumination", "felt_time"):
        targets |= set(_workspace_routes_for({"source": source}))
    for kind in ("rest", "active", "reactive"):
        targets |= set(_workspace_routes_for({"source": "energy", "kind": kind}))
    targets |= set(_workspace_routes_for({"source": "binding", "facets": {"read": "x"}}))
    assert targets and targets <= names, sorted(targets - names)
    from brain.utils.llm_gate import fn_requires_llm
    assert not [t for t in targets if fn_requires_llm(t)]
