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

import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from brain.utils.log import log_private
from brain.utils.json_utils import load_json
from brain.cog_memory.long_memory import update_long_memory
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import WORKING_MEMORY_FILE, LONG_MEMORY_FILE
from brain.utils.llm_gate import llm_callable_by
_log = get_logger(__name__)

# The storage + evidence-ledger core was extracted to opinions_store.py (Phase
# 4.5C); re-imported so the formation/reflection logic below + external callers
# keep their references.
from brain.cognition.opinions_store import (  # noqa: F401
    _EVIDENCE_WEIGHTS, _LEDGER_MAX, _INIT_STAKE, _STAKE_ON_SURVIVAL, _STAKE_ON_USE, _load,
    _LEGACY_JUNK_WORDS, _migration_done, _legacy_topic_is_junk, _migrate_legacy_entries,
    _save, _topic_id, get_opinion, get_all_opinions, _ensure_ledger_fields,
    _recompute_confidence, _eviction_key, _STOPWORDS, _NEGATION_WORDS, _tok, _overlap,
    _polarity_mismatch, add_evidence, _against_mass, _flip_threshold, _should_flip,
    _drop_with_costs, mark_opinion_used, _matching_opinions, _supports,
    ingest_experiment_verdict, ingest_prediction_outcome, _concept_words, _compute_links,
    _mark_neighbors_for_review,
)
# The opinion-formation + evidence-update layer was extracted to
# opinions_formation.py (Phase 4.5C); re-imported so the reflection logic below
# + external callers (finalize.py's maybe_form_opinion) keep their references.
from brain.cognition.opinions_formation import (  # noqa: F401
    _FORMATION_COOLDOWN_S, _TOPIC_MIN_COUNT, _MAX_OPINIONS, _MIN_CONFIDENCE,
    _SKIP_PREFIXES, _extract_topics, _conceptualize, _root_ids_for_topic,
    maybe_form_opinion, _candidate_topics, _new_opinion_entry,
    _evidence_weighted_opinion, _form, _update_evidence,
)


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
