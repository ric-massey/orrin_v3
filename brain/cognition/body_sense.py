# brain/cognition/body_sense.py
# Reads process-level vitals (RSS, FD count, CPU, step latency) and translates
# them into felt-state vocabulary that Orrin can reference and that merges into
# affect_state to bias function selection.
#
# Felt states are DEVIATION-based, not absolute-level based. This is the central
# correction of the embodiment architecture (docs/orrin_embodiment_architecture.md
# §8.1, §10.4 + the Part VIII/IX audit): the old code fired "heavy" on an ABSOLUTE
# RSS > 400 MB, and with sentence-transformers + PyTorch resident Orrin's RSS is
# essentially ALWAYS above 400 MB — so "heavy" was his *resting* state. That pumped
# resource_deficit every single cycle and pinned _stress_streak (→ stress_load), so
# the whole affect substrate saturated at 1.000 and "drowning felt like breathing."
#
# The fix: learn the *band* each vital oscillates within (body_band.Band) and feel
# only DEPARTURE from that band. 85% memory or 900 MB RSS is this body's homeostasis
# and reads as nothing; a vital LEAVING its learned band is what registers. While the
# body is still learning this machine (somatic infancy — bands not yet converged),
# the cortex stays lenient and emits no stress states (§10.3/§10.4). The autonomic
# reflex (reaper/host_resources.HostResourceGuard) is a SEPARATE, absolute system and
# is untouched by any of this — the brainstem never goes lenient (§10.5).
#
# Felt states:
#   heavy    — RSS above its learned band (sustained load departing from normal)
#   spacious — RSS below its learned band, CPU idle (more room than usual)
#   strained — FD or CPU above its band, OR FD genuinely near the OS limit (absolute)
#   sluggish — step latency above its learned band (slower than THIS body's normal)
#   swelling — RSS marching one way and not retreating (the death-spiral signature)
#   clear    — all vitals inside their bands (or still in infancy)
from __future__ import annotations
from core.runtime_log import get_logger

import os
import platform
from typing import Dict, Any, List

# `resource` is POSIX-only (absent on Windows). Import it optionally so this
# module loads everywhere; psutil supplies the same numbers cross-platform.
try:
    import resource  # type: ignore
except Exception:
    resource = None  # type: ignore

from utils.json_utils import load_json, save_json
from utils.log import log_private
from paths import BODY_SENSE_FILE, DATA_DIR
from utils.failure_counter import record_failure
from cognition.body_band import BodyBands
_log = get_logger(__name__)

# Absolute backstops (NOT felt-state triggers). FD genuinely near the OS limit is
# dangerous on any machine regardless of what Orrin has learned as normal — a
# newborn can still suffocate (§10.5), so this one stays absolute even in infancy.
_FD_DANGER_PCT   = 0.92    # FD pct at/above this → strained, band or no band

# How far OUTSIDE a learned band a vital must sit before it's *felt* (in band-widths).
# A small margin keeps the relaxed-inward ceiling from making him twitchy.
_FELT_MARGIN = 0.20

# The learned oscillation envelopes for THIS body. Hardware-bound, re-learned on
# every machine (the file is fingerprinted; a copy from another box is discarded).
# Lazily loaded so import stays cheap and test harnesses can repoint DATA_DIR.
_BAND_SPECS = {
    # RSS climbs as caches warm then holds; give convergence room before trusting it.
    "rss_mb":     {"min_samples": 120, "stable_needed": 90},
    "cpu_util":   {"min_samples": 80,  "stable_needed": 60},
    "fd_pct":     {"min_samples": 80,  "stable_needed": 60},
    "latency_ms": {"min_samples": 80,  "stable_needed": 60},
}

# Per-phase bands (§3.2 SL2). A body defends a DIFFERENT normal asleep than awake
# (Sterling 2012 — set-points are state-dependent). Dreaming legitimately spikes
# Orrin's own RSS/CPU above the idle band because it runs the heavy LLM/replay
# consolidation; against ONE band (dominated by idle samples) that spike reads as
# "heavy"/"swelling" and pumps resource_deficit UP, fighting the dream's own
# recovery nudge — the cycle meant to lower fatigue raises it. The fix is a
# SEPARATE sleep-phase band, learned only from dream-phase samples, so the dream's
# spike reads as normal-for-sleeping. Same convergence policy; learned per-machine.
_WAKE_BANDS_FILE  = "body_bands.json"
_DREAM_BANDS_FILE = "body_bands_dream.json"
_bands: BodyBands | None = None          # wake-phase envelope
_dream_bands: BodyBands | None = None    # sleep-phase envelope


