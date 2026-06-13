from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, List
import uuid

from utils.affect_utils import detect_affect_keyword
from paths import LONG_MEMORY_FILE
from utils.embedder import get_embedding
from utils.json_utils import load_json, save_json
from utils.log import log_error, log_private
from cog_memory.long_memory import DUPLICATE_WINDOW

def _emotion_name(e: Any) -> str:
    """Coerce detect_affect output into a lowercase string."""
    if isinstance(e, dict):
        return str(e.get("emotion", "neutral")).lower()
    return str(e or "neutral").lower()

def _snapshot_emotion(context: Optional[dict]) -> dict:
    """
    Extract key emotion intensities from context["affect_state"] for storage.
    Returns a compact dict so we know how Orrin felt when this memory was formed.
    """
    if not context:
        return {}
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return {}
    keys = ("positive_valence", "negative_valence", "exploration_drive", "impasse_signal", "confidence",
            "motivation", "stagnation_signal", "expected_gain", "threat_level", "social_penalty")
    snapshot = {k: round(float(core.get(k) or 0.0), 3) for k in keys if float(core.get(k) or 0.0) >= 0.05}
    stability = emo.get("affect_stability")
    if stability is not None:
        snapshot["affect_stability"] = round(float(stability), 3)
    return snapshot


def _emotion_importance_boost(emotional_snapshot: dict) -> int:
    """Return 0–2 importance bonus for memories formed during high-emotion moments."""
    if not emotional_snapshot:
        return 0
    high_emotion_keys = ("impasse_signal", "negative_valence", "positive_valence", "threat_level", "social_penalty", "exploration_drive")
    peak = max((emotional_snapshot.get(k, 0.0) for k in high_emotion_keys), default=0.0)
    if peak >= 0.6:
        return 2
    if peak >= 0.35:
        return 1
    return 0


def remember(
    event: Any,
    context: Optional[dict] = None,
    emotion: Optional[str] = None,
    event_type: str = "event",
    agent: str = "orrin",
    importance: int = 1,
    priority: int = 1,
    referenced: int = 0,
    pin: bool = False,
    related_memory_ids: Optional[List[str]] = None,
) -> None:
    """Store an event in long-term memory with deduplication and embeddings."""
    long_memory: list = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_memory, list):
        long_memory = []

    now = datetime.now(timezone.utc).isoformat()

    # Normalize content to a string but keep raw if non-string
    raw: Any = None
    if isinstance(event, str):
        content_str = event.strip()
    else:
        raw = event
        content_str = str(event).strip()

    if not content_str:
        return

    # Deduplication (compare using string form)
    for m in long_memory[-DUPLICATE_WINDOW:]:
        if not isinstance(m, dict):
            continue
        m_content = m.get("content", "")
        m_content_str = str(m_content) if not isinstance(m_content, str) else m_content
        if m_content_str == content_str and m.get("event_type", "") == event_type:
            log_private(f"[long_memory] Skipped duplicate memory: {content_str[:50]}")
            return

    # Get embedding (always use string content)
    try:
        emb = get_embedding(content_str)
        if hasattr(emb, "tolist"):
            emb = emb.tolist()
    except Exception as exc:
        log_error(f"remember: embedding failed: {exc}")
        emb = []

    detected = _emotion_name(emotion or detect_affect_keyword(content_str))
    emotional_snapshot = _snapshot_emotion(context)
    importance = min(10, importance + _emotion_importance_boost(emotional_snapshot))

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": now,
        "content": content_str,
        "raw": raw,
        "emotion": detected,
        "emotional_context": emotional_snapshot,   # full state snapshot at storage time
        "event_type": event_type,
        "agent": agent,
        "importance": importance,
        "priority": priority,
        "referenced": referenced,
        "pin": pin,
        "decay": 1.0,
        "recall_count": 0,
        "related_memory_ids": related_memory_ids or [],
        "embedding": emb,
    }

    # Route through update_long_memory for dedup, max-size enforcement, and reward signals
    try:
        from cog_memory.long_memory import update_long_memory as _ulm
        _ulm(entry, embedding=emb, context=context)
    except Exception:
        # Fallback to direct append if update_long_memory unavailable
        long_memory.append(entry)
        save_json(LONG_MEMORY_FILE, long_memory)