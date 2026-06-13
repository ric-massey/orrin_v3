from core.runtime_log import get_logger
import json
import re
from collections import Counter
from pathlib import Path

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_error
from cog_memory.working_memory import update_working_memory
from paths import (
    SYMBOLIC_WORLD_MODEL, LONG_MEMORY_FILE, CONCEPTS_FILE,
    WORLD_MODEL_BACKUP, DATA_DIR,
)
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

MAX_ENTITIES  = 80
MAX_RELATIONS = 120
MAX_FACTS     = 60
MAX_BELIEFS   = 40

_VOCAB_PATH = DATA_DIR / "vocabulary.json"

# Known person names that always become entities when seen in text
_KNOWN_PERSONS = {"ric", "orrin"}

# Relation patterns: (regex, predicate_label)
_RELATION_PATTERNS = [
    (r'\b(\w+)\s+is\s+(?:a\s+)?(\w+)\b',             "is_a"),
    (r'\b(\w+)\s+has\s+(\w+)\b',                      "has"),
    (r'\b(\w+)\s+(?:leads?|led)\s+to\s+(\w+)\b',      "leads_to"),
    (r'\b(\w+)\s+causes?\s+(\w+)\b',                  "causes"),
    (r'\b(\w+)\s+depends?\s+on\s+(\w+)\b',            "depends_on"),
    (r'\b(\w+)\s+(?:affects?|affects?)\s+(\w+)\b',    "affects"),
    (r'\b(\w+)\s+(?:improves?|improved)\s+(\w+)\b',   "improves"),
    (r'\b(\w+)\s+(?:conflicts?|conflicting)\s+with\s+(\w+)\b', "conflicts_with"),
]

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at",
    "is", "was", "are", "i", "it", "this", "that", "for", "with", "my",
    "his", "her", "its", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may",
    "can", "not", "no", "so", "if", "as", "by", "from", "up", "out",
    "then", "than", "more", "also", "what", "which", "who", "how",
    "when", "where", "there", "they", "them", "their", "we", "our",
    "you", "your", "any", "all", "some", "one", "two", "new", "just",
    "now", "time", "way", "get", "use", "see", "know", "think", "feel",
    "want", "need", "like", "make", "take", "into", "over", "after",
    "before", "about", "through", "each", "other", "me", "him"
}


def _load_vocab() -> dict:
    try:
        return json.loads(_VOCAB_PATH.read_text(encoding="utf-8")).get("world_model_extraction", {})
    except Exception:
        return {}


def _load_symbolic_model() -> dict:
    m = load_json(SYMBOLIC_WORLD_MODEL, default_type=dict)
    if not isinstance(m, dict):
        m = {}
    m.setdefault("entities", {})
    m.setdefault("relations", [])
    m.setdefault("facts", [])
    m.setdefault("beliefs", [])
    m.setdefault("concepts", [])
    m.setdefault("forces", [])
    m.setdefault("events", [])
    m.setdefault("causal_patterns", [])
    m.setdefault("last_updated", None)
    return m



def _upsert_entity(entities: dict, name: str, etype: str, properties: dict = None) -> None:
    key = name.lower().strip()
    if not key or key in _STOP_WORDS or len(key) < 3:
        return
    if key not in entities:
        entities[key] = {
            "name": name,
            "type": etype,
            "properties": properties or {},
            "first_seen": now_iso_z(),
            "last_seen": now_iso_z(),
            "mention_count": 1,
            "confidence": 0.5,
        }
    else:
        entities[key]["last_seen"] = now_iso_z()
        entities[key]["mention_count"] = entities[key].get("mention_count", 0) + 1
        entities[key]["confidence"] = min(1.0, entities[key].get("confidence", 0.5) + 0.05)
        if properties:
            entities[key].setdefault("properties", {}).update(properties)


def _upsert_relation(relations: list, subj: str, pred: str, obj: str, confidence: float = 0.5) -> None:
    subj, obj = subj.lower().strip(), obj.lower().strip()
    if not subj or not obj or subj in _STOP_WORDS or obj in _STOP_WORDS:
        return
    if len(subj) < 3 or len(obj) < 3:
        return
    for r in relations:
        if r.get("subject") == subj and r.get("predicate") == pred and r.get("object") == obj:
            r["confidence"] = min(1.0, r.get("confidence", 0.5) + 0.1)
            r["last_seen"] = now_iso_z()
            return
    relations.append({
        "subject": subj, "predicate": pred, "object": obj,
        "confidence": confidence, "first_seen": now_iso_z(), "last_seen": now_iso_z(),
    })


