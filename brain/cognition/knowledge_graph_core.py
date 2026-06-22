# brain/cognition/knowledge_graph_core.py
# Core of the symbolic knowledge graph (Phase 4.5C, from knowledge_graph.py):
# the schema/vocabulary/bootstrap constants, the extraction patterns + noise and
# stopword filters, the id/tokenize/jaccard/recency utility functions, graph I/O
# (_load_graph / _graph_session normalize-on-load + save-on-exit), and the
# low-level in-place entity/relation operations (_add_entity_inplace /
# _add_relation_inplace + name validation/normalization). This is the leaf the
# extraction layer and the public API both build on.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import getpass
import hashlib
import math
import platform
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional, Set

from brain.utils.json_utils import load_json, save_json, modify_json, AbortModify
from brain.paths import KNOWLEDGE_GRAPH_FILE
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)


# ─── Schema version ──────────────────────────────────────────────────────────
_SCHEMA_VERSION = 1

# ─── Entity and relation type vocabularies ───────────────────────────────────
ENTITY_TYPES: frozenset = frozenset({
    "person", "place", "concept", "project", "tool",
    "value", "event", "organization", "AI", "unknown",
})
RELATION_TYPES: frozenset = frozenset({
    "knows", "created", "works_on", "part_of", "related_to",
    "caused_by", "is_a", "uses", "said", "located_in", "authored_by",
    "cares_about", "opposes", "supports",
})

# ─── Bootstrap entities (seeded on first load) ───────────────────────────────
# Host facts are derived at load time so the seeded graph is correct on any OS.
_HOME         = str(Path.home())
_USERNAME     = getpass.getuser() or "user"
_OS_NAME      = f"{platform.system()} {platform.release()}".strip() or "unknown OS"
_ARCH         = platform.machine() or "unknown"
_HOSTNAME     = platform.node() or f"{platform.system()} machine"
_PROJECT_PATH = str(Path(__file__).resolve().parents[2])  # repo root (…/orrin_v3)

_BOOTSTRAP: List[Dict] = [
    {
        "name": "Orrin", "type": "AI",
        "tags": ["orrin", "ai", "self", "agent", "cognitive"],
        "properties": {"role": "self", "version": "v3"},
        "confidence": 1.0, "never_decay": True,
    },
    {
        "name": "Ric Massey", "type": "person",
        "tags": ["ric", "ricmassey", "user", "person", "human", "creator"],
        "properties": {"role": "creator", "username": _USERNAME, "home": _HOME},
        "confidence": 0.98, "never_decay": True,
    },
    {
        "name": _HOSTNAME, "type": "tool",
        "tags": ["computer", "machine", "hardware", platform.system().lower()],
        "properties": {"os": _OS_NAME, "arch": _ARCH, "hostname": _HOSTNAME},
        "confidence": 0.98, "never_decay": True,
    },
    {
        "name": "orrin_v3", "type": "project",
        "tags": ["orrin", "project", "brain", "v3", "python", "ai", "agent"],
        "properties": {"path": _PROJECT_PATH, "language": "Python"},
        "confidence": 0.98, "never_decay": True,
    },
]

# ─── Noise filter: known-garbage tokens the extraction patterns pick up ───────
# These are common English words / system-log artifacts that happen to be
# capitalized mid-sentence. Adding them to _STOPWORDS would affect tag
# generation; a separate exact-match blocklist keeps the two concerns distinct.
_KG_NOISE: frozenset = frozenset({
    # Common adjectives / verbs that appear Title-Case or ALL-CAPS
    "Weak", "Strong", "General", "Similar", "Working", "Event", "Object",
    "Error", "True", "False", "None", "Unknown", "Default", "Current",
    "State", "Data", "Note", "Text", "Type", "Item", "Value", "Key",
    "Process", "Thread", "Loop", "Step", "Task", "Node", "Edge", "Path",
    "Block", "Gap", "Draft", "Check", "Test", "Run", "Log", "File",
    "Update", "Change", "Result", "Output", "Input", "Signal", "Score",
    # ALL-CAPS system log / LLM schema artifacts
    "GENERAL", "CAUSES", "REQUIRES", "EMOTIONAL", "WEAK", "STRONG",
    "SIMILAR", "WORKING", "TRUE", "FALSE", "ERROR", "STATE", "DATA",
    "TYPE", "NOTE", "NONE", "UNKNOWN", "DEFAULT", "SYSTEM", "PROCESS",
    "CAUSES", "REQUIRES", "USES", "HAS", "ARE", "WAS", "WERE", "BEEN",
    "OUTPUT", "INPUT", "SIGNAL", "SCORE", "VALUE", "KEY", "PATH", "LOG",
    "FILE", "STEP", "TASK", "NODE", "EDGE", "BLOCK", "GAP", "DRAFT",
})

