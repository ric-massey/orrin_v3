# brain/cognition/metabolism.py
#
# §7, mapping #1 — ABSOLUTE CAPACITY → METABOLISM. This is the first of the three
# mappings the whole design depends on keeping separate, and it is the one that is
# explicitly NOT a feeling.
#
# "Runs slower on a small machine" is not a degraded or sick Orrin — it is a smaller
# body with a slower metabolic rate. A shrew's heart runs ~600 bpm and an elephant's
# ~30 bpm; neither is in distress. A small machine simply slows the clock: longer
# between cognitive cycles, dreams and reading less often, smaller caches. Set from
# absolute capacity (the budget Orrin is granted, §11.3), NOT from how he "feels"
# (that is mapping #2, interoception) and NOT from absolute safety floors (mapping #3,
# the reflex).
#
# §8.4 — hysteresis. A machine hovering at a tier boundary would thrash
# fast/slow/fast/slow if the tier switched on a hard threshold, so the switches carry
# a dead band: you must cross a boundary by a margin before the tier changes, and the
# tier is sticky until you do.
from __future__ import annotations

from typing import Dict

from brain.core.runtime_log import get_logger
from brain.cognition.body_budget import budget_bytes, cpu_count

_log = get_logger(__name__)

_GB = float(1024 * 1024 * 1024)

# Tier boundaries on the GRANTED body size (budget_bytes), in GB. A body is sized by
# what the user granted Orrin, not by the raw machine — so dialing the slider down
# genuinely slows his metabolism (a smaller body), §11.3.
_TIER_ORDER = ("tiny", "small", "normal", "large")
_TIER_UPPER_GB = {"tiny": 1.5, "small": 3.0, "normal": 8.0}  # "large" = above the last
_HYSTERESIS_GB = 0.5  # §8.4 dead band: must cross a boundary by this much to switch

# Per-tier metabolic profile. cadence > 1 slows the cycle clock (small body, slow
# metabolism); < 1 speeds it up. heavy_freq scales how often the memory-hungry cycles
# (dream, reading) are allowed to fire. vector_cap is the resident vector-store ceiling.
_PROFILE = {
    "tiny":   {"cadence": 2.0, "heavy_freq": 0.4, "vector_cap_mb": 128,  "concurrency": 1},
    "small":  {"cadence": 1.4, "heavy_freq": 0.7, "vector_cap_mb": 256,  "concurrency": 1},
    "normal": {"cadence": 1.0, "heavy_freq": 1.0, "vector_cap_mb": 512,  "concurrency": 2},
    "large":  {"cadence": 0.8, "heavy_freq": 1.3, "vector_cap_mb": 1024, "concurrency": 4},
}

# Sticky current tier (hysteresis state). Recomputed lazily; cached so we don't
# resample on every cadence read.
_current_tier: str | None = None


def _raw_tier(gb: float) -> str:
    for t in ("tiny", "small", "normal"):
        if gb < _TIER_UPPER_GB[t]:
            return t
    return "large"


def _tier_with_hysteresis(gb: float, prev: str | None) -> str:
    """Pick a tier but resist flipping at a boundary (§8.4). Once in a tier, only
    leave it when the body size moves a full dead-band past the boundary."""
    raw = _raw_tier(gb)
    if prev is None or raw == prev:
        return raw
    pi, ri = _TIER_ORDER.index(prev), _TIER_ORDER.index(raw)
    # Moving UP a tier: require gb to exceed the prev tier's upper bound + dead band.
    if ri > pi:
        bound = _TIER_UPPER_GB.get(prev)
        if bound is not None and gb < bound + _HYSTERESIS_GB:
            return prev
    # Moving DOWN a tier: require gb to fall below the new tier's upper bound − dead band.
    else:
        bound = _TIER_UPPER_GB.get(raw)
        if bound is not None and gb > bound - _HYSTERESIS_GB:
            return prev
    return raw


def current_tier() -> str:
    global _current_tier
    gb = budget_bytes() / _GB
    _current_tier = _tier_with_hysteresis(gb, _current_tier)
    return _current_tier


def _profile() -> Dict:
    return _PROFILE[current_tier()]


def cadence_multiplier() -> float:
    """Multiply the base inter-cycle sleep by this. A small body thinks at a slower
    metabolic rate — not distress, just a smaller heart at a lower rate (§7)."""
    return float(_profile()["cadence"])


def heavy_cycle_frequency() -> float:
    """Scales how often dream/reading (the memory-hungry cycles) are permitted. A small
    body dreams less often because it cannot afford the footprint as frequently.

    DEFERRED — computed but NOT yet consumed (no callers). The dream cycle still fires
    on the fixed ~6h interval in ORRIN_loop.py, so dream/reading cadence does not yet
    scale with body size. Folding this into the dream/reading scheduler was kept out of
    the embodiment pass to avoid touching dream cadence logic (see PART X of
    docs/orrin_embodiment_architecture.md). Wire here when picking that up."""
    return float(_profile()["heavy_freq"])


def vector_store_cap_bytes() -> int:
    """DEFERRED — computed but NOT yet consumed (no callers). The vector store is not
    yet capped by metabolic tier, so a small body's memory footprint isn't bounded by
    this. Wire into the embedding/vector-store layer when picking up the deferred
    metabolism work (see heavy_cycle_frequency above)."""
    return int(_profile()["vector_cap_mb"]) * 1024 * 1024


def concurrency() -> int:
    return int(_profile()["concurrency"])


def metabolism_status() -> Dict:
    """Telemetry/UI view of the current metabolic tier and what it implies."""
    t = current_tier()
    p = _PROFILE[t]
    return {
        "tier": t,
        "cadence_multiplier": p["cadence"],
        "heavy_cycle_frequency": p["heavy_freq"],
        "vector_cap_mb": p["vector_cap_mb"],
        "concurrency": p["concurrency"],
        "budget_gb": round(budget_bytes() / _GB, 2),
        "cpu_count": cpu_count(),
    }