def _is_dreaming() -> bool:
    """True while a dream cycle is in flight. Lazy + fail-safe: if the dream module
    can't be reached we treat it as awake (the conservative direction — the wake
    band still alarms on departure)."""
    try:
        from cognition.dreaming.dream_cycle import dreaming_now
        return bool(dreaming_now())
    except Exception:
        return False


def _get_bands(dreaming: bool = False) -> BodyBands:
    """Return the active phase's band set, loading it on first use."""
    global _bands, _dream_bands
    if dreaming:
        if _dream_bands is None:
            _dream_bands = BodyBands(DATA_DIR / _DREAM_BANDS_FILE, specs=_BAND_SPECS).load()
        return _dream_bands
    if _bands is None:
        _bands = BodyBands(DATA_DIR / _WAKE_BANDS_FILE, specs=_BAND_SPECS).load()
    return _bands


def reset_bands_for_resize(reason: str = "") -> None:
    """A budget resize enlarges/shrinks the body, so the learned band is now wrong —
    re-enter a PARTIAL somatic infancy and re-learn this body's normal (§11.4.2).
    Drops BOTH learned band sets (wake and sleep — the resize changes the body in
    every phase) and their on-disk files; in_infancy() goes true again and the
    cortex stays lenient until the new envelopes converge. The autonomic reflex is
    unaffected — it was always absolute and never went lenient (§10.5)."""
    global _bands, _dream_bands
    for fname in (_WAKE_BANDS_FILE, _DREAM_BANDS_FILE):
        try:
            (DATA_DIR / fname).unlink(missing_ok=True)
        except Exception:
            pass
    _bands = BodyBands(DATA_DIR / _WAKE_BANDS_FILE, specs=_BAND_SPECS)
    _dream_bands = BodyBands(DATA_DIR / _DREAM_BANDS_FILE, specs=_BAND_SPECS)
    log_private(f"[body_sense] re-baselining body after resize ({reason}) — partial infancy")


def read_vitals() -> Dict[str, float]:
    """Read raw process vitals. Returns dict with rss_mb, fd_pct, cpu_util, latency_ms."""
    vitals: Dict[str, float] = {}

    # RSS via resource module (POSIX fallback when psutil is unavailable)
    try:
        if resource is not None:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # ru_maxrss is bytes on Linux, pages on macOS → normalise to MB
            if platform.system() == "Darwin":
                vitals["rss_mb"] = usage.ru_maxrss / (1024 * 1024)
            else:
                vitals["rss_mb"] = usage.ru_maxrss / 1024.0
        else:
            vitals["rss_mb"] = 0.0
    except Exception:
        vitals["rss_mb"] = 0.0

    # Try psutil for richer data if available
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        vitals["rss_mb"] = proc.memory_info().rss / (1024 * 1024)
        vitals["cpu_util"] = proc.cpu_percent(interval=0.1) / 100.0
        # FD count — num_fds() on POSIX, num_handles() on Windows
        try:
            if hasattr(proc, "num_fds"):
                fd_open = proc.num_fds()
                fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0] if resource is not None else 1024
            else:  # Windows: no fd table, use handle count against a nominal ceiling
                fd_open = proc.num_handles()
                fd_limit = 10000
            vitals["fd_pct"] = fd_open / max(fd_limit, 1)
        except Exception:
            vitals["fd_pct"] = 0.0
    except ImportError:
        vitals.setdefault("cpu_util", 0.0)
        vitals.setdefault("fd_pct", 0.0)
    except Exception:
        vitals.setdefault("cpu_util", 0.0)
        vitals.setdefault("fd_pct", 0.0)

    return vitals


