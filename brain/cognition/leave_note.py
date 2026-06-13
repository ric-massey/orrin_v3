# brain/cognition/leave_note.py
# Orrin writes a note to the outbox for the user to read later.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any

from paths import NOTES_FILE
from utils.json_utils import load_json, save_json
from utils.log import log_activity


def leave_note(context: Dict[str, Any] = None) -> str:
    """Write a note or observation to the outbox for the user."""
    context = context or {}
    wm = context.get("working_memory") or []
    affect_state = context.get("affect_state") or {}
    core = affect_state.get("core_signals", affect_state)

    content = _compose_note(wm, core, context)
    if not content:
        return "Nothing worth noting right now."

    notes = load_json(NOTES_FILE, default_type=list) or []
    # NOTE: no "read" field — nothing ever consumed it (BEHAVIOR_FIX_PLAN §5:
    # dead protocol fields invite false debugging leads). If a delivery story
    # appears later, the consumer owns the read-state, not this writer.
    note = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "content": content,
        "emotion": _dominant_emotion(core),
    }
    notes.append(note)
    if len(notes) > 100:
        notes = notes[-100:]
    save_json(NOTES_FILE, notes)

    log_activity(f"[leave_note] {content[:80]}")
    return f"Left a note: {content[:120]}"


def _dominant_emotion(core: Dict) -> str:
    if not core:
        return "neutral"
    best = max(
        ((k, v) for k, v in core.items() if isinstance(v, (int, float))),
        key=lambda kv: kv[1],
        default=("neutral", 0),
    )
    return best[0]


_SKIP_PREFIXES = (
    "🌓", "🧠", "✅", "⚠️", "[question_answered]", "shadow",
    "chose:", "rewarded", "cognition action", "spoke:", "user response",
    "[metacog", "[world_perception]", "[rss:", "[wikipedia]",
    # Internal bookkeeping / consolidation artifacts — never user-facing notes.
    "[chunk:", "[goal pursuit]", "[goal_adopted]", "[goal_blocked]",
    "[subgoal_adapt]", "[done]", "[dream:", "[identity]", "[plan:",
)


def _compose_note(wm: list, core: Dict, context: Dict) -> str:
    # Look for something genuinely interesting in working memory
    for entry in reversed(wm[-15:]):
        if isinstance(entry, dict) and entry.get("internal_telemetry"):
            continue  # diagnostic writes are never note material
        text = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
        if len(text) < 20:
            continue
        # Case-insensitive prefix match so "[Chunk:" / "[chunk:" both filter.
        low = text.lstrip().lower()
        if any(low.startswith(p) for p in _SKIP_PREFIXES):
            continue
        # Generic guard: ANY leading [tag] is a system/telemetry line. The fixed
        # list above missed [regulation] and [housekeeping/NORMAL], which leaked
        # into a note unstripped (FINDINGS 2026-06-12 data sweep §10).
        if low.startswith("["):
            continue
        importance = (entry.get("importance", 1) if isinstance(entry, dict) else 1)
        if importance >= 2 or "?" in text or len(text) > 60:
            from utils.text_sanity import truncate_clean
            return truncate_clean(text, 400)

    # Fallback: note current emotional/cognitive state
    em = _dominant_emotion(core)
    mode = context.get("mode", "thinking")
    goal = (context.get("committed_goal") or {})
    goal_title = goal.get("title", "") if isinstance(goal, dict) else ""
    if goal_title:
        return f"I'm feeling {em} while working on: {goal_title[:120]}"
    return f"Currently feeling {em}, in {mode} mode."
