# 1D.2 (Run 12) — make ignition breathe. Run 11: 98.2 % of 18,327 cycles
# ignited; `action_debt` (a standing condition, level-triggered) was 93.2 % of
# the wins, and `drive_mastery` — the DemandEngine's leak-less mastery drive —
# sat welded at 1.00 all life with no recalibration event because neither
# saturation-tripwire sweep ever saw the engine's live pressures.
# Three locked-in behaviors: (1) tick-based drives equilibrate below their
# bounds instead of pinning; (2) the saturation tripwire covers live drive
# pressures and recalibrates a welded one; (3) the action-debt / multi-goal
# ignition triggers fire on onset/change with a refractory, not every cycle.

import pytest

from brain.runtime_coupling import demand_engine as de
from brain.think import deliberation_gate as gate


# ── (1) drive leak: no tick-based drive can pin at 1.0 ───────────────────────

def test_all_tick_drives_equilibrate_below_urgent_pin():
    engine = de.DemandEngine()
    for name, drive in engine.drives.items():
        if drive.buildup_per_tick <= 0:
            continue  # event-driven drives have no tick dynamics
        assert drive.leak_per_tick > 0, f"tick-based drive '{name}' has no leak (pins at 1.0)"
        for _ in range(3000):
            drive.tick()
        eq = drive.get_pressure()
        assert eq < 0.75, f"'{name}' equilibrium {eq} — above the urgent line, near-pinned"
        assert eq > 0.35, f"'{name}' equilibrium {eq} — leaked below its own signal threshold"


# ── (2) tripwire coverage of live drive pressures ────────────────────────────

def test_saturation_check_recalibrates_a_welded_drive(monkeypatch):
    engine = de.DemandEngine()
    monkeypatch.setattr(de, "_engine", engine)
    monkeypatch.setattr(de, "_drive_sat_state", {})
    # Weld mastery the way Run 11 saw it: pump beats leak every cycle.
    fired_keys: list = []
    from brain.control_signals.homeostasis import SATURATION_MAX_CYCLES
    for cyc in range(SATURATION_MAX_CYCLES + 5):
        engine.drives["mastery"].set_pressure(1.0)
        fired_keys += de.saturation_check(cyc)
        if fired_keys:
            break   # the pump stops re-welding once the trip is in
    assert "drive_mastery" in fired_keys, "welded drive never tripped the tripwire"
    # The recalibration was written back onto the live Demand (kicked off the
    # bound toward setpoint), not just onto a throwaway dict.
    assert engine.drives["mastery"].get_pressure() < 0.75


def test_saturation_check_leaves_resting_drives_alone(monkeypatch):
    engine = de.DemandEngine()
    monkeypatch.setattr(de, "_engine", engine)
    monkeypatch.setattr(de, "_drive_sat_state", {})
    from brain.control_signals.homeostasis import SATURATION_MAX_CYCLES
    fired: list = []
    for cyc in range(SATURATION_MAX_CYCLES + 5):
        fired += de.saturation_check(cyc)
    # All drives at 0.0 pressure: a bound AT the setpoint is rest, not a weld.
    assert fired == []


# ── (3) standing-condition triggers: edge + refractory, not per-cycle ────────

@pytest.fixture()
def quiet_context():
    gate._reset_standing_trigger_state()
    gate._eff_history_state.clear()
    gate._ignition_recent_state.clear()
    yield {
        "affect_state": {"core_signals": {}},
        "raw_signals": [],
        "_emo_pre_cycle": {},
        "_last_think_cycle": 0,   # floor (trigger 14) stays quiet at cycle 0
    }
    gate._reset_standing_trigger_state()


def test_action_debt_fires_on_crossing_then_respects_refractory(quiet_context):
    ctx = quiet_context
    ctx["committed_goals"] = [{"id": "g1", "title": "a goal"}]
    ctx["action_debt"] = 5
    fire, reason = gate.should_think(ctx)
    assert fire and reason.startswith("action_debt")
    # Debt keeps climbing (the Run 11 shape: 33 → 72, monotone) — but the
    # condition already ignited; within the refractory it must NOT re-fire.
    for debt in (6, 7, 8):
        ctx["action_debt"] = debt
        fire, reason = gate.should_think(ctx)
        assert not fire, f"standing debt re-fired inside refractory ({reason})"


def test_action_debt_refires_after_refractory(quiet_context, monkeypatch):
    ctx = quiet_context
    ctx["committed_goals"] = [{"id": "g1", "title": "a goal"}]
    ctx["action_debt"] = 5
    assert gate.should_think(ctx)[0]
    # Advance the clock past the refractory: a still-stalled goal is worth
    # deliberating about again.
    monkeypatch.setattr(gate, "get_cycle_count", lambda: gate._DEBT_REFIRE_CYCLES + 1)
    ctx["_last_think_cycle"] = gate._DEBT_REFIRE_CYCLES  # keep the floor quiet
    ctx["action_debt"] = 40
    fire, reason = gate.should_think(ctx)
    assert fire and reason.startswith("action_debt")


def test_multi_goal_fires_on_set_change_only(quiet_context):
    ctx = quiet_context
    ctx["committed_goals"] = [{"id": "g1"}, {"id": "g2"}]
    fire, reason = gate.should_think(ctx)
    assert fire and reason.startswith("multi_goal")
    # Same standing set: quiet.
    fire, reason = gate.should_think(ctx)
    assert not fire, f"unchanged goal set re-fired multi_goal ({reason})"
    # The set changes: that IS an event.
    ctx["committed_goals"] = [{"id": "g1"}, {"id": "g2"}, {"id": "g3"}]
    fire, reason = gate.should_think(ctx)
    assert fire and reason.startswith("multi_goal")