def compute_body_states(vitals: Dict[str, float]) -> List[str]:
    """Translate raw vitals into body-state vocabulary, felt as DEPARTURE from each
    vital's learned band rather than from an absolute threshold (§8.1/§10.4).

    Observes the vitals into the bands as a side effect (this is how he learns the
    body). While still in somatic infancy — bands not yet converged — the cortex is
    lenient: it emits only the absolute FD-exhaustion backstop and otherwise "clear",
    because there is no trustworthy band to deviate from yet (§10.3). A vital climbing
    one way and never retreating ("swelling") is the death-spiral signature and is
    alarmed even though a spike that returns is just breathing.

    Phase-aware (§3.2 SL2): during a dream the vitals are observed into, and
    measured against, a SEPARATE sleep-phase band, so the dream's own heavy
    consolidation reads as normal-for-sleeping rather than as distress."""
    dreaming = _is_dreaming()
    bands = _get_bands(dreaming)

    rss    = vitals.get("rss_mb", 0.0)
    cpu    = vitals.get("cpu_util", 0.0)
    fd_pct = vitals.get("fd_pct", 0.0)
    lat    = vitals.get("latency_ms", 0.0)

    # Learn the body: fold this cycle's sample into every band.
    bands.observe("rss_mb", rss)
    bands.observe("cpu_util", cpu)
    bands.observe("fd_pct", fd_pct)
    if lat > 0.0:
        bands.observe("latency_ms", lat)

    states: List[str] = []

    # Absolute FD-exhaustion backstop — fires regardless of band/infancy (§10.5).
    if fd_pct >= _FD_DANGER_PCT:
        states.append("strained")

    # In somatic infancy the felt body is not yet calibrated: stay lenient.
    if bands.in_infancy():
        if not states:
            states.append("clear")
        return states

    rss_b = bands.band("rss_mb")

    # heavy / spacious — RSS departing above / below its learned band.
    if rss_b.deviation(rss) > _FELT_MARGIN:
        states.append("heavy")
    elif rss_b.deviation(rss) < -_FELT_MARGIN and cpu < 0.3:
        states.append("spacious")

    # strained — FD or CPU above its band (relative to THIS body's normal).
    if (bands.deviation("fd_pct", fd_pct) > _FELT_MARGIN
            or bands.deviation("cpu_util", cpu) > _FELT_MARGIN) and "strained" not in states:
        states.append("strained")

    # sluggish — a cycle slower than this body's learned normal.
    if lat > 0.0 and bands.deviation("latency_ms", lat) > _FELT_MARGIN:
        states.append("sluggish")

    # swelling — RSS marching one way and not coming back (death-spiral, not breathing).
    if rss_b.marching():
        states.append("swelling")

    if not states:
        states.append("clear")

    return states