# ─── Stopwords excluded from tag generation ──────────────────────────────────
_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "that", "this", "these",
    "those", "it", "its", "i", "you", "he", "she", "we", "they", "me",
    "him", "her", "us", "them", "my", "your", "his", "our", "their",
    "not", "no", "any", "all", "each", "every", "some", "few", "also",
    "just", "then", "than", "there", "here", "when", "what", "which",
    "who", "how", "why", "very", "so", "too", "about", "into", "through",
    "during", "before", "after", "above", "below", "between", "more",
    "most", "other", "only", "same", "both", "because", "while",
    "although", "if", "as", "now", "still", "already", "much", "many",
    "think", "know", "feel", "want", "need", "make", "take", "get", "see",
    "look", "go", "come", "say", "tell", "ask", "help", "work", "use",
    "try", "find", "give", "keep", "start", "like", "seems", "seem",
    "actually", "really", "quite", "something", "nothing", "everything",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
}

# ─── Extraction patterns ──────────────────────────────────────────────────────
# Target groups use strict proper-noun sequences: each word must start with a capital
# letter. This prevents "Orrin every day" from being captured as a single entity.
_PROPER_WORD = r'[A-Z][a-zA-Z0-9]+'
_PROPER_SEQ  = rf'{_PROPER_WORD}(?:\s+{_PROPER_WORD}){{0,2}}'   # 1-3 capitalized words

# "X is a Y" → entity X, type hint Y
_IS_A_RE     = re.compile(rf'\b({_PROPER_SEQ})\s+is\s+an?\s+([a-z][a-zA-Z0-9 ]{{1,30}})\b')
# "X created/built/made/wrote Y"
_CREATED_RE  = re.compile(rf'\b({_PROPER_WORD})\s+(?:created?|made?|built?|wrote?|authored?)\s+({_PROPER_SEQ})\b')
# "X works on Y"
_WORKS_RE    = re.compile(rf'\b({_PROPER_WORD})\s+(?:is\s+)?works?\s+on\s+({_PROPER_SEQ})\b')
# "X uses Y"
_USES_RE     = re.compile(rf'\b({_PROPER_WORD})\s+uses?\s+({_PROPER_SEQ})\b')
# "X cares about Y" — target may be lowercase (values, concepts)
_CARES_RE    = re.compile(rf'\b({_PROPER_WORD})\s+cares?\s+about\s+([A-Za-z0-9]+(?:\s+[A-Za-z0-9]+){{0,3}})\b')
# Proper noun sequences (multi-word or single-word capitalized mid-sentence)
_PROPER_RE   = re.compile(r'(?<![.!?]\s)\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b')

# Type hint vocabulary for "is a/an" patterns
_TYPE_HINTS: Dict[str, str] = {
    "person": "person", "human": "person", "man": "person", "woman": "person",
    "place": "place", "city": "place", "location": "place", "country": "place",
    "project": "project", "initiative": "project",
    "tool": "tool", "library": "tool", "framework": "tool", "platform": "tool",
    "package": "tool", "module": "tool", "api": "tool", "sdk": "tool",
    "database": "tool", "engine": "tool",
    "concept": "concept", "idea": "concept", "principle": "concept", "theory": "concept",
    "algorithm": "concept", "technique": "concept", "approach": "concept", "method": "concept",
    "event": "event", "meeting": "event", "session": "event", "moment": "event",
    "organization": "organization", "company": "organization", "team": "organization",
    "value": "value", "belief": "value",
    "ai": "AI", "agent": "AI", "model": "AI", "system": "tool",
    "language": "tool", "protocol": "tool",
}

# Lowercase entity pattern — only fires when the type hint is an explicitly known keyword.
# Catches tech/code names that are conventionally lowercase: "python is a language",
# "pandas is a library", "docker is a platform".
# Using longest-first alternation prevents partial matches (e.g. "api" before "a").
_KNOWN_TYPE_WORDS = "|".join(
    re.escape(k) for k in sorted(_TYPE_HINTS, key=len, reverse=True)
)
_LOWERCASE_IS_A_RE = re.compile(
    rf'\b([a-z][a-z0-9_\-]{{1,30}})\s+is\s+an?\s+({_KNOWN_TYPE_WORDS})\b'
)

