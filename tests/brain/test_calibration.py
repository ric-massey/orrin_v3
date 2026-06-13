# Tests for confidence/value calibration (cognition/calibration.py).
#
# Nelson & Narens (1990) monitoring → control; Brier (1950) proper scoring.
# The bandit's per-function expected reward is the forecast; the realized reward
# is the outcome. Sustained over/under-confidence corrects raw confidence and
# surfaces a metacognitive observation.
import cognition.calibration as cal


def _ctx(monkeypatch):
    monkeypatch.setattr(cal, "save_json", lambda *a, **k: None)  # pure
    return {"_calibration": {"brier": 0.0, "bias": 0.0, "n": 0}}


def test_perfect_calibration_no_bias(monkeypatch):
    ctx = _ctx(monkeypatch)
    for _ in range(30):
        cal.record(ctx, 0.6, 0.6)
    c = cal.get_calibration(ctx)
    assert abs(c["bias"]) < 0.02
    assert not c["overconfident"] and not c["underconfident"]
    # confidence passes through unchanged when well-calibrated
    assert cal.recalibrate_confidence(ctx, 0.8) == 0.8


def test_overconfidence_detected_and_corrected(monkeypatch):
    ctx = _ctx(monkeypatch)
    # predicts 0.8 but only ever gets 0.4 → overconfident by ~0.4
    for _ in range(30):
        cal.record(ctx, 0.8, 0.4)
    c = cal.get_calibration(ctx)
    assert c["overconfident"] is True
    assert c["bias"] > cal._BIAS_DEADBAND
    # raw confidence is discounted (but correction is clamped)
    adj = cal.recalibrate_confidence(ctx, 0.9)
    assert adj < 0.9
    assert adj >= 0.9 - cal._MAX_CORRECTION - 1e-9
    assert "overconfident" in (cal.calibration_observation(ctx) or "")


def test_underconfidence_detected_and_corrected(monkeypatch):
    ctx = _ctx(monkeypatch)
    for _ in range(30):
        cal.record(ctx, 0.3, 0.7)  # things go better than predicted
    c = cal.get_calibration(ctx)
    assert c["underconfident"] is True
    assert c["bias"] < -cal._BIAS_DEADBAND
    adj = cal.recalibrate_confidence(ctx, 0.5)
    assert adj > 0.5
    assert "underconfident" in (cal.calibration_observation(ctx) or "")


def test_no_correction_before_min_samples(monkeypatch):
    ctx = _ctx(monkeypatch)
    for _ in range(cal._MIN_SAMPLES - 1):
        cal.record(ctx, 0.9, 0.1)   # wildly overconfident but too few samples
    assert cal.get_calibration(ctx)["overconfident"] is False
    assert cal.recalibrate_confidence(ctx, 0.8) == 0.8
    assert cal.calibration_observation(ctx) is None


def test_record_ignores_bad_input(monkeypatch):
    ctx = _ctx(monkeypatch)
    cal.record(ctx, "nan", 0.5)
    assert ctx["_calibration"]["n"] == 0


def test_recalibrated_confidence_stays_in_unit_interval(monkeypatch):
    ctx = _ctx(monkeypatch)
    for _ in range(30):
        cal.record(ctx, 1.0, 0.0)   # maximal overconfidence
    adj = cal.recalibrate_confidence(ctx, 0.05)
    assert 0.0 <= adj <= 1.0