def interoceptive_deltas(body_states: List[str], affect_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate body state into emotion deltas — body state IS a generative source of
    emotion, not a downstream correlate (Damasio 1994 somatic marker hypothesis;
    Craig 2003 interoception as the substrate of subjective feeling).

    These deltas are applied BEFORE appraisal and trigger processing so the body
    state acts as a prior that shapes how incoming events are interpreted — exactly
    how the insula and anterior cingulate cortex bias affective processing.

    States and their grounding:
      heavy    — sustained load; maps to heaviness/drag (Craig 2003: low-energy interoceptive signals)
      strained — acute resource threat; threat_detector-level threat response (LeDoux 1996)
      swelling — uncontrolled growth; generates urgency/risk_estimate (unpredictable body signal)
      sluggish — temporal dislocation; cycle taking longer than expected creates vague
                 "something is wrong" risk_estimate — interoceptive prediction error (Friston 2010)
      spacious — ease and resource availability; promotes exploratory openness (Fredrickson 2001)
      clear    — nominal; gentle positive prior, reduces resource_deficit accumulation
    """
    core = affect_state.get("core_signals") or affect_state

    def _nudge(key: str, delta: float) -> None:
        current = float(core.get(key, 0.0) or 0.0)
        core[key] = max(0.0, min(1.0, current + delta))

    def _resource_deficit(delta: float) -> None:
        affect_state["resource_deficit"] = max(0.0, min(1.0,
            float(affect_state.get("resource_deficit", 0.1) or 0.1) + delta))

    if "heavy" in body_states:
        _nudge("impasse_signal", +0.06)
        _nudge("motivation",  -0.04)   # heaviness saps drive
        _resource_deficit(+0.05)

    if "swelling" in body_states:
        # RSS accelerating → urgency, things feel out of control
        _nudge("risk_estimate",     +0.07)
        _nudge("uncertainty", +0.05)
        _resource_deficit(+0.04)

    if "strained" in body_states:
        # Acute resource pressure → threat_detector threat signal
        _nudge("impasse_signal", +0.08)
        _nudge("risk_estimate",     +0.06)
        _nudge("threat_level",        +0.04)
        _resource_deficit(+0.07)

    if "sluggish" in body_states:
        # Cycle slower than expected → interoceptive prediction error, vague unease
        _nudge("uncertainty", +0.07)
        _nudge("risk_estimate",     +0.04)
        _resource_deficit(+0.04)

    if "spacious" in body_states:
        # Low resource pressure → body ease promotes exploration (Fredrickson broaden-and-build)
        _nudge("exploration_drive",   +0.04)
        _nudge("confidence",  +0.03)
        _nudge("motivation",  +0.02)
        _resource_deficit(-0.03)

    if "clear" in body_states:
        _nudge("exploration_drive",   +0.02)
        _resource_deficit(-0.02)

    if "core_signals" in affect_state:
        affect_state["core_signals"] = core
    else:
        affect_state.update(core)

    return affect_state


def merge_into_affect_state(body_states: List[str], affect_state: Dict[str, Any]) -> Dict[str, Any]:
    """Alias kept for call-site compatibility. Delegates to interoceptive_deltas."""
    return interoceptive_deltas(body_states, affect_state)


_STRESS_STATES = {"heavy", "strained", "swelling", "sluggish"}
_PATTERN_THRESHOLD = 5   # consecutive stressed readings before writing to long_memory
_PATTERN_WRITE_EVERY = 20  # re-write pattern note every N stressed readings after first


def _update_body_pattern(felt: List[str], body_sense: Dict) -> None:
    """
    Track consecutive stressed readings and write to long_memory when a
    pattern persists, so Orrin can notice 'I've been running hot' over time.
    """
    is_stressed = bool(set(felt) & _STRESS_STATES)
    dominant    = felt[0] if felt else "clear"

    streak      = int(body_sense.get("_stress_streak", 0))
    streak      = min(1000, streak + 1) if is_stressed else 0  # cap at 1000, reset on clear
    body_sense["_stress_streak"] = streak

    # Write to long_memory only at the START of a stress episode and at 100-cycle milestones.
    # (was every 20 cycles — at 10K cycles this floods long_memory with ~500 duplicate entries)
    if streak > 0:
        should_write = (streak == _PATTERN_THRESHOLD) or (streak % 100 == 0 and streak > _PATTERN_THRESHOLD)
        if should_write:
            try:
                from cog_memory.long_memory import update_long_memory
                update_long_memory(
                    f"[body_sense_pattern] Feeling '{dominant}' for {streak} consecutive readings. "
                    f"This may indicate sustained resource pressure or inefficiency.",
                    emotion="discomfort",
                    event_type="body_sense_pattern",
                    importance=3,
                )
                log_private(f"[body_sense] pattern written — streak={streak} dominant={dominant}")
            except Exception as _e:
                record_failure("body_sense._update_body_pattern", _e)


def update_body_sense(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point: read vitals, compute felt states, merge into context.
    Writes body_sense to context and persists to BODY_SENSE_FILE.
    Returns the body_sense dict.
    """
    vitals = read_vitals()
    felt   = compute_body_states(vitals)

    # Load prior body_sense to carry streak counter forward
    try:
        prior = load_json(BODY_SENSE_FILE, default_type=dict) or {}
    except Exception:
        prior = {}

    dreaming = _is_dreaming()
    bands = _get_bands(dreaming)   # the phase compute_body_states just observed into
    body_sense = {
        "body_states": felt,
        "vitals": vitals,
        "dominant": felt[0] if felt else "clear",
        "_stress_streak": prior.get("_stress_streak", 0),
        # Which felt-body phase is active — wake vs. the dream-phase band (SL2).
        "phase": "sleep" if dreaming else "wake",
        # Somatic-infancy telemetry: is he still learning this body, and how far in.
        # Phase-specific: the sleep band converges separately from the wake band.
        "somatic_infancy": bands.in_infancy(),
        "body_converged": round(bands.converged_fraction(), 3),
    }

    _update_body_pattern(felt, body_sense)

    context["body_sense"] = body_sense

    # Merge into affect_state
    emo = context.get("affect_state") or {}
    context["affect_state"] = merge_into_affect_state(felt, emo)

    try:
        save_json(BODY_SENSE_FILE, body_sense)
    except Exception as _e:
        record_failure("body_sense.update_body_sense", _e)

    # Persist the learned bands (cheap; only writes when a band changed).
    try:
        bands.save()
    except Exception as _e:
        record_failure("body_sense.save_bands", _e)

    log_private(
        f"[body_sense] {felt} rss={vitals.get('rss_mb',0):.0f}MB cpu={vitals.get('cpu_util',0):.1%} "
        f"{'infant' if body_sense['somatic_infancy'] else 'calibrated'} "
        f"({body_sense['body_converged']:.0%})"
    )
    return body_sense


def body_sense_voice_hint(context: Dict[str, Any]) -> str:
    """
    Returns a short vocabulary hint that speak.py can use to color voice.
    e.g. 'heavy' → 'effortful', 'clear' → '' (no modifier)
    """
    bs = context.get("body_sense") or {}
    dominant = bs.get("dominant", "clear")
    return {
        "heavy":    "effortful",
        "strained": "terse",
        "sluggish": "halting",
        "swelling": "pressured",
        "spacious": "open",
        "clear":    "",
    }.get(dominant, "")
