"""Phase B cluster 5 — affect and pressure (B9, B25, B26)."""
from __future__ import annotations

import pytest


# ── B9: a repeatedly-unchosen want habituates ────────────────────────────────

def test_inhibition_cost_habituates_for_a_standing_want():
    from brain.cognition.inhibition import apply_inhibition_costs
    ctx = {"affect_state": {"core_signals": {"uncertainty": 0.0, "impasse_signal": 0.0}}}
    scored = [("reflection", 0.9, {}), ("generate_intrinsic_goals", 0.8, {})]
    pull = {"generate_intrinsic_goals": 0.7}
    costs = []
    for _ in range(6):
        before = ctx["affect_state"]["core_signals"]["impasse_signal"]
        apply_inhibition_costs(ctx, scored, "reflection", pull)
        costs.append(ctx["affect_state"]["core_signals"]["impasse_signal"] - before)
    assert costs[0] > 0
    assert costs[-1] <= costs[0] / 8
    # Choosing the want resets the streak: the next loss lands at full cost again.
    apply_inhibition_costs(ctx, scored, "generate_intrinsic_goals", {"reflection": 0.1})
    before = ctx["affect_state"]["core_signals"]["impasse_signal"]
    apply_inhibition_costs(ctx, scored, "reflection", pull)
    assert ctx["affect_state"]["core_signals"]["impasse_signal"] - before == pytest.approx(costs[0])


# ── B25: write-back habituates per situation ─────────────────────────────────

def test_writeback_habituates_on_a_standing_binding(monkeypatch):
    from brain.cognition import workspace_writeback as wb
    from brain.control_signals.arbiter import _PROP_KEY
    monkeypatch.setattr("brain.cognition.global_workspace.goal_in_focus", lambda ctx: True)
    ctx = {"_workspace_priors": {}, "affect_state": {"core_signals": {}}}
    moment = {"content": "step 3 of Understand tides closes", "source": "binding",
              "salience": 0.9, "goal_id": "g1"}
    deltas = []
    for _ in range(6):
        ctx[_PROP_KEY] = []
        wb.write_back(ctx, dict(moment))
        mot = [p["delta"] for p in ctx[_PROP_KEY] if p["target"] == "motivation"]
        deltas.append(mot[0] if mot else 0.0)
    assert deltas[0] == wb._MAX_AFFECT_DELTA
    assert deltas[1] == wb._MAX_AFFECT_DELTA / 2
    assert deltas[3:] == [0.0, 0.0, 0.0]
    # A different situation is fresh.
    ctx[_PROP_KEY] = []
    wb.write_back(ctx, {**moment, "goal_id": "g2", "content": "a step of Write the memo closes"})
    assert any(p["target"] == "motivation" and p["delta"] == wb._MAX_AFFECT_DELTA
               for p in ctx[_PROP_KEY])


# ── B26: allostatic_load is wired; it arms only above deficit 0.60 ───────────

def test_allostatic_load_gauge_moves_when_load_accrues(monkeypatch):
    """Run 13 read 0.000 all life because fatigue peaked at 0.21 (load accrues
    only above 0.60) — the gauge is wired, not dead. Lock the wire in."""
    from brain.cognition import cost_prediction as cp
    monkeypatch.setattr(cp, "_allostatic_enabled", lambda: True)
    state = {"resource_deficit": 0.7}
    for _ in range(10):
        cp.allostatic_setpoint({"cycle_count": {"count": 1}}, state)
    assert state["_allostatic_load"] > 0.1
    out = cp.observe("reflection", 120.0, {"affect_state": state})
    assert out["allostatic_load"] == round(state["_allostatic_load"], 3)
