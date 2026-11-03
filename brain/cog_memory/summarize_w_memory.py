from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.utils.memory_utils import summarize_memories
from brain.utils.signal_lexicon_utils import detect_signal_keyword
from brain.cog_memory.long_memory import update_long_memory
from brain.utils.embedder import get_embedding
from brain.utils.log import log_private, log_error

def _signal_name(e: Any) -> str:
    if isinstance(e, dict):
        return str(e.get("emotion", "neutral")).lower()
    return str(e or "neutral").lower()

def summarize_and_promote_working_memory(memories: List[Dict[str, Any]]) -> None:
    """
    Summarize a batch of working-memory entries and promote the result to long-term memory.
    """
    if not memories:
        return

    # B3's self-log share, held at write time (2026-11-02). prune_long_memory
    # enforces it only once the store is full, so smoke life 3's 429-row memory
    # (never pruned) was 43 % working-memory summaries. Checked here, at the one
    # writer of these summaries, rather than in update_long_memory, whose default
    # event_type is also "summary" for any untyped write.
    try:
        from brain.cog_memory.long_memory import (
            LONG_MEMORY_FILE, _SELF_LOG_EVENT_TYPES, _SELF_LOG_MAX_SHARE)
        from brain.utils.json_utils import load_json
        _ltm = load_json(LONG_MEMORY_FILE, default_type=list) or []
        _n_self = sum(1 for m in _ltm if isinstance(m, dict)
                      and m.get("event_type") in _SELF_LOG_EVENT_TYPES)
        if _n_self + 1 > _SELF_LOG_MAX_SHARE * (len(_ltm) + 1):
            log_private("[working_memory] Summary not promoted: self-log share at "
                        f"{_SELF_LOG_MAX_SHARE:.0%} of long memory.")
            return
    except Exception as e:
        log_error(f"summarize_and_promote_working_memory: share check failed: {e}")

    # Collect metadata
    referenced = [m for m in memories if m.get("referenced", 0) > 0]
    pins = [m for m in memories if m.get("pin", False)]
    topics = {m.get("event_type", "thought") for m in memories}

    summary_text = summarize_memories(memories) or ""
    extra_info = ""
    if referenced:
        extra_info += f"\nReferenced {len(referenced)} times during reasoning."
    if pins:
        extra_info += f"\nPinned items: {[m.get('content', '')[:40] for m in pins]}"
    if topics:
        # sort for stable output
        extra_info += f"\nEvent types: {', '.join(sorted(topics))}"

    related_ids = [m.get("id") for m in memories if m.get("id")]
    referenced_total = sum(m.get("referenced", 0) for m in memories)
    pin_flag = any(m.get("pin", False) for m in memories)
    decay_avg = sum((m.get("decay", 1.0) or 1.0) for m in memories) / max(len(memories), 1)
    recall_total = sum(m.get("recall_count") or 0 for m in memories)

    content_str = f"📝 Working memory summary: {summary_text}{extra_info}"

    # Embedding with safety
    embedding = []
    try:
        embedding = get_embedding(content_str)
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
    except Exception as e:
        log_error(f"summarize_and_promote_working_memory: embedding failed: {e}")

    summary_entry = {
        "content": content_str,
        "emotion": _signal_name(detect_signal_keyword(summary_text)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "summary",
        "agent": "orrin",
        "importance": 2,
        "priority": 2,
        "referenced": referenced_total,
        "pin": pin_flag,
        "decay": decay_avg,
        "recall_count": recall_total,
        "related_memory_ids": related_ids,
        "embedding": embedding,
    }

    update_long_memory(summary_entry)
    log_private("[working_memory] New working memory summary promoted to long-term.")