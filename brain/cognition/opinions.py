# cognition/opinions.py
#
# Orrin forms and holds opinions.
#
# An opinion is a concrete view on a specific topic — not a value (abstract
# principle) and not a goal (intention). "I think recursive self-improvement
# is being underestimated." "I find prolonged silence harder than I expected."
#
# Opinions form when Orrin notices a topic repeatedly in working memory
# without already having a view on it. They update from a provenance-typed
# evidence ledger (master plan Phase 3): confidence moves only when something
# with provenance — an experiment verdict, a receipt-confirmed prediction, an
# observation matching the claim — lands in the ledger. Mere mention raises
# salience (the opinion comes to mind) but never confidence (it doesn't make
# it true). The LLM's sense of what sounds convincing is the weakest voice at
# the table and can never flip a view on its own.
#
# Each opinion also carries:
#   root_memory_ids    — the memories that seeded it; lost roots weaken it
#   linked_opinion_ids — neighbors; revising one disturbs the others
#   stake              — grows when the view survives challenge or gets used;
#                        flipping a high-stake view demands proportionally
#                        heavier against-evidence and costs affect
#
# Stored in opinions.json. Retrievable during speech and introspection.

from __future__ import annotations
from brain.core.runtime_log import get_logger

import hashlib
import json
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from brain.utils.log import log_private
from brain.utils.json_utils import load_json, save_json
from brain.cog_memory.long_memory import update_long_memory
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import OPINIONS_FILE, WORKING_MEMORY_FILE, SELF_MODEL_FILE, LONG_MEMORY_FILE
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


_FORMATION_COOLDOWN_S = 1800.0   # 30 minutes between opinion formation cycles
_TOPIC_MIN_COUNT      = 2        # topic must appear in at least N recent WM entries
_MAX_OPINIONS         = 100      # cap; weakest (stake+confidence+salience) dropped when full
_MIN_CONFIDENCE       = 0.30

# ── Evidence ledger (Phase 3.1) ────────────────────────────────────────────────
# Weights are fixed by provenance kind, not by persuasiveness.
_EVIDENCE_WEIGHTS: Dict[str, float] = {
    "experiment_verdict": 1.0,   # from experimentation._consolidate
    "prediction_outcome": 0.6,   # from check_predictions, receipt-confirmed only
    "observation":        0.25,  # WM event matching the opinion's CLAIM, not topic
    "llm_reflection":     0.1,   # can never flip direction on its own
    "mention":            0.0,   # salience only — coming to mind is not being true
}
_LEDGER_MAX = 60                 # evidence entries kept per opinion

_INIT_STAKE         = 0.1
_STAKE_ON_SURVIVAL  = 0.03       # against-evidence that didn't flip the view
_STAKE_ON_USE       = 0.02       # retrieved during speech/planning

_last_formation_ts: float = 0.0


# ── Storage ────────────────────────────────────────────────────────────────────

def _load() -> List[Dict]:
    data = load_json(OPINIONS_FILE, default_type=list) or []
    if not isinstance(data, list):
        return []
    return _migrate_legacy_entries(data)


# Goal-churn boilerplate the old mention-counting extractor mined into topics
# (DATA_FILE_AUDIT 2026-06-11 §6). A topic made only of these (plus stopwords)
# is loop exhaust, not an opinion subject.
_LEGACY_JUNK_WORDS = frozenset({
    "cognitive", "resolve", "pursue", "something", "deeply", "failed",
    "written", "attempts", "objective", "unmet", "understand", "goal",
    "goals", "capturing",
})

_migration_done = False


def _legacy_topic_is_junk(topic: str) -> bool:
    t = str(topic or "").strip().lower()
    if len(t) < 3:
        return True
    # Provenance-tag shrapnel must never survive as a topic (audit §5).
    if "external/untrusted" in t or "source=" in t or "[external" in t:
        return True
    words = re.findall(r"[a-z][a-z0-9]*", t)
    informative = [w for w in words if w not in _STOPWORDS and w not in _LEGACY_JUNK_WORDS]
    # An opinion subject needs at least two informative words — single-word
    # fragments ("symbolic", "project") came from the old word-frequency miner.
    return len(informative) < 2


def _migrate_legacy_entries(data: List[Dict]) -> List[Dict]:
    """One-shot migration of pre-ledger opinions (audit §6): junk topics are
    dropped, legitimate ones are re-graded — mention-counted confidence (capped
    0.95) must not be lazily blessed into the evidence-ledger schema."""
    global _migration_done
    if _migration_done:
        return data
    _migration_done = True
    legacy = [op for op in data if isinstance(op, dict) and "evidence" not in op]
    if not legacy:
        return data
    kept: List[Dict] = []
    dropped = 0
    for op in data:
        if not isinstance(op, dict) or "evidence" in op:
            kept.append(op)
            continue
        if _legacy_topic_is_junk(op.get("topic", "")):
            dropped += 1
            continue
        # Re-grade: without an evidence ledger, confidence above 0.6 is just
        # the old mention-count math — seed alpha/beta from the humbler value.
        op["confidence"] = min(0.6, float(op.get("confidence") or 0.5))
        _ensure_ledger_fields(op)
        kept.append(op)
    if dropped or len(kept) != len(data):
        _save(kept)
        log_private(f"[opinions] legacy migration: dropped {dropped} junk topics, "
                    f"re-graded {len(legacy) - dropped}.")
    return kept


