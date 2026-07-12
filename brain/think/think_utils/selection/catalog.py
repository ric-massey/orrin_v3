"""Selection catalog / manifest + learned-stats loading (Phase 4D, from
select_function.py).

The dependency base of the selector: the capability-manifest cache + loaders
(_load_manifest, _capability_descriptions, _fns_tagged, _tag_weights,
_tagged_or) and the learned decision-stats cache (_learned_stats). Nothing here
depends on the selector's tag-derived frozenset constants, so it sits cleanly
below them with no import cycle. The cache dicts are module singletons; readers
in select_function import the same objects, so mutations stay coherent.
"""
from __future__ import annotations

import time as _time
from pathlib import Path as _Path
from typing import Any, Dict, cast

from brain.paths import DATA_DIR as _DATA_DIR
from brain.utils.failure_counter import record_failure


# Learned decision stats are RUNTIME state and must resolve through brain.paths
# (ORRIN_DATA_DIR-aware). The old __file__ anchoring read the live brain/data
# tree even under test isolation, so a life's learned stats leaked into the
# selector goldens (look_outward devalued by Run 6 flipped a pinned decision).
_STATS_PATH = _DATA_DIR / "decision_stats.json"
_STATS_CACHE: Dict[str, Any] = {"t": 0.0, "data": {}}
# The capability manifest is a COMMITTED seed read from the repo tree on
# purpose (parents[3]: this module lives one level deeper than the
# select_function.py these paths came from) — it ships with the code.
_CAPS_PATH = _Path(__file__).resolve().parents[3] / "data" / "capability_descriptions.json"
_CAPS_CACHE: Dict[str, Any] = {"t": 0.0, "data": {}, "tags": {}}


def _load_manifest() -> None:
    """Parse capability_descriptions.json into the cache. Phase 4 extended the
    file from {fn: "desc"} into a manifest {fn: {"desc": ..., "tags": [...]}}
    — both formats are accepted so older data files keep working. Weighted tags
    use a "name:0.15" suffix (e.g. the emo-mode boosts)."""
    import json as _json
    d = _json.loads(_CAPS_PATH.read_text("utf-8"))
    descs: Dict[str, str] = {}
    tags: Dict[str, Dict[str, float]] = {}   # tag → {fn: weight} (weight 1.0 when untagged)
    for fn, v in d.items():
        if isinstance(v, str):
            if v:
                descs[fn] = v
            continue
        if not isinstance(v, dict):
            continue
        desc = v.get("desc")
        if isinstance(desc, str) and desc:
            descs[fn] = desc
        for t in (v.get("tags") or []):
            if not isinstance(t, str) or not t:
                continue
            name, _, w = t.partition(":")
            try:
                weight = float(w) if w else 1.0
            except ValueError:
                weight = 1.0
            tags.setdefault(name, {})[fn] = weight
    _CAPS_CACHE["data"] = descs
    _CAPS_CACHE["tags"] = tags
    _CAPS_CACHE["t"] = _time.time()


def _capability_descriptions() -> Dict[str, str]:
    """Curated {fn_name: goal-prose capability description} (fn_selection_fix_v2
    §4.3). Shared by Phase 3a (executive semantic step→fn match) and Phase 3b
    (deliberate goal recruitment). Matching goals against this CURATED text —
    not raw docstrings — is the E5 fix for the docstring↔goal-prose mismatch that
    kept the executive lane stuck at 8 reachable functions. Cached ~60s; fails
    open to {} so a missing/broken file degrades to the keyword fallbacks."""
    if _time.time() - _CAPS_CACHE["t"] < 60.0 and _CAPS_CACHE["data"]:
        return cast(Dict[str, str], _CAPS_CACHE["data"])
    try:
        _load_manifest()
    except Exception as exc:
        record_failure("select_function.capability_descriptions", exc)
        _CAPS_CACHE["data"] = _CAPS_CACHE["data"] or {}
    return cast(Dict[str, str], _CAPS_CACHE["data"])


def _fns_tagged(*tag_names: str) -> frozenset[str]:
    """Union of functions carrying ANY of `tag_names` in the capability manifest
    (Phase 4). Empty when the manifest is missing/untagged — callers must pair
    with a literal fallback via _tagged_or so a broken data file can never
    collapse selection behavior."""
    try:
        if _time.time() - _CAPS_CACHE["t"] >= 60.0 or not _CAPS_CACHE["data"]:
            _load_manifest()
    except Exception as exc:
        record_failure("select_function.capability_tags", exc)
    out: set[str] = set()
    tags = _CAPS_CACHE.get("tags") or {}
    for t in tag_names:
        out.update((tags.get(t) or {}).keys())
    return frozenset(out)


def _tag_weights(tag_name: str) -> Dict[str, float]:
    """{fn: weight} for a weighted tag (e.g. "emo_focused:0.15" entries)."""
    try:
        if _time.time() - _CAPS_CACHE["t"] >= 60.0 or not _CAPS_CACHE["data"]:
            _load_manifest()
    except Exception as exc:
        record_failure("select_function.capability_tag_weights", exc)
    return dict((_CAPS_CACHE.get("tags") or {}).get(tag_name) or {})


def _tagged_or(tag_names: tuple[str, ...], default: frozenset[str]) -> frozenset[str]:
    """Tag-derived set with a literal fallback: the manifest is the source of
    truth (a newly tagged function participates automatically), but if it is
    missing or carries none of these tags, the in-code literal set still
    governs — selection never degrades on a bad data file."""
    derived = _fns_tagged(*tag_names)
    return derived if derived else default


def _learned_stats() -> Dict[str, Dict[str, float]]:
    if _time.time() - _STATS_CACHE["t"] < 15.0 and _STATS_CACHE["data"]:
        return cast(Dict[str, Dict[str, float]], _STATS_CACHE["data"])
    try:
        import json as _json
        d = _json.loads(_STATS_PATH.read_text("utf-8"))
        _STATS_CACHE["data"] = {
            k: {"avg_reward": float(v.get("avg_reward", 0.5) or 0.5),
                "count": int(v.get("count", 0) or 0)}
            for k, v in d.items() if isinstance(v, dict)
        }
        _STATS_CACHE["t"] = _time.time()
    except Exception as exc:
        record_failure("select_function.learned_stats", exc)
    return cast(Dict[str, Dict[str, float]], _STATS_CACHE["data"])
