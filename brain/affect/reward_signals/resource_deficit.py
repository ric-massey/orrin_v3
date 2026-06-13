# resource_deficit.py
import time
import random
import math
from typing import Dict, Any

def update_function_resource_deficit(context: Dict[str, Any], function_name: str) -> None:
    """
    Updates in-place:
      context["function_resource_deficit"][function_name] = {
        last_used, count, score (0..10), resource_deficit_history
      }
    Decay is per-minute and speeds up when motivation/excitement are high.
    """
    resource_deficit = context.setdefault("function_resource_deficit", {})
    now = time.time()
    info = resource_deficit.get(function_name, {"last_used": 0, "count": 0, "score": 0.0, "resource_deficit_history": []})

    # Seconds since last use
    dt = max(0.0, now - float(info.get("last_used", 0.0)))

    # Mood-based decay modulation: higher motivation/excitement => faster recovery (more decay)
    affect_state = context.get("affect_state", {}) or {}
    motivation = float(affect_state.get("motivation") or 0.5)
    excitement = float(affect_state.get("excitement") or 0.0)
    mood_factor = 1.0 + 0.3 * (motivation + excitement)
    mood_factor = max(0.5, min(mood_factor, 1.5))  # clamp both ways

    # Nonlinear decay rate rises with resource_deficit level
    decay_rate_base = 0.12  # per-minute-ish base
    resource_deficit_level = float(info.get("score", 0.0))
    nonlinear_decay = decay_rate_base * math.log1p(max(0.0, resource_deficit_level))
    decay_rate = nonlinear_decay * mood_factor

    # Exponential decay by elapsed minutes
    resource_deficit_after_decay = resource_deficit_level * math.exp(-decay_rate * (dt / 60.0))

    # Recovery boost if long rest
    if dt > 600:  # 10 minutes
        resource_deficit_after_decay *= 0.85

    # resource_deficit gain for this use (sometimes “push through”)
    push_through_factor = 0.5 if random.random() < 0.1 else 1.0
    resource_deficit_gain = 1.0 * push_through_factor

    new_resource_deficit = resource_deficit_after_decay + resource_deficit_gain

    # Short history to smooth/detect trends
    hist = list(info.get("resource_deficit_history", []))
    hist.append((now, new_resource_deficit))
    if len(hist) > 30:
        hist = hist[-30:]

    info.update({
        "last_used": now,
        "count": int(info.get("count", 0)) + 1,
        "score": min(new_resource_deficit, 10.0),
        "resource_deficit_history": hist,
    })
    resource_deficit[function_name] = info
    context["function_resource_deficit"] = resource_deficit  # explicit

def resource_deficit_penalty(context: Dict[str, Any], function_name: str) -> float:
    """
    Returns a *negative* multiplier-style penalty in [-0.6, 0],
    modulated by motivation (less negative), risk_estimate & stagnation_signal (more negative).
    """
    resource_deficit = context.get("function_resource_deficit", {})
    info = resource_deficit.get(function_name, {"score": 0.0})
    score = float(info.get("score", 0.0))

    # Base penalty scales 0 (no resource_deficit) to -0.6
    base_penalty = -0.6 * min(1.0, score / 7.0)

    affect_state = context.get("affect_state", {}) or {}
    motivation = float(affect_state.get("motivation") or 0.5)
    risk_estimate = float(affect_state.get("risk_estimate") or 0.0)
    stagnation_signal = float(affect_state.get("stagnation_signal") or 0.3)

    # Motivation reduces penalty, risk_estimate/stagnation_signal increase it
    motivation_factor = 1 - 0.7 * motivation
    risk_estimate_factor = 1 + 0.5 * risk_estimate
    stagnation_signal_factor = 1 + 0.4 * stagnation_signal

    penalty = base_penalty * motivation_factor * risk_estimate_factor * stagnation_signal_factor

    # 5% chance to ignore resource_deficit entirely
    if random.random() < 0.05:
        penalty = 0.0

    return float(penalty)

def resource_deficit_penalty_from_context(affect_state: Dict[str, float], action_type: str) -> float:
    """
    Returns a *positive* penalty in [0.0, 1.0] based on emotional resource_deficit/stress/overwhelm
    (Note: unit differs from resource_deficit_penalty above; callers should not mix them directly.)
    """
    resource_deficit_level = float(affect_state.get("resource_deficit") or 0.0)
    stress = float(affect_state.get("stress") or 0.0)
    overwhelm = float(affect_state.get("overwhelm") or 0.0)

    # Weighted blend
    resource_deficit_score = resource_deficit_level * 0.6 + stress * 0.3 + overwhelm * 0.1

    # Higher penalty for demanding actions
    if action_type in {"physical", "complex", "long_task", "creative"}:
        resource_deficit_score *= 1.5

    return max(0.0, min(resource_deficit_score, 1.0))