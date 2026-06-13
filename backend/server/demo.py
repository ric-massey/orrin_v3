"""
backend/server/demo.py — synthetic telemetry generator.

Emits believable frames so the UI is fully alive without the real cognitive
codebase. Enabled with ORRIN_TELEMETRY_DEMO=1; started/stopped by the app lifespan.
"""
from __future__ import annotations

import asyncio
import math
import random
import time

from .config import LOOP_NODES
from .hub import Hub

_NARRATIVES = {
    "perceive": "Taking in the moment…",
    "reflect": "Reflecting…",
    "plan": "Planning next step…",
    "act": "Acting on it…",
}
_LOG_SOURCES = ["affect", "select_function", "action_gate", "reward_engine", "homeostasis", "dream"]
_MEMORY_SUMMARIES = [
    "goal progress snapshot", "reward trace updated", "affect setpoint compared",
    "association surfaced", "self-model belief touched",
]


async def run_demo(hub: Hub) -> None:
    """Continuously broadcast synthetic frames until cancelled."""
    cycle = 0
    t0 = time.time()
    while True:
        cycle += 1
        node = LOOP_NODES[cycle % len(LOOP_NODES)]
        dt = time.time() - t0
        valence = 0.5 + 0.35 * math.sin(dt / 7.0)
        arousal = 0.45 + 0.30 * math.sin(dt / 3.0 + 1.0)
        homeostasis = 0.7 + 0.25 * math.sin(dt / 11.0)
        level = random.choices(["debug", "info", "warn", "error"], weights=[3, 6, 2, 1])[0]

        frame = {
            "active_node": node,
            "narrative": _NARRATIVES[node],
            "cycle": cycle,
            "affect": {
                "valence": valence, "arousal": arousal, "homeostasis": homeostasis,
                "extra": {
                    "motivation": 0.5 + 0.3 * math.sin(dt / 5.0),
                    "threat_level": max(0.0, 0.2 * math.sin(dt / 4.0)),
                },
            },
            "metrics": {"valence": valence, "arousal": arousal, "homeostasis": homeostasis},
            "logs": [{
                "level": level,
                "source": random.choice(_LOG_SOURCES),
                "message": f"cycle {cycle}: {node} stage processed (Δ={random.random():.3f})",
            }],
        }
        if cycle % 2 == 0:
            frame["memory"] = [{
                "op": random.choice(["read", "write"]),
                "store": random.choice(["working", "long", "episodic", "semantic"]),
                "key": f"node:{node}:{cycle}",
                "summary": random.choice(_MEMORY_SUMMARIES),
                "salience": round(random.random(), 2),
            }]

        delta = hub.merge(frame)
        await hub.broadcast({"type": "delta", "frame": delta})
        await asyncio.sleep(0.9)