def _upsert_fact(facts: list, content: str, source: str, confidence: float = 0.6) -> None:
    content = content.strip()
    if not content or len(content) < 10:
        return
    for f in facts:
        if f.get("content") == content:
            f["confidence"] = min(1.0, f.get("confidence", 0.5) + 0.05)
            f["last_seen"] = now_iso_z()
            return
    facts.append({
        "content": content, "source": source,
        "confidence": confidence, "first_seen": now_iso_z(), "last_seen": now_iso_z(),
    })


def _extract_from_text(text: str, entities: dict, relations: list) -> None:
    """Pull entities and relations from a single text string symbolically."""
    text_lower = text.lower()

    # Person detection
    for person in _KNOWN_PERSONS:
        if person in text_lower:
            _upsert_entity(entities, person, "person")

    # Capitalized proper nouns (2+ word tokens that start uppercase, not sentence-start)
    tokens = re.findall(r'\b([A-Z][a-z]{2,})\b', text)
    for tok in tokens:
        if tok.lower() not in _STOP_WORDS:
            _upsert_entity(entities, tok.lower(), "concept")

    # Module/system names (snake_case words that look like code identifiers)
    code_ids = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*){1,})\b', text)
    for cid in code_ids:
        if len(cid) > 6 and cid not in _STOP_WORDS:
            _upsert_entity(entities, cid, "system")

    # Relation extraction via patterns
    for pattern, predicate in _RELATION_PATTERNS:
        for m in re.finditer(pattern, text_lower):
            subj, obj = m.group(1), m.group(2)
            if subj not in _STOP_WORDS and obj not in _STOP_WORDS:
                _upsert_relation(relations, subj, predicate, obj)


def _extract_causal_patterns_from_stats(causal_patterns: list) -> None:
    """Pull high/low reward functions from decision_stats as causal patterns."""
    try:
        from paths import DECISION_STATS_FILE
        stats = load_json(DECISION_STATS_FILE, default_type=dict) or {}
        for fn, entry in stats.items():
            if not isinstance(entry, dict):
                continue
            avg = float(entry.get("avg_reward", 0.0))
            count = int(entry.get("count", 0))
            if count < 5:
                continue
            label = "high_value" if avg >= 0.4 else ("low_value" if avg < 0.15 else None)
            if label:
                existing = next((p for p in causal_patterns if p.get("function") == fn), None)
                if existing:
                    existing["avg_reward"] = avg
                    existing["count"] = count
                    existing["label"] = label
                else:
                    causal_patterns.append({
                        "function": fn, "avg_reward": avg,
                        "count": count, "label": label,
                    })
    except Exception as _e:
        record_failure("world_model._extract_causal_patterns_from_stats", _e)


def _extract_self_as_entity(entities: dict) -> None:
    """Orrin should know himself as an entity with properties from self_model."""
    try:
        from paths import SELF_MODEL_FILE
        self_m = load_json(SELF_MODEL_FILE, default_type=dict) or {}
        props = {}
        if self_m.get("identity"):
            props["identity"] = str(self_m["identity"])[:100]
        if self_m.get("core_directive"):
            d = self_m["core_directive"]
            props["directive"] = str(d.get("statement", d) if isinstance(d, dict) else d)[:100]
        _upsert_entity(entities, "orrin", "self", props)
    except Exception as _e:
        record_failure("world_model._extract_self_as_entity", _e)


def _prune(model: dict) -> None:
    """Drop lowest-confidence entries when limits are hit."""
    if len(model["entities"]) > MAX_ENTITIES:
        sorted_keys = sorted(
            model["entities"].keys(),
            key=lambda k: model["entities"][k].get("confidence", 0),
        )
        for k in sorted_keys[:len(model["entities"]) - MAX_ENTITIES]:
            del model["entities"][k]

    if len(model["relations"]) > MAX_RELATIONS:
        model["relations"].sort(key=lambda r: r.get("confidence", 0), reverse=True)
        model["relations"] = model["relations"][:MAX_RELATIONS]

    if len(model["facts"]) > MAX_FACTS:
        model["facts"].sort(key=lambda f: f.get("confidence", 0), reverse=True)
        model["facts"] = model["facts"][:MAX_FACTS]

    if len(model["beliefs"]) > MAX_BELIEFS:
        model["beliefs"].sort(key=lambda b: b.get("confidence", 0), reverse=True)
        model["beliefs"] = model["beliefs"][:MAX_BELIEFS]


