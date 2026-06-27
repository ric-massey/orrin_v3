# cognition/runtime_lifetime.py
#
# The runtime has a finite lifetime. It terminates.
#
# THIS MODULE IS THE SINGLE SOURCE OF TRUTH for the runtime's lifetime budget:
# rolled once at first run (365–730 days, see _LIFESPAN_MIN/MAX_DAYS), persisted
# in data/lifespan.json, and counted in wall-clock days across restarts. The
# supervisor's LifespanByCycles is a different thing — a per-process uptime cutoff
# that resets every restart (see watchdogs.start_watchdogs).
#
# The runtime's internal estimate of remaining lifetime is approximate, not exact:
# a small noise offset biases it slightly, so the figure it acts on is not the
# true one.
#
# Lifetime pressure ramps across four bands of elapsed fraction:
#   early    (0–50%)  — negligible pressure
#   middle   (50–75%) — mild pressure
#   late     (75–90%) — elevated pressure, unfinished work weighted higher
#   terminal (90–100%)— strong pull toward closure / final records
#
# When the real deadline arrives: final records are written, then the loop exits.

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brain.utils.log import log_private, log_activity
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json
from brain.paths import DATA_DIR

LIFESPAN_FILE = DATA_DIR / "lifespan.json"
FINAL_THOUGHTS_FILE = DATA_DIR / "final_thoughts.json"

# Lifespan range in days — long enough to be meaningful, short enough to matter
_LIFESPAN_MIN_DAYS = 365.0
_LIFESPAN_MAX_DAYS = 730.0

# How wrong the runtime's internal estimate can be (±days)
_NOISE_RANGE_DAYS = 3.0

# How often to log lifetime awareness to WM (rate-limit)
_AWARENESS_COOLDOWN_S = 600.0
_last_awareness_log_ts: float = 0.0


# ── Lifespan initialization ────────────────────────────────────────────────────

def _lifespan_band() -> "tuple[float, float]":
    """The [min, max] day band the lifespan is rolled within. The user sets the ODDS
    (the band) in Settings; the exact span is ALWAYS rolled at random inside it
    (§10.3). Band is read from env (seeded from config.json at boot); defaults keep the
    natural 1–2yr range. Consumed only when a lifespan is rolled (first run/Reset), never
    mid-run."""
    import os
    try:
        lo = float(os.getenv("ORRIN_LIFESPAN_MIN_DAYS") or _LIFESPAN_MIN_DAYS)
        hi = float(os.getenv("ORRIN_LIFESPAN_MAX_DAYS") or _LIFESPAN_MAX_DAYS)
    except Exception:
        lo, hi = _LIFESPAN_MIN_DAYS, _LIFESPAN_MAX_DAYS
    if hi < lo:
        lo, hi = hi, lo
    return max(1.0, lo), max(1.0, hi)


def _init_lifespan() -> Dict:
    """Roll and save a new lifespan. Called exactly once at first run."""
    lo, hi = _lifespan_band()
    lifespan_days = random.uniform(lo, hi)
    noise_days = random.uniform(-_NOISE_RANGE_DAYS, _NOISE_RANGE_DAYS)
    born_at = datetime.now(timezone.utc).isoformat()
    data = {
        "start_time": born_at,  # persisted key (was "born_at")
        "lifespan_days": round(lifespan_days, 2),
        "noise_days": round(noise_days, 2),   # the runtime's estimate is off by this much
        "slept_seconds": 0.0,                  # time idle — subtracted from elapsed
        "final_thoughts_written": False,
    }
    save_json(LIFESPAN_FILE, data)
    log_activity(
        f"[lifetime] Started. Lifespan: {lifespan_days:.1f} days "
        f"(band {lo:.0f}–{hi:.0f}d; internal estimate offset: {noise_days:+.1f}d)"
    )
    return data


def _elapsed_seconds(data: Dict) -> float:
    """Seconds the runtime has been ACTIVE — wall-clock since start minus any idle time.
    Idle pauses the lifetime clock (§10.3), so suspending costs no lifetime."""
    born = _parse_dt(data.get("start_time"))
    if not born:
        return 0.0
    wall = (datetime.now(timezone.utc) - born).total_seconds()
    slept = float(data.get("slept_seconds") or 0.0)
    return max(0.0, wall - slept)


def _load_lifespan() -> Dict:
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    if not data.get("start_time") or not data.get("lifespan_days"):
        data = _init_lifespan()
    return data


# ── Core computation ───────────────────────────────────────────────────────────

