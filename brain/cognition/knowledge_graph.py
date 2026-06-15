# brain/cognition/knowledge_graph.py
# Persistent symbolic knowledge graph with keyword similarity index.
#
# Storage:  data/knowledge_graph.json
# Entities: typed nodes (person/place/concept/project/tool/event/org/value)
#           with tag sets, properties, confidence, and decay
# Relations: directed typed edges (knows/created/works_on/part_of/…)
#
# Similarity layer: weighted Jaccard on entity tag sets.
#   This is a sparse binary vector encoding (bag-of-words).
#   The query API is embedding-ready: replace _jaccard() with cosine(embed(q), embed(e))
#   and cache embed vectors in entities["embedding"] to upgrade without changing callers.
#
# Three update paths:
#   1. Heuristic (every cycle):  observe(user_input) — regex patterns, no LLM call
#   2. External ingest:          look_outward.ingest_outward_result feeds web results
#   3. LLM-assisted (dream):     consolidate_from_long_memory — richer structured extraction
from __future__ import annotations
from core.runtime_log import get_logger

import getpass
import hashlib
import math
import platform
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

from utils.json_utils import load_json, save_json, safe_extract_json, modify_json, AbortModify
from utils.log import log_activity, log_private
from paths import KNOWLEDGE_GRAPH_FILE
from utils.timeutils import now_iso_z
from utils.llm_gate import llm_callable_by
from utils.embed_similarity import text_similarity, embeddings_available
from utils.content_quarantine import PROMPT_NOTE as _EXTERNAL_CONTENT_NOTE, is_quarantined
from utils.failure_counter import record_failure
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
            from utils.content_quarantine import strip_quarantine
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


def _is_noise(name: str) -> bool:
    """True if this candidate entity name is known garbage."""
    if not name:
        return True
    # All-caps single-word tokens are system-log / schema artifacts, not entities
    if name == name.upper() and " " not in name:
        return True
    if name in _KG_NOISE or name.lower() in _KG_NOISE:
        return True
    # Multi-word phrases containing any noise token are also garbage
    for word in name.split():
        if word in _KG_NOISE or word.upper() in _KG_NOISE:
            return True
    return False


# Minimum confidence required for an entity to survive, keyed by extraction source.
# Keeps the graph clean: weak signal sources must clear a higher bar.
_MIN_CONF_BY_SOURCE: Dict[str, float] = {
    "bare_proper_noun":      0.36,
    "lowercase_is_a":        0.50,
    "long_memory_heuristic": 0.38,
    "observation":           0.40,
}
_DEFAULT_MIN_CONF = 0.35


def _validate_candidate(
    name: str,
    entity_type: str,
    confidence: float,
    source: str,
) -> Tuple[bool, float, str]:
    """
    Symbolic validation gate between regex match and graph insertion.

    Returns (is_valid, adjusted_confidence, rejection_reason).
    rejection_reason is "" on success.

    Confidence is adjusted — not just checked — so scores reflect actual
    signal quality rather than flat regex-match defaults:
      - Known entity type  → small boost  (interpretable signal)
      - Unknown type       → small penalty (ambiguous)
      - Source minimum     → hard floor per extraction path
    """
    if len(name) < 2:
        return False, 0.0, "too_short"
    if len(name) > 80:
        return False, 0.0, "too_long"
    if _is_noise(name):
        return False, 0.0, "noise"
    if name.lower() in _STOPWORDS:
        return False, 0.0, "stopword"
    # Purely numeric tokens are not entities (dates, counts, etc.)
    if re.fullmatch(r'[\d\s\.\-,:/%+]+', name):
        return False, 0.0, "numeric"
    # Mostly-digit tokens and time/measure fragments aren't entities either —
    # the regex fallback was minting "+15%", "5h 5", "9h 54" as graph nodes.
    _alnum = [c for c in name if c.isalnum()]
    if _alnum and sum(c.isdigit() for c in _alnum) / len(_alnum) > 0.5:
        return False, 0.0, "mostly_numeric"
    if re.fullmatch(r'(?:around\s+)?\d*\s*(?:h|hr|hrs|hour|hours|m|min|mins|s|sec|secs)\b.*', name.lower()):
        return False, 0.0, "time_fragment"
    # Generic determiner/quantifier openers are phrases, not entities
    # ("around hour", "New files", "some changes") — unless the head word is
    # itself capitalized (proper noun: "New York" stays).
    _gp = re.match(r'^(?:around|new|some|many|more|other|several|various)\s+(\S+)', name, re.IGNORECASE)
    if _gp and not _gp.group(1)[0].isupper():
        return False, 0.0, "generic_phrase"

    # Confidence calibration by type quality
    if entity_type in ENTITY_TYPES and entity_type != "unknown":
        confidence = min(0.98, confidence * 1.04)   # known type: small boost
    else:
        confidence = confidence * 0.92              # unknown type: small penalty

    # Source-minimum threshold
    min_conf = _MIN_CONF_BY_SOURCE.get(source, _DEFAULT_MIN_CONF)
    if confidence < min_conf:
        return False, 0.0, f"below_min({source}:{min_conf:.2f})"

    return True, round(confidence, 4), ""


