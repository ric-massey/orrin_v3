# tests/brain/test_host_band.py
#
# The band-learner and the deviation-based body_sense it powers — the foundation
# of the embodiment architecture (docs/orrin_embodiment_architecture.md §10.4 and
# the Part VIII/IX audit). The load-bearing regression these tests lock in: a
# steady-high RSS (PyTorch resident ~900 MB) used to read "heavy" forever on an
# absolute threshold and pin the affect substrate; it must now read "clear."
import math

import pytest

from brain.cognition.host_band import Band, BodyBands


def _breathe(band: Band, center=920.0, amp=40.0, period=9.0, n=500):
    for i in range(n):
        band.observe(center + amp * math.sin(i / period))


# --------------------------------------------------------------- Band core ---

def test_converges_on_steady_breathing():
    b = Band("rss", min_samples=120, stable_needed=90)
    _breathe(b)
    assert b.converged
    assert b.lo < b.center < b.hi


def test_resting_value_is_not_felt_but_departure_is():
    b = Band("rss", min_samples=120, stable_needed=90)
    _breathe(b)
    # Deep inside the band — high but normal — registers as nothing.
    assert b.deviation(920) == 0.0
    assert not b.above_band(920)
    # A genuine departure above the ceiling registers, signed and normalised.
    assert b.deviation(1200) > 0.0
    assert b.above_band(1200)
    assert b.deviation(400) < 0.0  # below the floor


def test_one_off_spike_does_not_permanently_widen_band():
    b = Band("rss", min_samples=120, stable_needed=90)
    _breathe(b)
    hi_before = b.hi
    b.observe(3000.0)  # a single transient allocation blip
    # Percentile envelope ignores the rare outlier: a return to normal is breathing.
    assert b.hi == pytest.approx(hi_before, rel=0.05)
    assert b.deviation(940) == 0.0


def test_monotone_ramp_never_converges():
    # A one-way climb is a body sliding toward a wall, not a learned body (§10.5).
    b = Band("x", min_samples=120, stable_needed=90)
    for i in range(400):
        b.observe(i * 0.5)
    assert not b.converged
    assert b.marching()


def test_climb_then_plateau_converges():
    # The boot pattern: caches warm (RSS climbs), then steady-state breathing.
    b = Band("rss", min_samples=120, stable_needed=90)
    for i in range(150):
        b.observe(500 + i * 2)
    for i in range(400):
        b.observe(800 + 30 * math.sin(i / 8.0))
    assert b.converged


def test_danger_line_refuses_to_imprint():
    # §10.5/§10.6: while a sample is past the danger line, the body is sick and the
    # band must refuse to call that "normal."
    b = Band("disk_free", min_samples=50, stable_needed=30, danger_low=5.0)
    for _ in range(300):
        b.observe(3.0)  # pinned in the danger zone the whole time
    assert not b.converged


def test_persistence_round_trip():
    b = Band("rss", min_samples=120, stable_needed=90)
    _breathe(b)
    b2 = Band.from_dict(b.to_dict())
    assert b2.converged == b.converged
    assert b2.lo == pytest.approx(b.lo)
    assert b2.hi == pytest.approx(b.hi)
    assert b2.deviation(1200) == pytest.approx(b.deviation(1200))


# ------------------------------------------------------------- BodyBands ---

def test_bodybands_infancy_until_all_converge(tmp_path):
    bb = BodyBands(tmp_path / "bands.json",
                   specs={"a": {"min_samples": 50, "stable_needed": 30},
                          "b": {"min_samples": 50, "stable_needed": 30}})
    assert bb.in_infancy()  # nothing learned yet
    for i in range(300):
        bb.observe("a", 10 + math.sin(i / 5.0))
    assert bb.in_infancy()  # 'b' still unlearned
    for i in range(300):
        bb.observe("b", 5 + math.sin(i / 5.0))
    assert not bb.in_infancy()
    assert bb.converged_fraction() == 1.0


def test_bodybands_discards_foreign_machine_bands(tmp_path):
    p = tmp_path / "bands.json"
    bb = BodyBands(p, specs={"a": {"min_samples": 50, "stable_needed": 30}})
    for i in range(300):
        bb.observe("a", 10 + math.sin(i / 5.0))
    bb.save()
    # Reload but pretend we're on a different machine.
    bb2 = BodyBands(p, specs={"a": {"min_samples": 50, "stable_needed": 30}})
    bb2.fingerprint = "different-machine"
    bb2.load()
    assert not bb2.bands  # foreign calibration discarded; he re-learns this body


# ------------------------------------------------------- body_sense wiring ---

