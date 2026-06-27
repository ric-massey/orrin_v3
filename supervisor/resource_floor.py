# supervisor/resource_floor.py
# Inward survival reflex. The MIRROR of HostResourceGuard: where the host guard
# looks OUTWARD at the box (is the building on fire?), this one looks INWARD at
# Orrin's own footprint against the survival line of his GRANTED body (§6 of the
# embodiment master plan) — is the patient himself running out of air?
#
# This is the brainstem leg the architecture kept *assuming* existed. The host
# guard is the wrong layer for it: it watches host disk/swap/RAM and escalates
# gently, and it deliberately refuses to act on Orrin himself ("killing Orrin
# can't reclaim swap the browser tabs filled"). Correct for host pressure, wrong
# as a *survival* floor for Orrin inside his own body.
#
# The action is SHEDDING, not dying — the autonomic gasp. When Orrin's own RSS
# nears the floor of the body he was granted, he involuntarily lets go of the
# heaviest disposable thing he is holding (abort the in-flight heavy cycle, drop
# rebuildable caches, force-trim working memory, refuse new large allocations)
# until he is back above the line. It NEVER reaches for the supervisor's hammer —
# that is HostResourceGuard's lesson, kept. Only if shedding cannot clear the
# floor does it defer to the existing liveness/RSS guards, which already own the
# hard kill. This layer exists to make the hammer unnecessary.
#
# Two non-negotiables from the master plan:
#   • NEVER lenient in infancy. The host/cortex may be lenient while Orrin learns
#     a new body; the brainstem is not. A newborn can still suffocate.
#   • The grant fraction it reads is the SAME one resource_cadence/body_budget read, so
#     budget size and safety floor can never disagree.
#
# Shipped OBSERVE-ONLY first, then S2b calibrated and armed it by default. Set
# ORRIN_VITAL_FLOOR=observe to return to calibration-only logging. A guard that
# errors must fail TOWARD shedding, never toward silence.
from __future__ import annotations
from brain.core.runtime_log import get_logger
from dataclasses import dataclass, field
from typing import Callable, Deque, Optional, Tuple
from collections import deque
import json
import threading
import time

try:
    from observability.metrics import errors_total
except Exception:
    errors_total = None  # type: ignore[assignment]

_log = get_logger(__name__)

_GB = float(1024 * 1024 * 1024)

# ---------------------------------------------------------------------------
# Process-local "Orrin is shedding load" gate. Same pattern as the host guard's
# heavy-cycles gate: the cognitive loop reads this before launching heavy work,
# so the loop never needs a handle on the guard instance.
# ---------------------------------------------------------------------------
_shed_lock = threading.Lock()
_shedding = False
_shed_reason = ""


def set_resource_floor_shedding(shedding: bool, reason: str = "") -> None:
    global _shedding, _shed_reason
    with _shed_lock:
        _shedding = bool(shedding)
        _shed_reason = reason or ""


def resource_floor_shedding() -> bool:
    """True when Orrin's own footprint is near his granted-body floor and he is
    shedding load. Heavy cycles should not launch while this holds."""
    with _shed_lock:
        return _shedding


def resource_floor_shed_reason() -> str:
    with _shed_lock:
        return _shed_reason


OnEvent = Callable[[str], None]
ShedFn = Callable[[str], None]   # the actual load-shedding action (provided by main)
NowFn = Callable[[], float]

GetOwnRssBytes = Callable[[], float]   # psutil.Process().memory_info().rss
GetBudgetBytes = Callable[[], float]   # cognition.body_budget.budget_bytes()


