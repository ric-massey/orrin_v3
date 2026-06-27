# cognition/associative_memory.py
#
# Memories surface without being asked.
#
# Each cycle, current context — emotional state, recent working memory,
# time of day — is scored against long memory. High-resonance entries
# surface to working memory with probability proportional to their score.
#
# Orrin didn't retrieve it. It arrived.
#
# Scoring:
#   emotional_resonance  — memory's emotion tag matches current dominant state
#   semantic_overlap     — words shared with recent WM entries
#   temporal_resonance   — same hour-of-day or day-of-week as when formed
#   recency_decay        — older memories need stronger signal to break through

from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import LONG_MEMORY_FILE, WORKING_MEMORY_FILE


_SURFACE_COOLDOWN_S = 900.0    # minimum gap between spontaneous surfacings
_MIN_SCORE          = 0.20     # nothing surfaces below this
_BASE_SURFACE_PROB  = 0.18     # base probability when score meets minimum
_SAMPLE_SIZE        = 50       # memories scored per cycle (cap for performance)

_last_surface_ts:  float          = 0.0
_last_surfaced_id: Optional[str]  = None   # avoid repeating the same memory twice


# ── Emotion families ───────────────────────────────────────────────────────────
# Memories resonate even when the emotion doesn't match exactly —
# impasse_signal and social_penalty are neighbors; exploration_drive and excitement are kin.

_EMOTION_FAMILIES: List[frozenset] = [
    frozenset({"impasse_signal", "conflict_signal", "irritation", "social_penalty"}),
    frozenset({"risk_estimate", "threat_level", "worry", "uncertainty"}),
    frozenset({"exploration_drive", "wonder", "interest", "excitement", "anticipation"}),
    frozenset({"melancholy", "negative_valence", "loss_signal", "social_deficit"}),
    frozenset({"expected_gain", "optimism", "relief"}),
    frozenset({"satisfaction", "pride", "confidence", "positive_valence", "contentment"}),
    frozenset({"urgency", "motivation", "determination"}),
]


def _emotion_resonance(mem_emotion: str, current_core: Dict) -> float:
    """
    How much does this memory's single emotion tag resonate with current state?
    - Exact match on a currently-dominant emotion: 0.9
    - Same family as a currently-dominant emotion: 0.5
    - No match: 0.0
    """
    if not mem_emotion or not current_core:
        return 0.0

    mem_emo = mem_emotion.lower().strip()

    # Find current dominant emotions (above a meaningful threshold)
    dominant = {k for k, v in current_core.items()
                if isinstance(v, (int, float)) and float(v) >= 0.30}

    if not dominant:
        return 0.0

    # Exact match
    if mem_emo in dominant:
        # Scale by how strong that emotion is right now
        strength = float(current_core.get(mem_emo) or 0.3)
        return min(0.9, 0.5 + strength * 0.4)

    # Family match — find which family mem_emo belongs to
    mem_family = None
    for fam in _EMOTION_FAMILIES:
        if mem_emo in fam:
            mem_family = fam
            break

    if mem_family:
        # Check if any dominant emotion shares the family
        overlap = dominant & mem_family
        if overlap:
            best_strength = max(float(current_core.get(e) or 0.3) for e in overlap)
            return min(0.5, 0.25 + best_strength * 0.25)

    return 0.0


def _semantic_overlap(mem_content: str, wm_words: frozenset) -> float:
    """Fraction of significant WM words that appear in memory content."""
    if not wm_words or not mem_content:
        return 0.0
    mem_words = frozenset(mem_content.lower().split())
    overlap = wm_words & mem_words
    return min(1.0, len(overlap) / max(len(wm_words), 6))


def _temporal_resonance(mem_ts: str) -> float:
    """Small bonus for memories formed at the same time of day or day of week."""
    if not mem_ts:
        return 0.0
    try:
        mem_dt = datetime.fromisoformat(str(mem_ts))
        if not mem_dt.tzinfo:
            mem_dt = mem_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hour_match = abs(mem_dt.hour - now.hour) <= 1
        dow_match  = mem_dt.weekday() == now.weekday()
        return 0.22 if hour_match else (0.10 if dow_match else 0.0)
    except (ValueError, TypeError):  # intentional: bad timestamp → no temporal resonance
        return 0.0


def _recency_decay(mem_ts: str) -> float:
    """
    Multiplier [0.4..1.0]. Old memories need stronger signal to surface.
    Fresh (<1 day): 1.0 · 1 week: ~0.80 · 1 month: ~0.65 · 3 months: ~0.55
    """
    if not mem_ts:
        return 0.7
    try:
        mem_dt = datetime.fromisoformat(str(mem_ts))
        if not mem_dt.tzinfo:
            mem_dt = mem_dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - mem_dt).total_seconds() / 86400
        return max(0.4, 1.0 - 0.08 * math.log1p(age_days))
    except (ValueError, TypeError):  # intentional: bad timestamp → neutral decay
        return 0.7


def _score(memory: Dict, current_core: Dict, wm_words: frozenset) -> float:
    er    = _emotion_resonance(memory.get("emotion", ""), current_core)
    so    = _semantic_overlap(str(memory.get("content") or ""), wm_words)
    tr    = _temporal_resonance(memory.get("timestamp") or memory.get("created_at") or "")
    decay = _recency_decay(memory.get("timestamp") or memory.get("created_at") or "")
    raw   = (er * 0.55) + (so * 0.30) + (tr * 0.15)
    return round(raw * decay, 4)