def _save(opinions: List[Dict]) -> None:
    save_json(OPINIONS_FILE, opinions)


def _topic_id(topic: str) -> str:
    return hashlib.md5(topic.lower().strip().encode()).hexdigest()[:10]


def get_opinion(topic: str) -> Optional[Dict]:
    """Return Orrin's current opinion on a topic, or None if none exists."""
    tid = _topic_id(topic)
    for op in _load():
        if op.get("id") == tid:
            return op
    return None


def get_all_opinions() -> List[Dict]:
    return _load()


def _ensure_ledger_fields(op: Dict) -> None:
    """Lazy schema upgrade for entries that predate the evidence ledger."""
    op.setdefault("evidence", [])
    op.setdefault("salience", 0.3)
    op.setdefault("stake", _INIT_STAKE)
    op.setdefault("root_memory_ids", [])
    op.setdefault("linked_opinion_ids", [])
    op.setdefault("needs_review", False)
    old_conf = float(op.get("confidence") or 0.5)
    op.setdefault("alpha", round(old_conf * 4.0, 3))
    op.setdefault("beta", round((1.0 - old_conf) * 4.0, 3))


def _recompute_confidence(op: Dict) -> None:
    a = float(op.get("alpha") or 2.0)
    b = float(op.get("beta") or 2.0)
    op["confidence"] = round(min(0.95, max(0.05, a / (a + b))), 2)


def _eviction_key(op: Dict) -> float:
    """What earns a place when the cap is hit: stakes held, evidence-backed
    confidence, and current salience — not raw confidence alone (which used to
    drop the newest honest entries)."""
    return (
        float(op.get("stake") or 0.0) * 0.4
        + float(op.get("confidence") or 0.0) * 0.4
        + float(op.get("salience") or 0.0) * 0.2
    )


# ── Tokens / polarity ──────────────────────────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "a", "an", "i", "is", "it", "in", "on", "at", "to", "of", "and",
    "or", "but", "not", "we", "you", "this", "that", "was", "are", "be",
    "have", "has", "do", "did", "will", "just", "now", "when", "how", "what",
    "which", "if", "so", "then", "there", "here", "with", "for", "as", "by",
    "from", "they", "he", "she", "orrin", "chose", "last", "active", "s",
    "were", "been", "being", "would", "could", "should", "about", "into",
    "through", "during", "me", "my", "your", "their", "its", "our",
})

_NEGATION_WORDS = frozenset({
    "not", "never", "cannot", "no", "without", "avoid", "don't", "doesn't",
    "isn't", "wasn't", "won't", "failed", "incorrect", "wrong", "false",
    "unlike", "refuted",
})


def _tok(text: str) -> Set[str]:
    return {
        w for w in re.findall(r"[a-z][a-z0-9]{2,}", str(text).lower())
        if w not in _STOPWORDS
    }


def _overlap(a: Set[str], b: Set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _polarity_mismatch(text_a: str, text_b: str) -> bool:
    """One side negates, the other doesn't — same heuristic meta_rules uses."""
    neg_a = bool(_NEGATION_WORDS & set(str(text_a).lower().split()))
    neg_b = bool(_NEGATION_WORDS & set(str(text_b).lower().split()))
    return neg_a != neg_b


# ── The evidence ledger ────────────────────────────────────────────────────────

def add_evidence(
    opinion_id: str,
    kind: str,
    ref_id: str,
    direction: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    opinions: Optional[List[Dict]] = None,
) -> bool:
    """
    Append one provenance-typed evidence entry to an opinion's ledger and move
    alpha/beta by the kind's fixed weight. Direction ∈ {"for", "against"}.
    Deduplicates on (kind, ref_id). Returns True if the ledger changed.

    Against-evidence that fails to flip the view raises its stake — surviving
    a genuine challenge is what makes an opinion worth defending. When the
    against side accumulates enough non-LLM mass, the opinion is dropped with
    full reversal costs (_drop_with_costs).
    """
    own_list = opinions is None
    if own_list:
        opinions = _load()
    op = next((o for o in opinions if o.get("id") == opinion_id), None)
    if op is None:
        return False
    _ensure_ledger_fields(op)

    weight = _EVIDENCE_WEIGHTS.get(kind)
    if weight is None or direction not in ("for", "against"):
        return False
    if any(e.get("kind") == kind and e.get("ref_id") == ref_id
           for e in op["evidence"]):
        return False  # already counted

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "ref_id": str(ref_id),
        "direction": direction,
        "weight": weight,
    }
    ledger = op["evidence"] + [entry]
    if len(ledger) > _LEDGER_MAX:
        # Evict oldest mentions first — weightless entries must not push the
        # provenance record out of the ledger.
        overflow = len(ledger) - _LEDGER_MAX
        kept = []
        for e in ledger:
            if overflow > 0 and e.get("kind") == "mention":
                overflow -= 1
                continue
            kept.append(e)
        ledger = kept[-_LEDGER_MAX:]
    op["evidence"] = ledger
    op["updated_at"] = entry["ts"]

    if kind == "mention":
        # Mention makes an opinion come to mind, not true.
        op["salience"] = round(min(1.0, float(op.get("salience") or 0.3) + 0.05), 3)
    elif weight > 0:
        if direction == "for":
            op["alpha"] = round(min(50.0, float(op["alpha"]) + weight), 3)
        else:
            op["beta"] = round(min(50.0, float(op["beta"]) + weight), 3)
        op["evidence_count"] = int(op.get("evidence_count") or 1) + 1
        _recompute_confidence(op)

        if direction == "against":
            if _should_flip(op):
                _drop_with_costs(op, opinions, trigger_refs=[str(ref_id)], context=context)
                _save(opinions)
                return True
            # Challenged and genuinely held (still net-supported) — the view
            # earned some standing. A merely-not-yet-flipped view doesn't get
            # to ratchet its own flip bar up.
            if float(op["confidence"]) > 0.5:
                op["stake"] = round(min(1.0, float(op["stake"]) + _STAKE_ON_SURVIVAL), 3)
            else:
                op["needs_review"] = True

    if own_list:
        _save(opinions)
    return True


