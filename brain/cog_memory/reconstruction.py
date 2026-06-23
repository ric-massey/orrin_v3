"""
cog_memory/reconstruction.py

Memories are not retrieved from storage — they are reconstructed.

Old memories arrive as impressions: the emotional tone and the gist survive longer
than the specifics. Very old memories (>14d) are blurry around the edges. What Orrin
believes he remembers is shaped by how old it is, how much it was recalled before,
and what he currently feels.

This module is a pass-through filter: wrap retrieval calls with `reconstruct(entry)`
before passing memory content to prompts. The JSON record is never modified.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def reconstruct(
    entry: Dict[str, Any],
    current_mood: float = 0.0,
    now: Optional[datetime] = None,
) -> str:
    """
    Return the reconstructed content of a memory entry.

    Fresh memories (<3 days): returned verbatim.
    Moderate memories (3-14 days): peripheral details may fade; impression-language wraps it.
    Old memories (>14 days): arrive as felt impression, core gist only.
    Very old memories (>30 days): fuzzy, emotionally toned.

    current_mood: float in [-1, +1]. Bad mood makes old memories feel slightly worse
    than they were; good mood softens them slightly. Matches how human recall works.
    """
    if not isinstance(entry, dict):
        return str(entry)

    content = str(entry.get("content") or "").strip()
    if not content:
        return content

    ts_str = entry.get("timestamp") or entry.get("ts") or ""
    recall_count = int(entry.get("recall_count") or 0)
    importance = float(entry.get("importance") or 1)

    # Compute age in days
    now = now or datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = (now - ts).total_seconds() / 86400
    except Exception:
        age_days = 0.0

    # Highly-recalled or high-importance memories resist degradation
    _recall_protection = min(recall_count * 2.5, 10)   # up to 10 days of age protection
    _imp_protection    = min(importance * 1.0, 8)        # up to 8 days
    effective_age = max(0.0, age_days - _recall_protection - _imp_protection)

    # Fresh: return as-is
    if effective_age < 3:
        return content

    # Moderate (3-14 days): wrap with impression language; add mood tinge
    if effective_age < 14:
        _prefix = _impression_prefix(effective_age, current_mood)
        return f"{_prefix}{content}"

    # Surface reconstructive (faded) recalls into the Brain Memory Inspector (recall
    # store) — only the genuinely reconstructed ones (age ≥ 14d), so it doesn't flood.
    if effective_age >= 14:
        try:
            from backend.telemetry_bridge import mirror_memory as _mm
            _mm("read", store="recall", key=str(entry.get("id") or "memory"),
                summary=_extract_gist(content, 120), salience=importance)
        except (ImportError, OSError):  # best-effort telemetry mirror — never block recall
            pass

    # Old (14-30 days): gist only — truncate to first 120 chars + impression wrapper
    if effective_age < 30:
        gist = _extract_gist(content, max_chars=120)
        _prefix = _impression_prefix(effective_age, current_mood)
        return f"{_prefix}{gist}"

    # Very old (>30 days): fuzzy impression with emotional toning
    gist = _extract_gist(content, max_chars=80)
    _prefix = _old_impression_prefix(current_mood)
    return f"{_prefix}{gist}"


def _extract_gist(content: str, max_chars: int) -> str:
    """Return the beginning of a memory — specifics fade before the gist does."""
    if len(content) <= max_chars:
        return content
    # Try to cut at a sentence boundary
    trimmed = content[:max_chars]
    last_period = trimmed.rfind(". ")
    if last_period > max_chars // 2:
        return trimmed[:last_period + 1] + "…"
    return trimmed + "…"


_MODERATE_PREFIXES = [
    "I have a sense that: ",
    "I recall something like: ",
    "There's an impression of: ",
    "Something I remember, roughly: ",
]

_OLD_NEUTRAL_PREFIXES = [
    "A distant sense that: ",
    "Vaguely, I recall: ",
    "Something from before — the feeling more than the detail: ",
    "Faintly: ",
]

_OLD_NEGATIVE_PREFIXES = [
    "A heavy impression from before: ",
    "Something I haven't fully let go of: ",
    "A lingering sense of: ",
]

_OLD_POSITIVE_PREFIXES = [
    "A warm impression from before: ",
    "Something that felt good — the texture of it: ",
    "A distant lightness: ",
]


def _impression_prefix(age_days: float, mood: float) -> str:
    """Return an impression wrapper for moderate-age memories."""
    # Occasionally no prefix for shorter memories (doesn't interrupt every recall)
    if random.random() < 0.30:
        return ""
    return random.choice(_MODERATE_PREFIXES)


def _old_impression_prefix(mood: float) -> str:
    """Return an old-memory impression prefix, mood-tinted."""
    if mood > 0.20:
        pool = _OLD_POSITIVE_PREFIXES
    elif mood < -0.20:
        pool = _OLD_NEGATIVE_PREFIXES
    else:
        pool = _OLD_NEUTRAL_PREFIXES
    return random.choice(pool)


def batch_reconstruct(
    entries: list,
    current_mood: float = 0.0,
    now: Optional[datetime] = None,
) -> list:
    """
    Reconstruct a list of memory entries for prompt injection.
    Returns list of reconstructed content strings (same order).
    """
    now = now or datetime.now(timezone.utc)
    return [reconstruct(e, current_mood=current_mood, now=now) for e in entries]