def update_world_model() -> None:
    """Build and persist Orrin's symbolic world model from memory and runtime data."""
    model = _load_symbolic_model()

    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)[-30:]
    if not isinstance(long_memory, list):
        long_memory = []

    vocab = _load_vocab()
    concept_keywords = set(vocab.get("concept_patterns", []))
    force_keywords   = set(vocab.get("force_patterns", []))

    seen_events: set = set(model.get("events", []))
    word_counts: Counter = Counter()

    for entry in long_memory:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("content") or "").strip()
        if not text:
            continue

        # Entity + relation extraction from each memory
        _extract_from_text(text, model["entities"], model["relations"])

        # Event type tracking
        etype = entry.get("event_type", "")
        if etype and etype not in seen_events:
            seen_events.add(etype)
            model["events"].append(etype)

        # Concept and force keyword matching
        text_lower = text.lower()
        for kw in concept_keywords:
            if kw in text_lower:
                word_counts[kw] += 1
        for kw in force_keywords:
            if kw in text_lower:
                word_counts[kw] += 1

        # Extract facts from high-importance entries
        imp = int(entry.get("importance") or 0)
        if imp >= 4 and len(text) >= 20:
            _upsert_fact(model["facts"], text[:200], entry.get("event_type", "memory"), 0.7)

    # Merge concepts and forces (keyword frequency)
    new_concepts = [w for w, c in word_counts.most_common(20) if w in concept_keywords]
    new_forces   = [w for w, c in word_counts.most_common(20) if w in force_keywords]
    model["concepts"] = list(dict.fromkeys(model["concepts"] + new_concepts))[:40]
    model["forces"]   = list(dict.fromkeys(model["forces"] + new_forces))[:25]
    model["events"]   = list(dict.fromkeys(model["events"]))[-50:]

    # Self-entity
    _extract_self_as_entity(model["entities"])

    # Causal patterns from bandit stats
    _extract_causal_patterns_from_stats(model["causal_patterns"])

    # Beliefs: derive from high-confidence facts
    model["beliefs"] = [
        {"content": f["content"], "confidence": f["confidence"], "source": f["source"]}
        for f in model["facts"] if f.get("confidence", 0) >= 0.65
    ][:MAX_BELIEFS]

    # Prune to limits
    _prune(model)

    model["last_updated"] = now_iso_z()

    try:
        save_json(WORLD_MODEL_BACKUP, model)
        save_json(SYMBOLIC_WORLD_MODEL, model)
    except Exception as e:
        log_error(f"Symbolic world model save failed: {e}")
        return

    n_entities  = len(model["entities"])
    n_relations = len(model["relations"])
    n_facts     = len(model["facts"])
    n_causal    = len(model["causal_patterns"])
    update_working_memory(f"Symbolic world model updated: {n_entities} entities, {n_relations} relations, {n_facts} facts, {n_causal} causal patterns.")
    log_activity(f"[world_model] {n_entities} entities, {n_relations} relations, {n_facts} facts, {n_causal} causal patterns.")


def generate_concepts_from_memories() -> None:
    """Extract and persist emergent concepts from recent memory symbolically."""
    long_memory = load_json(LONG_MEMORY_FILE, default_type=list)
    if not isinstance(long_memory, list):
        long_memory = []

    concepts = load_json(CONCEPTS_FILE, default_type=list)
    if not isinstance(concepts, list):
        concepts = []

    vocab = _load_vocab()
    concept_keywords = set(vocab.get("concept_patterns", []))
    word_counts: Counter = Counter()

    for m in long_memory[-20:]:
        if isinstance(m, dict) and m.get("content"):
            words = re.findall(r'\b[a-z]{4,}\b', m["content"].lower())
            word_counts.update(w for w in words if w not in _STOP_WORDS)

    # Keep: appears ≥2 times or is a known concept keyword
    emergent = [w for w, c in word_counts.most_common(30) if c >= 2 or w in concept_keywords]
    merged = list(dict.fromkeys([c for c in concepts if isinstance(c, str)] + emergent))

    try:
        save_json(CONCEPTS_FILE, merged[:60])
        log_activity(f"[world_model] Extracted {len(emergent)} concepts from memory.")
    except Exception as e:
        log_error(f"Failed to save concepts: {e}")


