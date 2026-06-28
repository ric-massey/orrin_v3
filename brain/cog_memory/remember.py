from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, List
import uuid

from brain.utils.signal_lexicon_utils import detect_signal_keyword
from brain.paths import LONG_MEMORY_FILE
from brain.utils.embedder import get_embedding
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_error, log_private
# Emotion snapshot helpers live in long_memory (the canonical owner); imported
# here so the two storage paths share one implementation (structure audit §8).
from brain.cog_memory.long_memory import (
    DUPLICATE_WINDOW,
    _signal_name,
    _snapshot_signal,
    _signal_importance_boost,
)


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

    detected = _signal_name(emotion or detect_signal_keyword(content_str))
    emotional_snapshot = _snapshot_signal(context)
    importance = min(10, importance + _signal_importance_boost(emotional_snapshot))

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
        from brain.cog_memory.long_memory import update_long_memory as _ulm
        _ulm(entry, embedding=emb, context=context)
    except Exception:
        # Fallback to direct append if update_long_memory unavailable
        long_memory.append(entry)
        save_json(LONG_MEMORY_FILE, long_memory)