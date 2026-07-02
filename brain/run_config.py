"""Run configuration: per-run subsystem ablation flags + the run stamp (P7 / A2).

The ablation panel's contract: every run declares which subsystems were live,
each subsystem checks its flag at its OWN entry point (fail-safe: ablated means
no-op, never an exception), and the run is stamped with its config in the Life
Capsule so traces are comparable across configurations.

Sources, in override order:
  1. env `ORRIN_ABLATE` — comma-separated subsystem names (e.g. "memory,goals")
  2. `data/run_config.json` — `{"ablate": ["memory", ...]}` (what the UI panel
     writes; read at boot for the NEXT run)
Unknown names are ignored (a typo must not silently ablate something else — it
ablates nothing). All subsystems default ON.

Read once at first use and cached for the life of the process — flags are
boot-time by design (mid-run toggling would make traces unattributable).
`reload()` exists for tests.
"""
from __future__ import annotations

import json
import os
from typing import Dict, FrozenSet, List, Optional, Tuple

SUBSYSTEMS: Tuple[str, ...] = (
    "memory",              # long-term recall injection (reflect.integrate_recall_and_baseline)
    "goals",               # committed-goal pull (sense → goal_io.committed_goals_v1)
    "signals",             # affect/control-signal update (sense → update_signal_state)
    "workspace",           # global-workspace competition (deliberate → update_workspace)
    "metacognition",       # metacog channel (metacog_init / metacog_note)
    "host_coupling",       # host resource sensing (host_resource_monitor)
    "idle_consolidation",  # dream/replay cycle (should_consolidate / idle_consolidation_cycle)
    "llm_tools",           # LLM-as-tool calls (generate_response)
    "research_tools",      # web research (research_topic / fetch_and_read)
    "persistence",         # durable JSON writes (json_utils.save_json) — amnesic run
)

_cached: Optional[FrozenSet[str]] = None


def _read_ablated() -> FrozenSet[str]:
    names: List[str] = []
    env = os.environ.get("ORRIN_ABLATE", "")
    if env.strip():
        names = [x.strip().lower() for x in env.split(",")]
    else:
        try:
            from brain.paths import DATA_DIR
            cfg = json.loads((DATA_DIR / "run_config.json").read_text("utf-8"))
            raw = cfg.get("ablate") or []
            if isinstance(raw, list):
                names = [str(x).strip().lower() for x in raw]
        except Exception:
            names = []
    return frozenset(n for n in names if n in SUBSYSTEMS)


def ablated() -> FrozenSet[str]:
    global _cached
    if _cached is None:
        _cached = _read_ablated()
    return _cached


def reload() -> FrozenSet[str]:
    """Re-read the flags (tests / explicit boot refresh only)."""
    global _cached
    _cached = None
    return ablated()


def subsystem_enabled(name: str) -> bool:
    """The one question every subsystem entry point asks. Unknown names are ON
    (fail-safe: a rename can't silently ablate a live subsystem)."""
    return str(name).strip().lower() not in ablated()


def snapshot() -> Dict[str, bool]:
    """{subsystem: enabled} — written into Life Capsule provenance."""
    off = ablated()
    return {s: s not in off for s in SUBSYSTEMS}


def run_stamp(date: Optional[str] = None) -> str:
    """Human-readable run tag, e.g. `run_2026_07_01_all_on` or
    `run_2026_07_01_memory_off_goals_off`. Recoverable: the full per-subsystem
    map rides in provenance's `run_config`; the stamp names only what's OFF."""
    if date is None:
        import time
        date = time.strftime("%Y_%m_%d", time.gmtime())
    off = sorted(ablated())
    suffix = "_".join(f"{s}_off" for s in off) if off else "all_on"
    return f"run_{date}_{suffix}"
