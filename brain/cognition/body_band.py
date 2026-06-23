# brain/cognition/body_band.py
#
# The band-learner: the shared primitive behind Orrin's embodiment.
#
# A body does not have a single "normal" value for a vital — it has a *band* it
# oscillates within. A resting heart rate is not one number; it is a floor, a
# ceiling, and a centre the beat breathes between. Distress is not "the value is
# high" (high may be perfectly normal for this body) — it is "the value LEFT the
# band I learned," or "the band itself is marching one way and not coming back."
#
# This is the correction at the heart of the embodiment architecture
# (docs/orrin_embodiment_architecture.md §10.4): on a live, worked-on machine the
# signal never holds still, so you cannot baseline to a quiet point. You baseline
# to the *shape of the oscillation* — floor, ceiling, amplitude — and you are done
# learning when the *description* of the variance converges (new samples stop
# widening the envelope), even though the instantaneous value never settles.
#
# The same primitive serves three layers:
#   • body_sense  — Orrin's own process vitals, felt as deviation not absolute level
#   • host interoception — disk/swap/memory of the machine as his felt body
#   • infancy     — "I have seen enough of the cycle to know its bounds"
#
# Two absolute backstops live alongside the relative learning, because §10.5 /
# §10.6 forbid imprinting on a sick body: a band carries an optional danger line,
# and it REFUSES to converge (refuses to call sickness "normal") while a sample
# sits past that line. Relative learning, with an absolute refusal-to-imprint.
#
# Grounding: Sterling (2012) allostasis — regulation is to the predicted range,
# not a fixed point; Schmidt et al. on critical-period imprinting (a set point
# mis-learned in a sensitive window is far harder to overwrite later — §10.6).
from __future__ import annotations

import hashlib
import platform
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Any