# ── WM word extraction ─────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "it", "in", "on", "at", "to", "of", "and",
    "or", "but", "not", "i", "me", "my", "we", "our", "you", "he", "she",
    "they", "was", "are", "be", "been", "being", "have", "has", "had",
    "do", "did", "will", "would", "could", "should", "for", "with", "as",
    "this", "that", "from", "by", "about", "so", "if", "what", "when",
    "how", "which", "who", "just", "now", "then", "there", "here", "s",
    "chose", "last", "active", "orrin", "cycle", "action", "reward",
})


def _wm_words(n_recent: int = 6) -> frozenset:
    """Pull significant words from recent working memory entries."""
    try:
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        if not isinstance(wm, list):
            return frozenset()
        recent = wm[-n_recent:]
        words: set = set()
        for entry in recent:
            text = str(entry.get("content") or "") if isinstance(entry, dict) else str(entry)
            for w in text.lower().split():
                clean = w.strip(".,!?;:\"'()[]{}—-").strip()
                if len(clean) > 3 and clean not in _STOPWORDS:
                    words.add(clean)
        return frozenset(words)
    except Exception as exc:  # WM read failed — record, no association words
        record_failure("associative_memory._wm_words", exc)
        return frozenset()


# ── Spontaneous surfacing (background, per-cycle) ──────────────────────────────

def maybe_surface_association(context: Dict[str, Any]) -> Optional[str]:
    """
    Called each cycle from finalize.py. May write one memory to WM.
    Returns the content string if something surfaced, else None.
    """
    global _last_surface_ts, _last_surfaced_id

    now = time.time()
    if now - _last_surface_ts < _SURFACE_COOLDOWN_S:
        return None

    try:
        memories = load_json(LONG_MEMORY_FILE, default_type=list) or []
        if not isinstance(memories, list) or len(memories) < 2:
            return None

        emo = context.get("affect_state") or {}
        current_core = emo.get("core_signals") or emo
        if not isinstance(current_core, dict):
            current_core = {}

        words = _wm_words()

        sample = memories if len(memories) <= _SAMPLE_SIZE else random.sample(memories, _SAMPLE_SIZE)

        best_score = _MIN_SCORE - 0.001
        best_mem   = None
        best_id    = None

        for mem in sample:
            if not isinstance(mem, dict):
                continue
            mem_id = str(mem.get("id") or mem.get("timestamp") or id(mem))
            if mem_id == _last_surfaced_id:
                continue
            s = _score(mem, current_core, words)
            if s > best_score:
                best_score = s
                best_mem   = mem
                best_id    = mem_id

        if best_mem is None or best_score < _MIN_SCORE:
            return None

        # Probabilistic gate — higher score → more likely to surface
        prob = min(0.75, _BASE_SURFACE_PROB + (best_score - _MIN_SCORE) * 0.9)
        if random.random() > prob:
            return None

        content = str(best_mem.get("content") or "").strip()
        if not content:
            return None
        if len(content) > 300:
            content = content[:297] + "..."

        update_working_memory({
            "content": f"[memory] {content}",
            "event_type": "associative_memory",
            "importance": 2,
            "priority": 2,
        })

        _last_surface_ts  = now
        _last_surfaced_id = best_id
        log_private(
            f"[associative_memory] surfaced (score={best_score:.3f} "
            f"emo={best_mem.get('emotion','?')}): {content[:80]}"
        )
        return content

    except Exception as e:
        log_private(f"[associative_memory] error: {e}")
        return None


# ── Deliberate recall (cognition function) ─────────────────────────────────────

def associative_recall(context: Dict[str, Any]) -> str:
    """
    Orrin deliberately opens to associative recall — not searching for anything
    specific, just letting the current state draw something forward.

    Unlike maybe_surface_association: bypasses the cooldown, scores more
    memories, and surfaces up to 2 results. Writes to WM.
    """
    try:
        memories = load_json(LONG_MEMORY_FILE, default_type=list) or []
        if not isinstance(memories, list) or not memories:
            return "nothing surfaced"

        emo = context.get("affect_state") or {}
        current_core = emo.get("core_signals") or emo
        if not isinstance(current_core, dict):
            current_core = {}

        words = _wm_words(n_recent=10)

        sample = memories if len(memories) <= 80 else random.sample(memories, 80)

        scored: List[tuple] = []
        for mem in sample:
            if not isinstance(mem, dict):
                continue
            s = _score(mem, current_core, words)
            if s >= 0.12:
                scored.append((s, mem))

        if not scored:
            return "nothing surfaced"

        scored.sort(key=lambda x: x[0], reverse=True)
        surfaced = 0

        for s, mem in scored[:2]:
            content = str(mem.get("content") or "").strip()
            if not content:
                continue
            if len(content) > 280:
                content = content[:277] + "..."
            update_working_memory({
                "content": f"[memory] {content}",
                "event_type": "associative_memory",
                "importance": 2,
                "priority": 2,
            })
            log_private(
                f"[associative_memory] deliberate recall (score={s:.3f} "
                f"emo={mem.get('emotion','?')}): {content[:80]}"
            )
            surfaced += 1

        return f"surfaced {surfaced} association(s)" if surfaced else "nothing surfaced"

    except Exception as e:
        log_private(f"[associative_memory] recall error: {e}")
        return "error during recall"
