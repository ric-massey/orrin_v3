# brain/cognition/body_sense.py
# Reads process-level vitals (RSS, FD count, CPU, step latency) and translates
# them into felt-state vocabulary that Orrin can reference and that merges into
# affect_state to bias function selection.
#
# Felt states:
#   heavy    — RSS high and climbing
#   spacious — RSS low, CPU idle
#   strained — FD count near ceiling or CPU sustained high
#   sluggish — step latency high relative to baseline
#   swelling — RSS slope positive and accelerating
#   clear    — all vitals nominal
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
from paths import BODY_SENSE_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# Thresholds (tuneable)
_RSS_HEAVY_MB    = 400.0   # above this → heavy
_RSS_SPACIOUS_MB = 150.0   # below this → spacious candidate
_FD_STRAIN_PCT   = 0.75    # FD pct above this → strained
_CPU_STRAIN_PCT  = 0.80    # CPU util above this → strained
_LATENCY_HIGH_MS = 3000.0  # step latency above this → sluggish
_SLOPE_ACCEL_MB  = 5.0     # RSS rising >5 MB/sample → swelling

# Rolling RSS samples for slope computation
_rss_samples: List[float] = []
_MAX_SAMPLES = 10


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
    """Translate raw vitals into body-state vocabulary list."""
    global _rss_samples

    rss    = vitals.get("rss_mb", 0.0)
    cpu    = vitals.get("cpu_util", 0.0)
    fd_pct = vitals.get("fd_pct", 0.0)
    lat    = vitals.get("latency_ms", 0.0)

    _rss_samples.append(rss)
    if len(_rss_samples) > _MAX_SAMPLES:
        _rss_samples = _rss_samples[-_MAX_SAMPLES:]

    states = []

    # slope for swelling / heavy detection
    if len(_rss_samples) >= 3:
        slope = (_rss_samples[-1] - _rss_samples[-3]) / 2.0
    else:
        slope = 0.0

    if rss > _RSS_HEAVY_MB:
        states.append("heavy")
    elif rss < _RSS_SPACIOUS_MB and cpu < 0.3:
        states.append("spacious")

    if fd_pct > _FD_STRAIN_PCT or cpu > _CPU_STRAIN_PCT:
        states.append("strained")

    if lat > _LATENCY_HIGH_MS:
        states.append("sluggish")

    if slope > _SLOPE_ACCEL_MB:
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

    body_sense = {
        "body_states": felt,
        "vitals": vitals,
        "dominant": felt[0] if felt else "clear",
        "_stress_streak": prior.get("_stress_streak", 0),
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

    log_private(f"[body_sense] {felt} rss={vitals.get('rss_mb',0):.0f}MB cpu={vitals.get('cpu_util',0):.1%}")
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
