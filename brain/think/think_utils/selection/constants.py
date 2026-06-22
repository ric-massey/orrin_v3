"""Shared leaf constants for selection (Phase 4D, from select_function.py).

Pure data imported by both the core selector and the extracted scoring layer,
so they live here to keep those modules acyclic.
"""
from __future__ import annotations

FALLBACK_ACTIONS = ["reflect_on_self_beliefs", "assess_goal_progress", "consolidate_from_long_memory"]
