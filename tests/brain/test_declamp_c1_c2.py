# Run 11 §6.1 — the first two clamp→antagonist conversions, proven by harness
# (the R9-F7 forced-fire pattern):
#   C1: the ignition constant becomes a rolling percentile of the actual
#       effective-strength distribution (a pinned signal cannot saturate it).
#   C2: the staleness refractory / re-commit timer becomes aspiration neglect
#       pressure — unserved pull grows until displacement by ECONOMICS.
# Both flags default ON for Run 11; these tests exercise the ON paths.

import pytest

import brain.cognition.planning.commitment_value as cv
from brain.think import deliberation_gate as dg


# ── C1: adaptive ignition ────────────────────────────────────────────────────

def test_threshold_is_constant_until_distribution_is_warm():
    ctx: dict = {}
    assert dg.signal_trigger_threshold(ctx) == dg._SIGNAL_STRENGTH_TRIGGER


def test_threshold_tracks_the_lived_distribution():
    ctx: dict = {}
    hist = dg._eff_history(ctx)
    for v in [0.2] * 50 + [0.4] * 50:   # a cool stretch of life
        hist.append(v)
    thr = dg.signal_trigger_threshold(ctx)
    assert 0.30 <= thr <= 0.45, f"line should sit in the lived range, got {thr}"
    hist.clear()
    for v in [0.9] * 100:               # a hot stretch — "strong" means stronger
        hist.append(v)
    assert dg.signal_trigger_threshold(ctx) == pytest.approx(0.9)


def test_pinned_signal_cannot_saturate_the_percentile_gate():
    """Run 10's duty-cycle pathology: a signal welded at one value ignited
    trigger 3 ~every cycle against the 0.60 constant. Under C1 the pinned value
    IS the percentile, and the adaptive comparison is strictly-greater — so
    pinnedness alone stops winning once the distribution has learned it."""
    ctx: dict = {"affect_state": {}, "_emo_pre_cycle": {}}
    fired_reasons = []
    for cycle in range(120):
        ctx["raw_signals"] = [{"source": "drive_mastery", "signal_strength": 1.0}]
        ctx["_last_think_cycle"] = 10**9   # hold the periodic floor out of the way
        fire, reason = dg.should_think(ctx)
        fired_reasons.append(reason if fire else "quiet")
    early = fired_reasons[:10]
    late = fired_reasons[-40:]
    assert any(r.startswith("strong_signal") for r in early), (
        "a fresh strong signal must still ignite")
    assert not any(r.startswith("strong_signal") for r in late), (
        f"pinned signal still saturating trigger 3 late: {set(late)}")


def test_rising_signal_still_beats_the_adaptive_line():
    ctx: dict = {"affect_state": {}, "_emo_pre_cycle": {}}
    hist = dg._eff_history(ctx)
    for _ in range(60):
        hist.append(0.5)                 # ordinary life at 0.5
    ctx["raw_signals"] = [{"source": "threat_level", "signal_strength": 0.95}]
    ctx["_last_think_cycle"] = 10**9
    fire, reason = dg.should_think(ctx)
    assert fire and reason.startswith("strong_signal"), (
        "a genuinely out-of-distribution signal must ignite")


# ── C2: neglect pressure ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_signals(tmp_path, monkeypatch):
    monkeypatch.setattr(cv, "_SIGNALS_FILE", tmp_path / "commitment_signals.json",
                        raising=False)
    monkeypatch.setattr(cv, "_NEGLECT_PRESSURE_ENABLED", True, raising=False)


def test_neglect_accrues_for_the_unchosen_and_drains_for_the_served():
    holder, rival = "asp-a", "asp-b"
    for _ in range(50):
        cv.note_driver_selected(holder, [holder, rival])
    snap = cv.signals_snapshot()
    assert snap[rival]["neglect_pulls"] == 50.0
    assert snap[holder].get("neglect_pulls", 0.0) == 0.0
    # The rival takes the slot once — its accrued pull drains fast.
    cv.note_driver_selected(rival, [holder, rival])
    assert cv.signals_snapshot()[rival]["neglect_pulls"] == pytest.approx(12.5)


def test_credited_effect_satisfies_the_pull():
    rival = "asp-b"
    for _ in range(80):
        cv.note_driver_selected("asp-a", ["asp-a", rival])
    assert cv.signals_snapshot()[rival]["neglect_pulls"] == 80.0
    cv.note_goal_credit(rival, 0.8)
    assert cv.signals_snapshot()[rival]["neglect_pulls"] == 0.0


def test_neglect_displaces_a_higher_value_incumbent_by_economics():
    """The §10 health-axis proof shape: occupancy rotation happens because
    neglect PAIN wins, with zero refractory events — no timer involved."""
    incumbent = {"id": "asp-make", "title": "make things", "tier": "long_term",
                 "directional": True, "priority": "HIGH"}
    rival = {"id": "asp-connect", "title": "connect", "tier": "long_term",
             "directional": True, "priority": "HIGH"}
    # The incumbent EARNS (credited value well above the rival's prior).
    for _ in range(10):
        cv.note_goal_credit("asp-make", 1.0)

    flipped_at = None
    for pull in range(1, 220):
        out = cv.order_committable(
            [incumbent, rival], tier_weight_fn=lambda t: 1,
            priority_rank_fn=lambda p: 1, limit=2)
        driver = next(g["id"] for g in out if g.get("directional"))
        if driver == "asp-connect":
            flipped_at = pull
            break
    assert flipped_at is not None, (
        "neglect pressure never displaced the incumbent — monopoly is still "
        "administratively possible")
    # And it was economics, not the dead-man backstop.
    assert cv.refractory_events() == []
    # After the flip the ex-incumbent starts accruing pull of its own — the
    # restoring force works in both directions (§6.0 homeostat).
    cv.order_committable([incumbent, rival], tier_weight_fn=lambda t: 1,
                         priority_rank_fn=lambda p: 1, limit=2)
    assert cv.signals_snapshot()["asp-make"]["neglect_pulls"] > 0.0
