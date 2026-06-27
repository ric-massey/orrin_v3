# supervisor/host_resources.py
# Host-machine resource watchdog. Sibling to MemoryHealthGuard, but it looks
# OUTWARD at the box Orrin runs on instead of inward at Orrin.
#
# Every other guard in the supervisor suite watches the patient's vitals — heartbeat,
# RSS, goals, the memory subsystem. This one watches whether the building the
# patient is in is on fire: the host's free disk, swap depth, and system-wide
# memory pressure. That host layer was the blind spot that ambushed the process
# when the SSD filled (free disk is the lagging indicator; rising swap is the
# leading one).
#
# Crucially it escalates GENTLY instead of reaching for the supervisor's hammer.
# Killing Orrin does not reclaim swap that browser tabs filled, so "kill Orrin"
# is the wrong response here. Instead:
#   • soft line crossed  → WARN  (log + dashboard flag), nothing paused
#   • hard line crossed  → PAUSE the heavy, memory-hungry cycles (dream + reading)
# That buys time to reboot on your terms rather than getting ambushed, and the
# gate auto-resumes once the host recovers past the soft line again (hysteresis).
# Dream is still restorative in Orrin's felt body; this pause is only about the
# RAM/swap/disk footprint of consolidation under external host pressure.
from __future__ import annotations
from brain.core.runtime_log import get_logger
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional, Tuple
from collections import deque
from .trend import trim, window_ok, slope
import threading
import time

# Optional metrics (safe if missing)
try:
    from observability.metrics import errors_total
except Exception:
    errors_total = None  # type: ignore[assignment]

_log = get_logger(__name__)

_GB = float(1024 * 1024 * 1024)

# ---------------------------------------------------------------------------
# Process-local "pause heavy cycles" gate.
#
# The guard runs in the watchdog thread; the cognitive loop (brain/ORRIN_loop.py)
# reads this gate before launching a dream or a reading bout. Decoupled through a
# module-level flag so the loop never needs a handle on the guard instance — same
# spirit as utils/runtime_ctx's process-local context store.
# ---------------------------------------------------------------------------
_pause_lock = threading.Lock()
_heavy_paused = False
_heavy_reason = ""


def set_heavy_cycles_paused(paused: bool, reason: str = "") -> None:
    """Flip the gate that throttles dream/reading. Called by HostResourceGuard."""
    global _heavy_paused, _heavy_reason
    with _pause_lock:
        _heavy_paused = bool(paused)
        _heavy_reason = reason or ""


def heavy_cycles_paused() -> bool:
    """True when host pressure has paused the heavy, memory-hungry cycles."""
    with _pause_lock:
        return _heavy_paused


def heavy_pause_reason() -> str:
    """Human-readable reason the heavy cycles are paused (empty if running)."""
    with _pause_lock:
        return _heavy_reason


OnEvent = Callable[[str], None]
NowFn = Callable[[], float]

GetDiskFreeBytes = Callable[[], float]   # psutil.disk_usage('/').free
GetSwapUsedBytes = Callable[[], float]   # psutil.swap_memory().used
GetVmemPercent = Callable[[], float]     # psutil.virtual_memory().percent (0..100)