# ─── Decay and similarity constants ──────────────────────────────────────────
_RECENCY_HALFLIFE_DAYS = 30.0     # entity recency half-life
_DECAY_PER_DAY         = 0.008    # confidence erosion per idle day
_DECAY_FLOOR           = 0.05     # prune below this confidence
_ENTITY_CAP            = 600      # max entities to store
_RELATION_CAP          = 500      # max relations to store
_MENTION_LOG_BASE      = 5.0      # log base for mention-count scoring
_MIN_SIMILARITY        = 0.04     # minimum jaccard to include in results (fallback path)
_MIN_SIMILARITY_EMBED  = 0.20     # minimum cosine when dense embeddings are active
_MIN_PROMPT_ENTITIES   = 2        # skip prompt injection if fewer relevant entities


# ─── Utility functions ────────────────────────────────────────────────────────

def _entity_id(name: str) -> str:
    return hashlib.sha1(name.strip().lower().encode()).hexdigest()[:12]


def _relation_id(src_id: str, relation: str, tgt_id: str) -> str:
    return hashlib.sha1(f"{src_id}:{relation}:{tgt_id}".encode()).hexdigest()[:12]



def _tokenize(text: str) -> Set[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) >= 2}


def _entity_tags(ent: Dict) -> Set[str]:
    """Compute full tag set for an entity (name + type + aliases + properties)."""
    tags: Set[str] = set(ent.get("tags") or [])
    tags |= _tokenize(ent.get("name", ""))
    tags |= _tokenize(ent.get("type", ""))
    for alias in ent.get("aliases") or []:
        tags |= _tokenize(alias)
    for v in (ent.get("properties") or {}).values():
        if isinstance(v, str):
            tags |= _tokenize(v)
    return tags


