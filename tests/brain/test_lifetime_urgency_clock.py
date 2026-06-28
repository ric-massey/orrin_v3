"""T1.3 — mortality forward-pressure urgency clock (real/felt blend).

Owner decision (2026-06-28): the urgency phase is driven by a blend of the
within-run session-arc and the real life-fraction, with the real life-fraction as
a floor (so a fresh session late in life still reads its true age). This makes the
late/terminal urgency injections actually fire within a run — they never did when
keyed to the lifespan-noise _felt_fraction. Termination stays on the real clock.
"""
from brain.cognition import runtime_lifetime as rl


def test_blend_ramps_within_a_run():
    """A long session lifts the urgency phase past 'early' even when real
    life-fraction is near zero (a single run is a sliver of a 60-day life)."""
    blended = rl._blended_fraction(real_frac=0.02, session_frac=1.0)
    assert blended >= 0.50
    assert rl._phase(blended) != "early"          # injections fire (middle+ has bumps)
    # With no session progress and a young life, it stays 'early'.
    assert rl._phase(rl._blended_fraction(0.02, 0.0)) == "early"


def test_real_life_is_a_floor():
    """Late real life keeps urgency at its true age even in a fresh session — the
    'still respects the 60-day arc' half of the decision."""
    assert rl._phase(rl._blended_fraction(real_frac=0.95, session_frac=0.0)) == "terminal"
    assert rl._phase(rl._blended_fraction(real_frac=0.80, session_frac=0.0)) in ("late", "terminal")


def test_session_fraction_from_temporal_state():
    assert rl._session_fraction({"temporal_state": {"felt_cycles": 150}}) == 1.0
    assert rl._session_fraction({"temporal_state": {"felt_cycles": 75}}) == 0.5
    assert rl._session_fraction({}) == 0.0
    assert rl._session_fraction({"temporal_state": None}) == 0.0


def test_injection_fires_in_a_run_without_terminating(tmp_path, monkeypatch):
    """End-to-end: a long felt session drives the phase past 'early' and applies a
    phase signal injection to affect, without the real deadline passing."""
    monkeypatch.setattr(rl, "LIFESPAN_FILE", tmp_path / "runtime_lifetime.json")
    ctx = {
        # Non-empty core_signals (an empty dict is falsy and trips the legacy
        # `core or emo` fallback — real affect_state is never empty).
        "affect_state": {"core_signals": {"motivation": 0.10}},
        "temporal_state": {"felt_cycles": 200},   # deep session → session_frac 1.0
    }
    summary = rl.apply_lifetime_pressure(ctx)
    assert summary["terminate"] is False
    assert summary["phase"] != "early"
    assert summary["session_fraction"] == 1.0
    assert summary["urgency_fraction"] >= 0.50
    # The phase signal injection actually moved affect (middle+ has bumps).
    core = ctx["affect_state"]["core_signals"]
    assert core.get("expected_gain", 0.0) > 0.0 or core.get("loss_signal", 0.0) > 0.0