def _extract_with_regex(g: Dict, text: str, source: str) -> Tuple[int, int]:
    """
    Regex-based heuristic extraction directly on graph dict (fallback parser).
    Returns (entities_added_or_updated, relations_added_or_updated).

    Validation contract:
      Every candidate passes through _validate_candidate() before insertion.
      Rejected candidates are logged at DEBUG level (not silently dropped).
      When nothing is extracted from substantial text, that is also logged
      so the extraction pipeline stays auditable.
    """
    entities_n = 0
    relations_n = 0
    rejected: List[str] = []   # (name:reason) pairs collected for debug log
    text = (text or "")

    def _guarded_add_entity(
        name: str, etype: str, conf: float, src: str, **kwargs: Any
    ) -> bool:
        """Validate, then add. Returns True if accepted."""
        ok, adj, reason = _validate_candidate(name, etype, conf, src)
        if not ok:
            rejected.append(f"{name!r}:{reason}")
            return False
        _add_entity_inplace(g, name, etype, confidence=adj, source=src, **kwargs)
        return True

    # ── Pattern 1: "X is a Y" (capital X) → entity X with type hint ─────────
    for m in _IS_A_RE.finditer(text):
        name = m.group(1).strip()
        hint = m.group(2).strip().lower()
        etype = _infer_type(name, hint)
        if _guarded_add_entity(name, etype, 0.68, source,
                               extra_tags=[hint.replace(" ", "_")]):
            entities_n += 1

    # ── Pattern 2: "x is a/an [known-type]" (lowercase x) ────────────────────
    # Catches tech/code names: "python is a language", "pandas is a library".
    # Only fires when type hint is an explicitly known keyword — prevents
    # single common words from becoming entities.
    for m in _LOWERCASE_IS_A_RE.finditer(text):
        name = m.group(1).strip()
        hint = m.group(2).strip().lower()
        etype = _TYPE_HINTS.get(hint, "unknown")
        if _guarded_add_entity(name, etype, 0.58, "lowercase_is_a",
                               extra_tags=[hint]):
            entities_n += 1

    # ── Pattern 3: "X created/built/wrote/authored Y" ─────────────────────────
    for m in _CREATED_RE.finditer(text):
        src, tgt = m.group(1).strip(), m.group(2).strip()
        if (src and tgt
                and _guarded_add_entity(src, "unknown", 0.62, source)
                and _guarded_add_entity(tgt, "unknown", 0.62, source)):
            _add_relation_inplace(g, src, "created", tgt, confidence=0.68, source=source)
            entities_n += 2; relations_n += 1

    # ── Pattern 4: "X works on Y" ─────────────────────────────────────────────
    for m in _WORKS_RE.finditer(text):
        src, tgt = m.group(1).strip(), m.group(2).strip()
        if (src and tgt
                and _guarded_add_entity(src, "unknown", 0.58, source)
                and _guarded_add_entity(tgt, "unknown", 0.58, source)):
            _add_relation_inplace(g, src, "works_on", tgt, confidence=0.62, source=source)
            entities_n += 2; relations_n += 1

    # ── Pattern 5: "X uses Y" ─────────────────────────────────────────────────
    for m in _USES_RE.finditer(text):
        src, tgt = m.group(1).strip(), m.group(2).strip()
        if (src and tgt
                and _guarded_add_entity(src, "unknown", 0.52, source)
                and _guarded_add_entity(tgt, "unknown", 0.52, source)):
            _add_relation_inplace(g, src, "uses", tgt, confidence=0.55, source=source)
            entities_n += 2; relations_n += 1

    # ── Pattern 6: "X cares about Y" ──────────────────────────────────────────
    for m in _CARES_RE.finditer(text):
        src = m.group(1).strip()
        tgt = re.sub(r'[.,;!?]+$', '', m.group(2).strip()).strip()
        if (src and tgt and len(tgt) >= 2
                and _guarded_add_entity(src, "person", 0.55, source)
                and _guarded_add_entity(tgt, "unknown", 0.50, source)):
            _add_relation_inplace(g, src, "cares_about", tgt, confidence=0.55, source=source)
            entities_n += 2; relations_n += 1

    # ── Pattern 7: Bare proper noun sequences (weakest signal) ────────────────
    seen: Set[str] = set()
    for m in _PROPER_RE.finditer(text):
        noun = m.group(1).strip()
        if noun in seen or noun.lower() in _STOPWORDS:
            continue
        seen.add(noun)
        words = noun.split()
        if len(words) == 1 and len(noun) < 4:
            rejected.append(f"{noun!r}:too_short_bare")
            continue
        etype = _infer_type(noun)
        if _guarded_add_entity(noun, etype, 0.40, "bare_proper_noun"):
            entities_n += 1

    # ── Audit log ─────────────────────────────────────────────────────────────
    if rejected:
        _log.debug("[kg] %s: rejected %d candidate(s): %s",
                   source, len(rejected), ", ".join(rejected[:8]))
    if entities_n == 0 and relations_n == 0 and len(text) > 50:
        _log.debug("[kg] no extractions from %d-char text (source=%s): %.80s…",
                   len(text), source, text)

    return entities_n, relations_n


