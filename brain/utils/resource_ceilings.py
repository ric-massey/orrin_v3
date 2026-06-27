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

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure

_GB = 1024 ** 3

# Growable, non-semantic stores it's safe to trim under pressure, with the cap to
# trim each to (entries for JSON lists, lines for .jsonl). Ordered biggest-bang first.
_TRIMMABLE_JSON_LISTS = {
    "workspace_broadcast.json": 2000,
    "idle_consolidation_log.json": 500,
    "symbolic_idle_consolidation_log.json": 500,
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
        except (TypeError, ValueError):  # intentional: malformed env override → fall back
            pass
    try:
        from brain.utils.prefs import get as _pref
        return float(_pref("disk_ceiling_gb", 5))
    except Exception as exc:  # prefs unavailable/bad value — record, use default
        record_failure("resource_ceilings.disk_ceiling_gb", exc)
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
            except OSError:  # intentional: file vanished mid-walk / unreadable
                continue
    except Exception as exc:  # the data-dir walk failed entirely — record it
        record_failure("resource_ceilings.data_dir_bytes", exc)
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
    except Exception as exc:  # external I/O / bad JSON while trimming a store
        record_failure("resource_ceilings._trim_json_list", exc)
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
        from brain.utils.json_utils import cap_jsonl
        for name, max_lines in _TRIMMABLE_JSONL.items():
            p = DATA_DIR / name
            if p.exists():
                cap_jsonl(p, max_lines=max_lines)
                trimmed.setdefault(name, max_lines)
    except Exception as exc:  # external I/O while capping jsonl stores
        record_failure("resource_ceilings.enforce_disk_ceiling.jsonl", exc)
    return {"over": True, "trimmed": trimmed, "usage": usage()}


# ── Memory ceiling (§10.3) ───────────────────────────────────────────────────
# Advisory with a hard floor: the ML stack (torch + a resident embedder + spaCy) needs
# ~4 GB, so the pref warns below that rather than starving him. ABOVE the floor, this is
# where the ceiling earns its keep — when resident memory is over budget, evict the
# in-process caches (LLM response cache, embedding cache, provider) to give memory back.
# It never trims semantic memory and never kills the process; clearing caches only costs
# a little recompute.
def memory_ceiling_gb() -> float:
    env = os.getenv("ORRIN_MEMORY_CEILING_GB")
    if env:
        try:
            return float(env)
        except (TypeError, ValueError):  # intentional: malformed env override → fall back
            pass
    try:
        from brain.utils.prefs import get as _pref
        return float(_pref("memory_ceiling_gb", 4))
    except Exception as exc:  # prefs unavailable/bad value — record, use default
        record_failure("resource_ceilings.memory_ceiling_gb", exc)
        return 4.0


def memory_ceiling_bytes() -> int:
    return int(memory_ceiling_gb() * _GB)


def process_rss_bytes() -> int:
    """Resident set size of this process — what the memory ceiling bounds. 0 if psutil
    is unavailable (then the ceiling is a no-op rather than a guess)."""
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except Exception as exc:  # optional dep absent / probe failed — RSS unknown
        record_failure("resource_ceilings.process_rss_bytes", exc)
        return 0


def memory_usage() -> Dict[str, Any]:
    rss = process_rss_bytes()
    ceil = memory_ceiling_bytes()
    return {"rss_bytes": rss, "ceiling_bytes": ceil, "ratio": (rss / ceil) if ceil > 0 else 0.0}


def over_memory_ceiling() -> bool:
    rss = process_rss_bytes()
    return rss > 0 and rss > memory_ceiling_bytes()


def _evict_caches() -> List[str]:
    """Clear the safe-to-drop in-process caches. Each is best-effort and independent."""
    cleared: List[str] = []
    try:
        from brain.utils import generate_response as _gr
        _gr._GR_CACHE.clear()
        cleared.append("llm_response_cache")
    except Exception as exc:  # best-effort eviction — record if a cache won't clear
        record_failure("resource_ceilings._evict_caches.llm", exc)
    try:
        from brain.utils import embed_similarity as _es
        # The embedding cache is an lru_cache on _embed (up to 8192 vectors).
        _es._embed.cache_clear()
        cleared.append("embedding_cache")
    except Exception as exc:  # best-effort eviction — record if a cache won't clear
        record_failure("resource_ceilings._evict_caches.embedding", exc)
    try:
        from brain.utils import llm_providers as _p
        _p.reinit()
        cleared.append("provider")
    except Exception as exc:  # best-effort eviction — record if the provider won't reinit
        record_failure("resource_ceilings._evict_caches.provider", exc)
    return cleared


def enforce_memory_ceiling() -> Dict[str, Any]:
    """If resident memory is over the ceiling, evict in-process caches to give it back.
    No-op when under (the common case). Returns a small report."""
    if not over_memory_ceiling():
        return {"over": False, "evicted": []}
    return {"over": True, "evicted": _evict_caches(), "usage": memory_usage()}