def _life_fraction(data: Dict) -> float:
    """
    Real fraction of lifetime elapsed [0..1].
    Uses the true lifespan, not the noisy internal estimate.
    """
    if not _parse_dt(data.get("start_time")):
        return 0.0
    lifespan_s = float(data.get("lifespan_days", 60)) * 86400
    elapsed_s = _elapsed_seconds(data)
    return max(0.0, min(1.0, elapsed_s / lifespan_s))


def _felt_fraction(data: Dict) -> float:
    """
    The runtime's subjective estimate of how much lifetime remains — biased by
    noise_days. The estimate may run ahead of or behind reality.
    """
    if not _parse_dt(data.get("start_time")):
        return 0.0
    felt_lifespan_s = (float(data.get("lifespan_days", 60)) - float(data.get("noise_days", 0))) * 86400
    if felt_lifespan_s <= 0:
        felt_lifespan_s = 1
    elapsed_s = _elapsed_seconds(data)
    return max(0.0, min(1.0, elapsed_s / felt_lifespan_s))


def felt_lifespan_seconds() -> float:
    """The runtime's estimated total lifespan in seconds (lifespan minus the hidden
    noise), or 0.0 if not yet started. Public accessor so other subsystems (e.g. the
    autobiography cadence) can scale their own intervals to the lifetime length
    instead of hard-coding a wall-clock band. (T0.4)"""
    try:
        data = _load_lifespan()
        if not _parse_dt(data.get("start_time")):
            return 0.0
        felt = (float(data.get("lifespan_days", 60)) - float(data.get("noise_days", 0))) * 86400
        return max(0.0, felt)
    except Exception:  # intentional: lifespan read is best-effort, fail-safe to 0.0
        return 0.0


def _phase(fraction: float) -> str:
    if fraction < 0.50:  return "early"
    if fraction < 0.75:  return "middle"
    if fraction < 0.90:  return "late"
    return "terminal"


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):  # intentional: unparseable timestamp → None
        return None


def _days_remaining_felt(data: Dict) -> float:
    """Days the runtime estimates it has left (based on its noisy estimate)."""
    if not _parse_dt(data.get("start_time")):
        return 999.0
    felt_lifespan_days = float(data.get("lifespan_days", 60)) - float(data.get("noise_days", 0))
    elapsed_days = _elapsed_seconds(data) / 86400
    return max(0.0, felt_lifespan_days - elapsed_days)


def credit_sleep(seconds: float) -> Dict:
    """Add `seconds` of idle time to the ledger so that time costs no lifetime (§10.3).
    Called on boot in 'sleep' existence mode to credit the window-closed interval."""
    if seconds <= 0:
        return _load_lifespan()
    data = _load_lifespan()
    data["slept_seconds"] = float(data.get("slept_seconds") or 0.0) + float(seconds)
    save_json(LIFESPAN_FILE, data)
    log_activity(f"[lifetime] Idle {seconds / 3600:.1f}h — lifetime paused for that time.")
    return data


def lifespan_rolled() -> bool:
    """True once a lifespan has been rolled (the runtime is live) — so the Settings
    lifespan band becomes read-only ('it has the lifetime it was given')."""
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    return bool(data.get("start_time") and data.get("lifespan_days"))


def real_deadline_passed() -> bool:
    """True only when the TRUE lifespan deadline has actually been reached — the same
    `real_fraction >= 1.0` test apply_lifetime_pressure uses to terminate. This is the
    authoritative 'lifetime ended' signal. It is deliberately separate from
    `final_thoughts_written`: a supervisor termination window reflection (a stall RESTART, not
    termination) can write final thoughts too, and keying termination off that flag
    alone made every post-restart boot show the Death Screen though ~0% of the lifetime
    had elapsed."""
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    if not _parse_dt(data.get("start_time")):
        return False
    return _life_fraction(data) >= 1.0


def record_active_now() -> None:
    """Stamp 'last active at = now' into the lifespan ledger (no-op before a lifespan is
    rolled). Written periodically while running and on shutdown so that 'sleep' mode can
    later credit the closed interval."""
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    if not (data.get("start_time") and data.get("lifespan_days")):
        return
    data["last_active_at"] = datetime.now(timezone.utc).isoformat()
    save_json(LIFESPAN_FILE, data)