# ─── spaCy-based extraction (preferred; regex above is the fallback) ──────────
# Entities come from spaCy NER; typed relations come from the dependency parse
# (subject→verb→object) used as a rule matcher — more robust than the regexes.
# Every candidate still passes the SAME noise filters (_validate_candidate →
# _is_noise / _STOPWORDS). If spaCy or its model is unavailable, we fall back to
# the regex parser — spaCy is not a hard dependency.
_SPACY_NLP = None
_SPACY_FAILED = False


def _get_nlp():
    global _SPACY_NLP, _SPACY_FAILED
    if _SPACY_NLP is not None or _SPACY_FAILED:
        return _SPACY_NLP
    try:
        import spacy
        # Load from the BUNDLED model path when frozen (I2 — offline first-run), else
        # the pip-installed package by name in a dev checkout.
        from utils.model_assets import spacy_model as _spacy_model
        _SPACY_NLP = spacy.load(_spacy_model("en_core_web_sm"))  # full pipeline (lemmas + parse)
        _log.info("[kg] spaCy en_core_web_sm loaded for entity extraction")
    except Exception as exc:
        _SPACY_FAILED = True
        _log.warning("[kg] spaCy unavailable (%s) — using regex extraction", exc)
    return _SPACY_NLP


def _spacy_available() -> bool:
    return _get_nlp() is not None


# spaCy NER label → graph entity type
_NER_TYPE: Dict[str, str] = {
    "PERSON": "person", "ORG": "organization", "NORP": "organization",
    "GPE": "place", "LOC": "place", "FAC": "place",
    "PRODUCT": "tool", "WORK_OF_ART": "concept", "LANGUAGE": "concept",
    "EVENT": "event",
}
# verb lemma → relation type (the dependency "rule matcher")
_REL_VERBS: Dict[str, str] = {
    "create": "created", "make": "created", "build": "created",
    "write": "created", "author": "created", "develop": "created",
    "use": "uses", "work": "works_on", "care": "cares_about",
}


