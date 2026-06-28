# brain/cognition/opinions_store.py
# Storage + evidence-ledger core of the opinions system (Phase 4.5C, from
# opinions.py): load/save with legacy migration + eviction, the topic-id /
# confidence / eviction-key primitives, token/polarity matching, the
# provenance-weighted evidence ledger (add_evidence + flip/drop logic +
# mark_opinion_used), the external-evidence ingestion entry points, and the
# opinion-link computation. The foundational leaf — formation and reflection
# both build on it.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from brain.utils.log import log_private
from brain.utils.json_utils import load_json, save_json
from brain.cog_memory.long_memory import update_long_memory
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import OPINIONS_FILE
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)


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
        emotion="reward_negative",
        event_type="opinion_reversal",
        importance=3,
        priority=3,
        related_memory_ids=related,
        context=context,
    )
    if isinstance(context, dict):
        try:
            from brain.control_signals.arbiter import submit_signal
            submit_signal(context, "reward_negative", round(0.10 + 0.25 * stake, 3),
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
    except ImportError:  # intentional: concept store optional → no attachments
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


