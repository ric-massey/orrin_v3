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
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

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
    # Truncation/quarantine-wrapper fingerprints must never be minted into graph
    # entities. A sliced ingestion like "The Panic Divis] Wikipedia/The Panic:",
    # "Hacker News]", or "[EXTERNAL/UNTRUSTED source=https" otherwise becomes a
    # permanent node, surfaces as the top symbolic_search hit, and gets the whole
    # downstream result re-quarantined every cycle (run audit 2026-06-15 §emotion;
    # FINDINGS 2026-06-12 §9). NB: we deliberately do NOT use is_corrupt_text here
    # — its ends_mid_word predicate false-positives on legitimate long single-word
    # entities ("Photosynthesis", "cyanobacteria"). Unbalanced brackets and chunk
    # headers are the precise, name-appropriate signatures.
    try:
        from brain.utils.text_sanity import has_unbalanced_brackets
        if has_unbalanced_brackets(name) or "[chunk" in name.lower():
            return False, 0.0, "corrupt_text"
    except Exception:
        pass
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
        from brain.utils.model_assets import spacy_model as _spacy_model
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
        from brain.paths import LONG_MEMORY_FILE as _LMF
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