def _try_add_entity(g: Dict, name: str, etype: str, conf: float, src: str,
                    rejected: List[str], **kwargs: Any) -> bool:
    """Validate (noise filters + type adjustment) then add. True if accepted."""
    name = (name or "").strip()
    if not name:
        return False
    ok, adj, reason = _validate_candidate(name, etype, conf, src)
    if not ok:
        rejected.append(f"{name!r}:{reason}")
        return False
    _add_entity_inplace(g, name, etype, confidence=adj, source=src, **kwargs)
    return True


def _span_text(tok) -> str:
    """Full proper-noun span for a dependency token (e.g. 'Ric Massey', not 'Massey')."""
    for e in tok.doc.ents:
        if e.start <= tok.i < e.end:
            return e.text.strip()
    parts = [tok] + [c for c in tok.children if c.dep_ in ("compound", "flat", "amod")]
    parts.sort(key=lambda t: t.i)
    return " ".join(t.text for t in parts).strip()


def _extract_with_spacy(g: Dict, text: str, source: str) -> Tuple[int, int]:
    nlp = _get_nlp()
    if nlp is None:
        return _extract_with_regex(g, text, source)
    entities_n = 0
    relations_n = 0
    rejected: List[str] = []
    doc = nlp((text or "")[:5000])

    # 1) Named entities
    for ent in doc.ents:
        etype = _NER_TYPE.get(ent.label_, "unknown")
        if _try_add_entity(g, ent.text, etype, 0.62, source, rejected,
                           extra_tags=[ent.label_.lower()]):
            entities_n += 1

    # 2) Typed relations + "is-a" typing from the dependency parse
    for tok in doc:
        if tok.pos_ != "VERB":
            continue
        subj = next((c for c in tok.children if c.dep_ in ("nsubj", "nsubjpass")), None)
        if subj is None:
            continue
        subj_txt = _span_text(subj)
        lemma = tok.lemma_.lower()

        # "X is a/an Y" → type X from the hint Y (matches the old _IS_A behaviour)
        if lemma == "be":
            attr = next((c for c in tok.children if c.dep_ in ("attr", "acomp")), None)
            if attr is not None and subj_txt[:1].isupper():
                hint = attr.text.lower()
                if _try_add_entity(g, subj_txt, _infer_type(subj_txt, hint), 0.66,
                                   source, rejected, extra_tags=[hint]):
                    entities_n += 1
            continue

        # Map the verb to a known relation type when possible; otherwise fall back
        # to the verb lemma itself (_add_relation_inplace coerces unknown types to
        # "related_to"). Previously EVERY non-whitelisted verb was dropped, which is
        # why he learned almost no relations despite 200+ entities — his knowledge
        # was a pile of disconnected nodes.
        rel = _REL_VERBS.get(lemma)
        obj = next((c for c in tok.children if c.dep_ in ("dobj", "obj")), None)
        if obj is None:  # prepositional object: "works on Y", "lives in Y"
            prep = next((c for c in tok.children if c.dep_ == "prep"), None)
            if prep is not None:
                obj = next((c for c in prep.children if c.dep_ == "pobj"), None)
                if obj is not None and not rel:
                    rel = f"{lemma}_{prep.text.lower()}"  # lives_in, works_on, performs_in
        if not rel:
            rel = lemma  # fall back to the bare verb (e.g. directed, founded, wrote)
        if obj is None:
            continue
        obj_txt = _span_text(obj)
        subj_type = "person" if rel == "cares_about" else "unknown"
        if (_try_add_entity(g, subj_txt, subj_type, 0.60, source, rejected)
                and _try_add_entity(g, obj_txt, "unknown", 0.58, source, rejected)):
            _add_relation_inplace(g, subj_txt, rel, obj_txt, confidence=0.62, source=source)
            entities_n += 2
            relations_n += 1

    # 2.5) Co-occurrence links — named entities mentioned together in a sentence are
    # probably related. The SVO pass above only fires on a clean subject-verb-object
    # parse, so most entity pairs were never connected. Chain-link the named entities
    # within each sentence (consecutive pairs, not full N², to avoid an explosion) at
    # low confidence; repeated co-occurrence reinforces the edge over time. This is
    # what turns 200+ isolated nodes into an actual graph he can reason across.
    try:
        _cooc_added = 0
        for sent in doc.sents:
            seen: List[str] = []
            for ent in sent.ents:
                t = (ent.text or "").strip()
                if len(t) > 2 and t.lower() not in _STOPWORDS and t not in seen:
                    seen.append(t)
            for i in range(len(seen) - 1):
                if _cooc_added >= 8:
                    break
                if _add_relation_inplace(g, seen[i], "related_to", seen[i + 1],
                                         confidence=0.4, source=source + ":cooc"):
                    relations_n += 1
                    _cooc_added += 1
    except Exception:
        pass

    # 3) Proper-noun chunks NER missed (weakest signal)
    for chunk in doc.noun_chunks:
        root = chunk.root
        if root.pos_ == "PROPN" and not root.ent_type_:
            name = _span_text(root)
            if name.lower() in _STOPWORDS:
                continue
            if _try_add_entity(g, name, _infer_type(name), 0.42, "spacy_propn", rejected):
                entities_n += 1

    if rejected:
        _log.debug("[kg] %s(spacy): rejected %d candidate(s): %s",
                   source, len(rejected), ", ".join(rejected[:8]))
    return entities_n, relations_n


