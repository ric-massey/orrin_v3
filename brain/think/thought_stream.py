# brain/think/thought_stream.py
# In-memory thought stream: a thread-safe circular buffer of the last 100
# cognitive events. Consumed by the dashboard's /api/thought_history endpoint
# and pushed to SSE clients in real-time via push_event().
#
# Also owns the meta_control signal that lets the UI influence
# meta_controller.decide() on the next cycle:
#   "pause"      → meta_controller returns "defer"
#   "go_deeper"  → meta_controller returns "think_more" on round 1
#   "normal"     → default behaviour
from __future__ import annotations
from brain.core.runtime_log import get_logger

import collections
import threading
import time
from typing import Any, Dict, List
_log = get_logger(__name__)

_BUFFER: collections.deque = collections.deque(maxlen=100)
_LOCK   = threading.Lock()
_meta_control: str = "normal"  # "pause" | "go_deeper" | "normal"

# Phase → colour hint (consumed by the frontend for colour coding)
PHASE_COLORS: Dict[str, str] = {
    "drafting":          "#58a6ff",   # blue
    "critiquing":        "#d29922",   # amber
    "revising":          "#d29922",   # amber
    "deciding":          "#bc8cff",   # purple
    "executing":         "#3fb950",   # green
    "cycle_start":       "#8b949e",   # grey
    "function_selected": "#8b949e",   # grey
    "planning":          "#58a6ff",   # blue
    "memory_update":     "#da3633",   # red
    "goal_pursuit":      "#3fb950",   # green
    "inner_loop":        "#58a6ff",   # blue
    "outcome":           "#a78bfa",   # violet — delayed reward resolved
}


def emit_thought(
    phase: str,
    summary: str,
    *,
    full_trace: str = "",
    scratchpad_snippet: str = "",
    depth: int = 1,
    meta_decision: str = "",
    goal: str = "",
    cycle: int = 0,
) -> None:
    """
    Emit a cognitive event to the in-memory buffer and the dashboard SSE stream.
    Safe to call from any thread; degrades silently if dashboard isn't running.
    """
    entry: Dict[str, Any] = {
        "ts":                 time.time(),
        "phase":              phase,
        "color":              PHASE_COLORS.get(phase, "#8b949e"),
        "summary":            (summary or "")[:200],
        "full_trace":         (full_trace or "")[:1200],
        "scratchpad_snippet": (scratchpad_snippet or "")[:500],
        "depth":              depth,
        "meta_decision":      meta_decision,
        "goal":               (goal or "")[:100],
        "cycle":              cycle,
    }

    with _LOCK:
        _BUFFER.append(entry)
    # The legacy dashboard SSE push was removed with the old dashboard/ UI.
    # The in-memory _BUFFER above still backs get_recent_thoughts(); wire the new
    # UI explicitly via backend.telemetry_bridge if you want thoughts streamed.


def get_recent_thoughts(n: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent n thought entries (oldest first)."""
    with _LOCK:
        buf = list(_BUFFER)
    return buf[-n:]


# ── Meta control ─────────────────────────────────────────────────────────────

def set_meta_control(cmd: str) -> None:
    """
    Set the meta control signal. Called by /api/meta_control in server.py.
    cmd: "pause" | "go_deeper" | "resume" (resume = "normal")
    """
    global _meta_control
    _meta_control = "normal" if cmd == "resume" else cmd


def get_meta_control() -> str:
    return _meta_control


def consume_meta_control() -> str:
    """
    Read the current control signal.  Called once per cycle by meta_controller.decide().
    "pause"     — sticky: keeps returning "pause" until "resume" is sent.
    "go_deeper" — one-shot: resets to "normal" after being consumed once.
    """
    global _meta_control
    cmd = _meta_control
    if cmd != "pause":
        _meta_control = "normal"
    return cmd