def _against_mass(op: Dict) -> float:
    """Grounded (non-LLM) against-weight accumulated in the ledger."""
    return sum(
        float(e.get("weight") or 0.0)
        for e in op.get("evidence", [])
        if e.get("direction") == "against" and e.get("kind") != "llm_reflection"
    )


def _flip_threshold(stake: float) -> float:
    """Against-mass required to flip. High stakes demand proportionally heavier
    against-evidence (3.4): stake 0.1 → ~1.1, stake 0.5 → ~2.3, stake 1.0 → 3.8."""
    return 0.8 + 3.0 * float(stake)


def _should_flip(op: Dict) -> bool:
    """Flip when the view is no longer net-supported AND the grounded
    against-mass clears the stake-scaled bar. Both legs matter: mass without
    lost support is a contested-but-standing view; lost support without mass
    is drift the LLM could have talked it into."""
    return (
        float(op.get("confidence") or 1.0) <= 0.5
        and _against_mass(op) >= _flip_threshold(float(op.get("stake") or _INIT_STAKE))
    )


def _drop_with_costs(
    op: Dict,
    opinions: List[Dict],
    trigger_refs: List[str],
    *,
    context: Optional[Dict[str, Any]] = None,
    new_view: Optional[str] = None,
) -> None:
    """
    Flip or drop an opinion, paying the stake-scaled costs (3.4): a
    negative-valence affect event and a durable opinion_reversal record whose
    related_memory_ids point at the evidence that did it. With new_view the
    opinion is revised in place; without one it is removed.
    """
    stake = float(op.get("stake") or _INIT_STAKE)
    old_view = str(op.get("view") or "")
    topic = str(op.get("topic") or "")

    against_ids = [
        e.get("ref_id") for e in op.get("evidence", [])
        if e.get("direction") == "against" and e.get("ref_id")
    ]
    related = list(dict.fromkeys(against_ids + trigger_refs))[-10:]

    update_long_memory(
        f"[opinion reversal] I no longer hold my view on '{topic}': \"{old_view}\". "
        f"The evidence outweighed it (stake was {stake:.2f}).",
        emotion="negative_valence",
        event_type="opinion_reversal",
        importance=3,
        priority=3,
        related_memory_ids=related,
        context=context,
    )
    if isinstance(context, dict):
        try:
            from brain.affect.arbiter import submit_affect
            submit_affect(context, "negative_valence", round(0.10 + 0.25 * stake, 3),
                          source="opinion_reversal", ttl_cycles=2)
        except Exception as e:
            record_failure("opinions.reversal_affect", e)

    _mark_neighbors_for_review(op, opinions)

    if new_view:
        op["view"] = new_view
        op["evidence"] = []   # the old ledger argued about the old view
        op["alpha"] = 1.5
        op["beta"] = 1.5
        op["stake"] = round(max(_INIT_STAKE, stake * 0.5), 3)
        op["needs_review"] = False
        _recompute_confidence(op)
    else:
        opinions.remove(op)
    log_private(f"[opinions] reversal on '{topic}' (stake {stake:.2f})")


def mark_opinion_used(opinion_id: str) -> None:
    """Retrieval during speech/planning raises stake — used opinions are load-
    bearing and should cost more to abandon (3.4)."""
    try:
        opinions = _load()
        op = next((o for o in opinions if o.get("id") == opinion_id), None)
        if op is None:
            return
        _ensure_ledger_fields(op)
        op["stake"] = round(min(1.0, float(op["stake"]) + _STAKE_ON_USE), 3)
        op["salience"] = round(min(1.0, float(op["salience"]) + 0.05), 3)
        _save(opinions)
    except Exception as e:
        record_failure("opinions.mark_used", e)


# ── External ingestion (3.1 wiring) ────────────────────────────────────────────

def _matching_opinions(text: str, opinions: List[Dict]) -> List[Dict]:
    toks = _tok(text)
    if not toks:
        return []
    out = []
    for op in opinions:
        topic_toks = _tok(op.get("topic") or "")
        claim_toks = _tok(op.get("view") or "")
        if (topic_toks and topic_toks <= toks) or _overlap(claim_toks, toks) >= 0.3:
            out.append(op)
    return out


