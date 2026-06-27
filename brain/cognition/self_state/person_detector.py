# brain/cognition/self_state/person_detector.py
#
# Detects who is speaking and maintains a persistent registry of known persons.
# Sets context["user_id"] each cycle so all downstream systems (relationships,
# expression, environment) operate on the correct person.
#
# "Person" here means any distinct entity Orrin interacts with:
#   - A human (the person running this, their family, colleagues, anyone)
#   - Another Orrin instance or AI peer
#   - An anonymous or unnamed speaker
#
# There is no hardcoded "primary user". Whoever is speaking right now
# is tracked as their own person with their own relationship model.
#
# Identity detection sources (in priority order):
#   1. Explicit introduction: "I'm Sarah", "My name is Alex", "Call me Jo"
#   2. Relational description: "I'm Sam's sister" → stored with relation to Sam
#   3. AI peer announcement: "I'm another Orrin", "I'm an AI"
#   4. Session memory: if this conversation already resolved an identity, keep it
#   5. Alias matching: name matches a known alias for a stored person
#   6. Default: anonymous session ID — a distinct unnamed speaker
#
# known_persons.json schema:
#   {
#     "<person_id>": {
#       "display_name": "Sarah",          # how Orrin addresses them
#       "person_type":  "human" | "ai_peer" | "unknown",
#       "aliases":      ["sarah", "s"],
#       "relation_to_others": {"<other_id>": "<relation>"},
#       "first_seen":   "<iso>",
#       "last_seen":    "<iso>",
#       "session_count": 3,
#       "notes":        ""               # Orrin-written observations
#     }
#   }
from __future__ import annotations

import re
import uuid
from typing import Dict, Any, Optional, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private, log_activity
from brain.paths import DATA_DIR
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

KNOWN_PERSONS_FILE = DATA_DIR / "known_persons.json"

# When a speaker doesn't identify themselves, give them a session-scoped anonymous ID
ANONYMOUS_PREFIX = "anon"

# Introduction patterns — ordered from most specific to least
_INTRO_PATTERNS = [
    # "I'm Sarah" / "I am Alex"
    re.compile(r"\bi(?:'m| am)\s+([A-Za-z][A-Za-z '-]{1,40})", re.IGNORECASE),
    # "My name is Sarah" / "my name's Sam"
    re.compile(r"\bmy name(?:'s| is)\s+([A-Za-z][A-Za-z '-]{1,40})", re.IGNORECASE),
    # "This is Sarah" / "This is Jo's friend"
    re.compile(r"\bthis is\s+([A-Za-z][A-Za-z 'sS-]{1,50})", re.IGNORECASE),
    # "It's Alex" (when speaking to Orrin directly)
    re.compile(r"\bit'?s\s+([A-Za-z][A-Za-z '-]{1,30})\s*[,!.]", re.IGNORECASE),
    # "Call me Sam"
    re.compile(r"\bcall me\s+([A-Za-z][A-Za-z '-]{1,30})", re.IGNORECASE),
]

# Detect AI/peer introductions
_AI_PEER_PATTERNS = [
    re.compile(r"\bi(?:'m| am)\s+(?:another\s+)?orrin\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+an?\s+ai\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+(?:an?\s+)?(?:ai\s+)?(?:instance|agent|model|assistant)\b", re.IGNORECASE),
    re.compile(r"\bthis is\s+(?:another\s+)?orrin\b", re.IGNORECASE),
]

# Words that are never names
_NAME_STOPWORDS = frozenset({
    "me", "you", "him", "her", "them", "us", "we", "just", "here", "there",
    "right", "ok", "okay", "sure", "fine", "good", "bad", "true", "false",
    "not", "no", "yes", "yep", "yeah", "hi", "hey", "hello", "sorry",
    "back", "done", "ready", "going", "talking", "saying", "not",
})

# Track current session's resolved person_id
_session_person_id: Optional[str] = None


# ── Persistence ──────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    return load_json(KNOWN_PERSONS_FILE, default_type=dict) or {}


def _save(persons: Dict[str, Any]) -> None:
    save_json(KNOWN_PERSONS_FILE, persons)



# ── Name / type extraction ────────────────────────────────────────────────────

