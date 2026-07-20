# brain/cognition/thought.py
#
# T1 (Run 11 §4) — the Thought Object as inter-subsystem currency.
#
# THE PROBLEM (project_prose_bus_label_authority). Working memory is a prose
# message bus: ~12 subsystems mine entry CONTENT strings, each with its own
# drifting prefix list, to answer questions the entry itself should carry —
# who authored this? who was it addressed to? can it be researched? Every
# self-echo bug (the question miner harvesting Orrin's own "What do you
# think?" sign-off; user speech becoming "his" open question; telemetry lines
# becoming opinions) is a source-monitoring error born on this bus.
#
# THE FIX, PHASE 2A. Entries carry TYPED fields — provenance, addressee, kind,
# researchability — and readers consume ONE canonical classifier instead of
# twelve prefix lists. `content` stays for display; it stops being authority.
# Legacy entries (and strings) are classified by inference from event_type /
# agent / the established markers, so both currencies flow during migration.
# C7 (question-miner dedup clamps) retires against this provenance.
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ── the closed vocabularies ───────────────────────────────────────────────────

PROVENANCE = ("self_thought", "self_speech", "user", "perception", "instrumentation")
ADDRESSEE = ("self", "user", "none")
RESEARCHABILITY = ("world", "self", "none")

# Legacy inference tables — the markers the string bus already uses. These are
# the *migration shim*, not the API: new writers stamp fields, readers call the
# classifiers, and entries these tables misjudge get their fields stamped at
# the writer as they are found.
_INSTRUMENTATION_EVENTS = frozenset({
    "choice", "system", "reward_penalty", "search", "file_search_result",
    "goal_blocked", "goal_degraded", "goal_disengaged", "goal_repromoted",
    "goal_released", "closed_loop_break", "telemetry",
})
_SELF_SPEECH_EVENTS = frozenset({"unanswered_question", "speech", "expression"})
_INSTRUMENTATION_PREFIXES = (
    "🧠", "⏳", "🎉", "✅", "⚠️", "❌", "[goal_", "[pursue_goal]", "[metacog]",
    "[impasse]", "[epistemic]", "[maintenance]", "[self_search]", "[file_search]",
)
_SELF_SPEECH_PREFIXES = ("[unanswered_question]", "[i_said]", "[expressed]")
_USER_PREFIXES = ("[input/",)

_SELF_REF_RE = re.compile(
    r"\b(i|me|my|myself|my own|orrin)\b|\b(you think|do you|would you|could you)\b",
    re.IGNORECASE,
)


# ── builder ───────────────────────────────────────────────────────────────────

def mk_thought(content: str, *,
               provenance: str = "self_thought",
               addressee: str = "none",
               kind: str = "thought",
               researchability: Optional[str] = None,
               importance: int = 1, priority: int = 1,
               **fields: Any) -> Dict[str, Any]:
    """A working-memory-ready entry whose authority is its TYPED fields.
    `update_working_memory` preserves extra dict keys, so this flows through
    the existing bus unchanged; readers on the classifiers see the stamps."""
    if provenance not in PROVENANCE:
        provenance = "self_thought"
    if addressee not in ADDRESSEE:
        addressee = "none"
    entry: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": str(content or ""),
        "event_type": str(kind or "thought"),
        "provenance": provenance,
        "addressee": addressee,
        "researchability": (researchability if researchability in RESEARCHABILITY
                            else researchability_of_text(str(content or ""), provenance)),
        "importance": int(importance),
        "priority": int(priority),
    }
    entry.update(fields)
    return entry


# ── classifiers (the one list to rule the twelve) ─────────────────────────────

def provenance_of(entry: Any) -> str:
    """Who authored this entry. Typed field wins; legacy entries are inferred
    from event_type / agent / the established content markers."""
    if isinstance(entry, dict):
        p = str(entry.get("provenance") or "")
        if p in PROVENANCE:
            return p
        ev = str(entry.get("event_type") or "")
        if ev.startswith("user") or str(entry.get("agent") or "").lower() == "user":
            return "user"
        if ev in _SELF_SPEECH_EVENTS:
            return "self_speech"
        if ev in _INSTRUMENTATION_EVENTS or entry.get("internal_telemetry"):
            return "instrumentation"
        if ev.startswith("perception") or ev in ("world_event", "fs_perception"):
            return "perception"
    text = _content_of(entry)
    if text.startswith(_USER_PREFIXES):
        return "user"
    if text.startswith(_SELF_SPEECH_PREFIXES):
        return "self_speech"
    if text.startswith(_INSTRUMENTATION_PREFIXES):
        return "instrumentation"
    return "self_thought"


def addressee_of(entry: Any) -> str:
    if isinstance(entry, dict):
        a = str(entry.get("addressee") or "")
        if a in ADDRESSEE:
            return a
    p = provenance_of(entry)
    if p == "self_speech":
        return "user"     # his outbound speech was addressed to someone
    if p == "user":
        return "self"     # user speech is addressed TO Orrin
    return "none"


def researchability_of_text(text: str, provenance: str = "self_thought") -> str:
    """Can this content be pursued as research — and where does the answer
    live? Own speech / user speech / telemetry are 'none' (they are records of
    a conversation, not gaps); self-referential subjects are 'self' (the
    answer is in his own history — M4); the rest is 'world'."""
    if provenance in ("self_speech", "user", "instrumentation"):
        return "none"
    if _SELF_REF_RE.search(str(text or "")):
        return "self"
    return "world"


def researchability_of(entry: Any) -> str:
    if isinstance(entry, dict):
        r = str(entry.get("researchability") or "")
        if r in RESEARCHABILITY:
            return r
    return researchability_of_text(_content_of(entry), provenance_of(entry))


def is_minable_as_own_gap(entry: Any) -> bool:
    """THE miner predicate (question miner, opinion formation, thread mining):
    may this entry seed new intrinsic cognition as Orrin's own material?
    False for user speech (belongs to the conversational path), his own
    outbound speech (mining it back is a source-monitoring error), and
    instrumentation (machine lines are not thoughts)."""
    return provenance_of(entry) in ("self_thought", "perception")


def _content_of(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("content") or "")
    return str(entry or "")