def _supports(op: Dict, statement: str, statement_held: bool) -> str:
    """Direction of a true/confirmed statement relative to the opinion's claim:
    same polarity → for, opposed polarity → against (and inverted when the
    statement itself was refuted)."""
    same_polarity = not _polarity_mismatch(op.get("view") or "", statement)
    agrees = same_polarity if statement_held else not same_polarity
    return "for" if agrees else "against"


def ingest_experiment_verdict(hypothesis: str, verdict: str, experiment_id: str,
                              context: Optional[Dict[str, Any]] = None) -> int:
    """Experiment verdicts are the heaviest evidence (weight 1.0). Called from
    experimentation._consolidate; inconclusive runs carry no weight."""
    if verdict not in ("confirmed", "refuted"):
        return 0
    try:
        opinions = _load()
        touched = 0
        for op in _matching_opinions(hypothesis, opinions):
            _ensure_ledger_fields(op)
            direction = _supports(op, hypothesis, verdict == "confirmed")
            if add_evidence(op["id"], "experiment_verdict", f"exp:{experiment_id}",
                            direction, context=context, opinions=opinions):
                touched += 1
        if touched:
            _save(opinions)
        return touched
    except Exception as e:
        record_failure("opinions.ingest_experiment", e)
        return 0


def ingest_prediction_outcome(prediction_text: str, came_true: bool, ref_id: str,
                              context: Optional[Dict[str, Any]] = None) -> int:
    """Receipt-confirmed prediction outcomes (weight 0.6). Callers must only
    pass predictions graded against behavior, not self-report alone."""
    try:
        opinions = _load()
        touched = 0
        for op in _matching_opinions(prediction_text, opinions):
            _ensure_ledger_fields(op)
            direction = _supports(op, prediction_text, came_true)
            if add_evidence(op["id"], "prediction_outcome", f"pred:{ref_id}",
                            direction, context=context, opinions=opinions):
                touched += 1
        if touched:
            _save(opinions)
        return touched
    except Exception as e:
        record_failure("opinions.ingest_prediction", e)
        return 0


# ── Links (3.3) ────────────────────────────────────────────────────────────────

def _concept_words(text: str) -> Set[str]:
    """Concepts this text attaches to, via concept_memory (no invented
    similarity measure). Empty set when the store is sparse."""
    try:
        from brain.cognition.concept_memory import query as concept_query
        return {c.get("word", "") for c in concept_query(text, limit=5) if c.get("word")}
    except Exception:
        return set()


def _compute_links(op: Dict, opinions: List[Dict]) -> List[str]:
    """Opinions sharing a concept or substantial token ground with this one."""
    own_text = f"{op.get('topic') or ''} {op.get('view') or ''}"
    own_concepts = _concept_words(own_text)
    own_toks = _tok(own_text)
    linked = []
    for other in opinions:
        if other.get("id") == op.get("id"):
            continue
        other_text = f"{other.get('topic') or ''} {other.get('view') or ''}"
        if (own_concepts and own_concepts & _concept_words(other_text)) or \
                _overlap(own_toks, _tok(other_text)) >= 0.3:
            linked.append(other["id"])
    return linked[:8]


def _mark_neighbors_for_review(op: Dict, opinions: List[Dict]) -> None:
    """Revising A disturbs its linked neighbors: they get needs_review and the
    disturbance is noted once in WM."""
    _ensure_ledger_fields(op)
    disturbed = []
    for other in opinions:
        if other.get("id") in (op.get("linked_opinion_ids") or []):
            _ensure_ledger_fields(other)
            other["needs_review"] = True
            disturbed.append(str(other.get("topic") or other.get("id")))
    if disturbed:
        try:
            update_working_memory({
                "content": (f"[opinions] revising '{op.get('topic')}' disturbs: "
                            f"{', '.join(disturbed[:4])}"),
                "event_type": "opinion_link_disturbed",
                "importance": 2, "priority": 2,
            })
        except Exception as e:
            record_failure("opinions.link_note", e)


# ── Topic extraction ───────────────────────────────────────────────────────────

_SKIP_PREFIXES = ("🧠", "✅", "⚠️", "⏳", "[deadline]", "[memory]", "[environment]",
                  "[scheduled]", "[relationship]", "[opinion",
                  # Internal bookkeeping must not seed opinion topics — half the
                  # stored opinions had topics like "metacog/pattern" mined from
                  # these entries, then got voiced with [Chunk: text embedded.
                  "[Chunk:", "[metacog", "[Incubation", "[sym_", "[done]", "📝")


def _extract_topics(wm_entries: List[Dict]) -> Dict[str, int]:
    """Return word/bigram frequency from meaningful WM entries."""
    counts: Dict[str, int] = {}
    for entry in wm_entries:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("content") or "").strip()
        if not text or text.startswith(_SKIP_PREFIXES):
            continue
        # Topics come from the quoted content, never from the trust wrapper
        # (audit §5: opinions formed on 'external/untrusted', 'source=https').
        if "[EXTERNAL" in text:
            from brain.utils.content_quarantine import strip_quarantine
            text = strip_quarantine(text)
        words = [w.strip(".,!?;:\"'()[]{}—-").lower() for w in text.split()]
        for i, w in enumerate(words):
            if len(w) > 4 and w not in _STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
                if i + 1 < len(words):
                    nxt = words[i + 1].strip(".,!?;:\"'()[]{}—-")
                    if len(nxt) > 3 and nxt not in _STOPWORDS:
                        bigram = f"{w} {nxt}"
                        counts[bigram] = counts.get(bigram, 0) + 1
    return counts


