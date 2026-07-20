# brain/cognition/opinions_formation.py
# Opinion formation (Phase 4.5C, from opinions.py): notice topics recurring in
# working memory (_extract_topics / _conceptualize / _root_ids_for_topic) and,
# off cooldown, form a new provenance-grounded opinion (maybe_form_opinion / _form
# + _candidate_topics / _new_opinion_entry / _evidence_weighted_opinion), plus the
# per-cycle evidence update (_update_evidence). Builds on the store leaf.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from brain.utils.log import log_private
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import WORKING_MEMORY_FILE, SELF_MODEL_FILE
from brain.utils.llm_gate import llm_callable_by
from brain.cognition.opinions_store import (
    _EVIDENCE_WEIGHTS, _INIT_STAKE, _load,
    _save, _topic_id, _ensure_ledger_fields,
    _eviction_key, _STOPWORDS, _tok, _overlap,
    _polarity_mismatch, add_evidence, _compute_links,
)

_log = get_logger(__name__)


_FORMATION_COOLDOWN_S = 1800.0   # 30 minutes between opinion formation cycles
_TOPIC_MIN_COUNT      = 2        # topic must appear in at least N recent WM entries
_MAX_OPINIONS         = 100      # cap; weakest (stake+confidence+salience) dropped when full
_MIN_CONFIDENCE       = 0.30

_last_formation_ts: float = 0.0


# ── Topic extraction ───────────────────────────────────────────────────────────

_SKIP_PREFIXES = ("🧠", "✅", "⚠️", "⏳", "[deadline]", "[memory]", "[environment]",
                  "[scheduled]", "[relationship]", "[opinion",
                  # Internal bookkeeping must not seed opinion topics — half the
                  # stored opinions had topics like "metacog/pattern" mined from
                  # these entries, then got voiced with [Chunk: text embedded.
                  "[Chunk:", "[metacog", "[Incubation", "[sym_", "[done]", "📝")


def _extract_topics(wm_entries: List[Dict]) -> Dict[str, int]:
    """Return word/bigram frequency from meaningful WM entries."""
    from brain.cognition.thought import is_minable_as_own_gap   # T1 provenance
    counts: Dict[str, int] = {}
    for entry in wm_entries:
        if not isinstance(entry, dict):
            continue
        if not is_minable_as_own_gap(entry):
            continue   # opinions form on HIS material, not telemetry/conversation
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
    except Exception as exc:  # vocab query failed — record, no grounded word
        record_failure("opinions_formation._grounded_word", exc)
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
_OPINION_POS_EMO = {"reward_positive", "expected_gain", "confidence", "motivation",
                    "excitement", "novelty_signal", "exploration_drive"}
_OPINION_NEG_EMO = {"reward_negative", "threat_level", "conflict_signal", "impasse_signal",
                    "social_penalty", "rejection_signal", "low_affect_signal", "risk_estimate"}
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
    except (ValueError, TypeError, AttributeError, IndexError):  # intentional: unparseable LLM JSON
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