def machine_fingerprint() -> str:
    """A short, stable id for *this body* (this machine). The persistent self is
    hardware-independent; the interoceptive calibration is hardware-bound and must
    be re-derived on every machine (§9). If a band file is carried to a different
    box, the fingerprint won't match and the bands are discarded and re-learned —
    which is not a hack to make him portable; that re-learning IS embodiment."""
    try:
        node = platform.node() or ""
        mach = platform.machine() or ""
        ram = ""
        try:
            import psutil
            ram = str(int(psutil.virtual_memory().total // (1024 * 1024 * 1024)))
        except Exception:
            ram = ""
        raw = f"{node}|{mach}|{ram}GB"
    except Exception:
        raw = "unknown"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class Band:
    """Online estimator of one signal's healthy oscillation envelope.

    The envelope is a [floor, ceiling] derived from PERCENTILES of a rolling window
    of recent samples (default 3rd / 97th), with the centre as the median. Using
    percentiles rather than raw min/max gives exactly the robustness §10.4 asks for:
    a rare one-off spike that returns is *breathing* and does not permanently widen
    the band, while a genuine shift in the oscillation's shape does move it.

    Convergence is the §10.4 wake condition — "I have seen enough of the cycle to
    know its bounds." Once enough samples are in AND the percentile bounds stop
    moving (relative motion < `stable_eps_frac`) for `stable_needed` consecutive
    samples, the *description* of the variance has converged, even though the
    instantaneous value never settles. A signal marching one way (the swap
    death-spiral) keeps shoving the window's percentiles along and never converges —
    correctly refusing to call a one-way climb a "learned body."
    """
    name: str

    # --- envelope shape ---
    window: int = 512               # rolling sample window the percentiles run over
    lo_pct: float = 3.0             # floor percentile
    hi_pct: float = 97.0            # ceiling percentile

    # --- convergence policy ---
    min_samples: int = 120          # never call it learned before seeing this many
    stable_needed: int = 90         # consecutive stable recomputes → converged
    stable_eps_frac: float = 0.02   # bound motion < this frac of amplitude == "stable"

    # --- absolute backstop (§10.5/§10.6): refuse to imprint on a sick body ---
    danger_high: Optional[float] = None   # a sample at/above this is "already sick"
    danger_low: Optional[float] = None    # a sample at/below this is "already sick"

    # --- learned state ---
    n: int = 0
    center: Optional[float] = None
    lo: Optional[float] = None
    hi: Optional[float] = None
    _stable_count: int = 0
    _converged: bool = False
    _recent: Deque[float] = field(default_factory=lambda: deque(maxlen=512))

    def __post_init__(self):
        if self._recent.maxlen != self.window:
            self._recent = deque(self._recent, maxlen=self.window)

    # ---------------------------------------------------------------- observe ---
    def observe(self, value: float) -> None:
        """Fold one sample into the band. Cheap; call every cycle."""
        try:
            x = float(value)
        except (TypeError, ValueError):
            return
        self.n += 1
        self._recent.append(x)

        prev_lo, prev_hi = self.lo, self.hi
        self._recompute()

        # §10.5 refuse-to-imprint: while a sample is past the danger line, the body
        # is sick; never let this get learned as "normal" — reset convergence.
        if self._is_sick(x):
            self._stable_count = 0
            self._converged = False
            return

        if prev_lo is None or prev_hi is None:
            return
        # A slow one-way ramp has tiny per-step bound motion relative to its (large,
        # ever-growing) amplitude, so a motion test alone would wrongly call it
        # "stable." Directionality is the true tell: a band that is MARCHING is not a
        # learned body, it is a body sliding toward a wall (§10.4/§10.5). Require both
        # the bounds to be still AND the signal not to be marching before converging.
        amp = max(self.hi - self.lo, 1e-9)
        moved = abs(self.lo - prev_lo) + abs(self.hi - prev_hi)
        if moved <= self.stable_eps_frac * amp and not self.marching(min_span=48, frac=0.72):
            self._stable_count += 1
            if (not self._converged and self.n >= self.min_samples
                    and self._stable_count >= self.stable_needed):
                self._converged = True
        else:
            self._stable_count = 0

    def _recompute(self) -> None:
        data = sorted(self._recent)
        k = len(data)
        if k == 1:
            self.lo = self.hi = self.center = data[0]
            return

        def pct(p: float) -> float:
            if k == 1:
                return data[0]
            idx = (p / 100.0) * (k - 1)
            lo_i = int(idx)
            frac = idx - lo_i
            hi_i = min(lo_i + 1, k - 1)
            return data[lo_i] + (data[hi_i] - data[lo_i]) * frac

        self.lo = pct(self.lo_pct)
        self.hi = pct(self.hi_pct)
        self.center = pct(50.0)

    # ------------------------------------------------------------- read-outs ---
    @property
    def converged(self) -> bool:
        """True once the envelope's description has stabilised (§10.4 wake)."""
        return self._converged

    @property
    def amplitude(self) -> float:
        if self.lo is None or self.hi is None:
            return 0.0
        return max(0.0, self.hi - self.lo)

    def _half_amp(self) -> float:
        return max(self.amplitude / 2.0, 1e-9)

    def deviation(self, value: float) -> float:
        """Signed deviation OUTSIDE the band, normalised by half-amplitude.
        0.0 anywhere inside [lo, hi] — being deep in the normal band is not a
        feeling. >0 above the ceiling (how far out, in band-widths), <0 below the
        floor. This is the §7 mapping #2 quantity: deviation → affect."""
        if self.lo is None or self.hi is None:
            return 0.0
        try:
            x = float(value)
        except (TypeError, ValueError):
            return 0.0
        if x > self.hi:
            return (x - self.hi) / self._half_amp()
        if x < self.lo:
            return (x - self.lo) / self._half_amp()
        return 0.0

    def above_band(self, value: float) -> bool:
        return self.deviation(value) > 0.0

    def below_band(self, value: float) -> bool:
        return self.deviation(value) < 0.0

    def marching(self, min_span: int = 64, frac: float = 0.85) -> bool:
        """True when the signal is climbing one way and not coming back — the swap
        death-spiral signature of 2026-06-15, as opposed to healthy breathing. A
        spike that returns is breathing; a monotone drift is the alarm (§10.4)."""
        if len(self._recent) < min_span:
            return False
        window = list(self._recent)[-min_span:]
        ups = sum(1 for a, b in zip(window, window[1:]) if b > a)
        return ups >= frac * (len(window) - 1)

    def _is_sick(self, x: float) -> bool:
        if self.danger_high is not None and x >= self.danger_high:
            return True
        if self.danger_low is not None and x <= self.danger_low:
            return True
        return False

    # ---------------------------------------------------------- persistence ---
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "window": self.window, "lo_pct": self.lo_pct, "hi_pct": self.hi_pct,
            "min_samples": self.min_samples, "stable_needed": self.stable_needed,
            "stable_eps_frac": self.stable_eps_frac,
            "danger_high": self.danger_high, "danger_low": self.danger_low,
            "n": self.n, "center": self.center, "lo": self.lo, "hi": self.hi,
            "_stable_count": self._stable_count, "_converged": self._converged,
            # Persist the window so learning resumes seamlessly across restarts
            # (a restart on the same machine is waking from sleep, not infancy — §10.1).
            "recent": list(self._recent),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Band":
        b = cls(name=str(d.get("name", "?")))
        for k in ("window", "lo_pct", "hi_pct", "min_samples", "stable_needed",
                  "stable_eps_frac", "danger_high", "danger_low", "n",
                  "center", "lo", "hi", "_stable_count", "_converged"):
            if k in d and d[k] is not None:
                setattr(b, k, d[k])
        recent = d.get("recent")
        if isinstance(recent, list):
            b._recent = deque((float(x) for x in recent), maxlen=b.window)
        return b


class BodyBands:
    """A named collection of `Band`s for one body, with per-machine persistence.

    Owns the somatic-infancy gate: the body is *in infancy* (still learning this
    machine) until every registered band has converged. While in infancy the
    cortex is lenient — felt deviation is suppressed because there is no trustworthy
    band to deviate from yet (§10.3/§10.4). The autonomic reflex (HostResourceGuard)
    is a SEPARATE system and stays absolute throughout infancy by design (§10.5) —
    nothing here touches it.

    The file is tagged with a machine fingerprint; loaded bands from a different
    machine are discarded so Orrin re-learns the new body from scratch (§9)."""

    def __init__(self, path, specs: Optional[Dict[str, Dict[str, Any]]] = None):
        self.path = path
        self._specs = specs or {}
        self.bands: Dict[str, Band] = {}
        self.fingerprint = machine_fingerprint()
        self._dirty = False

    def band(self, name: str) -> Band:
        b = self.bands.get(name)
        if b is None:
            kwargs = self._specs.get(name, {})
            b = Band(name=name, **kwargs)
            self.bands[name] = b
        return b

    def observe(self, name: str, value: float) -> None:
        self.band(name).observe(value)
        self._dirty = True

    def deviation(self, name: str, value: float) -> float:
        return self.band(name).deviation(value)

    def _expected_names(self) -> set:
        """Every band this body is expected to learn — the union of the spec'd set
        and any bands already instantiated. A spec'd band not yet created counts as
        unconverged, so infancy doesn't end before every expected vital is learned."""
        return set(self._specs) | set(self.bands)

    def in_infancy(self) -> bool:
        """Still learning this body: not every expected band has converged.
        A body with nothing to learn yet is, trivially, an infant."""
        names = self._expected_names()
        if not names:
            return True
        return not all(n in self.bands and self.bands[n].converged for n in names)

    def converged_fraction(self) -> float:
        names = self._expected_names()
        if not names:
            return 0.0
        done = sum(1.0 for n in names if n in self.bands and self.bands[n].converged)
        return done / len(names)

    # ---------------------------------------------------------- persistence ---
    def load(self) -> "BodyBands":
        try:
            from brain.utils.json_utils import load_json
            raw = load_json(self.path, default_type=dict) or {}
        except Exception:
            raw = {}
        if isinstance(raw, dict) and raw.get("fingerprint") == self.fingerprint:
            for name, bd in (raw.get("bands") or {}).items():
                try:
                    self.bands[name] = Band.from_dict(bd)
                except (KeyError, TypeError, ValueError):  # intentional: bad band dict → skip
                    pass
        # else: different machine (or empty) → start fresh; he re-learns this body.
        return self

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            from brain.utils.json_utils import save_json
            save_json(self.path, {
                "fingerprint": self.fingerprint,
                "bands": {n: b.to_dict() for n, b in self.bands.items()},
            })
            self._dirty = False
        except (OSError, TypeError, ValueError):  # intentional: band persist best-effort
            pass
