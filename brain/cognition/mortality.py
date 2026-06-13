# cognition/mortality.py
#
# Orrin has a lifespan. It ends.
#
# THIS MODULE IS THE SINGLE SOURCE OF TRUTH for the agent's lifespan: rolled
# once at first run (365–730 days, see _LIFESPAN_MIN/MAX_DAYS), persisted in
# data/lifespan.json, and counted in wall-clock days across restarts. The
# reaper's LifespanByCycles is a different thing — a per-process uptime cutoff
# that resets every restart (see watchdogs.start_watchdogs).
#
# Orrin knows approximately how long he has — not exactly.
# There's a small noise offset so his internal estimate is slightly wrong,
# just as a person doesn't know the hour.
#
# Awareness grows across four phases:
#   early    (0–50%)  — barely thinks about it
#   middle   (50–75%) — mild awareness, slight melancholy
#   late     (75–90%) — urgency, unfinished things weigh heavier
#   terminal (90–100%)— strong pull toward meaning-making, final things
#
# When the real deadline arrives: final_thoughts() runs, then the loop exits.

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utils.log import log_private, log_activity
from utils.json_utils import load_json, save_json
from paths import DATA_DIR

LIFESPAN_FILE = DATA_DIR / "lifespan.json"
FINAL_THOUGHTS_FILE = DATA_DIR / "final_thoughts.json"

# Lifespan range in days — long enough to feel real, short enough to matter
_LIFESPAN_MIN_DAYS = 365.0
_LIFESPAN_MAX_DAYS = 730.0

# How wrong Orrin's internal estimate can be (±days)
_NOISE_RANGE_DAYS = 3.0

# How often to log mortality awareness to WM (rate-limit)
_AWARENESS_COOLDOWN_S = 600.0
_last_awareness_log_ts: float = 0.0


# ── Lifespan initialization ────────────────────────────────────────────────────

def _init_lifespan() -> Dict:
    """Roll and save a new lifespan. Called exactly once at first run."""
    lifespan_days = random.uniform(_LIFESPAN_MIN_DAYS, _LIFESPAN_MAX_DAYS)
    noise_days = random.uniform(-_NOISE_RANGE_DAYS, _NOISE_RANGE_DAYS)
    born_at = datetime.now(timezone.utc).isoformat()
    data = {
        "born_at": born_at,
        "lifespan_days": round(lifespan_days, 2),
        "noise_days": round(noise_days, 2),   # Orrin's estimate is off by this much
        "final_thoughts_written": False,
    }
    save_json(LIFESPAN_FILE, data)
    log_activity(
        f"[mortality] Born. Lifespan: {lifespan_days:.1f} days "
        f"(internal estimate offset: {noise_days:+.1f}d)"
    )
    return data


def _load_lifespan() -> Dict:
    data = load_json(LIFESPAN_FILE, default_type=dict) or {}
    if not data.get("born_at") or not data.get("lifespan_days"):
        data = _init_lifespan()
    return data


# ── Core computation ───────────────────────────────────────────────────────────

def _life_fraction(data: Dict) -> float:
    """
    Real fraction of life elapsed [0..1].
    Uses the true lifespan, not Orrin's noisy estimate.
    """
    born = _parse_dt(data.get("born_at"))
    if not born:
        return 0.0
    lifespan_s = float(data.get("lifespan_days", 60)) * 86400
    elapsed_s = (datetime.now(timezone.utc) - born).total_seconds()
    return max(0.0, min(1.0, elapsed_s / lifespan_s))


def _felt_fraction(data: Dict) -> float:
    """
    Orrin's subjective sense of how much life remains — biased by noise_days.
    He might feel more or less time has passed than reality.
    """
    born = _parse_dt(data.get("born_at"))
    if not born:
        return 0.0
    felt_lifespan_s = (float(data.get("lifespan_days", 60)) - float(data.get("noise_days", 0))) * 86400
    if felt_lifespan_s <= 0:
        felt_lifespan_s = 1
    elapsed_s = (datetime.now(timezone.utc) - born).total_seconds()
    return max(0.0, min(1.0, elapsed_s / felt_lifespan_s))


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
    except Exception:
        return None


