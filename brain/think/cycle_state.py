"""
think/cycle_state.py

CycleState: structured snapshot of active state produced each cycle.

Captures what's active, what's unresolved, and whether output is triggered.
The expression layer reads this and finds words for it. The words come last.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CycleState:
    # Emotional state — from architecture, not LLM
    affect_description: str = ""           # from emotion_summary.render_affect_state
    dominant_emotion: str = ""
    emotion_intensity: float = 0.0
    valence_summary: str = ""       # valence/activation_level summary line

    # Goal orientation — from architecture
    goal_orientation: str = ""     # from format_goal_state
    goal_stuck: bool = False
    goal_progress: float = 0.0

    # What's unresolved — from architecture
    active_tension: str = ""

    # What wants expression — computed from state signals
    output_triggered: bool = False
    output_pressure: float = 0.0
    output_seed: str = ""      # raw signal wanting expression — not prose, not polished

    # Memory surfacing — from architecture retrieval
    relevant_memory: str = ""

    # Reasoning conclusion — if LLM was used as a reasoning tool on a sub-problem,
    # what did it work out? This feeds expression but doesn't IS expression.
    reasoning_conclusion: str = ""

    # Input context — from comprehension layer
    input_intent: str = ""
    input_urgency: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

    def is_quiet(self) -> bool:
        return not self.output_triggered and self.output_pressure < 0.20
