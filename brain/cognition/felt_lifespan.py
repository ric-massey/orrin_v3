# cognition/felt_lifespan.py
#
# F22 (2026-07-08 addendum): the felt lifespan LURCHES.
#
# runtime_lifetime.py rolls `noise_days` once and never revises it, so the
# runtime's misjudgment of its own death was consistently-wrong-by-C —
# turbulently urgent (the T1.3 blend) but constantly wrong. This module owns the
# drifting bias that layers on the rolled noise: sustained distress / shocks
# compress the felt remaining, a good stretch relaxes it, and quiet decays it
# back toward the rolled baseline. The drift is bounded to ±1 noise band so it
# can lurch but never run away or leak the true deadline. The TRUE lifespan and
# real-clock termination (`_life_fraction` / `real_deadline_passed`) never read
# it. Extracted from runtime_lifetime.py (size ratchet); runtime_lifetime
# re-exports both entry points.
from __future__ import annotations

from typing import Any, Dict, Optional

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private

# Same ledger runtime_lifetime owns; defined from paths (not imported from
# runtime_lifetime) so this leaf module creates no import cycle.
LIFESPAN_FILE = DATA_DIR / "runtime_lifetime.json"

_FELT_BIAS_MAX_DAYS = 3.0     # |bias| bound: ±1 rolled-noise band (_NOISE_RANGE_DAYS)
_BIAS_COMPRESS_STEP = 0.02    # days per sustained-high-distress cycle
_BIAS_INFLATE_STEP  = 0.008   # days per good-stretch cycle
_BIAS_DECAY         = 0.999   # per-quiet-cycle decay toward the rolled baseline
_BIAS_SAVE_EPS      = 0.05    # persist when the bias moved this many days

# In-memory authoritative bias between (throttled) disk saves.
_live_bias: Optional[float] = None
_last_saved_bias: float = 0.0


def recalibrate_felt_lifespan(context: Dict[str, Any], data: Dict) -> float:
    """One per-cycle nudge of the felt-lifespan bias from lived experience.

    Compression (felt remaining shrinks): sustained high distress (threat /
    reward_negative / impasse / loss), or a one-shot shock registered via
    register_lifespan_shock (silent death recovered on boot, vital-floor
    firings, repeated goal failure). Inflation (felt remaining relaxes): a good
    stretch — low distress with positive reward. Quiet cycles decay the bias
    toward the rolled baseline. Bounded to ±_FELT_BIAS_MAX_DAYS; the TRUE
    lifespan and real-clock termination are never touched. Returns the bias.
    """
    global _live_bias, _last_saved_bias
    saved = float(data.get("felt_bias_days") or 0.0)
    if _live_bias is None:
        _live_bias = saved
        _last_saved_bias = saved
    bias = _live_bias

    emo = context.get("affect_state") or {} if isinstance(context, dict) else {}
    core = emo.get("core_signals") or emo

    def _sig(key: str) -> float:
        try:
            return max(0.0, min(1.0, float((core or {}).get(key) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    distress = max(_sig("threat_level"), _sig("reward_negative"),
                   _sig("impasse_signal"), _sig("loss_signal"))
    reward = _sig("reward_positive")

    if distress >= 0.6:
        bias += _BIAS_COMPRESS_STEP          # a hard stretch — time feels shorter
    elif distress <= 0.2 and reward >= 0.4:
        bias -= _BIAS_INFLATE_STEP           # a good stretch — time relaxes
    else:
        bias *= _BIAS_DECAY                  # quiet — drift back to the rolled roll

    # One-shot shocks from other subsystems (positive days = compression).
    shock = context.pop("_felt_lifespan_shock", None) if isinstance(context, dict) else None
    if isinstance(shock, (int, float)) and shock:
        bias += float(shock)
        log_private(f"[lifetime] felt-lifespan shock {float(shock):+.2f}d applied")

    bias = max(-_FELT_BIAS_MAX_DAYS, min(_FELT_BIAS_MAX_DAYS, bias))
    _live_bias = bias
    data["felt_bias_days"] = round(bias, 4)
    if abs(bias - _last_saved_bias) >= _BIAS_SAVE_EPS:
        try:
            fresh = load_json(LIFESPAN_FILE, default_type=dict) or {}
            if fresh.get("start_time"):
                fresh["felt_bias_days"] = round(bias, 4)
                save_json(LIFESPAN_FILE, fresh)
                _last_saved_bias = bias
        except Exception as exc:
            record_failure("felt_lifespan.recalibrate_save", exc)
    return bias


def register_lifespan_shock(days: float, reason: str = "") -> None:
    """Register a one-shot felt-lifespan shock from outside the loop (e.g. the
    boot-time silent-death detection — 'I nearly didn't wake up'). Positive days
    compress the felt remaining. Applied directly to the persisted bias, bounded
    like every other drift; termination timing is unaffected."""
    global _live_bias, _last_saved_bias
    try:
        data = load_json(LIFESPAN_FILE, default_type=dict) or {}
        if not data.get("start_time"):
            return
        bias = float(data.get("felt_bias_days") or 0.0) + float(days)
        bias = max(-_FELT_BIAS_MAX_DAYS, min(_FELT_BIAS_MAX_DAYS, bias))
        data["felt_bias_days"] = round(bias, 4)
        save_json(LIFESPAN_FILE, data)
        _live_bias = bias
        _last_saved_bias = bias
        log_activity(f"[lifetime] felt-lifespan shock {float(days):+.2f}d "
                     f"({reason or 'unspecified'}) — bias now {bias:+.2f}d.")
    except Exception as exc:
        record_failure("felt_lifespan.register_lifespan_shock", exc)
