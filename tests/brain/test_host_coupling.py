# tests/brain/test_host_coupling.py
#
# Parts IV–VI of the host-coupling architecture: the budget/floor knob (§11), resource
# cadence (§7, mapping #1), host interoception (§6.2), and the warm-up split (§10).
import math

import pytest

from brain.cognition import host_budget as bb
from brain.cognition import resource_cadence as mb


_GB = float(1024 * 1024 * 1024)


@pytest.fixture
def ram8(monkeypatch):
    """Pin the detected machine to 8 GB so budget maths is deterministic."""
    monkeypatch.setattr(bb, "machine_ram_bytes", lambda: 8.0 * _GB)
    return 8.0 * _GB


# ------------------------------------------------------------- budget/floor ---

def test_budget_is_a_fraction_of_the_machine(ram8, monkeypatch):
    monkeypatch.setattr(bb, "budget_fraction", lambda: 0.5)
    assert bb.budget_bytes() == pytest.approx(4.0 * _GB)


def test_floor_is_non_overridable(ram8, monkeypatch):
    # Drag the slider to 95% — the survival reserve still clamps real allocation so the
    # machine can breathe/hibernate (§11.4.1). budget never exceeds ram - reserve.
    monkeypatch.setattr(bb, "budget_fraction", lambda: 0.95)
    reserve = bb.survival_reserve_bytes()
    assert bb.budget_bytes() <= 8.0 * _GB - reserve + 1
    assert reserve >= 2.0 * _GB  # absolute minimum host courtesy


def test_too_small_grant_is_refused_loudly(ram8):
    ok, reason = bb.validate_grant(0.05)
    assert not ok
    assert "minimum viable" in reason.lower()
    # And the setter refuses without persisting.
    res = bb.set_budget_fraction(0.05)
    assert res["ok"] is False


def test_viable_grant_passes(ram8):
    ok, _ = bb.validate_grant(0.5)
    assert ok


# ------------------------------------------------------------- resource cadence ---

def test_cadence_tier_tracks_budget_size(monkeypatch):
    monkeypatch.setattr(mb, "_current_tier", None, raising=False)
    assert mb._raw_tier(1.0) == "tiny"
    assert mb._raw_tier(2.0) == "small"
    assert mb._raw_tier(5.0) == "normal"
    assert mb._raw_tier(32.0) == "large"


def test_cadence_hysteresis_dead_band():
    # Hovering just past the small→normal boundary (3.0 GB) must NOT flip while within
    # the dead band; a budget sitting at 3.1 GB that was 'small' stays 'small' (§8.4).
    assert mb._tier_with_hysteresis(3.1, "small") == "small"
    # But a clear move past the dead band switches.
    assert mb._tier_with_hysteresis(4.0, "small") == "normal"
    # Coming back down, it sticks to 'normal' until well under the boundary.
    assert mb._tier_with_hysteresis(2.9, "normal") == "normal"
    assert mb._tier_with_hysteresis(2.0, "normal") == "small"


def test_small_budget_slows_the_clock():
    assert mb._PROFILE["tiny"]["cadence"] > mb._PROFILE["normal"]["cadence"]
    assert mb._PROFILE["large"]["cadence"] < mb._PROFILE["normal"]["cadence"]


# --------------------------------------------------------- host interoception ---

def test_host_interoception_silent_in_infancy(monkeypatch):
    import brain.cognition.host_resource_monitor as hi
    hi._host_bands = None
    # Force a tiny sample set → host bands not converged → infancy → no felt stress.
    monkeypatch.setattr(hi, "read_host_vitals", lambda: {
        "disk_free_gb": 1.0, "swap_used_gb": 9.0, "vmem_percent": 99.0,
    })
    ctx = {}
    out = hi.update_host_interoception(ctx)
    assert out["host_infancy"] is True
    assert out["host_states"] == ["clear"]  # lenient until the host band converges


def test_host_interoception_feels_departure_after_convergence(monkeypatch):
    import brain.cognition.host_resource_monitor as hi
    hi._host_bands = None
    g = hi._bands()
    # Converge the bands on a calm, breathing host.
    for i in range(400):
        g.observe("disk_free_gb", 200 + 5 * math.sin(i / 7.0))
        g.observe("swap_used_gb", 1.0 + 0.2 * math.sin(i / 6.0))
        g.observe("vmem_percent", 60 + 4 * math.sin(i / 5.0))
    assert not g.in_infancy()
    # Now a genuine swap climb far above the learned band → "sluggish".
    monkeypatch.setattr(hi, "read_host_vitals", lambda: {
        "disk_free_gb": 200.0, "swap_used_gb": 6.0, "vmem_percent": 60.0,
    })
    out = hi.update_host_interoception({})
    assert "sluggish" in out["host_states"]


def test_battery_drain_is_felt_gently(monkeypatch):
    import brain.cognition.host_resource_monitor as hi
    hi._host_bands = None
    g = hi._bands()
    for i in range(400):
        g.observe("disk_free_gb", 200.0)
        g.observe("swap_used_gb", 1.0)
        g.observe("vmem_percent", 60.0)
    monkeypatch.setattr(hi, "read_host_vitals", lambda: {
        "disk_free_gb": 200.0, "swap_used_gb": 1.0, "vmem_percent": 60.0,
        "battery_percent": 10.0, "battery_plugged": 0.0,
    })
    out = hi.update_host_interoception({})
    assert out["battery"]["percent"] == 10.0
    assert "draining" in out["host_states"]


# -------------------------------------------------------------------- infancy ---

def test_infancy_scenarios(monkeypatch):
    import brain.cognition.infancy as inf
    # true birth: no learned body AND no life
    monkeypatch.setattr(inf, "somatic_infancy", lambda: True)
    monkeypatch.setattr(inf, "developmental_infancy", lambda: True)
    assert inf.scenario() == "first_birth"
    # transplant: a life behind him, new body still learning
    monkeypatch.setattr(inf, "developmental_infancy", lambda: False)
    assert inf.scenario() == "new_body"
    # waking: body already known
    monkeypatch.setattr(inf, "somatic_infancy", lambda: False)
    assert inf.scenario() == "waking"
