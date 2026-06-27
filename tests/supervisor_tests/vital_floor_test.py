from supervisor.vital_floor import (
    VitalFloorGuard,
    set_vital_shedding,
    vital_floor_shedding,
)
from supervisor.vital_floor_calibration import load_samples, summarize

_GB = float(1024 * 1024 * 1024)


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def now(self):
        return self.t

    def step(self, dt):
        self.t += dt


class Box:
    def __init__(self, v):
        self.v = v

    def set(self, v):
        self.v = v


class EventRecorder:
    def __init__(self):
        self.msgs = []

    def __call__(self, msg):
        self.msgs.append(msg)


def _reset_gate():
    set_vital_shedding(False, "")


def _make_guard(clock, rss, budget, **kw):
    warn = EventRecorder()
    shed = EventRecorder()
    recover = EventRecorder()
    shed_calls = []
    guard = VitalFloorGuard(
        on_warn=warn,
        on_shed=shed,
        on_recover=recover,
        shed_fn=lambda reason: shed_calls.append(reason),
        get_own_rss_bytes=lambda: rss.v,
        get_budget_bytes=lambda: budget.v,
        now_fn=clock.now,
        warn_frac=0.60,
        shed_frac=0.80,
        recover_frac=0.50,
        sustain_s=5.0,
        **kw,
    )
    return guard, warn, shed, recover, shed_calls


def test_observe_only_reports_but_does_not_shed():
    _reset_gate()
    clk = FakeClock()
    budget = Box(4 * _GB)
    rss = Box(3.4 * _GB)  # 85% of grant, above shed
    guard, warn, shed, recover, shed_calls = _make_guard(
        clk, rss, budget, observe_only=True
    )

    for _ in range(7):
        guard.step()
        clk.step(1.0)

    assert vital_floor_shedding() is False
    assert shed_calls == []
    assert warn.msgs == []
    assert recover.msgs == []


def test_armed_guard_sheds_and_recovers_with_hysteresis():
    _reset_gate()
    clk = FakeClock()
    budget = Box(4 * _GB)
    rss = Box(3.4 * _GB)  # above shed
    guard, warn, shed, recover, shed_calls = _make_guard(
        clk, rss, budget, observe_only=False
    )

    for _ in range(7):
        guard.step()
        clk.step(1.0)

    assert vital_floor_shedding() is True
    assert len(shed.msgs) == 1
    assert len(shed_calls) == 1

    # Back below shed/warn but still above recover: stay in shedding.
    rss.set(2.2 * _GB)  # 55% of grant
    for _ in range(7):
        guard.step()
        clk.step(1.0)
    assert vital_floor_shedding() is True
    assert recover.msgs == []

    # Recover below the recovery line: gate clears.
    rss.set(1.6 * _GB)  # 40% of grant
    for _ in range(7):
        guard.step()
        clk.step(1.0)
    assert vital_floor_shedding() is False
    assert recover.msgs


def test_warn_is_non_shedding():
    _reset_gate()
    clk = FakeClock()
    budget = Box(4 * _GB)
    rss = Box(2.8 * _GB)  # 70% of grant, above warn but below shed
    guard, warn, shed, recover, shed_calls = _make_guard(
        clk, rss, budget, observe_only=False
    )

    for _ in range(7):
        guard.step()
        clk.step(1.0)

    assert len(warn.msgs) == 1
    assert shed.msgs == []
    assert shed_calls == []
    assert vital_floor_shedding() is False


def test_transient_spike_does_not_trip():
    _reset_gate()
    clk = FakeClock()
    budget = Box(4 * _GB)
    rss = Box(1.6 * _GB)
    guard, warn, shed, recover, shed_calls = _make_guard(
        clk, rss, budget, observe_only=False
    )

    for i in range(7):
        rss.set(3.6 * _GB if i == 3 else 1.6 * _GB)
        guard.step()
        clk.step(1.0)

    assert warn.msgs == []
    assert shed.msgs == []
    assert shed_calls == []
    assert vital_floor_shedding() is False


def test_calibration_samples_are_written(tmp_path):
    _reset_gate()
    clk = FakeClock()
    budget = Box(4 * _GB)
    rss = Box(2 * _GB)
    sample_file = tmp_path / "vital.jsonl"
    guard, warn, shed, recover, shed_calls = _make_guard(
        clk,
        rss,
        budget,
        observe_only=True,
        calibration_file=str(sample_file),
        calibration_phase="calm",
        calibration_sample_s=0.0,
    )

    guard.step()

    samples = load_samples(sample_file)
    assert len(samples) == 1
    assert samples[0]["phase"] == "calm"
    assert samples[0]["frac"] == 0.5
    assert samples[0]["observe_only"] is True


def test_calibration_summary_recommends_ordered_thresholds():
    report = summarize([
        {"phase": "calm", "frac": 0.40},
        {"phase": "calm", "frac": 0.45},
        {"phase": "stress", "frac": 0.62},
        {"phase": "stress", "frac": 0.70},
    ])

    rec = report["recommendation"]
    assert report["phases"]["calm"]["n"] == 2
    assert rec["recover_frac"] < rec["warn_frac"] < rec["shed_frac"]


def test_oscillation_verdict_is_step_based_not_range_based():
    # A slow drift across a wide total range but with tiny consecutive steps is
    # GENTLE (idle GC sawtooth), not a slam (§8.2). The verdict keys on step size.
    drift = summarize([
        {"phase": "calm", "frac": f, "monotonic_s": i}
        for i, f in enumerate([0.10, 0.12, 0.14, 0.18, 0.22, 0.28, 0.34, 0.40])
    ])
    assert drift["phases"]["calm"]["oscillation"]["verdict"] == "gentle"
    assert drift["phases"]["calm"]["oscillation"]["range"] > 0.25

    # Large, fast swings back and forth DO slam.
    slam = summarize([
        {"phase": "stress", "frac": f, "monotonic_s": i}
        for i, f in enumerate([0.10, 0.50, 0.12, 0.55, 0.15, 0.60])
    ])
    assert slam["phases"]["stress"]["oscillation"]["verdict"] == "slams"


def test_min_viable_body_from_peak_rss():
    _GB_ = float(1024 * 1024 * 1024)
    report = summarize([
        {"phase": "calm", "frac": 0.20, "rss_bytes": 0.8 * _GB_, "budget_bytes": 4 * _GB_},
        {"phase": "dream_reading", "frac": 0.25, "rss_bytes": 1.0 * _GB_, "budget_bytes": 4 * _GB_},
    ])
    mvb = report["min_viable_body"]
    # Peak comes from the dream/reading phase (1.0 GB), not calm.
    assert mvb["from_phase"] == "dream/reading"
    assert abs(mvb["peak_rss_gb"] - 1.0) < 0.01
    # floor = peak / shed_frac (0.55) ≈ 1.82 GB; recommended = peak / warn_frac (0.50) = 2.0 GB.
    assert mvb["floor_grant_gb"] < mvb["recommended_grant_gb"]
    assert abs(mvb["recommended_grant_gb"] - 2.0) < 0.01