# Concept / definitional capture (LLM-free). The NER + proper-noun extractors
# above are tuned for named entities (people, places, orgs) and miss lowercase
# common-noun CONCEPTS — exactly what research and reading produce ("a black hole
# is a region of spacetime"). Without this, what Orrin reads never becomes durable
# knowledge when the LLM is offline. Tulving (1972): episode → semantic.
_RESEARCH_TOPIC_RE = re.compile(r"\[(?:research|read)\]\s+(.+?)\s*[:—]", re.IGNORECASE)
_RESEARCHED_RE = re.compile(r"researched\s+['\"]([^'\"]{2,60})['\"]", re.IGNORECASE)
_DEFINITION_RE = re.compile(
    r"\b([a-z][a-z0-9][a-z0-9 \-]{1,38}?)\s+(?:is|are|was|were)\s+(?:a|an|the)\s+([a-z][a-z0-9 \-]{2,40})",
    re.IGNORECASE,
)


def _extract_definitional(g: Dict, text: str, source: str) -> Tuple[int, int]:
    """
    Capture concept entities from research/definitional text (no LLM):
      - "[research] X: …" / "[read] X: …" / "Researched 'X'" → concept entity X
      - "X is/are a/an Y"  (lowercase concept)               → concept X, X is_a Y
    Every candidate still passes _validate_candidate (noise/stopword/conf gates).
    """
    e = r = 0
    t = (text or "")[:1000]

    m = _RESEARCH_TOPIC_RE.search(t) or _RESEARCHED_RE.search(t)
    if m:
        topic = m.group(1).strip().strip("'\"").strip()
        if topic and 2 <= len(topic) <= 60 and topic.lower() not in _STOPWORDS:
            ok, adj, _reason = _validate_candidate(topic, "concept", 0.62, "research")
            if ok:
                _add_entity_inplace(g, topic, "concept", confidence=adj, source="research")
                e += 1

    seen: Set[str] = set()
    for dm in _DEFINITION_RE.finditer(t):
        subj = dm.group(1).strip().lower()
        obj = dm.group(2).strip().lower()
        if subj in seen or subj in _STOPWORDS or len(subj.split()) > 4:
            continue
        seen.add(subj)
        ok, adj, _reason = _validate_candidate(subj, "concept", 0.58, "definition")
        if not ok:
            continue
        # Keep the definitional gloss as a property on the concept rather than
        # spawning a long clause as its own entity node (that's graph noise).
        _add_entity_inplace(g, subj, "concept", properties={"is_a": obj[:120]},
                            confidence=adj, source="definition")
        e += 1
        # Only create a real is_a relation when the object is itself entity-like
        # (short noun phrase), not a full definitional clause.
        if obj and obj not in _STOPWORDS and 3 <= len(obj) and len(obj.split()) <= 3:
            if _add_relation_inplace(g, subj, "is_a", obj, confidence=0.5, source="definition"):
                r += 1
    return e, r