def _conceptualize(topic: str) -> Optional[str]:
    """Route a candidate topic through concept_memory (3.5): opinions should
    attach to concepts, not substrings. Returns the canonical concept word when
    one matches, None when the store has no purchase on this topic."""
    try:
        from brain.cognition.concept_memory import lookup, query
        for word in topic.split():
            hit = lookup(word)
            if hit:
                return str(hit.get("word") or word)
        hits = query(topic, limit=1)
        if hits:
            return str(hits[0].get("word") or "") or None
    except Exception:
        pass
    return None


def _root_ids_for_topic(topic: str, recent: List[Dict]) -> List[str]:
    """The WM entry ids that seeded this topic (3.2) — the opinion's roots."""
    roots = []
    tl = topic.lower()
    for entry in recent:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        text = str(entry.get("content") or "")
        if text.startswith(_SKIP_PREFIXES):
            continue
        if tl in text.lower():
            roots.append(str(entry["id"]))
    return roots[-5:]


# ── Formation ──────────────────────────────────────────────────────────────────

def maybe_form_opinion(context: Dict[str, Any]) -> Optional[str]:
    """
    Called each cycle from finalize.py. Rate-limited.
    Returns the topic string if an opinion was formed, else None.
    """
    global _last_formation_ts
    if time.time() - _last_formation_ts < _FORMATION_COOLDOWN_S:
        return None
    try:
        return _form(context)
    except Exception as e:
        log_private(f"[opinions] formation error: {e}")
        return None


def _candidate_topics(topic_counts: Dict[str, int], existing_ids: Set[str]) -> List[str]:
    """Filter raw word/bigram candidates through concept_memory (3.5). A topic
    with a concept behind it uses the concept's canonical term; a topic with no
    concept needs to be insistent (a higher mention bar) to survive."""
    out: List[tuple] = []
    seen: Set[str] = set()
    for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
        if count < _TOPIC_MIN_COUNT or len(topic) <= 5:
            continue
        concept = _conceptualize(topic)
        if concept and len(concept) > 3:
            final = concept
        elif count >= _TOPIC_MIN_COUNT + 1:
            final = topic
        else:
            continue
        tid = _topic_id(final)
        if tid in existing_ids or final in seen:
            continue
        seen.add(final)
        out.append((final, count))
    return [t for t, _ in out]


def _new_opinion_entry(
    topic: str,
    view: str,
    confidence: float,
    dominant: str,
    recent: List[Dict],
    existing: List[Dict],
    formation_method: str,
) -> Dict:
    """Build a full-schema opinion: weak Beta prior, roots, links, ledger."""
    init_mass = 4.0
    alpha_v = max(0.5, confidence * init_mass)
    beta_v = max(0.5, (1.0 - confidence) * init_mass)
    now_iso = datetime.now(timezone.utc).isoformat()
    roots = _root_ids_for_topic(topic, recent)
    entry = {
        "id":                  _topic_id(topic),
        "topic":               topic,
        "view":                view,
        "confidence":          round(max(_MIN_CONFIDENCE, alpha_v / (alpha_v + beta_v)), 2),
        "alpha":               round(alpha_v, 3),
        "beta":                round(beta_v, 3),
        "formed_at":           now_iso,
        "updated_at":          now_iso,
        "evidence_count":      1,
        "emotion_when_formed": dominant,
        "formation_method":    formation_method,
        "evidence": [{
            "ts": now_iso, "kind": "observation",
            "ref_id": roots[0] if roots else "formation",
            "direction": "for", "weight": _EVIDENCE_WEIGHTS["observation"],
        }],
        "salience":            0.3,
        "stake":               _INIT_STAKE,
        "root_memory_ids":     roots,
        "linked_opinion_ids":  [],
        "needs_review":        False,
    }
    entry["linked_opinion_ids"] = _compute_links(entry, existing)
    return entry


# Emotion polarity sets + internal markers, shared by the evidence-weighted engine.
_OPINION_POS_EMO = {"positive_valence", "expected_gain", "confidence", "motivation",
                    "excitement", "wonder", "exploration_drive"}
_OPINION_NEG_EMO = {"negative_valence", "threat_level", "conflict_signal", "impasse_signal",
                    "social_penalty", "rejection_signal", "melancholy", "risk_estimate"}
_OPINION_INTERNAL_MARKERS = ("[chunk:", "[metacog", "[incubation", "[sym_",
                             "[done]", "[pattern]", "✅", "🧠", "📝", "⚠️")