@dataclass
class HostResourceGuard:
    """
    Host-machine resource watchdog with staged, NON-fatal escalation.

    Samples three things the OS exposes through psutil and tracks them on rolling
    windows (so a transient spike never flips the gate):

      1) Free disk space — the lagging indicator. The absolute floor below which
         the host is about to wedge; the one that would have caught the crash
         days early.
      2) Swap used / swap growth — the LEADING indicator. Rising swap precedes
         the disk filling, so a steep swap slope warns before any floor is hit.
      3) System-wide memory pressure — virtual_memory().percent for the WHOLE
         machine (tabs included), not Orrin's RSS.

    Escalation levels (worst across all three signals wins):
      NORMAL → nothing.
      WARN   → on_warn() fires (log + dashboard flag). Heavy cycles keep running.
      PAUSE  → heavy cycles (dream + reading) are paused via the module gate and
               on_pause() fires. Auto-resumes (on_resume) when the host recovers
               back past the soft lines.

    Note the deliberate band between the warn and pause lines (warn floor > pause
    floor for disk; warn% < pause% for memory): leaving PAUSE requires recovering
    past the warn line, not merely back over the pause line, so it cannot flap on
    the boundary.
    """
    NORMAL = 0
    WARN = 1
    PAUSE = 2

    # ---- staged escalation callbacks (all optional; logging/dashboard only) ----
    on_warn: Optional[OnEvent] = None     # soft line crossed
    on_pause: Optional[OnEvent] = None    # hard line crossed → heavy cycles paused
    on_resume: Optional[OnEvent] = None   # host recovered → heavy cycles resumed

    now_fn: NowFn = time.monotonic

    # ---- providers (pass the ones you can measure; psutil-backed in main) ----
    get_disk_free_bytes: Optional[GetDiskFreeBytes] = None
    get_swap_used_bytes: Optional[GetSwapUsedBytes] = None
    get_vmem_percent: Optional[GetVmemPercent] = None

    # ---- disk thresholds (warn floor must sit ABOVE the pause floor) ----
    disk_warn_free_bytes: float = 20.0 * _GB   # soft line: start warning
    disk_pause_free_bytes: float = 10.0 * _GB  # hard line: pause heavy cycles
    disk_sustain_s: float = 10.0               # disk doesn't jitter; short window

    # ---- swap thresholds ----
    swap_warn_used_bytes: float = 2.0 * _GB
    swap_pause_used_bytes: float = 4.0 * _GB
    swap_growth_warn_bytes_per_s: float = 5.0 * 1024 * 1024  # 5 MB/s rising → warn
    swap_sustain_s: float = 20.0

    # ---- system-wide memory pressure thresholds ----
    vmem_warn_percent: float = 85.0
    vmem_pause_percent: float = 95.0
    vmem_sustain_s: float = 15.0

    # ---- internal rolling buffers (t, value) ----
    _disk_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=2048))
    _swap_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=2048))
    _vmem_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=2048))

    _level: int = NORMAL

    def step(self) -> None:
        """Call periodically from the watchdog thread."""
        now = self.now_fn()

        if self.get_disk_free_bytes:
            try:
                self._disk_samples.append((now, float(self.get_disk_free_bytes())))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        if self.get_swap_used_bytes:
            try:
                self._swap_samples.append((now, float(self.get_swap_used_bytes())))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        if self.get_vmem_percent:
            try:
                self._vmem_samples.append((now, float(self.get_vmem_percent())))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        # Worst signal wins; collect the reasons that justify the level.
        reasons: list[str] = []
        level = self.NORMAL

        dl, dr = self._disk_level(now)
        level = max(level, dl)
        if dr:
            reasons.append(dr)

        sl, sr = self._swap_level(now)
        level = max(level, sl)
        if sr:
            reasons.append(sr)

        vl, vr = self._vmem_level(now)
        level = max(level, vl)
        if vr:
            reasons.append(vr)

        self._apply_level(level, reasons)

    # ------------------- per-signal level evaluation -------------------

    def _disk_level(self, now: float) -> Tuple[int, str]:
        if not self._disk_samples:
            return self.NORMAL, ""
        trim(self._disk_samples, now - self.disk_sustain_s)
        if not window_ok(self._disk_samples, self.disk_sustain_s):
            return self.NORMAL, ""
        vals = [v for _, v in self._disk_samples]
        last = vals[-1]
        if all(v < self.disk_pause_free_bytes for v in vals):
            return self.PAUSE, (f"disk_free={last / _GB:.1f}GB < pause_floor="
                                f"{self.disk_pause_free_bytes / _GB:.1f}GB")
        if all(v < self.disk_warn_free_bytes for v in vals):
            return self.WARN, (f"disk_free={last / _GB:.1f}GB < warn_floor="
                               f"{self.disk_warn_free_bytes / _GB:.1f}GB")
        return self.NORMAL, ""

    def _swap_level(self, now: float) -> Tuple[int, str]:
        if not self._swap_samples:
            return self.NORMAL, ""
        trim(self._swap_samples, now - self.swap_sustain_s)
        if not window_ok(self._swap_samples, self.swap_sustain_s):
            return self.NORMAL, ""
        vals = [v for _, v in self._swap_samples]
        last = vals[-1]
        if all(v > self.swap_pause_used_bytes for v in vals):
            return self.PAUSE, (f"swap_used={last / _GB:.1f}GB > pause="
                                f"{self.swap_pause_used_bytes / _GB:.1f}GB")
        swap_slope = slope(self._swap_samples) or 0.0  # bytes/sec
        if all(v > self.swap_warn_used_bytes for v in vals):
            return self.WARN, (f"swap_used={last / _GB:.1f}GB > warn="
                               f"{self.swap_warn_used_bytes / _GB:.1f}GB")
        if swap_slope > self.swap_growth_warn_bytes_per_s:
            return self.WARN, (f"swap_growth={swap_slope / (1024 * 1024):.1f}MB/s > "
                               f"{self.swap_growth_warn_bytes_per_s / (1024 * 1024):.1f}MB/s")
        return self.NORMAL, ""

    def _vmem_level(self, now: float) -> Tuple[int, str]:
        if not self._vmem_samples:
            return self.NORMAL, ""
        trim(self._vmem_samples, now - self.vmem_sustain_s)
        if not window_ok(self._vmem_samples, self.vmem_sustain_s):
            return self.NORMAL, ""
        vals = [v for _, v in self._vmem_samples]
        last = vals[-1]
        if all(v > self.vmem_pause_percent for v in vals):
            return self.PAUSE, f"vmem={last:.0f}% > pause={self.vmem_pause_percent:.0f}%"
        if all(v > self.vmem_warn_percent for v in vals):
            return self.WARN, f"vmem={last:.0f}% > warn={self.vmem_warn_percent:.0f}%"
        return self.NORMAL, ""

    # ------------------- staged escalation -------------------

    def _apply_level(self, level: int, reasons: list[str]) -> None:
        prev = self._level
        if level == prev:
            return
        detail = "; ".join(reasons) or "host resources"

        # The pause gate is STICKY through the WARN band: it trips at PAUSE and
        # clears only on a full return to NORMAL (recovery past the soft line).
        # That gives a real hysteresis band so it can't flap on the hard line,
        # while NORMAL→WARN on the way up still leaves heavies running.
        was_paused = heavy_cycles_paused()
        if level >= self.PAUSE:
            now_paused = True
        elif level == self.NORMAL:
            now_paused = False
        else:  # WARN: keep whatever the gate already was
            now_paused = was_paused

        gate_changed = now_paused != was_paused
        if gate_changed:
            set_heavy_cycles_paused(now_paused, detail)

        if gate_changed and now_paused:
            self._bump("HOST:pause_heavy", severity="2")
            self._fire(self.on_pause, f"HOST:pause_heavy {detail}")

        if level == self.WARN and prev == self.NORMAL:
            self._bump("HOST:warn", severity="3")
            self._fire(self.on_warn, f"HOST:warn {detail}")

        if gate_changed and not now_paused:
            self._fire(self.on_resume, f"HOST:resume_heavy {detail}")
        elif level == self.NORMAL and prev == self.WARN:
            self._fire(self.on_resume, f"HOST:recovered {detail}")

        self._level = level

    # ------------------- helpers -------------------

    @staticmethod
    def _fire(cb: Optional[OnEvent], msg: str) -> None:
        if cb is None:
            return
        try:
            cb(msg)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    @staticmethod
    def _bump(key: str, severity: str) -> None:
        if errors_total is None:
            return
        try:
            errors_total.labels(key=key, severity=severity).inc()
        except Exception as _e:
            _log.warning("silent except: %s", _e)
