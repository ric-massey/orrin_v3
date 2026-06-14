# brain/cognition/leave_note.py
# Orrin leaves a note for the user. The note is *composed* by Orrin through the
# one expression door (behavior.express_to_user) from his motive + felt state —
# it is NOT populated by scraping working memory. The backend (raw WM,
# symbolic/causal tags, telemetry) is unreachable from here.
# (EXPRESSION_MEMBRANE_FIX_PLAN E1/E4, 2026-06-14.)
from __future__ import annotations

from typing import Dict, Any

from utils.log import log_activity


def leave_note(context: Dict[str, Any] = None) -> str:
    """Compose and deliver a note to the user via the expression door."""
    context = context or {}

    from behavior.express_to_user import build_motive, express_to_user

    motive = build_motive(context, intent="leave_note", recipient="Ric")
    result = express_to_user(motive, "note", context)
    content = (result or {}).get("text") or ""
    if not content:
        return "Nothing worth noting right now."

    log_activity(f"[leave_note] {content[:80]}")

    # Reafference: report the real artifact into working memory so milestone
    # verification (env_snapshot, which only sees WM) can observe that a note was
    # actually written. This writes a marker INTO WM; it never reads raw WM out —
    # the membrane stays intact (EXPRESSION_MEMBRANE_FIX_PLAN §1.4).
    try:
        from cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content": f"[note_written] {content[:160]}",
            "event_type": "note_written",
            "importance": 2,
        })
    except Exception:
        pass

    return f"Left a note: {content[:120]}"