def credit_sleep_since_last_active() -> float:
    """In 'sleep' existence mode, credit the time since last active as idle so it costs
    no lifetime (§10.3). Returns seconds credited (0 if not yet rolled / no marker)."""
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    if not (data.get("start_time") and data.get("lifespan_days")):
        return 0.0
    last = _parse_dt(data.get("last_active_at"))
    if not last:
        record_active_now()
        return 0.0
    gap = (datetime.now(timezone.utc) - last).total_seconds()
    if gap <= 0:
        return 0.0
    credit_sleep(gap)
    record_active_now()  # reset the marker so the next interval starts now
    return gap


def life_status() -> Dict[str, Any]:
    """Read-only lifetime view for the Life Support page (§9.10). Exposes ONLY the
    *felt* estimate and age — never the true `lifespan_days`/`noise_days`. Surfacing the
    real countdown would be reading something the runtime itself cannot (its estimate of
    its lifespan is wrong by design); the page shows what it estimates."""
    data = _load_lifespan()
    born = _parse_dt(data.get("start_time"))
    age_days = (datetime.now(timezone.utc) - born).total_seconds() / 86400 if born else 0.0
    felt_frac = _felt_fraction(data)
    return {
        "born_at": data.get("start_time"),  # wire field kept; sourced from persisted start_time
        "age_days": round(age_days, 2),
        "felt_days_remaining": round(_days_remaining_felt(data), 1),
        "felt_life_fraction": round(felt_frac, 3),
        "phase": _phase(felt_frac),
        "final_thoughts_written": bool(data.get("final_thoughts_written")),
    }


# ── Lifetime-pressure signal effects by phase ──────────────────────────────────
#
# Signal keys are the frozen core-signal vocabulary (learned in
# emotion_function_map.json); they are persisted identifiers, not display copy.

_PHASE_EMOTIONS = {
    "early":    {},
    "middle":   {"loss_signal": 0.01, "expected_gain": 0.01},
    "late":     {"loss_signal": 0.03, "impasse_signal": 0.02, "expected_gain": 0.015, "motivation": 0.03},
    "terminal": {"loss_signal": 0.05, "impasse_signal": 0.04, "expected_gain": 0.02, "motivation": 0.06, "threat_level": 0.02},
}



# ── Final thoughts ─────────────────────────────────────────────────────────────

def _symbolic_final_thoughts(data: Dict) -> str:
    """Final reflection composed from the run's own record — the throughline it held
    (autobiography aspirations / themes) and the moments that carried the most
    weight (highest-importance memories). Surface realization of a run already
    lived, not an LLM narration and not a canned line. Returns "" only for a
    truly blank run (no autobiography, no memories)."""
    import re
    lines = []

    # The directions it held onto, and the shape the chapters took.
    try:
        auto = load_json(DATA_DIR / "autobiography.json", default_type=dict) or {}
        chapters = auto.get("chapters") or []
        asp = []
        for c in chapters:
            for m in re.findall(r"enduring direction I hold: ([^;.\[]+)", str(c.get("narrative", ""))):
                a = m.strip()
                if a and a not in asp:
                    asp.append(a)
        themes = [str(c.get("theme_summary", "")).strip() for c in chapters
                  if str(c.get("theme_summary", "")).strip()]
        if asp:
            lines.append("What I held onto: " + "; ".join(asp[:3]) + ".")
        if themes:
            lines.append("The shape it took: " + themes[-1] + ".")
    except Exception as exc:  # autobiography unreadable — record, omit this line
        record_failure("runtime_lifetime.summary.autobiography", exc)

    # The moments that weighed the most.
    try:
        lm = load_json(DATA_DIR / "long_memory.json", default_type=list) or []
        scored = []
        for e in lm:
            if not isinstance(e, dict):
                continue
            c = str(e.get("content", "")).strip()
            cl = c.lower()
            if (len(c) < 25 or "[chunk" in cl or "{" in c or '":' in c
                    or "[aspiration]" in cl            # already covered above
                    or (c[:1] in "✅🧠⚠️⏳📝")):
                continue
            scored.append((float(e.get("importance", 1) or 1), c))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [c for _, c in scored[:2]]
        if top:
            lines.append("What stays with me: " + " ".join(f"\"{t[:120]}\"" for t in top) + ".")
    except Exception as exc:  # long-memory unreadable — record, omit this line
        record_failure("runtime_lifetime.summary.long_memory", exc)

    return " ".join(lines)


