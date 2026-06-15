"""
utils/resource_ceilings.py — the disk ceiling Orrin's forgetting respects (§10.3).

The user caps how big his MIND may grow (the data dir, not the whole disk). The
forgetting machinery treats that cap as a target: when his mind exceeds it, the
dream-cycle forgetting calls enforce_disk_ceiling(), which trims the SAFE, growable,
append-only stores (rolling logs, the conscious stream, dream/forgetting ledgers) back
under budget. Semantic memory eviction stays the memory system's importance-based job;
this is the bounded-log discipline already used across the codebase, aimed at a ceiling.

Life Support (§9.10) shows current usage against this ceiling, not the raw disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from paths import DATA_DIR

_GB = 1024 ** 3

# Growable, non-semantic stores it's safe to trim under pressure, with the cap to
# trim each to (entries for JSON lists, lines for .jsonl). Ordered biggest-bang first.
_TRIMMABLE_JSON_LISTS = {
    "conscious_stream.json": 2000,
    "dream_log.json": 500,
    "symbolic_dream_log.json": 500,
    "forgetting_log.json": 1000,
    "egress_log.jsonl": 3000,  # also handled by egress itself; double-safe
}
_TRIMMABLE_JSONL = {
    "trace.jsonl": 2000,
    "events.jsonl": 2000,
}


def disk_ceiling_gb() -> float:
    """The configured ceiling in GB — env override wins (ORRIN_DISK_CEILING_GB), else
    the config.json pref, else 5."""
    env = os.getenv("ORRIN_DISK_CEILING_GB")
    if env:
        try:
            return float(env)
        except Exception:
            pass
    try:
        from utils.prefs import get as _pref
        return float(_pref("disk_ceiling_gb", 5))
    except Exception:
        return 5.0


def disk_ceiling_bytes() -> int:
    return int(disk_ceiling_gb() * _GB)


def data_dir_bytes() -> int:
    """Total bytes of Orrin's mind on disk (the data dir) — what the ceiling bounds."""
    total = 0
    try:
        for f in DATA_DIR.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except Exception:
                continue
    except Exception:
        pass
    return total


def usage() -> Dict[str, Any]:
    """Ceiling usage for Life Support: bytes used by his mind, the ceiling, and the
    ratio (0..1+)."""
    used = data_dir_bytes()
    ceil = disk_ceiling_bytes()
    return {"used_bytes": used, "ceiling_bytes": ceil, "ratio": (used / ceil) if ceil > 0 else 0.0}


def over_disk_ceiling() -> bool:
    return data_dir_bytes() > disk_ceiling_bytes()


def _trim_json_list(path: Path, keep: int) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and len(data) > keep:
            removed = len(data) - keep
            path.write_text(json.dumps(data[-keep:]), encoding="utf-8")
            return removed
    except Exception:
        pass
    return 0


def enforce_disk_ceiling() -> Dict[str, Any]:
    """If his mind is over the disk ceiling, trim the safe growable stores back toward
    budget. A no-op when under the ceiling (so it costs nothing in the common case).
    Returns a small report for the forgetting log."""
    if not over_disk_ceiling():
        return {"over": False, "trimmed": {}}
    trimmed: Dict[str, int] = {}
    for name, keep in _TRIMMABLE_JSON_LISTS.items():
        n = _trim_json_list(DATA_DIR / name, keep)
        if n:
            trimmed[name] = n
    try:
        from utils.json_utils import cap_jsonl
        for name, max_lines in _TRIMMABLE_JSONL.items():
            p = DATA_DIR / name
            if p.exists():
                cap_jsonl(p, max_lines=max_lines)
                trimmed.setdefault(name, max_lines)
    except Exception:
        pass
    return {"over": True, "trimmed": trimmed, "usage": usage()}