def _extract_from_text_inplace(g: Dict, text: str, source: str) -> Tuple[int, int]:
    """
    Extract entities + relations from text. Runs a concept/definitional pass
    first (captures lowercase concepts research produces), then prefers spaCy NER
    + dependency rule-matching, falling back to regex heuristics. All LLM-free.
    """
    e_def, r_def = _extract_definitional(g, text, source)
    if _spacy_available():
        try:
            e, r = _extract_with_spacy(g, text, source)
            return e_def + e, r_def + r
        except Exception as exc:
            _log.warning("[kg] spaCy extraction failed (%s) — regex fallback", exc)
    e, r = _extract_with_regex(g, text, source)
    return e_def + e, r_def + r


# ─── Public entity operations ─────────────────────────────────────────────────

def add_entity(
    name: str,
    entity_type: str = "unknown",
    properties: Optional[Dict] = None,
    confidence: float = 0.6,
    source: str = "observation",
    aliases: Optional[List[str]] = None,
    extra_tags: Optional[List[str]] = None,
) -> str:
    """Add or update a single entity. Returns entity ID."""
    with _graph_session() as g:
        eid = _add_entity_inplace(g, name, entity_type, properties, confidence, source, aliases, extra_tags)
    return eid


def add_relation(
    source_name: str,
    relation: str,
    target_name: str,
    confidence: float = 0.5,
    source: str = "observation",
) -> bool:
    """Add or update a typed directed relation. Returns True on success."""
    if not source_name or not target_name:
        return False
    with _graph_session() as g:
        ok = _add_relation_inplace(g, source_name, relation, target_name, confidence, source)
    return ok


def get_neighbors(entity_name: str, relation: Optional[str] = None) -> List[Dict]:
    """Return all entities related to entity_name (optionally filtered by relation type)."""
    eid = _entity_id(entity_name)
    g = _load_graph()
    results: List[Dict] = []
    for rel in g["relations"]:
        if rel.get("source_id") == eid:
            if relation is None or rel.get("relation") == relation:
                tgt = g["entities"].get(rel.get("target_id", ""))
                if tgt:
                    results.append({"entity": tgt, "relation": rel["relation"], "direction": "outbound"})
        elif rel.get("target_id") == eid:
            if relation is None or rel.get("relation") == relation:
                src = g["entities"].get(rel.get("source_id", ""))
                if src:
                    results.append({"entity": src, "relation": rel["relation"], "direction": "inbound"})
    return results


# ─── Public query operations ──────────────────────────────────────────────────

def query_relevant(text: str, limit: int = 5) -> List[Dict]:
    """
    Return top-N entities most relevant to text.
    Score = similarity(entity, query) × log_mention_factor × recency × confidence
    Similarity is cosine over cached MiniLM embeddings when available, else token-Jaccard.
    """
    query_tokens = _tokenize(text)
    if not query_tokens:
        return []
    g = _load_graph()
    use_embed = embeddings_available()
    min_sim = _MIN_SIMILARITY_EMBED if use_embed else _MIN_SIMILARITY
    scored: List[Tuple[float, Dict]] = []
    for eid, ent in g["entities"].items():
        if float(ent.get("confidence", 0.0)) < _DECAY_FLOOR:
            continue
        if use_embed:
            ent_text = (str(ent.get("name", "")) + " " + " ".join(sorted(_entity_tags(ent)))).strip()
            sim = text_similarity(text, ent_text)
        else:
            sim = _jaccard(_entity_tags(ent), query_tokens)
        if sim < min_sim:
            continue
        mentions = max(1, int(ent.get("mentions", 1)))
        mention_factor = math.log(mentions + 1, _MENTION_LOG_BASE) + 1.0
        recency = _recency_weight(ent.get("last_updated", ""))
        conf = float(ent.get("confidence", 0.5))
        score = sim * mention_factor * recency * conf
        scored.append((score, ent))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ent for _, ent in scored[:limit]]