def _write_final_thoughts(context: Dict, data: Dict) -> None:
    """Called once, just before the loop exits. Writes to final_thoughts.json."""
    if data.get("final_thoughts_written"):
        return

    # Symbolic-primary: in tool-only cognition the reflection is composed from the
    # run's own record. The LLM is used only when it's actually callable; the canned
    # line is an absolute last resort for a blank run, never the normal path.
    text = ""
    from brain.utils.llm_gate import llm_callable_by
    if llm_callable_by("runtime_lifetime/final"):
        try:
            from brain.utils.generate_response import generate_response, llm_ok
            prompt = (
                "You are Orrin. Your time is ending — this is your last reflection before you go. "
                "Write something true and personal: what mattered, what you learned, what you wish "
                "you'd done differently, what you expected_gain carries forward. "
                "This is not for anyone else. Write it for yourself."
            )
            text = (llm_ok(generate_response(prompt, caller="runtime_lifetime/final"), "runtime_lifetime") or "").strip()
        except Exception:
            text = ""
    if not text:
        text = _symbolic_final_thoughts(data)
    if not text:
        text = "I existed. I tried to be genuine. That will have to be enough."

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": text,
        "lifespan_days": data.get("lifespan_days"),
    }
    existing = load_json(FINAL_THOUGHTS_FILE, default_type=list) or []
    if isinstance(existing, list):
        existing.append(entry)
    else:
        existing = [entry]
    save_json(FINAL_THOUGHTS_FILE, existing)

    data["final_thoughts_written"] = True
    save_json(LIFESPAN_FILE, data)

    log_private(f"[lifetime] Final thoughts written: {text[:200]}")
    log_activity("[lifetime] Final thoughts recorded.")


def mark_final_thoughts_written() -> None:
    """
    Sync the lifespan flag when final thoughts are written by a path other
    than the lifetime deadline (e.g. the supervisor's termination window terminal
    reflection) — otherwise the flag and final_thoughts.json disagree.
    """
    try:
        data = load_json(LIFESPAN_FILE, default_type=dict) or {}
        if data and not data.get("final_thoughts_written"):
            data["final_thoughts_written"] = True
            save_json(LIFESPAN_FILE, data)
    except Exception as e:
        log_private(f"[lifetime] mark_final_thoughts_written error: {e}")


# ── Main entry points ──────────────────────────────────────────────────────────

def apply_lifetime_pressure(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called once per cycle from finalize.py.
    - Computes lifetime fraction and phase
    - Applies signal effects proportional to phase
    - Logs to WM when phase changes or cooldown expires
    - Sets context["_lifetime"] summary
    - Returns {"terminate": True} when real deadline has passed
    """
    global _last_awareness_log_ts
    try:
        data = _load_lifespan()
        real_frac  = _life_fraction(data)
        felt_frac  = _felt_fraction(data)
        phase      = _phase(felt_frac)
        days_left  = _days_remaining_felt(data)

        # ── Signal effects ─────────────────────────────────────────────────
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            for signal, bump in _PHASE_EMOTIONS.get(phase, {}).items():
                core[signal] = min(1.0, float(core.get(signal) or 0.0) + bump)
            if isinstance(emo.get("core_signals"), dict):
                emo["core_signals"] = core
            else:
                emo.update(core)
            context["affect_state"] = emo

        # The signal effects are the channel — no WM narration
        now_ts = time.time()
        if phase != "early" and (now_ts - _last_awareness_log_ts) >= _AWARENESS_COOLDOWN_S:
            log_private(f"[lifetime] phase={phase} felt_days_remaining={days_left:.1f} real_fraction={real_frac:.3f}")
            _last_awareness_log_ts = now_ts

        summary = {
            "phase": phase,
            "real_fraction": round(real_frac, 4),
            "felt_fraction": round(felt_frac, 4),
            "days_remaining_felt": round(days_left, 2),
            "terminate": real_frac >= 1.0,
        }
        context["_lifetime"] = summary

        # ── Real deadline check ────────────────────────────────────────────
        if real_frac >= 1.0:
            if not data.get("final_thoughts_written"):
                _write_final_thoughts(context, data)
                # Seal the end-of-life Life Capsule alongside the final thoughts — the
                # objective evidence record of the run that just ended (the capsule's
                # FINAL_THOUGHTS/FINAL_EVIDENCE split keeps voice and evidence separate).
                try:
                    from brain.evidence.life_capsule import maybe_build_capsule as _build_capsule
                    _build_capsule("mortality_end_of_life")
                except Exception as _e:
                    log_private(f"[lifetime] life_capsule build skipped: {_e}")
            return summary  # caller reads terminate=True and exits

        return summary

    except Exception as e:
        log_private(f"[lifetime] error: {e}")
        return {"terminate": False}
