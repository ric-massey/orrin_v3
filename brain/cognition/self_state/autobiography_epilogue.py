# brain/cognition/self_state/autobiography_epilogue.py
#
# Death-continuity + session-epilogue narrative for autobiography.py
# (CODEBASE_CLEANUP_PLAN 4.5C), lifted verbatim to bring that module under the
# 600-line soft limit. The machine-tag sanitizer (_sanitize_prose), the
# end-of-life continuity note (append_death_continuity), and the end-of-session
# reflection + epilogue (_session_reflection / session_epilogue).
# autobiography.py re-exports the public entry points for its external callers
# (loop.services, terminal, selection.constants).
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json
from brain.utils.log import log_activity
from brain.utils.timeutils import now_iso_z

# load_autobiography / save_autobiography live in the parent module; imported
# lazily inside the functions below to avoid an import-time cycle (Phase 4.5C).


# ── Death continuity ──────────────────────────────────────────────────────────

# Internal bracket markers ([symbolic], [working_memory], [orrin, ai, …]) that
# the rule-based fallbacks serialize into text. Autobiographical prose must not
# carry machine syntax (DATA_FILE_AUDIT 2026-06-11 §3: the 2026-06-11 chapter
# narrative was raw symbolic facts).
_MACHINE_TAG_RE = re.compile(r"\[[a-zA-Z_/][^\]]*\]\s*")


def _sanitize_prose(text: str) -> str:
    return _MACHINE_TAG_RE.sub("", str(text or "")).strip()


def append_death_continuity(final_reflection: str, context: Optional[Dict[str, Any]] = None) -> None:
    """
    Called at shutdown: close the current chapter with the final words so the
    next instance inherits the narrative arc.

    When NO chapter was ever opened, the final words go to a continuity note,
    not a fabricated chapter — the 2026-06-11 phantom "Before the beginning"
    chapter left an autobiography whose only chapter was two death
    certificates (DATA_FILE_AUDIT §3).
    """
    from brain.cognition.self_state.autobiography import load_autobiography, save_autobiography
    context = context or {}
    auto = load_autobiography()
    chapters = auto.get("chapters", [])
    ts = now_iso_z()
    closing = f"[Final words] {_sanitize_prose(final_reflection)}"

    if chapters:
        chapters[-1].setdefault("entries", []).append(
            {"ts": ts, "text": closing, "type": "death_closing"}
        )
        chapters[-1]["closed_ts"] = ts
        chapters[-1]["closed_by"] = "death"
        auto["chapters"] = chapters
    else:
        auto.setdefault("continuity_notes", []).append(
            {"ts": ts, "text": closing, "type": "death_closing"}
        )
        log_activity("[autobiography] No chapter was ever opened this life — "
                     "final words stored as a continuity note, not a chapter.")

    auto["last_updated"] = ts
    save_autobiography(auto)
    log_activity("[autobiography] Death closing written to autobiography.")


# ── Session epilogue (master plan Phase 2.1) ──────────────────────────────────

def _session_reflection(context: Dict[str, Any], deadline: float) -> str:
    """2-3 sentence session reflection. LLM when available and time remains;
    otherwise a rule-based summary of the session's WM highlights. Never empty."""
    # Rule-based summary built first — it is also the LLM prompt material.
    highlights: List[str] = []
    cycles = 0
    try:
        from brain.paths import WORKING_MEMORY_FILE
        wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        raw = context.get("cycle_count") or 0
        cycles = int(raw.get("count", 0) if isinstance(raw, dict) else raw)
        scored = sorted(
            (e for e in wm[-40:] if isinstance(e, dict) and e.get("content")),
            key=lambda e: float(e.get("importance") or 1),
            reverse=True,
        )
        for e in scored[:3]:
            highlights.append(str(e["content"])[:120].strip())
    except Exception as e:
        record_failure("autobiography.session_reflection", e)

    fallback = "This session ended in the ordinary way."
    if highlights:
        fallback = (
            f"The session closed at cycle {cycles}. What stood out: "
            + " | ".join(highlights)
            + ". I stop here and pick the thread up next time."
        )

    try:
        from brain.utils.llm_gate import llm_available
        if llm_available() and (deadline - time.monotonic()) > 6.0:
            from brain.symbolic.llm_gate import gated_generate
            prompt = (
                "My session is ending normally (not death — just a pause). In 2-3 "
                "first-person sentences, reflect on what this session held and what "
                "to carry forward. Material:\n" + "\n".join(f"- {h}" for h in highlights)
            )
            text = gated_generate(prompt, caller="session_epilogue", outcome=0.6)
            if isinstance(text, str) and 20 < len(text.strip()) < 800:
                return text.strip()
    except Exception as e:
        record_failure("autobiography.session_reflection.llm", e)
    return fallback


def session_epilogue(context: Optional[Dict[str, Any]] = None) -> None:
    """
    Called after the cognitive loop exits on an ORDINARY shutdown
    (KeyboardInterrupt / SIGTERM / stop_event). Appends a session_close entry to
    the current chapter — it does NOT close the chapter (that is death's job,
    append_death_continuity). Budgeted (≤10 s) and crash-proof so it can never
    block shutdown — the corrigibility guarantee stays true.
    """
    from brain.cognition.self_state.autobiography import load_autobiography, save_autobiography
    deadline = time.monotonic() + 10.0
    try:
        reflection = _session_reflection(context or {}, deadline)
        auto = load_autobiography()
        chapters = auto.get("chapters", [])
        ts = now_iso_z()
        entry = {"ts": ts, "text": f"[Session close] {reflection}", "type": "session_close"}
        if chapters:
            chapters[-1].setdefault("entries", []).append(entry)
        else:
            chapters.append({
                "number":     1,
                "title":      "First days",
                "started_ts": ts,
                "narrative":  "",
                "entries":    [entry],
            })
        auto["chapters"] = chapters
        # Deliberately NOT touching auto["last_updated"]: that key gates
        # narrative_update's min-interval and a shutdown is not a narrative event.
        auto["last_session_close"] = ts
        save_autobiography(auto)
        log_activity("[autobiography] Session epilogue written.")
    except Exception as e:
        record_failure("autobiography.session_epilogue", e)