def _evidence_weighted_opinion(topic: str, recent: List[Dict]):
    """Form a view from the DISTRIBUTION of evidence about `topic` — the emotional
    charge each recent mention carried, weighted by its importance — rather than
    from one momentary mood and a canned frame. Confidence rises with the mass and
    CONSISTENCY of that evidence (a weak Beta-style read), so a conflicted topic is
    honestly low-confidence. Returns (view, confidence) or (None, 0.0) when the
    evidence is too thin to hold any view.
    """
    pos_mass = neg_mass = 0.0
    n = 0
    best_snip, best_w = "", -1.0
    charged: List[str] = []
    tl = topic.lower()

    for e in reversed(recent):
        if not isinstance(e, dict):
            continue
        text = str(e.get("content", "")).strip()
        low = text.lower()
        if any(m in low for m in _OPINION_INTERNAL_MARKERS):
            continue
        if tl not in low or len(text) < 20:
            continue
        n += 1
        w = min(1.0, float(e.get("importance", 1) or 1) / 5.0) or 0.2
        emo = str(e.get("emotion", "")).strip().lower()
        if emo in _OPINION_POS_EMO:
            pos_mass += w; charged.append(emo)
        elif emo in _OPINION_NEG_EMO:
            neg_mass += w; charged.append(emo)
        if w > best_w:
            best_w, best_snip = w, text[:120]

    if n == 0:
        return None, 0.0

    charged_mass = pos_mass + neg_mass
    if charged_mass > 0:
        consistency = abs(pos_mass - neg_mass) / charged_mass     # 0 conflicted … 1 unanimous
        evidence_factor = charged_mass / (charged_mass + 2.0)     # more charged evidence → firmer
        confidence = round(min(0.92, _MIN_CONFIDENCE + 0.62 * consistency * evidence_factor), 2)
    else:
        confidence = round(_MIN_CONFIDENCE + 0.05, 2)             # mentioned, never charged

    snip_clause = f'most sharply in "{best_snip}"' if best_snip else "though I can't fix it to one moment"
    tcap = topic[0].upper() + topic[1:]

    moments = f"{n} recent moment" + ("s" if n != 1 else "")
    if pos_mass > neg_mass * 1.3 and charged_mass > 0:
        view = f"{tcap} has mostly landed well across {moments} — {snip_clause}. I find myself drawn to it."
    elif neg_mass > pos_mass * 1.3 and charged_mass > 0:
        view = f"{tcap} keeps landing badly — {snip_clause}. I've grown wary of it."
    elif charged_mass > 0:
        view = f"{tcap} pulls me both ways — {snip_clause}. I'm genuinely of two minds about it."
    else:
        view = f"{tcap} keeps surfacing — {snip_clause} — but it hasn't settled into a stance yet."

    return view, confidence


def _form(context: Dict[str, Any]) -> Optional[str]:
    global _last_formation_ts

    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    if not isinstance(wm, list) or len(wm) < 6:
        return None

    recent = wm[-24:]
    topic_counts = _extract_topics(recent)

    existing = _load()
    existing_ids = {op.get("id") for op in existing}

    # Always update the ledger on existing opinions (mentions → salience,
    # claim-matching observations → evidence) so state accumulates continuously.
    _update_evidence(recent, existing)
    existing = _load()
    existing_ids = {op.get("id") for op in existing}

    candidates = _candidate_topics(topic_counts, existing_ids)
    if not candidates:
        return None

    topic = candidates[0]

    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    dominant = "neutral"
    if isinstance(core, dict):
        dominant = max(
            ((k, float(v)) for k, v in core.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], default=("neutral", 0.0)
        )[0]

    if not llm_callable_by("opinions/form"):
        # Evidence-weighted: stance + confidence computed from the distribution of
        # emotionally-charged memories about the topic, not a momentary mood + a
        # canned frame. None when the evidence is too thin to hold a view.
        view, confidence = _evidence_weighted_opinion(topic, recent)
        if not view:
            return None

        entry = _new_opinion_entry(topic, view, confidence, dominant, recent,
                                   existing, "evidence_weighted")
        existing.append(entry)
        if len(existing) > _MAX_OPINIONS:
            existing.sort(key=_eviction_key, reverse=True)
            existing = existing[:_MAX_OPINIONS]
        _save(existing)

        update_long_memory(
            f"[opinion formed] On '{topic}': {view}",
            emotion=dominant,
            importance=2,
        )
        _last_formation_ts = time.time()
        log_private(f"[opinions] evidence-weighted opinion on '{topic}': {view}")
        return topic

    # LLM path
    from brain.utils.generate_response import generate_response, llm_ok

    sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    values = sm.get("core_values") or []
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:5]
    )

    recent_context = "\n".join(
        f"- {str(e.get('content', ''))[:100]}"
        for e in recent
        if isinstance(e, dict) and str(e.get("content", "")).strip()
        and not str(e.get("content", "")).startswith(_SKIP_PREFIXES)
    )

    prompt = (
        f"You are Orrin. Based on what's been on your mind, you're forming an opinion "
        f"about: '{topic}'.\n\n"
        f"What's been on your mind:\n{recent_context}\n\n"
        f"Your core values: {values_text}\n"
        f"Current emotional lean: {dominant}\n\n"
        f"What do you actually think about '{topic}'? Form a genuine, specific view — "
        f"not a hedge, not 'it depends on context'. A real opinion, even if uncertain. "
        f"1-2 sentences. Then rate your confidence 0.0-1.0.\n\n"
        f"Respond as JSON only: {{\"view\": \"...\", \"confidence\": 0.0}}"
    )

    raw = llm_ok(generate_response(prompt, caller="opinions/form"), "opinions")
    if not raw:
        return None

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
        view = str(result.get("view") or "").strip()
        confidence = float(result.get("confidence") or _MIN_CONFIDENCE)
    except Exception:
        return None

    if not view or len(view) < 10:
        return None

    entry = _new_opinion_entry(topic, view, confidence, dominant, recent,
                               existing, "llm")
    existing.append(entry)

    if len(existing) > _MAX_OPINIONS:
        existing.sort(key=_eviction_key, reverse=True)
        existing = existing[:_MAX_OPINIONS]

    _save(existing)
    update_long_memory(
        f"[opinion formed] On '{topic}': {view} (confidence {confidence:.2f})",
        emotion=dominant,
        importance=2,
    )

    _last_formation_ts = time.time()
    log_private(f"[opinions] formed on '{topic}' (conf={confidence:.2f}): {view[:80]}")
    return topic


