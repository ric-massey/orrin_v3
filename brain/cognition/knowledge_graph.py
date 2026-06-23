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
from brain.core.runtime_log import get_logger

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json, safe_extract_json
from brain.utils.log import log_activity, log_private
from brain.utils.timeutils import now_iso_z
from brain.utils.llm_gate import llm_callable_by
from brain.utils.embed_similarity import text_similarity, embeddings_available
from brain.utils.content_quarantine import PROMPT_NOTE as _EXTERNAL_CONTENT_NOTE, is_quarantined
_log = get_logger(__name__)

# The graph core (constants, utils, I/O, low-level in-place ops) was extracted to
# knowledge_graph_core.py (Phase 4.5C); re-imported so the extraction layer + public
# API below and external callers keep their references.
from brain.cognition.knowledge_graph_core import (  # noqa: F401
    _SCHEMA_VERSION, ENTITY_TYPES, RELATION_TYPES, _HOME, _USERNAME, _OS_NAME, _ARCH,
    _HOSTNAME, _PROJECT_PATH, _BOOTSTRAP, _KG_NOISE, _STOPWORDS, _PROPER_WORD, _PROPER_SEQ,
    _IS_A_RE, _CREATED_RE, _WORKS_RE, _USES_RE, _CARES_RE, _PROPER_RE, _TYPE_HINTS,
    _KNOWN_TYPE_WORDS, _LOWERCASE_IS_A_RE, _RECENCY_HALFLIFE_DAYS, _DECAY_PER_DAY,
    _DECAY_FLOOR, _ENTITY_CAP, _RELATION_CAP, _MENTION_LOG_BASE, _MIN_SIMILARITY,
    _MIN_SIMILARITY_EMBED, _MIN_PROMPT_ENTITIES, _entity_id, _relation_id, _tokenize,
    _entity_tags, _jaccard, _recency_weight, _infer_type, _normalize_graph_inplace,
    _load_graph, _graph_session, _SCAFFOLD_LEAD_RE, _SCAFFOLD_DEEPLY_RE, _UNIT_STOPWORDS,
    is_valid_entity_name, normalize_entity_name, _add_entity_inplace, _norm_relation,
    _add_relation_inplace,
)
# The text->graph extraction layer was extracted to knowledge_graph_extract.py
# (Phase 4.5C); re-imported so observe/consolidate below + external callers reach it.
from brain.cognition.knowledge_graph_extract import (  # noqa: F401
    _extract_from_text_inplace, _extract_with_regex, _extract_with_spacy,
    _extract_definitional, _validate_candidate, _is_noise,
)


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
        from brain.paths import LONG_MEMORY_FILE as _LMF
        long_mem = load_json(_LMF, default_type=list) or []
    except (ImportError, OSError, ValueError):  # intentional: long memory unavailable → skip
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
            from brain.utils.generate_response import generate_response, llm_ok
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