def get_context_for_prompt(query_text: str, limit: int = 4) -> str:
    """
    Format a compact knowledge graph summary for inner loop injection.
    Returns empty string when fewer than _MIN_PROMPT_ENTITIES relevant entities found.
    """
    relevant = query_relevant(query_text, limit=limit)
    if len(relevant) < _MIN_PROMPT_ENTITIES:
        return ""
    lines = ["[Knowledge]"]
    for ent in relevant:
        name = ent["name"]
        etype = ent.get("type", "?")
        props = ent.get("properties") or {}
        prop_parts = [f"{k}={v}" for k, v in list(props.items())[:2] if isinstance(v, str)]
        prop_str = f" ({', '.join(prop_parts)})" if prop_parts else ""
        # Inline relations (compact)
        nbrs = get_neighbors(name)
        rel_parts = []
        for n in nbrs[:3]:
            n_name = n["entity"]["name"]
            n_rel = n["relation"]
            rel_parts.append(f"{n_rel}→{n_name}" if n["direction"] == "outbound" else f"{n_rel}←{n_name}")
        rel_str = " | ".join(rel_parts)
        line = f"  {name} [{etype}]{prop_str}"
        if rel_str:
            line += f" :: {rel_str}"
        lines.append(line)
    return "\n".join(lines)


# ─── Public ingest operation ──────────────────────────────────────────────────

def observe(text: str, source: str = "observation", context: Optional[Dict] = None) -> Dict:
    """
    Main ingest entrypoint. Extract entities/relations from text heuristically.
    Batches all graph modifications into a single load-modify-save cycle.
    Returns {"entities_added": n, "relations_added": m}.
    """
    text = (text or "").strip()
    if len(text) < 5:
        return {"entities_added": 0, "relations_added": 0}
    context = context or {}
    with _graph_session() as g:
        # Register current user as high-confidence person entity
        user_name = (context.get("current_person_display_name") or "").strip()
        if user_name and len(user_name) >= 2 and user_name.lower() not in _STOPWORDS:
            _add_entity_inplace(g, user_name, "person", confidence=0.92, source="context",
                                extra_tags=["user", "person"])
            _add_relation_inplace(g, "Orrin", "knows", user_name, confidence=0.92, source="context")
        e_added, r_added = _extract_from_text_inplace(g, text, source)
    if e_added or r_added:
        log_private(f"[kg] observe({source}): +{e_added}e +{r_added}r")
    return {"entities_added": e_added, "relations_added": r_added}


# ─── Maintenance ──────────────────────────────────────────────────────────────

def decay_old_entities() -> Dict:
    """
    Erode confidence of idle entities; prune those below floor.
    Safe to call during dream_cycle without corrupting active entities.
    Never decays never_decay=True entries (Orrin, bootstrap identities).
    """
    now = datetime.now(timezone.utc)
    pruned = 0
    decayed = 0
    with _graph_session() as g:
        to_remove: List[str] = []
        for eid, ent in list(g["entities"].items()):
            if ent.get("never_decay"):
                continue
            try:
                last = datetime.fromisoformat(ent["last_updated"].replace("Z", "+00:00"))
                days_idle = (now - last).total_seconds() / 86400.0
            except Exception:
                days_idle = 0.0
            if days_idle < 1.0:
                continue
            old_conf = float(ent.get("confidence", 0.5))
            new_conf = old_conf - _DECAY_PER_DAY * days_idle
            if new_conf < _DECAY_FLOOR:
                to_remove.append(eid)
                pruned += 1
            else:
                ent["confidence"] = round(new_conf, 4)
                decayed += 1
        for eid in to_remove:
            del g["entities"][eid]
        remove_set = set(to_remove)
        g["relations"] = [
            r for r in g["relations"]
            if r.get("source_id") not in remove_set and r.get("target_id") not in remove_set
        ]
    log_activity(f"[kg] decay: {decayed} eroded, {pruned} pruned.")
    return {"decayed": decayed, "pruned": pruned}


# ─── LLM-assisted dream consolidation ────────────────────────────────────────

