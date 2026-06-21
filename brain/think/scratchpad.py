# brain/think/scratchpad.py
# Volatile per-cycle workspace: init / append / flush.
# Mirrors metacog.py's API shape (init / note / flush) with richer content entries.
#
# Distinction:
#   scratchpad = CONTENT  (drafts, critiques, revisions — the actual LLM outputs)
#   metacog    = PHASE TRACE (what happened when, why — lightweight breadcrumbs)
#
# Stored on context["_scratchpad"] as a list of entries.
# Flushed at cycle end — entries are NOT persisted; metacog_flush() handles the summary.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from typing import Any, Dict, List
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def scratchpad_init(context: Dict[str, Any]) -> None:
    """Call at the top of each cognitive cycle to create a fresh workspace."""
    context["_scratchpad"] = []


def scratchpad_append(
    context: Dict[str, Any],
    role: str,
    content: str,
    phase: str = "",
) -> None:
    """
    Append an entry to the current cycle's scratchpad.

    role:  "draft" | "critique" | "revision" | "plan" | "question"
    phase: optional label passed through to metacog as a phase marker
    """
    pad = context.setdefault("_scratchpad", [])
    pad.append({
        "role":    role,
        "content": str(content)[:800],
        "phase":   phase,
        "ts":      time.time(),
    })
    # Cross-post a lightweight breadcrumb to metacog if it's active
    if phase:
        try:
            from brain.cognition.metacog import metacog_note
            metacog_note(context, phase, f"[{role}] {str(content)[:120]}")
        except Exception as _e:
            record_failure("scratchpad.scratchpad_append", _e)


def scratchpad_latest(context: Dict[str, Any], role: str = "") -> str:
    """
    Return the content of the most recent entry, optionally filtered by role.
    Returns empty string if nothing matches.
    """
    pad = context.get("_scratchpad") or []
    if role:
        pad = [e for e in pad if e.get("role") == role]
    return pad[-1]["content"] if pad else ""


def scratchpad_all(context: Dict[str, Any], role: str = "") -> List[Dict[str, Any]]:
    """Return all scratchpad entries, optionally filtered by role."""
    pad = context.get("_scratchpad") or []
    if role:
        return [e for e in pad if e.get("role") == role]
    return list(pad)


def scratchpad_flush(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Called at cycle end. Clears the scratchpad and returns the entries.
    The best "revision" entry is saved to working_memory so the draft→critique→revise
    cycle produces durable output, not just a metacog breadcrumb.
    """
    entries = list(context.pop("_scratchpad", []))

    # Save the last revision entry (the finished product of the think cycle)
    revisions = [e for e in entries if e.get("role") == "revision" and e.get("content", "").strip()]
    if revisions:
        best = revisions[-1]["content"].strip()
        if len(best) > 20:
            try:
                from brain.cog_memory.working_memory import update_working_memory
                update_working_memory(f"[scratchpad_revision] {best[:400]}")
            except Exception as _e:
                record_failure("scratchpad.scratchpad_flush", _e)

    return entries
