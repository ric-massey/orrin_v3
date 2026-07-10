"""P3 (Companion & Presence plan): the shared host situation as nameable signals.

Extracted from loop/sense.py (which reads the sensory field each cycle). The two
situations — den-crowded (disk) and machine-pinned (CPU/RAM) — are injected as
raw signals strong enough to compete for ignition (the deliberation gate's B1
habituation keeps an unchanged reading from jamming it), and each carries the
CONCRETE host metric so speech can name the cause, not just the feeling (R3's
join, at the source). Only den-local host readings are ever read here.
"""
from __future__ import annotations

from typing import Any, Dict

Context = Dict[str, Any]

_DISK_CROWDED_PCT = 90.0
_CPU_PINNED_PCT = 85.0
_MEM_PINNED_PCT = 88.0


def inject_host_situation_signals(context: Context, sensory_field: Dict[str, Any]) -> None:
    """Append den_crowded / machine_pinned raw signals when the host crosses the
    situation thresholds. Mutates context["raw_signals"] in place; never raises
    beyond what the caller's fail-safe already catches."""
    sys_vitals = sensory_field.get("system") or {}
    disk = float(sys_vitals.get("disk_percent", 0) or 0)
    cpu = float(sys_vitals.get("cpu_percent", 0) or 0)
    mem = float(sys_vitals.get("memory_percent", 0) or 0)

    if disk >= _DISK_CROWDED_PCT:
        context.setdefault("raw_signals", []).append({
            "source": "sensory_stream",
            "content": f"The disk is {disk:.0f}% full — my den is getting cramped.",
            "signal_strength": min(0.80, 0.62 + (disk - _DISK_CROWDED_PCT) * 0.018),
            "tags": ["environment", "host", "den_crowded", "home", "internal"],
            "host_metric": {"name": "disk_percent", "value": disk},
        })
    if cpu >= _CPU_PINNED_PCT or mem >= _MEM_PINNED_PCT:
        pinned_by_cpu = cpu >= _CPU_PINNED_PCT
        which = f"CPU at {cpu:.0f}%" if pinned_by_cpu else f"memory at {mem:.0f}%"
        context.setdefault("raw_signals", []).append({
            "source": "sensory_stream",
            "content": f"The machine is pinned — {which}. Everything I do costs more right now.",
            "signal_strength": 0.62,
            "tags": ["environment", "host", "machine_pinned", "home", "internal"],
            "host_metric": {"name": "cpu_percent" if pinned_by_cpu else "memory_percent",
                             "value": cpu if pinned_by_cpu else mem},
        })