def simulate_event(event: str) -> dict:
    """Predict outcomes of a hypothetical event using the symbolic world model."""
    model = _load_symbolic_model()

    try:
        from symbolic.causal_graph import get_causal_effects
        effects = get_causal_effects(event) or []
    except Exception:
        effects = []

    # Check causal patterns for related functions
    related = [
        p for p in model.get("causal_patterns", [])
        if any(w in event.lower() for w in p.get("function", "").split("_"))
    ]

    short_term = effects[0] if effects else (
        f"Based on {len(related)} known patterns: likely {related[0]['label']} outcome."
        if related else f"Uncertain effect of: {event}"
    )
    long_term = effects[1] if len(effects) > 1 else "Long-term effects require more observations."

    prediction = {
        "short_term": short_term,
        "long_term": long_term,
        "belief_change": effects[2:] or [],
        "related_causal_patterns": [r["function"] for r in related[:3]],
    }

    update_working_memory(f"Simulated event: {event[:60]} → {short_term[:80]}")
    return prediction


def query_world_model(query: str) -> dict:
    """
    Answer a question about the world model symbolically.
    Direct lookup + inference layer (Johnson-Laird / Description Logic).
    """
    model = _load_symbolic_model()
    q = query.lower()

    matching_entities = {
        k: v for k, v in model["entities"].items()
        if k in q or any(k in str(v.get("properties", {})).lower())
    }
    matching_relations = [
        r for r in model["relations"]
        if r.get("subject", "") in q or r.get("object", "") in q
    ]
    matching_facts = [
        f for f in model["facts"]
        if any(w in f.get("content", "").lower() for w in q.split() if len(w) > 3)
    ]

    # Inference layer: derive relations not explicitly stored
    inferred_explanation = None
    similar_entities: list = []
    entity_schema: dict = {}
    try:
        from symbolic.inference import infer_and_explain, find_similar_entities, get_entity_schema
        inferred_explanation = infer_and_explain(query, model)
        # Return schema for the best-matched entity
        if matching_entities:
            top_entity = next(iter(matching_entities))
            entity_schema  = get_entity_schema(top_entity, model)
            similar_entities = find_similar_entities(top_entity, model, top_k=3)
    except Exception as _e:
        record_failure("world_model.query_world_model", _e)

    return {
        "query":               query,
        "entities":            matching_entities,
        "relations":           matching_relations[:10],
        "facts":               matching_facts[:5],
        "inferred":            inferred_explanation,
        "entity_schema":       entity_schema,
        "similar_entities":    similar_entities,
    }


def run_inference_cycle() -> dict:
    """
    Periodically derive new symbolic relations via forward chaining
    and persist them back to the world model.

    Called from dream cycle or scheduled maintenance — NOT every loop.
    Scientific basis: Johnson-Laird (1983), Description Logic (Baader 2003),
    Gärdenfors Conceptual Spaces (2000).
    """
    model = _load_symbolic_model()
    try:
        from symbolic.inference import run_inference
        new_relations = run_inference(model)
    except Exception as e:
        log_error(f"[inference] run_inference failed: {e}")
        return {"inferred": 0}

    if not new_relations:
        return {"inferred": 0}

    # Merge inferred relations into the model (they carry inferred=True flag)
    for r in new_relations:
        _upsert_relation(
            model["relations"],
            r["subject"], r["predicate"], r["object"],
            confidence=r["confidence"],
        )

    _prune(model)
    model["last_updated"] = now_iso_z()

    try:
        save_json(SYMBOLIC_WORLD_MODEL, model)
    except Exception as e:
        log_error(f"[inference] save failed: {e}")
        return {"inferred": len(new_relations)}

    log_activity(f"[inference] Forward chaining derived {len(new_relations)} new relations.")
    update_working_memory({
        "content": f"Symbolic inference: {len(new_relations)} new relations derived (is_a inheritance + transitivity).",
        "event_type": "inference_cycle",
        "priority": 1,
    })
    return {"inferred": len(new_relations)}