def test_body_sense_resting_high_rss_reads_clear_not_heavy():
    import brain.cognition.resource_self_monitor as bs
    bs._bands = None  # fresh, isolated by conftest's tmp DATA_DIR
    bs._dream_bands = None
    g = bs._get_bands()
    for i in range(500):
        g.observe("rss_mb", 920 + 40 * math.sin(i / 9.0))
        g.observe("cpu_util", 0.2 + 0.05 * math.sin(i / 7.0))
        g.observe("fd_pct", 0.2 + 0.03 * math.sin(i / 6.0))
        g.observe("latency_ms", 0.21 + 0.05 * math.sin(i / 5.0))
    assert not g.in_infancy()

    resting = {"rss_mb": 920, "cpu_util": 0.2, "fd_pct": 0.2, "latency_ms": 0.21}
    assert bs.compute_body_states(resting) == ["clear"]

    spike = {"rss_mb": 1400, "cpu_util": 0.2, "fd_pct": 0.2, "latency_ms": 0.21}
    assert "heavy" in bs.compute_body_states(spike)

    # Absolute FD-exhaustion backstop fires regardless of band.
    fd_crit = {"rss_mb": 920, "cpu_util": 0.2, "fd_pct": 0.95, "latency_ms": 0.21}
    assert "strained" in bs.compute_body_states(fd_crit)


def test_body_sense_lenient_during_infancy():
    import brain.cognition.resource_self_monitor as bs
    bs._bands = None
    bs._dream_bands = None
    g = bs._get_bands()
    # Only a handful of samples — bands not converged → infancy → stay clear even
    # though RSS is "high" in absolute terms.
    for _ in range(10):
        g.observe("rss_mb", 1500)
    assert g.in_infancy()
    assert bs.compute_body_states({"rss_mb": 1500, "cpu_util": 0.2,
                                   "fd_pct": 0.2, "latency_ms": 0.2}) == ["clear"]


def test_body_sense_uses_separate_sleep_phase_band(tmp_path, monkeypatch):
    import brain.cognition.resource_self_monitor as bs
    from brain.cognition.idle_consolidation.consolidation_cycle import set_consolidating

    monkeypatch.setattr(bs, "DATA_DIR", tmp_path)
    bs._bands = None
    bs._dream_bands = None

    wake = bs._get_bands(False)
    sleep = bs._get_bands(True)
    for i in range(500):
        wake.observe("rss_mb", 920 + 40 * math.sin(i / 9.0))
        wake.observe("cpu_util", 0.20 + 0.05 * math.sin(i / 7.0))
        wake.observe("fd_pct", 0.20 + 0.03 * math.sin(i / 6.0))
        wake.observe("latency_ms", 0.21 + 0.05 * math.sin(i / 5.0))

        sleep.observe("rss_mb", 1450 + 80 * math.sin(i / 9.0))
        sleep.observe("cpu_util", 0.78 + 0.08 * math.sin(i / 7.0))
        sleep.observe("fd_pct", 0.22 + 0.03 * math.sin(i / 6.0))
        sleep.observe("latency_ms", 0.34 + 0.05 * math.sin(i / 5.0))

    high_dream_vitals = {
        "rss_mb": 1450,
        "cpu_util": 0.78,
        "fd_pct": 0.22,
        "latency_ms": 0.34,
    }
    try:
        set_consolidating(False)
        assert "heavy" in bs.compute_body_states(high_dream_vitals)

        set_consolidating(True)
        assert bs.compute_body_states(high_dream_vitals) == ["clear"]
    finally:
        set_consolidating(False)


def test_completed_sleep_is_net_negative_despite_high_vitals(tmp_path, monkeypatch):
    import brain.control_signals.arbiter as arbiter
    from brain.control_signals.arbiter import commit_signals, submit_signal
    import brain.cognition.resource_self_monitor as bs
    from brain.cognition.idle_consolidation.consolidation_cycle import set_consolidating

    monkeypatch.setattr(bs, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bs, "BODY_SENSE_FILE", tmp_path / "resource_self_monitor.json")
    bs._bands = None
    bs._dream_bands = None

    sleep = bs._get_bands(True)
    for i in range(500):
        sleep.observe("rss_mb", 1450 + 80 * math.sin(i / 9.0))
        sleep.observe("cpu_util", 0.78 + 0.08 * math.sin(i / 7.0))
        sleep.observe("fd_pct", 0.22 + 0.03 * math.sin(i / 6.0))
        sleep.observe("latency_ms", 0.34 + 0.05 * math.sin(i / 5.0))

    high_dream_vitals = {
        "rss_mb": 1450,
        "cpu_util": 0.78,
        "fd_pct": 0.22,
        "latency_ms": 0.34,
    }
    monkeypatch.setattr(bs, "read_vitals", lambda: dict(high_dream_vitals))
    with arbiter._inbox_lock:
        arbiter._inbox.clear()

    context = {"affect_state": {"core_signals": {}, "resource_deficit": 0.55}}
    before = context["affect_state"]["resource_deficit"]
    try:
        set_consolidating(True)
        body = bs.update_body_sense(context)
        assert body["phase"] == "sleep"
        assert body["body_states"] == ["clear"]
        assert body["vitals"]["rss_mb"] > 1400
        assert body["vitals"]["cpu_util"] > 0.70

        submit_signal(None, "resource_deficit", -0.35, source="dream_rest", ttl_cycles=2)
        commit_signals(context)
    finally:
        set_consolidating(False)
        with arbiter._inbox_lock:
            arbiter._inbox.clear()

    assert context["affect_state"]["resource_deficit"] < before