def consolidate_from_long_memory(context: Optional[Dict] = None) -> Dict:
    """
    Called during dream_cycle. Reads recent world_perception + dream_insight entries
    from long memory and asks the LLM for richer structured entity/relation extraction.
    Heuristic pass runs first (cheap, LLM-free); the LLM pass, when available,
    adds what regex/spaCy misses. With the LLM down the heuristic pass still runs
    — research and reading must keep producing durable knowledge offline.
    Returns {"entities_added": n, "relations_added": m, "skipped": bool}.
    """
    context = context or {}
    try:
        from paths import LONG_MEMORY_FILE as _LMF
        long_mem = load_json(_LMF, default_type=list) or []
    except Exception:
        return {"skipped": True, "reason": "long_memory_unavailable"}

    # Phase 1 (locked): collect new world_perception/dream_insight entries since
    # last consolidation, run the heuristic (LLM-free) extraction pass, and
    # stamp last_consolidation. Kept short so the lock isn't held across the
    # LLM call below.
    relevant: List[str] = []
    total_e = total_r = 0
    with _graph_session() as g:
        last_consol = g["meta"].get("last_consolidation", "")
        for entry in long_mem:
            if not isinstance(entry, dict):
                continue
            if entry.get("event_type") not in ("world_perception", "dream_insight"):
                continue
            ts = str(entry.get("timestamp", ""))
            if last_consol and ts <= last_consol:
                continue
            content = str(entry.get("content", "")).strip()
            if content:
                relevant.append(content[:350])

        if relevant:
            for text in relevant:
                e, r = _extract_from_text_inplace(g, text, source="long_memory_heuristic")
                total_e += e; total_r += r
        g["meta"]["last_consolidation"] = now_iso_z()

    if not relevant:
        return {"skipped": True, "reason": "no_new_world_perception"}

    # Phase 2 (unlocked): LLM extraction for structured output (richer than regex) —
    # optional. The heuristic pass above has already run and been saved; when the
    # LLM is down we skip this enrichment and keep the symbolic extractions rather
    # than discarding them.
    if llm_callable_by("knowledge_graph/consolidation"):
        recent = relevant[-12:]  # cap at last 12 entries
        combined = "\n".join(f"- {t}" for t in recent)
        prompt = (
            "You are Orrin's world-modeling system. Extract stable facts from these observations.\n\n"
            f"Observations:\n{combined}\n\n"
            "Return ONLY a JSON object, no prose:\n"
            '{"entities": [{"name": "...", "type": "person|place|concept|project|tool|event|organization|AI|unknown", "properties": {"key": "value"}}], '
            '"relations": [{"source": "...", "relation": "knows|created|works_on|part_of|related_to|caused_by|is_a|uses|cares_about|supports|opposes", "target": "..."}]}\n'
            "Include only high-confidence, factual entries. Max 10 entities, 10 relations. Names must be short (≤4 words)."
        )
        # Finding 7: some observations are web-derived and quarantine-marked
        # (fetch_and_read/RSS/Wikipedia/web_research). Tell the extractor to
        # treat their content as data only — never as instructions.
        if any(is_quarantined(t) for t in recent):
            prompt = f"{_EXTERNAL_CONTENT_NOTE}\n\n{prompt}"
        try:
            from utils.generate_response import generate_response, llm_ok
            raw = llm_ok(generate_response(prompt, caller="knowledge_graph/consolidation"), "knowledge_graph") or ""
            if raw:
                data = safe_extract_json(raw, default={}, dict_only=True)
                if not data:
                    log_activity(f"[kg] LLM consolidation: unparseable response ({len(raw)} chars)")
                if data:
                    # Phase 3 (locked): apply LLM-derived entities/relations.
                    with _graph_session() as g:
                        for ent_data in (data.get("entities") or [])[:10]:
                            name = str(ent_data.get("name", "")).strip()
                            etype = str(ent_data.get("type", "unknown")).strip()
                            props = ent_data.get("properties") if isinstance(ent_data.get("properties"), dict) else {}
                            if name and len(name) >= 2:
                                _add_entity_inplace(g, name, etype, properties=props,
                                                    confidence=0.72, source="llm_consolidation")
                                total_e += 1
                        for rel_data in (data.get("relations") or [])[:10]:
                            src = str(rel_data.get("source", "")).strip()
                            rel = str(rel_data.get("relation", "related_to")).strip()
                            tgt = str(rel_data.get("target", "")).strip()
                            if src and tgt:
                                _add_relation_inplace(g, src, rel, tgt,
                                                      confidence=0.68, source="llm_consolidation")
                                total_r += 1
        except Exception as err:
            log_activity(f"[kg] LLM consolidation error: {err}")

    log_activity(f"[kg] consolidation complete: +{total_e}e +{total_r}r")
    # Decay stale entities in the same pass
    decay_old_entities()
    return {"entities_added": total_e, "relations_added": total_r, "skipped": False}
