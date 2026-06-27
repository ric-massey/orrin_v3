"""
cognition/signal_routing.py

Emotion → cognitive policy routing.

Emotions control cognitive routing and policy at the selection layer — not
just prompts. This module returns per-function weight multipliers that the
bandit's select_function uses alongside its learned arm values.

Routing rules (additive to bandit scores):

  exploration_drive > 0.65  → widen search: +0.3 to look_outward / look_around / wonder-related
  risk_estimate > 0.55    → increase verification: +0.4 to self_review / metacog_flush / reflect
  stagnation_signal > 0.60    → force novelty: +0.5 to skill synthesis, experimentation, self_extension
  Confidence > 0.70 → prune low-utility branches: −0.2 to repetitive introspection
  impasse_signal > 0.55 → action bias: +0.3 to pursue_committed_goal, +0.2 to agentic actions
  threat_level > 0.50       → caution: −0.3 to agentic / code_writer, +0.3 to self_review
  Wonder > 0.55     → speculative exploration: +0.3 to experimentation, dreaming-adjacent
  reward_negative > 0.55    → inward: +0.3 to autobiography / identity / relationship reflection
  Motivation > 0.75 → execution mode: +0.4 to pursue_committed_goal

These multipliers do not override the bandit — they bias it. The bandit still
learns from outcomes and can override these biases over time.
"""
from __future__ import annotations

from typing import Any, Dict

# ── Routing table ─────────────────────────────────────────────────────────────
# Each entry: (emotion, threshold, sign, magnitude, target_fn_substrings)
# sign: +1 boosts, -1 dampens
_ROUTES = [
    # emotion           thresh  sign  mag   target substrings
    ("exploration_drive",       0.65,  +1,  0.30,  ["look_outward", "look_around", "world_perception",
                                             "exploration_drive", "novelty_signal", "explore"]),
    ("risk_estimate",         0.55,  +1,  0.40,  ["self_review", "metacog", "reflect", "check",
                                             "review", "repair"]),
    ("stagnation_signal",         0.60,  +1,  0.50,  ["skill_synthesis", "synthesize_from_gap",
                                             "run_active_experiment", "self_extension",
                                             "decide_to_write_code", "explore"]),
    ("stagnation_signal",         0.60,  -1,  0.30,  ["reflect_on", "review", "autobiography"]),
    ("confidence",      0.70,  -1,  0.20,  ["reflect_on", "introspect", "self_query",
                                             "metacog"]),
    ("impasse_signal",     0.55,  +1,  0.30,  ["pursue_committed_goal", "assess_goal",
                                             "pursue_goal"]),
    ("impasse_signal",     0.55,  +1,  0.20,  ["tool", "search", "look_outward"]),
    ("threat_level",            0.50,  -1,  0.30,  ["write_code", "code_writer", "skill_synthesis",
                                             "self_extension", "tool_runner"]),
    ("threat_level",            0.50,  +1,  0.30,  ["self_review", "metacog", "reflect"]),
    ("novelty_signal",          0.55,  +1,  0.30,  ["run_active_experiment", "explore",
                                             "look_outward", "exploration_drive"]),
    ("reward_negative",         0.55,  +1,  0.30,  ["autobiography", "identity", "relationship",
                                             "reflect", "narrative"]),
    ("motivation",      0.75,  +1,  0.40,  ["pursue_committed_goal", "pursue_goal",
                                             "assess_goal_progress"]),
    ("motivation",      0.75,  -1,  0.20,  ["reflect_on", "introspect"]),
]


def signal_bias(
    fn_name: str,
    affect_state: Dict[str, Any],
) -> float:
    """
    Return an additive bias for `fn_name` based on current emotional state.
    Positive = boost, negative = dampen. Range roughly −0.5 to +0.8.
    """
    if not fn_name or not affect_state:
        return 0.0

    core = affect_state.get("core_signals") or affect_state
    fn_lower = fn_name.lower()
    total_bias = 0.0

    for (emotion, thresh, sign, mag, targets) in _ROUTES:
        val = float(core.get(emotion) or 0.0)
        if val < thresh:
            continue
        # Scale magnitude by how far above threshold
        scale = min(1.0, (val - thresh) / max(thresh, 0.01))
        if any(t in fn_lower for t in targets):
            total_bias += sign * mag * (0.5 + 0.5 * scale)

    return round(total_bias, 3)


def top_biased_functions(
    fn_names: list,
    affect_state: Dict[str, Any],
    top_n: int = 5,
) -> list:
    """
    Return the top_n function names most strongly biased (positively) by
    the current emotional state. Useful for logging and introspection.
    """
    scored = [(fn, signal_bias(fn, affect_state)) for fn in fn_names]
    scored.sort(key=lambda x: -x[1])
    return [(fn, b) for fn, b in scored[:top_n] if b > 0.05]


def apply_signal_routing(
    fn_scores: Dict[str, float],
    affect_state: Dict[str, Any],
) -> Dict[str, float]:
    """
    Apply emotion biases to a dict of {fn_name: score} and return adjusted scores.
    Scores are additive. This should be called after bandit scoring, before selection.
    """
    if not affect_state:
        return fn_scores
    return {fn: score + signal_bias(fn, affect_state) for fn, score in fn_scores.items()}