def _jaccard(a: Set[str], b: Set[str]) -> float:
    """Weighted Jaccard similarity — sparse bag-of-words analogue of cosine."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _recency_weight(last_updated_iso: str) -> float:
    """Exponential recency decay with 30-day half-life."""
    try:
        ts = datetime.fromisoformat(last_updated_iso.replace("Z", "+00:00"))
        days_old = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
        return math.exp(-days_old * math.log(2.0) / _RECENCY_HALFLIFE_DAYS)
    except Exception:
        return 0.3


def _infer_type(name: str, hint: str = "") -> str:
    combined = (name + " " + hint).lower()
    for keyword, etype in _TYPE_HINTS.items():
        if keyword in combined:
            return etype
    return "unknown"


# ─── Graph I/O ───────────────────────────────────────────────────────────────

def _normalize_graph_inplace(g: Dict) -> None:
    """Ensure schema defaults and bootstrap entities/relations exist. Mutates g in place."""
    g.setdefault("entities", {})
    g.setdefault("relations", [])
    g.setdefault("meta", {
        "version": _SCHEMA_VERSION,
        "last_updated": now_iso_z(),
        "last_consolidation": "",
    })
    # Upsert bootstrap entities every load — ensures new bootstrap entries
    # are added even if the graph already has other entities.
    now = now_iso_z()
    for bp in _BOOTSTRAP:
        eid = _entity_id(bp["name"])
        if eid not in g["entities"]:
            g["entities"][eid] = {
                "id": eid, "name": bp["name"], "type": bp.get("type", "unknown"),
                "aliases": bp.get("aliases", []), "tags": list(bp.get("tags", [])),
                "properties": dict(bp.get("properties", {})),
                "confidence": bp.get("confidence", 0.7),
                "never_decay": bp.get("never_decay", False),
                "first_seen": now, "last_updated": now,
                "source": "bootstrap", "mentions": 1,
            }
        else:
            # Always keep never_decay flag synced for existing bootstrap entries
            g["entities"][eid]["never_decay"] = bp.get("never_decay", False)
    # Upsert bootstrap relations
    for rel_src, rel_type, rel_tgt, conf in [
        ("Orrin",       "is_a",    "orrin_v3",   0.98),
        ("Orrin",       "knows",   "Ric Massey",  0.98),
        ("Ric Massey",  "created", "Orrin",       0.98),
        ("Orrin",       "uses",    "MacBook Air", 0.95),
    ]:
        _add_relation_inplace(g, rel_src, rel_type, rel_tgt, confidence=conf, source="bootstrap")


def _load_graph() -> Dict:
    """Read-only load for query paths (get_neighbors, query_relevant, …)."""
    g = load_json(KNOWLEDGE_GRAPH_FILE, default_type=dict) or {}
    if not isinstance(g, dict):
        g = {}
    _normalize_graph_inplace(g)
    return g


@contextmanager
def _graph_session() -> Generator[Dict, None, None]:
    """
    Hold the knowledge-graph file lock across a full read -> modify -> write cycle
    (modify_json), so concurrent mutators (add_entity, add_relation, observe,
    decay_old_entities, consolidate_from_long_memory) can't interleave and lose
    each other's updates.

    Usage:
        with _graph_session() as g:
            _add_entity_inplace(g, ...)
        # graph saved automatically with refreshed meta counts
    """
    # Self-heal: if the file holds valid-but-wrong-typed JSON (not a dict),
    # reset it before acquiring the lock so modify_json's default_type=dict
    # path is exercised below.
    try:
        _existing = load_json(KNOWLEDGE_GRAPH_FILE, default_type=dict)
        if not isinstance(_existing, dict):
            save_json(KNOWLEDGE_GRAPH_FILE, {})
    except Exception as _e:
        record_failure("knowledge_graph._graph_session", _e)

    with modify_json(KNOWLEDGE_GRAPH_FILE, default_type=dict) as g:
        if not isinstance(g, dict):
            raise AbortModify("knowledge graph corrupt")
        _normalize_graph_inplace(g)
        yield g
        g["meta"]["last_updated"] = now_iso_z()
        g["meta"]["entity_count"] = len(g["entities"])
        g["meta"]["relation_count"] = len(g["relations"])


# ─── Low-level in-place operations (no I/O, operate on graph dict) ────────────

# Goal-phrasing scaffolding that must never enter the knowledge graph as a concept.
# A concept is a TOPIC ("the island"), not a goal phrasing ("Understand the island
# more deeply"). When goal titles leaked in via the research path they fed the goal
# template back into itself ("…more deeply more deeply"). Normalising here — the
# single entity-ingestion chokepoint — stops the loop at its source for every caller.
_SCAFFOLD_LEAD_RE  = re.compile(r"^\s*(?:understand|learn about|find out)\b\s*:?\s*", re.I)
_SCAFFOLD_DEEPLY_RE = re.compile(r"\s+more deeply\b\.?\s*$", re.I)

# Entity sanity (Phase 1.5): pure numbers / percentages / durations ("+15%",
# "5h 5", "around hour") are measurements, not entities. A valid entity needs
# at least one alphabetic token that isn't a stopword or a bare unit word.
_UNIT_STOPWORDS = frozenset({
    "the", "a", "an", "of", "in", "on", "at", "to", "and", "or", "about",
    "around", "approximately", "roughly", "nearly", "over", "under", "per",
    "hour", "hours", "hr", "hrs", "minute", "minutes", "min", "mins",
    "second", "seconds", "sec", "secs", "day", "days", "week", "weeks",
    "month", "months", "year", "years", "percent", "pct", "ms", "kb", "mb",
    "gb", "h", "m", "s",
})


def is_valid_entity_name(name: str) -> bool:
    """Reject number-only / unit-only candidates at the ingestion chokepoint."""
    if not isinstance(name, str):
        return False
    tokens = re.findall(r"[A-Za-z]+", name)
    return any(t.lower() not in _UNIT_STOPWORDS for t in tokens)


def normalize_entity_name(name: str) -> str:
    """Reduce a name to its bare topic, idempotently: strip goal scaffolding
    ('Understand …', 'Find out: …', trailing ' more deeply' — repeated). A clean
    name passes through unchanged. Shared with intrinsic_goals so there is one
    definition of 'bare topic' across production and consumption."""
    out = (name or "").strip()
    # The provenance wrapper gates trust; it must never become an entity name
    # (audit §5: a concept named '[EXTERNAL/UNTRUSTED source=https' was learned).
    if "[EXTERNAL" in out:
        try:
            from brain.utils.content_quarantine import strip_quarantine
            out = strip_quarantine(out)
        except Exception:
            out = re.sub(r"\[/?EXTERNAL[^\]]*\]?", " ", out).strip()
    for _ in range(8):
        before = out
        out = _SCAFFOLD_DEEPLY_RE.sub("", out).strip()
        out = _SCAFFOLD_LEAD_RE.sub("", out).strip()
        if out == before:
            break
    return out


def _add_entity_inplace(
    g: Dict, name: str, entity_type: str = "unknown",
    properties: Optional[Dict] = None, confidence: float = 0.6,
    source: str = "observation", aliases: Optional[List[str]] = None,
    extra_tags: Optional[List[str]] = None,
) -> str:
    # Normalise away goal-phrasing scaffolding before anything else, so a leaked
    # goal title ("Understand the island more deeply") merges with the real concept
    # ("the island") instead of spawning a corrupted duplicate.
    name = normalize_entity_name(name)
    if not name or len(name) < 2:
        return ""
    if not is_valid_entity_name(name):
        return ""  # "+15%", "5h 5", "around hour" — measurements, not entities
    eid = _entity_id(name)
    now = now_iso_z()
    if eid in g["entities"]:
        ent = g["entities"][eid]
        ent["mentions"] = ent.get("mentions", 0) + 1
        # Confidence creeps toward 0.98 with repeated observation
        old_conf = float(ent.get("confidence", 0.6))
        ent["confidence"] = round(min(0.98, old_conf + (0.98 - old_conf) * 0.08), 4)
        ent["last_updated"] = now
        if properties:
            ent.setdefault("properties", {}).update(properties)
        if aliases:
            ea = ent.setdefault("aliases", [])
            for a in aliases:
                if a not in ea:
                    ea.append(a)
        if extra_tags:
            et = ent.setdefault("tags", [])
            for t in extra_tags:
                if t not in et:
                    et.append(t)
    else:
        tags = list(_tokenize(name) | _tokenize(entity_type))
        if extra_tags:
            tags = list(set(tags) | set(extra_tags))
        etype = entity_type if entity_type in ENTITY_TYPES else "unknown"
        g["entities"][eid] = {
            "id": eid, "name": name, "type": etype,
            "aliases": list(aliases or []),
            "tags": list(set(tags)),
            "properties": dict(properties or {}),
            "confidence": round(confidence, 4),
            "never_decay": False,
            "first_seen": now, "last_updated": now,
            "source": source, "mentions": 1,
        }
        try:  # surface new entities into the Brain Memory Inspector (knowledge store)
            from backend.telemetry_bridge import mirror_memory as _mm
            _mm("write", store="knowledge", key=name, summary=f"{etype}: {name}", salience=confidence)
        except Exception:
            pass
        # Evict oldest low-confidence entities if at cap
        if len(g["entities"]) > _ENTITY_CAP:
            candidates = sorted(
                [(k, v) for k, v in g["entities"].items() if not v.get("never_decay")],
                key=lambda kv: float(kv[1].get("confidence", 0)) * _recency_weight(kv[1].get("last_updated", "")),
            )
            for k, _ in candidates[:20]:
                del g["entities"][k]
    return eid


def _norm_relation(rel: str) -> str:
    """Sanitize a verb-derived relation into a stable type (lives_in, directed,
    founded…). spaCy already lemmatizes verbs, so tenses collapse to one form. Only
    truly empty/garbage falls back to the generic 'related_to'."""
    r = "".join(ch if (ch.isalpha() or ch == "_") else "_" for ch in str(rel).lower()).strip("_")
    while "__" in r:
        r = r.replace("__", "_")
    return r if 2 <= len(r) <= 32 else "related_to"


def _add_relation_inplace(
    g: Dict, source_name: str, relation: str, target_name: str,
    confidence: float = 0.5, source: str = "observation",
) -> bool:
    if not source_name or not target_name or not relation:
        return False
    # Keep real, meaningful relation types (directed / performs / lives_in / founded)
    # instead of flattening every learned relation to "related_to". Known canonical
    # types pass straight through; verb-derived ones are sanitized; only garbage
    # degrades to the generic link.
    relation = relation if relation in RELATION_TYPES else _norm_relation(relation)
    # Ensure both endpoints exist
    for nm in (source_name, target_name):
        if _entity_id(nm) not in g["entities"]:
            _add_entity_inplace(g, nm, source=source, confidence=0.45)
    src_id = _entity_id(source_name)
    tgt_id = _entity_id(target_name)
    rid = _relation_id(src_id, relation, tgt_id)
    now = now_iso_z()
    for rel in g["relations"]:
        if rel.get("id") == rid:
            rel["confidence"] = round(min(0.98, float(rel.get("confidence", 0.5)) + 0.07), 4)
            rel["last_updated"] = now
            return True
    g["relations"].append({
        "id": rid, "source_id": src_id, "source_name": source_name,
        "relation": relation, "target_id": tgt_id, "target_name": target_name,
        "confidence": round(confidence, 4),
        "first_seen": now, "last_updated": now, "source": source,
    })
    try:  # surface new relations into the Brain Memory Inspector (knowledge store)
        from backend.telemetry_bridge import mirror_memory as _mm
        _mm("write", store="knowledge", key=f"{source_name} {relation} {target_name}"[:80],
            summary=f"{source_name} —[{relation}]→ {target_name}", salience=confidence)
    except Exception:
        pass
    if len(g["relations"]) > _RELATION_CAP:
        g["relations"].sort(key=lambda r: r.get("last_updated", ""), reverse=True)
        g["relations"] = g["relations"][:int(_RELATION_CAP * 0.85)]
    return True