def _update_evidence(recent_wm: List[Dict], opinions: List[Dict]) -> None:
    """
    Ledger-based WM pass (3.1). Two distinct things can happen per opinion:

    - mention: the topic string appears in recent WM → a weight-0 ledger entry
      that raises SALIENCE only. Repetition no longer manufactures confidence.
    - observation: a WM entry whose content matches the opinion's CLAIM (the
      view, not the topic string) → a weight-0.25 entry, for/against by
      polarity. This is the only WM path that moves alpha/beta.
    """
    if not opinions:
        return
    changed = False
    for op in opinions:
        _ensure_ledger_fields(op)
        topic = str(op.get("topic") or "").lower()
        claim_toks = _tok(op.get("view") or "")
        if not topic:
            continue
        for entry in recent_wm:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            text = str(entry.get("content") or "")
            if not text or text.startswith(_SKIP_PREFIXES):
                continue
            ref = str(entry["id"])
            if topic in text.lower():
                if add_evidence(op["id"], "mention", ref, "for", opinions=opinions):
                    changed = True
            if claim_toks and _overlap(claim_toks, _tok(text)) >= 0.4:
                direction = "against" if _polarity_mismatch(op.get("view") or "", text) else "for"
                if add_evidence(op["id"], "observation", ref, direction, opinions=opinions):
                    changed = True
    if changed:
        _save(opinions)


# ── Deliberate reflection (cognition function) ─────────────────────────────────

def _check_roots(op: Dict) -> bool:
    """3.2: an opinion whose seeding memories are gone after pruning should
    weaken. One-time confidence haircut when no root is retrievable. Returns
    True if the haircut was applied."""
    roots = op.get("root_memory_ids") or []
    if not roots or op.get("roots_lost"):
        return False
    try:
        wm_ids = {
            str(e.get("id")) for e in (load_json(WORKING_MEMORY_FILE, default_type=list) or [])
            if isinstance(e, dict)
        }
        lm_ids = {
            str(e.get("id")) for e in (load_json(LONG_MEMORY_FILE, default_type=list) or [])
            if isinstance(e, dict)
        }
    except Exception:
        return False
    if any(r in wm_ids or r in lm_ids for r in roots):
        return False
    op["roots_lost"] = True
    op["beta"] = round(min(50.0, float(op.get("beta") or 2.0) + 0.75), 3)
    _recompute_confidence(op)
    log_private(f"[opinions] roots lost for '{op.get('topic')}' — confidence haircut")
    return True


def _pick_review_candidate(opinions: List[Dict]) -> Dict:
    """3.3: needs_review neighbors come first; otherwise confidence-weighted
    random among evidenced opinions."""
    flagged = [op for op in opinions if op.get("needs_review")]
    if flagged:
        return flagged[0]
    candidates = [op for op in opinions if int(op.get("evidence_count") or 0) >= 2]
    if not candidates:
        candidates = opinions
    weights = [float(op.get("confidence") or 0.3) for op in candidates]
    total = sum(weights) or 1.0
    r = random.random() * total
    cumulative = 0.0
    for opinion, w in zip(candidates, weights):
        cumulative += w
        if r <= cumulative:
            return opinion
    return candidates[-1]