def _is_ai_peer(text: str) -> bool:
    """True when the speaker identifies as an AI or another Orrin instance."""
    return any(p.search(text) for p in _AI_PEER_PATTERNS)


def _extract_name_from_text(text: str) -> Optional[str]:
    """Return the first plausible name found in text, or None."""
    for pattern in _INTRO_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        raw = m.group(1).strip().rstrip(".,!?")
        words = raw.split()
        if not raw[0].isupper():
            continue
        head = words[0].lower().rstrip("'s")
        if head in _NAME_STOPWORDS:
            continue
        if len(raw) > 50:
            continue
        return raw
    return None


# ── person_id derivation ──────────────────────────────────────────────────────

def _name_to_id(display_name: str) -> str:
    """Convert display name to a stable person_id slug."""
    slug = display_name.lower()
    slug = re.sub(r"['\s]+", "_", slug)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug[:40] or "unknown"


def _new_anon_id() -> str:
    """Generate a unique anonymous session ID."""
    return f"{ANONYMOUS_PREFIX}_{uuid.uuid4().hex[:6]}"


def _find_by_alias(alias: str, persons: Dict[str, Any]) -> Optional[str]:
    """Return person_id if alias matches any known person, else None."""
    alias_lower = alias.lower()
    for pid, info in persons.items():
        if not isinstance(info, dict):
            continue
        if alias_lower == str(info.get("display_name", "")).lower():
            return pid
        for a in (info.get("aliases") or []):
            if alias_lower == str(a).lower():
                return pid
    return None


# ── Person record management ──────────────────────────────────────────────────

