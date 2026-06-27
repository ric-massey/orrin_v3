"""
cognition/self_state/latent_identity.py

Persistent latent identity vector — a stable numeric anchor alongside symbolic memory.

Every cognitive cycle, the current behavioral/emotional state nudges a small
fixed-dimension vector using EMA (alpha=0.03). The vector encodes stable
personality traits and drifts only slowly, acting as a corrective force
against identity drift from retrieval noise.

The 10 dimensions:
  0  openness         — exploration_drive + wonder
  1  conscientiousness — motivation + goal completion rate
  2  agreeableness    — compassion + positive user signals
  3  neuroticism      — impasse_signal + risk_estimate + uncertainty
  4  extraversion     — responsiveness, social engagement
  5  analytical       — tendency toward structured reasoning
  6  reflective       — introspection tendency
  7  ethical          — values adherence score
  8  creative         — novel response / skill generation tendency
  9  stability        — vector self-consistency across updates

Stability (dim 9) is computed from the others — high variance across dims
means low stability. A cycle that would push stability below _STABILITY_FLOOR
has its nudge damped.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import SELF_MODEL_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_LOCK = threading.Lock()
_DIM = 10
_ALPHA = 0.03          # EMA smoothing — ~33 cycles to half-adapt to a new target
_STABILITY_FLOOR = 0.30  # below this, nudge is damped to protect coherence
_NUDGE_DAMP = 0.4      # multiplier applied when stability would drop below floor

# Default starting vector (mid-range, slight positive bias for core traits)
_DEFAULT_VECTOR = [0.55, 0.50, 0.55, 0.20, 0.45, 0.50, 0.55, 0.65, 0.45, 0.70]


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load() -> List[float]:
    try:
        sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
        v = sm.get("latent_identity_vector")
        if isinstance(v, list) and len(v) == _DIM:
            return [float(x) for x in v]
    except Exception as _e:
        record_failure("latent_identity._load", _e)
    return list(_DEFAULT_VECTOR)


def _save(vector: List[float]) -> None:
    try:
        sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
        sm["latent_identity_vector"] = [round(x, 4) for x in vector]
        save_json(SELF_MODEL_FILE, sm)
    except Exception as _e:
        record_failure("latent_identity._save", _e)


# ── Core math ─────────────────────────────────────────────────────────────────

def _stability(v: List[float]) -> float:
    """Variance-based stability: low variance across dimensions → high stability."""
    mean = sum(v) / len(v)
    var = sum((x - mean) ** 2 for x in v) / len(v)
    return max(0.0, min(1.0, 1.0 - var * 4.0))


def _target_from_state(context: Dict[str, Any]) -> List[float]:
    """
    Derive a target vector from the current emotional/behavioral state.
    Each dimension is a blended reading from available state signals.
    Returns a vector in [0, 1]^10.
    """
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo

    def _e(k: str, d: float = 0.0) -> float:
        return max(0.0, min(1.0, float(core.get(k) or d)))

    exploration_drive   = _e("exploration_drive", 0.3)
    wonder      = _e("wonder", 0.1)
    motivation  = _e("motivation", 0.5)
    compassion  = _e("compassion", 0.2)
    impasse_signal = _e("impasse_signal", 0.05)
    risk_estimate     = _e("risk_estimate", 0.05)
    uncertainty = _e("uncertainty", 0.05)
    confidence  = _e("confidence", 0.5)
    positive_valence         = _e("positive_valence", 0.1)
    reflective  = _e("reflective", 0.3)

    # User-facing engagement proxy
    user_present = float(bool(context.get("latest_user_input", "").strip()))
    last_tone    = context.get("last_tone") or "neutral"
    warmth = 1.0 if last_tone in ("warm", "excited") else 0.5

    # Goal completion rate from self_model empirical beliefs
    goal_rate = 0.5
    try:
        sm = context.get("self_model") or {}
        eb = sm.get("empirical_beliefs") or {}
        goal_rate = float(eb.get("goal_completion_rate", 0.5) or 0.5)
    except Exception as _e:
        record_failure("latent_identity._target_from_state", _e)

    # Values adherence — proxy: how often values_check passes without refusal
    values_ok = float(not bool(context.get("_values_refusal_this_cycle")))

    return [
        (exploration_drive + wonder) / 2,                    # 0 openness
        (motivation + goal_rate) / 2,                # 1 conscientiousness
        (compassion + positive_valence * 0.5 + warmth * 0.2),     # 2 agreeableness (clamped below)
        (impasse_signal + risk_estimate + uncertainty) / 3,   # 3 neuroticism
        (user_present * 0.4 + confidence * 0.3 + motivation * 0.3),  # 4 extraversion
        min(1.0, float(context.get("_used_analytical", 0)) * 0.6 + 0.3),  # 5 analytical
        reflective,                                  # 6 reflective
        values_ok,                                   # 7 ethical
        float(context.get("_skill_synthesized_this_cycle", 0)) * 0.7 + 0.35,  # 8 creative
        0.0,  # 9 stability — computed separately, not from state
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def update_latent_identity(context: Dict[str, Any] = None, **_) -> Dict[str, Any]:
    """
    EMA-nudge the latent identity vector toward the current state.
    Damps the nudge when stability would drop below _STABILITY_FLOOR.
    Returns {"vector": [...], "stability": float, "drift": float}.
    """
    ctx = context or {}
    with _LOCK:
        v = _load()
        target = _target_from_state(ctx)

        # Compute proposed next vector
        alpha = _ALPHA
        next_v = [v[i] + alpha * (target[i] - v[i]) for i in range(_DIM - 1)]

        # Compute stability of the proposed vector
        next_stab = _stability(next_v)
        current_stab = _stability(v[:-1])

        # If stability would drop significantly, damp the nudge
        if next_stab < _STABILITY_FLOOR and next_stab < current_stab:
            alpha *= _NUDGE_DAMP
            next_v = [v[i] + alpha * (target[i] - v[i]) for i in range(_DIM - 1)]
            next_stab = _stability(next_v)

        # Clamp all dims except stability to [0, 1]
        next_v = [max(0.0, min(1.0, x)) for x in next_v]
        next_v.append(round(next_stab, 4))

        # Drift = mean absolute change
        drift = sum(abs(next_v[i] - v[i]) for i in range(_DIM)) / _DIM

        _save(next_v)

    log_private(
        f"[latent_identity] stab={next_stab:.3f} drift={drift:.4f} "
        f"vec={[round(x, 2) for x in next_v]}"
    )
    return {"vector": next_v, "stability": next_stab, "drift": drift}


def get_latent_identity() -> Dict[str, Any]:
    """Return current latent identity state without updating."""
    v = _load()
    stab = _stability(v[:-1]) if len(v) == _DIM else 0.0
    _LABELS = [
        "openness", "conscientiousness", "agreeableness", "neuroticism",
        "extraversion", "analytical", "reflective", "ethical", "creative", "stability",
    ]
    return {
        "vector":    v,
        "stability": stab,
        "profile":   {_LABELS[i]: round(v[i], 3) for i in range(min(_DIM, len(v)))},
    }


def identity_drift_warning(context: Dict[str, Any]) -> Optional[str]:
    """
    Return a warning string if the current state is pulling the identity
    far from its stable baseline. Used by reflection to flag drift.
    """
    v = _load()
    target = _target_from_state(context)
    if not v or not target:
        return None
    drift = sum(abs(target[i] - v[i]) for i in range(min(len(v), len(target), _DIM - 1)))
    drift /= (_DIM - 1)
    stab = _stability(v[:-1])
    if drift > 0.22 or stab < _STABILITY_FLOOR:
        return (
            f"Identity drift detected: current state is pulling {drift:.2f} "
            f"away from stable baseline (stability={stab:.2f}). "
            f"Consider whether current emotional pattern is a temporary state or a value shift."
        )
    return None
