"""
brain/evidence — the Life Capsule (Autopsy Engine).

One run → one self-describing evidence file. See
`brain/evidence/life_capsule.py` and
`docs/Behavioral Evaluation & Runtime Diagnostics/ORRIN_LIFE_CAPSULE_PLAN_2026-06-18.md`.
"""
from __future__ import annotations

from .life_capsule import build_life_capsule, CAPSULE_SCHEMA_VERSION

__all__ = ["build_life_capsule", "CAPSULE_SCHEMA_VERSION"]