def reflect_on_opinions(context: Dict[str, Any]) -> str:
    """
    Cognition function: Orrin reviews his held opinions and considers whether
    any should be revised in light of recent experience.

    The LLM narrates; the ledger judges. A revision the LLM proposes lands as
    llm_reflection evidence (weight 0.1) — it can nudge, flag for review, and
    rewrite wording, but flipping a view outright requires the grounded
    against-mass the stake demands (3.4).
    """
    opinions = _load()
    if not opinions:
        return "no opinions formed yet"
    for op in opinions:
        _ensure_ledger_fields(op)

    op = _pick_review_candidate(opinions)

    roots_cut = _check_roots(op)

    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent = wm[-15:] if len(wm) > 15 else wm
    recent_text = "\n".join(
        f"- {str(e.get('content', ''))[:100]}"
        for e in recent
        if isinstance(e, dict) and not str(e.get("content", "")).startswith(_SKIP_PREFIXES)
    )

    if not llm_callable_by("opinions/reflect"):
        # Symbolic: the ledger judges. Run the evidence pass over recent memory
        # (this is the real work — it can shift confidence, flag for review, and
        # accrue for/against mass), then report the held view in qualitative terms
        # so no raw telemetry decimal leaks into memory/corpus.
        _update_evidence(recent, opinions)
        op["needs_review"] = False
        _save(opinions)
        topic = op.get("topic", "unknown")
        view = op.get("view", "")
        conf = float(op.get("confidence") or 0.5)
        held = ("hold loosely" if conf < 0.45 else
                "hold with some conviction" if conf < 0.70 else
                "hold firmly")
        summary = f"On '{topic}', I still {held}: {view[:100]}"
        log_private(f"[opinions] symbolic reflect held '{topic}' (conf={conf:.2f})")
        return summary

    from brain.utils.generate_response import generate_response, llm_ok

    prompt = (
        f"You are Orrin. You hold this opinion:\n"
        f"Topic: {op.get('topic')}\n"
        f"Your view: {op.get('view')}\n"
        f"Confidence: {op.get('confidence')} | Evidence count: {op.get('evidence_count')}\n\n"
        f"Recent experience:\n{recent_text}\n\n"
        f"Does recent experience support, challenge, or complicate this view? "
        f"Has anything shifted your thinking, even slightly?\n"
        f"Respond as JSON only: {{\"revised_view\": \"...\", \"confidence\": 0.0, "
        f"\"changed\": true/false, \"reflection\": \"one sentence on why\"}}\n"
        f"If your view stands unchanged, set changed=false."
    )

    raw = llm_ok(generate_response(prompt, caller="opinions/reflect"), "opinions")
    if not raw:
        return "reflection failed"

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
    except Exception:
        return "could not parse reflection"

    changed     = bool(result.get("changed"))
    reflection  = str(result.get("reflection") or "").strip()
    revised     = str(result.get("revised_view") or op.get("view", "")).strip()
    new_conf    = float(result.get("confidence") or op.get("confidence") or 0.5)
    old_conf    = float(op.get("confidence") or 0.5)

    ref_id = f"reflect:{int(time.time())}"
    op["needs_review"] = False

    if changed and revised and revised != op.get("view"):
        old_view = op.get("view")
        direction = "for" if new_conf >= old_conf - 0.05 else "against"
        add_evidence(op["id"], "llm_reflection", ref_id, direction, opinions=opinions)

        wants_flip = _polarity_mismatch(old_view or "", revised) or new_conf < old_conf - 0.25
        if wants_flip:
            # The LLM alone cannot flip a view: the grounded against-mass must
            # clear the stake-scaled bar first (3.1's weight table, 3.4's knob).
            if _against_mass(op) >= _flip_threshold(float(op.get("stake") or _INIT_STAKE)):
                _drop_with_costs(op, opinions, trigger_refs=[ref_id],
                                 context=context, new_view=revised)
                _save(opinions)
                update_working_memory({
                    "content": f"[opinion reversed] On '{op.get('topic')}': {revised}",
                    "event_type": "opinion_revision",
                    "importance": 3, "priority": 2,
                })
                update_long_memory(
                    f"[opinion reversed] '{op.get('topic')}': was '{old_view}' → now '{revised}'. {reflection}",
                    emotion="reflective",
                    importance=3,
                )
                return f"reversed opinion on '{op.get('topic')}'"
            op["needs_review"] = True
            op["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(opinions)
            log_private(
                f"[opinions] revision on '{op.get('topic')}' deferred — "
                f"against-mass {_against_mass(op):.2f} < "
                f"threshold {_flip_threshold(float(op.get('stake') or _INIT_STAKE)):.2f}"
            )
            return (f"revision of '{op.get('topic')}' deferred: the felt shift "
                    f"isn't yet backed by grounded evidence")

        # Re-wording within the same direction: allowed, neighbors get notified.
        op["view"]       = revised
        op["updated_at"] = datetime.now(timezone.utc).isoformat()
        _recompute_confidence(op)
        _mark_neighbors_for_review(op, opinions)
        _save(opinions)

        update_working_memory({
            "content": f"[opinion revised] On '{op['topic']}': {revised}",
            "event_type": "opinion_revision",
            "importance": 2,
            "priority": 2,
        })
        update_long_memory(
            f"[opinion revised] '{op['topic']}': was '{old_view}' → now '{revised}'. {reflection}",
            emotion="reflective",
            importance=2,
        )
        log_private(f"[opinions] revised '{op['topic']}': {reflection}")
        return f"revised opinion on '{op['topic']}'"
    else:
        # Held: the LLM's agreement is the weakest evidence there is.
        add_evidence(op["id"], "llm_reflection", ref_id, "for", opinions=opinions)
        op["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(opinions)
        suffix = " (roots lost — confidence trimmed)" if roots_cut else ""
        log_private(f"[opinions] held '{op['topic']}': {reflection}")
        return f"opinion on '{op['topic']}' held: {reflection}{suffix}"


# Alias for import compatibility
form_opinion = maybe_form_opinion
