# brain/cognition/leave_note.py
# Orrin leaves a note for the user. The note is *composed* by Orrin through the
# one expression door (behavior.express_to_user) from his motive + felt state —
# it is NOT populated by scraping working memory. The backend (raw WM,
# symbolic/causal tags, telemetry) is unreachable from here.
# (EXPRESSION_MEMBRANE_FIX_PLAN E1/E4, 2026-06-14.)
from __future__ import annotations

from typing import Dict, Any

from brain.utils.log import log_activity


def leave_note(context: Dict[str, Any] = None) -> str:
    """Compose and deliver a note to the user via the expression door."""
    context = context or {}

    from brain.behavior.express_to_user import build_motive, express_to_user

    # Ground a knowledge note in its SUBJECT, not the affect status line
    # (RUN_AUDIT_REPORT_2026-06-16 Issue 4b). For a degraded acquire_knowledge goal
    # ("Note what I already know about: X") seed the motive with the topic so the
    # artifact carries real signal. The seed is a meaning kernel — the expression door
    # rewords/sanitises it, so the membrane stays intact. Empty seed → unchanged
    # (affect-kernel) behaviour for every other note.
    _seed = None
    _goal = context.get("committed_goal") or {}
    if isinstance(_goal, dict):
        _title = str(_goal.get("title") or "")
        if "what i already know about" in _title.lower():
            _topic = _title.split(":", 1)[-1].strip()
            _orig = str(_goal.get("_original_title")
                        or (_goal.get("_predegrade") or {}).get("title") or "")
            _subject = _topic or _orig
            if _subject:
                _seed = f"what I actually know about {_subject}"

    # P4 — ground the note in the FINDING that triggered it, not the ambient affect
    # status line. The run showed 100 byte-identical empty notes because the body was
    # the ~40-char affect string; sourcing it from the most recent real finding gives
    # the artifact content, so record_effect(note_novel) mostly will NOT dedupe.
    if _seed is None:
        try:
            from brain.utils.json_utils import load_json as _lj
            from brain.paths import LONG_MEMORY_FILE as _LMF
            _lm = _lj(_LMF, default_type=list) or []
            for _entry in reversed(_lm[-25:]):
                _c = str(_entry.get("content", _entry) if isinstance(_entry, dict) else _entry)
                _lc = _c.lower()
                if ("from searching" in _lc or "finding was written" in _lc
                        or "[world_perception]" in _lc):
                    _payload = _c.split(":", 1)[-1].strip() if ":" in _c else _c
                    _payload = " ".join(_payload.split())[:240]
                    if len(_payload) >= 40:
                        _seed = f"something I actually found out: {_payload}"
                        break
        except Exception:
            pass

    motive = build_motive(context, intent="leave_note", recipient="Ric", seed=_seed)
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
        from brain.cog_memory.working_memory import update_working_memory
        update_working_memory({
            "content": f"[note_written] {content[:160]}",
            "event_type": "note_written",
            "importance": 2,
        })
    except Exception:
        pass

    return f"Left a note: {content[:120]}"