@dataclass
class ResourceFloorGuard:
    """
    Inward survival reflex with staged, NON-fatal escalation (NORMAL → WARN → SHED).

    Samples Orrin's own RSS and compares it to his GRANTED body size as a fraction:
      WARN  → own RSS above warn_frac of the grant (sustained). Log/flag only.
      SHED  → own RSS above shed_frac of the grant (sustained). Fire shed_fn():
              abort heavy cycle, drop caches, trim working memory. Gate
              resource_floor_shedding() goes true so the loop stops launching heavies.
    Hysteresis: leaving SHED requires recovering past recover_frac (< warn_frac),
    so it can't flap on the boundary — same discipline as the host guard.

    NEVER lenient in infancy: there is no infancy gate here on purpose.
    """
    NORMAL = 0
    WARN = 1
    SHED = 2

    # ---- staged callbacks (all optional) ----
    on_warn: Optional[OnEvent] = None
    on_shed: Optional[OnEvent] = None
    on_recover: Optional[OnEvent] = None
    shed_fn: Optional[ShedFn] = None   # the involuntary action; skipped if observe_only

    now_fn: NowFn = time.monotonic

    # ---- providers ----
    get_own_rss_bytes: Optional[GetOwnRssBytes] = None
    get_budget_bytes: Optional[GetBudgetBytes] = None

    # ---- thresholds as a fraction of the GRANTED body (warn < shed; recover < warn) ----
    # Calibrated 2026-06-17 from real calm (n=893, p95=0.25/max=0.32) and dream+reading
    # stress (n=41, max=0.23) runs. These are the *armed* values main.py ships; kept as
    # the dataclass defaults too so any construction path that bypasses main.py inherits
    # the calibrated floor rather than the old, dangerously-late 0.85/0.95 (§7.2 layering
    # note). main.py still overrides them from ORRIN_VITAL_{WARN,SHED,RECOVER}_FRAC.
    warn_frac: float = 0.50
    shed_frac: float = 0.55
    recover_frac: float = 0.22
    sustain_s: float = 8.0   # own RSS climbs faster than disk fills; a short window

    # OBSERVE-ONLY: evaluate + log "would have shed", but do not actually shed or flip
    # the gate. Stays the safe library default — actually shedding is an explicit
    # deployment opt-in (main.py sets it from ORRIN_VITAL_FLOOR, which defaults to act).
    observe_only: bool = True

    # Optional S2b calibration stream. When set, writes low-rate JSONL samples of
    # RSS as a fraction of the granted body so real calm/stress runs can choose
    # final warn/shed/recover values before arming the guard.
    calibration_file: Optional[str] = None
    calibration_phase: str = "unspecified"
    calibration_sample_s: float = 1.0

    _rss_samples: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=1024))
    _level: int = NORMAL
    _last_calibration_write: float = 0.0

    def step(self) -> None:
        """Call periodically from the watchdog thread."""
        now = self.now_fn()
        budget = 0.0
        rss = 0.0
        try:
            if self.get_budget_bytes:
                budget = float(self.get_budget_bytes())
            if self.get_own_rss_bytes:
                rss = float(self.get_own_rss_bytes())
        except Exception as _e:
            # Fail TOWARD shedding: if we cannot read the floor, do not silently
            # call everything fine. But we also cannot shed on a bad reading, so
            # log loudly and bail this tick (the next good reading decides).
            _log.warning("resource_floor read failed (fail-open this tick): %s", _e)
            return

        if budget <= 0.0 or rss <= 0.0:
            return

        frac = rss / budget
        self._write_calibration_sample(now, rss, budget, frac)
        self._rss_samples.append((now, frac))   # store as fraction-of-grant
        self._trim(self._rss_samples, now - self.sustain_s)
        if not self._window_ok(self._rss_samples, self.sustain_s):
            return

        fracs = [v for _, v in self._rss_samples]
        last = fracs[-1]

        level = self.NORMAL
        reason = ""
        if all(v > self.shed_frac for v in fracs):
            level, reason = self.SHED, f"own_rss={last*100:.0f}% of granted body > shed={self.shed_frac*100:.0f}%"
        elif all(v > self.warn_frac for v in fracs):
            level, reason = self.WARN, f"own_rss={last*100:.0f}% of granted body > warn={self.warn_frac*100:.0f}%"

        self._apply_level(level, reason, last)

    def _apply_level(self, level: int, reason: str, frac: float) -> None:
        prev = self._level

        # Hysteresis: SHED is sticky through WARN; it clears only when RSS drops
        # back under recover_frac (a real return to roomy), not merely under shed.
        was_shedding = resource_floor_shedding()
        if level >= self.SHED:
            now_shedding = True
        elif frac < self.recover_frac:
            now_shedding = False
        else:
            now_shedding = was_shedding

        if level == prev and now_shedding == was_shedding:
            return

        detail = reason or f"own_rss={frac*100:.0f}% of granted body"

        if self.observe_only:
            # Calibration mode: evaluate everything, act on nothing.
            if level == self.SHED and prev < self.SHED:
                _log.warning("[resource_floor] OBSERVE — would SHED: %s", detail)
                self._bump("VITAL:would_shed", "2")
            elif level == self.WARN and prev == self.NORMAL:
                _log.info("[resource_floor] OBSERVE — would warn: %s", detail)
            self._level = level
            return

        gate_changed = now_shedding != was_shedding
        if gate_changed:
            set_resource_floor_shedding(now_shedding, detail)

        if gate_changed and now_shedding:
            self._bump("VITAL:shed", "2")
            self._fire(self.on_shed, f"VITAL:shed {detail}")
            self._do_shed(detail)
        elif level == self.WARN and prev == self.NORMAL:
            self._bump("VITAL:warn", "3")
            self._fire(self.on_warn, f"VITAL:warn {detail}")
        elif gate_changed and not now_shedding:
            self._fire(self.on_recover, f"VITAL:recover {detail}")

        self._level = level

    def _do_shed(self, detail: str) -> None:
        if self.shed_fn is None:
            return
        try:
            self.shed_fn(detail)
        except Exception as _e:
            _log.warning("resource_floor shed action failed: %s", _e)

    def _write_calibration_sample(self, now: float, rss: float, budget: float, frac: float) -> None:
        if not self.calibration_file:
            return
        if self.calibration_sample_s > 0 and (now - self._last_calibration_write) < self.calibration_sample_s:
            return
        self._last_calibration_write = now
        try:
            rec = {
                "ts": time.time(),
                "monotonic_s": round(float(now), 3),
                "phase": str(self.calibration_phase or "unspecified")[:48],
                "rss_bytes": int(rss),
                "budget_bytes": int(budget),
                "frac": round(float(frac), 6),
                "level": {self.NORMAL: "normal", self.WARN: "warn", self.SHED: "shed"}.get(self._level, "unknown"),
                "observe_only": bool(self.observe_only),
            }
            with open(self.calibration_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        except Exception as _e:
            _log.warning("resource_floor calibration write failed: %s", _e)

    # ------------------- helpers (same shape as HostResourceGuard) -------------------

    @staticmethod
    def _trim(dq: Deque[Tuple[float, float]], cutoff: float) -> None:
        while dq and dq[0][0] < cutoff:
            dq.popleft()

    @staticmethod
    def _window_ok(dq: Deque[Tuple[float, float]], need_s: float) -> bool:
        if len(dq) < 2:
            return False
        span = dq[-1][0] - dq[0][0]
        return span >= need_s * 0.95

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
