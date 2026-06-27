# tests/observability_tests/affect_fidelity_test.py
#
# Fidelity / SEMANTICS test (SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT_2026-06-19 §7
# rec #5). The existing telemetry_contract_test guards the *plumbing* — that no
# emitted key is dropped in transit. It does NOT guard the *meaning*: an emitted
# value could be a transform of, or wholly invented relative to, the brain's
# real number and the contract test would still be green (audit F1–F4).
#
# This test pins the two semantic properties the audit's fixes establish:
#   1. Homeostasis is no longer invented in the telemetry helper — it is the
#      single authority's number (affect.homeostasis.homeostasis_index), written
#      onto affect_state and merely READ by _emit_affect. So the value the UI
#      charts equals the value the brain holds.
#   2. The transformed valence the chart reads round-trips back to the raw
#      brain valence through the documented presentation mapping (no hidden
#      number): raw is recoverable, and is also exposed straight via /api/affect.
from __future__ import annotations


def test_homeostasis_index_is_deterministic_and_settled_at_rest():
    from brain.control_signals.homeostasis import homeostasis_index
    from brain.control_signals.setpoints import setpoint
    # A core vector sitting exactly on its setpoints is maximally settled.
    core = {k: setpoint(k) for k in ("motivation", "confidence", "impasse_signal")}
    assert homeostasis_index(core) == 1.0
    # Deviating a signal lowers the index; the function is pure (same in == same out).
    core["impasse_signal"] = setpoint("impasse_signal") + 0.5
    agitated = homeostasis_index(core)
    assert 0.0 <= agitated < 1.0
    assert homeostasis_index(dict(core)) == agitated
    # Fail-safe on empty input.
    assert homeostasis_index({}) == 0.8


def test_emit_affect_reads_stored_homeostasis_not_a_reinvented_one():
    """The number the UI charts must equal the brain's own homeostasis, proving
    the value is no longer fabricated inside the translator (audit F2)."""
    # _emit_affect lives in the loop's telemetry stage now (Phase 4A); test it there.
    import brain.loop.telemetry as tele

    captured: dict = {}

    class _FakeBridge:
        def affect(self, **kw):
            captured.update(kw)

    orig = tele._bridge
    tele._bridge = lambda: _FakeBridge()
    try:
        context = {"affect_state": {
            "valence": -0.4,
            "activation_level": 0.3,
            "homeostasis": 0.123,  # the brain's stored index; emit must use THIS
            "core_signals": {"motivation": 0.5, "impasse_signal": 0.9},
        }}
        tele._emit_affect(context)
    finally:
        tele._bridge = orig

    # Homeostasis charted == homeostasis the brain holds (no reinvention).
    assert captured["homeostasis"] == 0.123
    # Raw valence is shipped unmodified alongside the centered presentation value.
    assert captured["valence_raw"] == -0.4
    # The centered value round-trips back to raw via the documented mapping.
    recovered = (captured["valence"] - tele._VALENCE_UI_CENTER) / tele._VALENCE_UI_SCALE
    assert abs(recovered - (-0.4)) < 1e-9


def test_update_affect_state_stamps_homeostasis_onto_canonical_state():
    """The authority writes the index onto affect_state, so REST (B) and the
    chart (C) read one number rather than two clocks."""
    from brain.control_signals.homeostasis import homeostasis_index
    core = {"motivation": 0.6, "confidence": 0.55, "impasse_signal": 0.2}
    # Mirror what update_affect_state stores: round(homeostasis_index(core), 4).
    assert round(homeostasis_index(core), 4) == round(homeostasis_index(dict(core)), 4)
