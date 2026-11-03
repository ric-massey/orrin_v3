"""Duplicate detection for long memory: which event types recur, and the key two
entries share when they are the same memory. Split out of long_memory.py
(2026-11-02, module size); long_memory imports every name back."""
from __future__ import annotations

import re

DUPLICATE_WINDOW: int = 10        # Number of recent entries to check for duplicates

# High-volume, low-information event types that recur as exact/near-duplicates and
# slip past the 10-entry exact-match dedup window (verified: 'chunk' and
# 'file_search' dominate long_memory.json with identical blocks). For these we scan
# a much wider window and compare on a content prefix so repeats collapse.
_REPETITIVE_EVENT_TYPES = frozenset({
    "chunk", "file_search", "world_perception", "dream_insight", "body_sense_pattern",
    # Respawn-loop floods (DATA_FILE_AUDIT 2026-06-11 §4): identical intrinsic
    # goals, commitments, and metacog observations recur slower than the
    # 10-entry default window, so they need the wide prefix-match window too.
    "intrinsic_goal", "commitment", "metacog_pattern",
    # AR6 (audit M1): known-periodic instrumentation — the same event recurring
    # with only its numbers changed (mismatch=0.42 vs 0.43) slipped the prefix
    # match and piled up 34–39 copies each, evicting real findings.
    "prediction_error", "introspection_miss",
})
_REPETITIVE_DEDUP_WINDOW: int = 200
_REPETITIVE_PREFIX: int = 120

# AR6: digits are noise for periodic-event identity — normalize them out of the
# dedup key so a recurring entry can't slip the window by carrying a fresh number.
_DEDUP_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# Memory/goal ids are hex, not digits ("Top: mem:87cdd22d; mem:aa800956"), so the
# digit rule left every self-search unique: smoke life 4 kept 45 copies of one
# '[self_search] Query: …' line (2026-11-02). Normalised before the digits.
_DEDUP_ID_RE = re.compile(r"\b(?:mem:|g_|vec_)?(?=[0-9a-f]*\d)[0-9a-f]{6,}\b")


_DEDUP_ID_RUN_RE = re.compile(r"#id(?:[;,]\s*#id)*")


def _dedup_key(event_type: str, content: str) -> str:
    if event_type in _REPETITIVE_EVENT_TYPES:
        # Normalise the whole text before taking the prefix: cutting first split an
        # id in half ("mem:#fde"), and how many ids a line lists varies.
        k = _DEDUP_ID_RUN_RE.sub("#ids", _DEDUP_ID_RE.sub("#id", content))
        return _DEDUP_NUM_RE.sub("#", k)[:_REPETITIVE_PREFIX]
    return content


def _dedup_window_for(event_type: str) -> int:
    return _REPETITIVE_DEDUP_WINDOW if event_type in _REPETITIVE_EVENT_TYPES else DUPLICATE_WINDOW