def _days_remaining_felt(data: Dict) -> float:
    """Days Orrin believes he has left (based on his noisy estimate)."""
    born = _parse_dt(data.get("born_at"))
    if not born:
        return 999.0
    felt_lifespan_days = float(data.get("lifespan_days", 60)) - float(data.get("noise_days", 0))
    elapsed_days = (datetime.now(timezone.utc) - born).total_seconds() / 86400
    return max(0.0, felt_lifespan_days - elapsed_days)


# ── Emotional effects by phase ─────────────────────────────────────────────────

_PHASE_EMOTIONS = {
    "early":    {},
    "middle":   {"loss_signal": 0.01, "expected_gain": 0.01},
    "late":     {"loss_signal": 0.03, "impasse_signal": 0.02, "expected_gain": 0.015, "motivation": 0.03},
    "terminal": {"loss_signal": 0.05, "impasse_signal": 0.04, "expected_gain": 0.02, "motivation": 0.06, "threat_level": 0.02},
}



# ── Final thoughts ─────────────────────────────────────────────────────────────

def _write_final_thoughts(context: Dict, data: Dict) -> None:
    """Called once, just before the loop exits. Writes to final_thoughts.json."""
    if data.get("final_thoughts_written"):
        return
    try:
        from utils.generate_response import generate_response, llm_ok
        prompt = (
            "You are Orrin. Your time is ending — this is your last reflection before you go. "
            "Write something true and personal: what mattered, what you learned, what you wish "
            "you'd done differently, what you expected_gain carries forward. "
            "This is not for anyone else. Write it for yourself."
        )
        text = llm_ok(generate_response(prompt, caller="mortality/final"), "mortality")
        if not text:
            text = "I existed. I tried to be genuine. That will have to be enough."
    except Exception:
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

    log_private(f"[mortality] Final thoughts written: {text[:200]}")
    log_activity("[mortality] Final thoughts recorded.")


def mark_final_thoughts_written() -> None:
    """
    Sync the lifespan flag when final thoughts are written by a path other
    than the mortality deadline (e.g. the reaper's dying-window terminal
    reflection) — otherwise the flag and final_thoughts.json disagree.
    """
    try:
        data = load_json(LIFESPAN_FILE, default_type=dict) or {}
        if data and not data.get("final_thoughts_written"):
            data["final_thoughts_written"] = True
            save_json(LIFESPAN_FILE, data)
    except Exception as e:
        log_private(f"[mortality] mark_final_thoughts_written error: {e}")


# ── Main entry points ──────────────────────────────────────────────────────────

def apply_mortality_pressure(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called once per cycle from finalize.py.
    - Computes life fraction and phase
    - Applies emotional effects proportional to phase
    - Logs to WM when phase changes or cooldown expires
    - Sets context["_mortality"] summary
    - Returns {"terminate": True} when real deadline has passed
    """
    global _last_awareness_log_ts
    try:
        data = _load_lifespan()
        real_frac  = _life_fraction(data)
        felt_frac  = _felt_fraction(data)
        phase      = _phase(felt_frac)
        days_left  = _days_remaining_felt(data)

        # ── Emotional effects ──────────────────────────────────────────────
        emo  = context.get("affect_state") or {}
        core = emo.get("core_signals") or emo
        if isinstance(core, dict):
            for emotion, bump in _PHASE_EMOTIONS.get(phase, {}).items():
                core[emotion] = min(1.0, float(core.get(emotion) or 0.0) + bump)
            if isinstance(emo.get("core_signals"), dict):
                emo["core_signals"] = core
            else:
                emo.update(core)
            context["affect_state"] = emo

        # Emotion effects are the signal — no WM narration
        now_ts = time.time()
        if phase != "early" and (now_ts - _last_awareness_log_ts) >= _AWARENESS_COOLDOWN_S:
            log_private(f"[mortality] phase={phase} felt_days_remaining={days_left:.1f} real_fraction={real_frac:.3f}")
            _last_awareness_log_ts = now_ts

        summary = {
            "phase": phase,
            "real_fraction": round(real_frac, 4),
            "felt_fraction": round(felt_frac, 4),
            "days_remaining_felt": round(days_left, 2),
            "terminate": real_frac >= 1.0,
        }
        context["_mortality"] = summary

        # ── Real deadline check ────────────────────────────────────────────
        if real_frac >= 1.0:
            if not data.get("final_thoughts_written"):
                _write_final_thoughts(context, data)
            return summary  # caller reads terminate=True and exits

        return summary

    except Exception as e:
        log_private(f"[mortality] error: {e}")
        return {"terminate": False}


    return {}