def _ensure_person(
    person_id: str,
    display_name: str,
    persons: Dict[str, Any],
    person_type: str = "human",
    extra_alias: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a person record. Returns the mutable record."""
    if person_id not in persons or not isinstance(persons.get(person_id), dict):
        persons[person_id] = {
            "display_name":       display_name,
            "person_type":        person_type,
            "aliases":            [],
            "relation_to_others": {},
            "first_seen":         now_iso_z(),
            "last_seen":          now_iso_z(),
            "session_count":      1,
            "notes":              "",
        }
        label = f"[{person_type}]" if person_type != "human" else ""
        log_activity(f"[person_detector] New person: '{display_name}' {label}→ {person_id}")
    else:
        p = persons[person_id]
        p["last_seen"]     = now_iso_z()
        p["session_count"] = int(p.get("session_count", 0)) + 1
        # Update person_type if it was previously unknown
        if p.get("person_type") == "unknown" and person_type != "unknown":
            p["person_type"] = person_type

    p = persons[person_id]
    if extra_alias:
        alias_lower = extra_alias.lower()
        existing = [a.lower() for a in (p.get("aliases") or [])]
        if alias_lower not in existing and alias_lower != display_name.lower():
            p.setdefault("aliases", []).append(extra_alias)

    return p


def _merge_person_records(persons: Dict[str, Any], from_id: str, into_id: str) -> None:
    """Fold `from_id` (typically an anonymous session record) into `into_id`."""
    src = persons.get(from_id)
    dst = persons.get(into_id)
    if not isinstance(src, dict) or not isinstance(dst, dict) or from_id == into_id:
        return
    if str(src.get("first_seen") or "") and (
            not dst.get("first_seen") or src["first_seen"] < dst["first_seen"]):
        dst["first_seen"] = src["first_seen"]
    dst["session_count"] = int(dst.get("session_count") or 0) + int(src.get("session_count") or 0)
    src_notes = str(src.get("notes") or "").strip()
    if src_notes:
        dst["notes"] = f"{dst.get('notes', '')}\n{src_notes}".strip()[-2000:]
    for rid, rel in (src.get("relation_to_others") or {}).items():
        dst.setdefault("relation_to_others", {}).setdefault(rid, rel)
    del persons[from_id]
    log_activity(f"[person_detector] Merged '{from_id}' into '{into_id}'.")


def _merge_anonymous_duplicates(persons: Dict[str, Any]) -> None:
    """Collapse empty duplicate anonymous 'someone' records into the newest one.
    Records carrying any signal (notes, aliases, relations) are kept distinct —
    two unnamed speakers with content stay two people."""
    empties = [
        pid for pid, p in persons.items()
        if pid.startswith(ANONYMOUS_PREFIX) and isinstance(p, dict)
        and not str(p.get("notes") or "").strip()
        and not (p.get("aliases") or [])
        and not (p.get("relation_to_others") or {})
    ]
    if len(empties) <= 1:
        return
    empties.sort(key=lambda pid: str(persons[pid].get("last_seen") or ""))
    keep = empties[-1]
    for pid in empties[:-1]:
        if pid != _session_person_id:
            del persons[pid]
    log_activity(f"[person_detector] Collapsed {len(empties) - 1} empty anonymous record(s) into '{keep}'.")


def _link_kg_entity(persons: Dict[str, Any], person_id: str) -> None:
    """Link the knowledge-graph entity for this person's name to the record."""
    p = persons.get(person_id)
    if not isinstance(p, dict):
        return
    name = str(p.get("display_name") or "").strip()
    if not name or name.lower() == "someone":
        return
    try:
        from brain.cognition.knowledge_graph import add_entity
        eid = add_entity(name, entity_type="person",
                         properties={"person_id": person_id}, source="person_detector")
        if eid:
            p["kg_entity_id"] = eid
    except Exception as e:
        log_private(f"[person_detector] KG link failed for '{name}': {e}")


def _detect_relation(raw_name: str) -> Optional[Tuple[str, str]]:
    """
    Extract a relational description, e.g. "Sam's sister" → ("sam", "sister").
    Returns (related_to_id, relation) or None. Fully dynamic — no names hardcoded.
    """
    m = re.match(r"([A-Za-z][A-Za-z]+)'s\s+([a-z]+)", raw_name, re.IGNORECASE)
    if m:
        related_name = m.group(1).strip()
        relation     = m.group(2).strip().lower()
        related_id   = _name_to_id(related_name)
        return (related_id, relation)
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def detect_and_set_person_id(context: Dict[str, Any]) -> str:
    """
    Main entry point — call once per cycle before cognitive processing.

    Resolves who is speaking, writes context["person_id"], context["person_display_name"],
    and context["person_type"]. Returns the resolved person_id.

    Priority:
      1. Context already has person_id set (another module resolved it this cycle)
      2. Session memory — keeps identity stable within a session
      3. Parse latest_user_input for introduction or AI-peer announcement
      4. Anonymous fallback — a unique ID so two unnamed speakers are still distinct

    Note: context["user_id"] is kept as an alias for backward compatibility.
    """
    global _session_person_id

    # 1. Another module already resolved it this cycle
    existing = context.get("person_id") or context.get("user_id")
    if existing and not existing.startswith(ANONYMOUS_PREFIX) and existing != "default_user":
        _session_person_id = existing
        _annotate_context(context, existing, _load().get(existing) or {})
        return existing

    # 2. Session memory
    if _session_person_id and not _session_person_id.startswith(ANONYMOUS_PREFIX):
        persons = _load()
        if _session_person_id in persons:
            _annotate_context(context, _session_person_id, persons[_session_person_id])
            return _session_person_id

    # 3. Parse user input
    user_input = (context.get("latest_user_input") or "").strip()
    if user_input:
        persons = _load()

        # AI peer detection
        if _is_ai_peer(user_input):
            # Try to extract a name ("I'm Orrin-beta") otherwise use generic AI id
            raw_name = _extract_name_from_text(user_input)
            if raw_name and raw_name.lower() not in ("an", "a", "another"):
                person_id = _name_to_id(raw_name)
            else:
                person_id = "ai_peer"
            display_name = raw_name or "AI peer"
            _ensure_person(person_id, display_name, persons, person_type="ai_peer")
            _save(persons)
            _session_person_id = person_id
            _annotate_context(context, person_id, persons[person_id])
            log_private(f"[person_detector] AI peer identified: {person_id}")
            return person_id

        # Human introduction
        raw_name = _extract_name_from_text(user_input)
        if raw_name:
            existing_id = _find_by_alias(raw_name, persons)
            if existing_id:
                person_id = existing_id
                _ensure_person(person_id, persons[person_id]["display_name"], persons, extra_alias=raw_name)
            else:
                person_id = _name_to_id(raw_name)
                rel = _detect_relation(raw_name)
                if rel:
                    display = raw_name
                    _ensure_person(person_id, display, persons)
                    related_to_id, relation_label = rel
                    persons[person_id].setdefault("relation_to_others", {})[related_to_id] = relation_label
                else:
                    display = raw_name.split("'")[0].strip()
                    _ensure_person(person_id, display, persons)

            # A self-introduction names the active record (BEHAVIOR_FIX_PLAN
            # Phase 3): the speaker IS the anonymous session person — fold that
            # record into the named one instead of leaving a "someone" orphan.
            persons[person_id]["person_type"] = "named"
            if _session_person_id and _session_person_id.startswith(ANONYMOUS_PREFIX):
                _merge_person_records(persons, _session_person_id, person_id)
            _merge_anonymous_duplicates(persons)
            _link_kg_entity(persons, person_id)

            _save(persons)
            _session_person_id = person_id
            _annotate_context(context, person_id, persons[person_id])
            log_private(f"[person_detector] Person resolved from input: {person_id}")
            return person_id

    # 4. Anonymous fallback — preserve session continuity even for unnamed speakers
    if _session_person_id and _session_person_id.startswith(ANONYMOUS_PREFIX):
        persons = _load()
        if _session_person_id in persons:
            _annotate_context(context, _session_person_id, persons[_session_person_id])
            return _session_person_id

    # Anonymous person: REUSE the most recent unnamed record before minting a
    # new one. Single-user installs were accumulating a fresh "someone" every
    # session (5+ identical anon records in a day), which also meant a later
    # introduction could only ever name the latest sliver of history.
    persons = _load()
    anon_id = None
    try:
        anons = [
            (pid, p) for pid, p in persons.items()
            if pid.startswith(ANONYMOUS_PREFIX) and p.get("person_type") == "unknown"
        ]
        if anons:
            anon_id, _p = max(anons, key=lambda kv: str(kv[1].get("last_seen", "")))
            _p["last_seen"] = now_iso_z()
            _p["session_count"] = int(_p.get("session_count", 0) or 0) + 1
            log_private(f"[person_detector] Reusing anonymous person {anon_id} "
                        f"(session {_p['session_count']})")
    except Exception as _e:
        record_failure("person_detector.detect_and_set_person_id", _e)
    if anon_id is None:
        anon_id = _new_anon_id()
        _ensure_person(anon_id, "someone", persons, person_type="unknown")
    _save(persons)
    _session_person_id = anon_id
    _annotate_context(context, anon_id, persons[anon_id])
    return anon_id


def _annotate_context(context: Dict[str, Any], person_id: str, person: Dict[str, Any]) -> None:
    context["person_id"]            = person_id
    context["user_id"]              = person_id   # backward-compat alias
    context["person_display_name"]  = person.get("display_name", "someone")
    context["person_type"]          = person.get("person_type", "unknown")
    relations = person.get("relation_to_others") or {}
    if relations:
        context["person_relations"] = relations


def reset_session_identity() -> None:
    """Call at session start to allow re-detection. Does NOT clear the file."""
    global _session_person_id
    _session_person_id = None


def get_known_persons() -> Dict[str, Any]:
    return _load()


def write_person_note(person_id: str, note: str) -> None:
    """Let Orrin append a social observation to a person's record."""
    try:
        persons = _load()
        if person_id not in persons:
            return
        existing = persons[person_id].get("notes", "")
        ts = now_iso_z()[:10]
        persons[person_id]["notes"] = f"{existing}\n[{ts}] {note}".strip()[-2000:]
        _save(persons)
    except Exception as e:
        log_private(f"[person_detector] write_person_note failed: {e}")


def get_person_display_name(person_id: str) -> str:
    """Return display name for a person_id, or 'them' as fallback."""
    try:
        persons = _load()
        return persons.get(person_id, {}).get("display_name", "them") or "them"
    except Exception as _e:
        record_failure("person_detector.get_person_display_name", _e)
        return "them"


def get_person_type(person_id: str) -> str:
    """Return 'human' | 'ai_peer' | 'unknown' for a person_id."""
    try:
        return _load().get(person_id, {}).get("person_type", "unknown")
    except Exception as _e:
        record_failure("person_detector.get_person_type", _e)
        return "unknown"


# Backward compat — old callers used detect_and_set_user_id
detect_and_set_user_id = detect_and_set_person_id
