# tests/reaper_tests/host_resources_test.py
from supervisor.host_resources import (
    HostResourceGuard,
    heavy_cycles_paused,
    set_heavy_cycles_paused,
)

_GB = float(1024 * 1024 * 1024)
_MB = float(1024 * 1024)

# ---------- helpers ----------

class FakeClock:
    def __init__(self, t=0.0): self.t = t
    def now(self): return self.t
    def step(self, dt): self.t += dt  # seconds

class EventRecorder:
    def __init__(self): self.msgs = []
    def __call__(self, msg: str): self.msgs.append(msg)

class Box:
    def __init__(self, v): self.v = v
    def set(self, v): self.v = v

def make_guard(clock, **kw):
    warn, pause, resume = EventRecorder(), EventRecorder(), EventRecorder()
    guard = HostResourceGuard(
        on_warn=warn, on_pause=pause, on_resume=resume,
        now_fn=clock.now, **kw,
    )
    return guard, warn, pause, resume

def _reset_gate():
    set_heavy_cycles_paused(False, "")


# ---------- DISK: the lagging indicator that ambushed the host ----------

def test_disk_warn_then_pause_then_resume():
    _reset_gate()
    clk = FakeClock()
    free = Box(25 * _GB)  # comfortably above the 20GB soft line
    guard, warn, pause, resume = make_guard(
        clk,
        get_disk_free_bytes=lambda: free.v,
        disk_warn_free_bytes=20 * _GB,
        disk_pause_free_bytes=10 * _GB,
        disk_sustain_s=5.0,
    )

    # Healthy: no events, heavies running.
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert warn.msgs == [] and pause.msgs == []
    assert heavy_cycles_paused() is False

    # Cross the soft line (free 15GB): WARN only, heavies still running.
    free.set(15 * _GB)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert len(warn.msgs) == 1 and "disk_free" in warn.msgs[-1]
    assert pause.msgs == []
    assert heavy_cycles_paused() is False

    # Cross the hard line (free 8GB): PAUSE, heavies gated off.
    free.set(8 * _GB)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert len(pause.msgs) == 1 and "pause_heavy" in pause.msgs[-1]
    assert heavy_cycles_paused() is True

    # Recover past the soft line again (free 25GB): resume, heavies back on.
    free.set(25 * _GB)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert resume.msgs, "expected a resume event after recovery"
    assert heavy_cycles_paused() is False


def test_disk_pause_does_not_flap_in_hysteresis_band():
    """Recovering only past the pause floor (but still below the warn floor)
    must NOT resume heavies — the band between the lines is deliberate."""
    _reset_gate()
    clk = FakeClock()
    free = Box(8 * _GB)
    guard, warn, pause, resume = make_guard(
        clk,
        get_disk_free_bytes=lambda: free.v,
        disk_warn_free_bytes=20 * _GB,
        disk_pause_free_bytes=10 * _GB,
        disk_sustain_s=5.0,
    )
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert heavy_cycles_paused() is True

    # Climb to 12GB: above pause floor, still below warn floor → stay paused.
    free.set(12 * _GB)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert heavy_cycles_paused() is True


def test_disk_transient_dip_does_not_trip():
    """A single sub-floor sample inside the window is not sustained → no trip."""
    _reset_gate()
    clk = FakeClock()
    free = Box(25 * _GB)
    guard, warn, pause, resume = make_guard(
        clk,
        get_disk_free_bytes=lambda: free.v,
        disk_warn_free_bytes=20 * _GB,
        disk_pause_free_bytes=10 * _GB,
        disk_sustain_s=5.0,
    )
    for i in range(7):
        free.set(5 * _GB if i == 3 else 25 * _GB)  # one transient dip
        guard.step(); clk.step(1.0)
    assert warn.msgs == [] and pause.msgs == []
    assert heavy_cycles_paused() is False


# ---------- SWAP: the leading indicator ----------

def test_swap_growth_slope_warns_before_floor():
    _reset_gate()
    clk = FakeClock()
    used = Box(0.5 * _GB)  # below warn level, but climbing fast
    guard, warn, pause, resume = make_guard(
        clk,
        get_swap_used_bytes=lambda: used.v,
        swap_warn_used_bytes=2 * _GB,
        swap_pause_used_bytes=4 * _GB,
        swap_growth_warn_bytes_per_s=5 * _MB,
        swap_sustain_s=10.0,
    )
    # +20 MB/s for 11s: never crosses the 2GB warn level, but slope >> 5 MB/s.
    for i in range(11):
        used.set(0.5 * _GB + 20 * _MB * i)
        guard.step(); clk.step(1.0)
    assert warn.msgs, "rising swap should warn on slope alone"
    assert "swap_growth" in warn.msgs[-1]
    assert heavy_cycles_paused() is False  # warn, not pause


def test_swap_used_over_pause_pauses():
    _reset_gate()
    clk = FakeClock()
    used = Box(5 * _GB)
    guard, warn, pause, resume = make_guard(
        clk,
        get_swap_used_bytes=lambda: used.v,
        swap_warn_used_bytes=2 * _GB,
        swap_pause_used_bytes=4 * _GB,
        swap_sustain_s=5.0,
    )
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert pause.msgs and "swap_used" in pause.msgs[-1]
    assert heavy_cycles_paused() is True


# ---------- VMEM: system-wide pressure (the whole box, tabs included) ----------

def test_vmem_percent_warn_and_pause():
    _reset_gate()
    clk = FakeClock()
    pct = Box(50.0)
    guard, warn, pause, resume = make_guard(
        clk,
        get_vmem_percent=lambda: pct.v,
        vmem_warn_percent=85.0,
        vmem_pause_percent=95.0,
        vmem_sustain_s=5.0,
    )
    pct.set(90.0)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert len(warn.msgs) == 1 and "vmem" in warn.msgs[-1]
    assert heavy_cycles_paused() is False

    pct.set(97.0)
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert pause.msgs and heavy_cycles_paused() is True


# ---------- worst-signal-wins ----------

def test_worst_signal_dominates():
    """Disk is healthy but vmem is critical → overall level is PAUSE."""
    _reset_gate()
    clk = FakeClock()
    guard, warn, pause, resume = make_guard(
        clk,
        get_disk_free_bytes=lambda: 100 * _GB,  # plenty
        get_vmem_percent=lambda: 99.0,          # critical
        disk_sustain_s=5.0,
        vmem_sustain_s=5.0,
        vmem_pause_percent=95.0,
    )
    for _ in range(7):
        guard.step(); clk.step(1.0)
    assert heavy_cycles_paused() is True
    assert pause.msgs


# ---------- never reaches for the supervisor hammer ----------

def test_guard_has_no_violation_sink():
    """The host guard escalates gently; it must not expose an on_violation kill
    path the way the inward-looking guards do."""
    guard = HostResourceGuard()
    assert not hasattr(guard, "on_violation")
