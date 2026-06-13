# brain/cognition/privacy.py
# Privacy layer: Orrin can mark memories as private. Private memories are
# filtered from all person-facing outputs (speak.py, chat_log, dashboard)
# but remain accessible to internal cognition (dream, reflection, etc.).
#
# mark_private(query, context)  — cognition function: tag matching memories private
# filter_private(memories)      — utility: strip private entries for output
# set_memory_private(mem_id)    — low-level toggle
from __future__ import annotations

from typing import Dict, Any, List

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from paths import LONG_MEMORY_FILE


def filter_private(memories: List[Dict]) -> List[Dict]:
    """Return only entries where private is not True. Safe to call on any list."""
    if not isinstance(memories, list):
        return memories
    return [m for m in memories if not (isinstance(m, dict) and m.get("private"))]


def mark_private(query: str = "", context: Dict[str, Any] = None) -> str:
    """
    Cognition function: find long-memory entries matching query text and mark
    them private. If query is empty, marks the most recent entry.
    """
    context = context or {}
    memories = load_json(LONG_MEMORY_FILE, default_type=list) or []

    marked = 0
    if not query.strip():
        # Mark the single most recent non-private entry
        for m in reversed(memories):
            if isinstance(m, dict) and not m.get("private"):
                m["private"] = True
                marked = 1
                log_private(f"[privacy] Marked most recent entry private: {str(m.get('content',''))[:60]!r}")
                break
    else:
        q = query.lower()
        for m in memories:
            if not isinstance(m, dict):
                continue
            content = str(m.get("content", "")).lower()
            if q in content:
                m["private"] = True
                marked += 1

    if marked:
        save_json(LONG_MEMORY_FILE, memories)
        log_activity(f"[privacy] Marked {marked} memory entry/entries private.")
        return f"Marked {marked} memory entry/entries as private."
    return "No matching entries found to mark private."


def set_memory_private(mem_id: str, private: bool = True) -> bool:
    """Toggle privacy on a specific memory by its id. Returns True if found."""
    memories = load_json(LONG_MEMORY_FILE, default_type=list) or []
    for m in memories:
        if isinstance(m, dict) and m.get("id") == mem_id:
            m["private"] = private
            save_json(LONG_MEMORY_FILE, memories)
            return True
    return False
