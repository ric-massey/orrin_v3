# think/speech_log.py
#
# Speech reply store — the exemplar database.
#
# Every reply Orrin emits is logged here with full context (what the user said,
# what the planner decided, which topics were active, affect tone).  When the
# evaluator scores a reply, the quality score is written back.
#
# Three files:
#   SPEECH_LOG_FILE    — rolling list of reply entries, capped at MAX_ENTRIES
#   SPEECH_SCORES_FILE — per-(response_type, tone) running average scores
#   SPEECH_SEEDS_FILE  — permanent exemplars: hand-crafted seeds + promoted
#                        entries that scored >= PROMOTE_MIN_SCORE and were
#                        retrieved >= PROMOTE_MIN_RETRIEVALS times
#
# The seed file is the permanent layer that never rolls off.  It serves two
# purposes:
#   1. Cold start — provides exemplars on day 1 before Orrin has real data.
#   2. Persistence — high-quality replies that would otherwise disappear after
#      500 entries live here indefinitely.
#
# Promotion logic (Bybee 1985, 2006 — frequency entrenchment):
#   A reply that is repeatedly retrieved because it is topically relevant and
#   scores high reflects a stable, reusable construction.  Promoting it to
#   permanent storage mirrors how high-frequency exemplars become entrenched
#   schemas in the mental lexicon.
from __future__ import annotations
from core.runtime_log import get_logger

import uuid
from typing import Any, Dict, List, Optional, Set

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_error
from paths import SPEECH_LOG_FILE, SPEECH_SCORES_FILE, SPEECH_SEEDS_FILE
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

MAX_ENTRIES          = 500    # rolling cap on speech_log.json
PROMOTE_MIN_SCORE    = 0.75   # quality score required for promotion
PROMOTE_MIN_RETRIEVE = 3      # retrieval count required for promotion


# ── Internal helpers ──────────────────────────────────────────────────────────


def _load_log() -> List[Dict]:
    data = load_json(SPEECH_LOG_FILE, default_type=list)
    return data if isinstance(data, list) else []


def _save_log(entries: List[Dict]) -> None:
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    save_json(SPEECH_LOG_FILE, entries)


def _load_seeds() -> List[Dict]:
    data = load_json(SPEECH_SEEDS_FILE, default_type=list)
    return data if isinstance(data, list) else []


def _save_seeds(seeds: List[Dict]) -> None:
    save_json(SPEECH_SEEDS_FILE, seeds)


def _load_scores() -> Dict[str, Any]:
    data = load_json(SPEECH_SCORES_FILE, default_type=dict)
    return data if isinstance(data, dict) else {}


def _save_scores(scores: Dict) -> None:
    save_json(SPEECH_SCORES_FILE, scores)


def _construction_key(response_type: str, tone: str) -> str:
    return f"{response_type}__{tone}"


# ── Write a reply to the log ──────────────────────────────────────────────────

def log_reply(
    user_input:    str,
    reply:         str,
    plan:          Dict[str, Any],
    comprehension: Dict[str, Any],
) -> str:
    """
    Append a reply to the speech log.  Returns the entry id (used by evaluator).
    """
    if not reply or not reply.strip():
        return ""

    entry_id = str(uuid.uuid4())
    entry: Dict[str, Any] = {
        "id":            entry_id,
        "timestamp":     now_iso_z(),
        "user_input":    (user_input or "").strip(),
        "reply":         reply.strip(),
        "response_type": plan.get("response_type", ""),
        "tone":          plan.get("tone", ""),
        "source":        plan.get("source", ""),
        "length":        plan.get("length", ""),
        "intent":        comprehension.get("intent", ""),
        "topics":        comprehension.get("topics", [])[:6],
        "quality_score":     None,
        "user_reply_words":  None,
        "user_reply_time_s": None,
        "evaluated":         False,
        "retrieval_count":   0,
        "is_seed":           False,
    }

    entries = _load_log()
    entries.append(entry)
    _save_log(entries)
    log_activity(
        f"[speech_log] logged id={entry_id[:8]} "
        f"type={entry['response_type']} tone={entry['tone']}"
    )
    return entry_id


# ── Score a reply (called by evaluator) ──────────────────────────────────────

def score_reply(
    entry_id:          str,
    quality_score:     float,
    user_reply_words:  int,
    user_reply_time_s: float,
) -> None:
    """
    Write the quality score back onto the log entry, update the running
    average for this (response_type, tone) construction, and promote the
    entry to seeds if it meets the thresholds.
    """
    entries = _load_log()
    target  = None
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["quality_score"]     = round(quality_score, 4)
            entry["user_reply_words"]  = user_reply_words
            entry["user_reply_time_s"] = round(user_reply_time_s, 1)
            entry["evaluated"]         = True
            target = entry
            break
    else:
        log_error(f"[speech_log] score_reply: id {entry_id[:8]} not found")
        return

    _save_log(entries)
    _update_construction_score(target, quality_score)
    _maybe_promote(target)
    log_activity(
        f"[speech_log] scored id={entry_id[:8]} "
        f"score={quality_score:.3f} words={user_reply_words}"
    )


def _update_construction_score(entry: Dict, score: float) -> None:
    """Update the running average for this (response_type, tone) bucket."""
    rt   = entry.get("response_type", "")
    tone = entry.get("tone", "")
    if not rt or not tone:
        return

    scores = _load_scores()
    key    = _construction_key(rt, tone)
    bucket = scores.get(key) or {"sum": 0.0, "count": 0, "avg": 0.5}

    bucket["sum"]   = float(bucket.get("sum",   0.0)) + score
    bucket["count"] = int(bucket.get("count",   0))   + 1
    bucket["avg"]   = round(bucket["sum"] / bucket["count"], 4)

    scores[key] = bucket
    _save_scores(scores)


# ── Promotion ─────────────────────────────────────────────────────────────────

def _maybe_promote(entry: Dict) -> None:
    """
    Promote a log entry to the permanent seed file if it meets thresholds.

    Conditions (both must hold):
      - quality_score >= PROMOTE_MIN_SCORE (entry earned high user engagement)
      - retrieval_count >= PROMOTE_MIN_RETRIEVE (entry was found relevant enough
        to be returned by get_exemplars() multiple times)

    This mirrors Bybee's (1985) frequency entrenchment: constructions that are
    both high-quality AND frequently activated become stored as stable schemas.
    """
    if entry.get("is_seed"):
        return
    score = float(entry.get("quality_score") or 0)
    count = int(entry.get("retrieval_count") or 0)
    if score < PROMOTE_MIN_SCORE or count < PROMOTE_MIN_RETRIEVE:
        return

    seeds = _load_seeds()
    # Avoid duplicate promotion (check by reply text)
    reply_text = (entry.get("reply") or "").strip()
    if any((s.get("reply") or "").strip() == reply_text for s in seeds):
        return

    seed = {
        "id":              "promoted-" + entry["id"][:12],
        "reply":           reply_text,
        "response_type":   entry.get("response_type", ""),
        "tone":            entry.get("tone", ""),
        "topics":          entry.get("topics", []),
        "quality_score":   score,
        "is_seed":         True,
        "retrieval_count": 0,
        "evaluated":       True,
        "user_input":      entry.get("user_input", ""),
        "promoted_at":     now_iso_z(),
    }
    seeds.append(seed)
    _save_seeds(seeds)
    log_activity(
        f"[speech_log] promoted id={entry['id'][:8]} → seed "
        f"score={score:.3f} retrievals={count}"
    )


# ── Read construction scores (used by speech_builder) ────────────────────────

def get_construction_score(response_type: str, tone: str) -> float:
    """
    Return the running average quality score for a (response_type, tone) bucket.
    Returns 0.5 (neutral) if fewer than 2 data points exist.
    """
    try:
        scores = _load_scores()
        key    = _construction_key(response_type, tone)
        bucket = scores.get(key)
        if bucket and isinstance(bucket, dict) and bucket.get("count", 0) >= 2:
            return float(bucket.get("avg", 0.5))
    except Exception as _e:
        record_failure("speech_log.get_construction_score", _e)
    return 0.5


# ── Exemplar retrieval ────────────────────────────────────────────────────────

def get_exemplars(
    topics:        List[str],
    response_type: Optional[str] = None,
    tone:          Optional[str]  = None,
    min_score:     float          = 0.55,
    n:             int            = 6,
) -> List[Dict]:
    """
    Return past high-quality replies relevant to the current topics.

    Draws from both the rolling speech log AND the permanent seed file.
    Seeds provide cold-start coverage and preserve promoted exemplars
    that would otherwise roll off the 500-entry cap.

    Filtering:
      - minimum quality score (default 0.55)
      - optional response_type / tone exact match
      - topic overlap: at least one topic word appears in past reply,
        user_input, or stored topic list

    After filtering, retrieval_count is incremented for every entry
    returned from the log (seeds are counted separately but also
    incremented for the promotion system to track re-use).

    Returns entries sorted by quality_score descending.
    """
    topic_set: Set[str] = {t.lower() for t in (topics or []) if len(t) > 3}

    # ── Load both sources ────────────────────────────────────────────────────
    log_entries  = _load_log()
    seed_entries = _load_seeds()

    # Tag source so we can save them back separately
    for e in log_entries:
        e.setdefault("_src", "log")
    for e in seed_entries:
        e.setdefault("_src", "seed")

    all_entries = list(reversed(log_entries)) + seed_entries   # recency-first for log

    # ── Filter ───────────────────────────────────────────────────────────────
    results: List[Dict] = []
    seen_replies: Set[str] = set()

    for entry in all_entries:
        if not entry.get("evaluated"):
            continue
        score = float(entry.get("quality_score") or 0.0)
        if score < min_score:
            continue
        if response_type and entry.get("response_type") != response_type:
            continue
        if tone and entry.get("tone") != tone:
            continue

        # Topic overlap (skip if no topics specified — collect everything)
        if topic_set:
            entry_text = " ".join([
                entry.get("reply", ""),
                entry.get("user_input", ""),
                " ".join(entry.get("topics", [])),
            ]).lower()
            if not any(t in entry_text for t in topic_set):
                continue

        # Deduplicate by reply text across log and seeds
        reply_key = (entry.get("reply") or "").strip()[:80]
        if reply_key in seen_replies:
            continue
        seen_replies.add(reply_key)

        results.append(entry)
        if len(results) >= n:
            break

    results.sort(key=lambda e: e.get("quality_score", 0), reverse=True)

    # ── Increment retrieval counts ────────────────────────────────────────────
    if results:
        returned_ids = {e.get("id") for e in results}

        log_dirty  = False
        seed_dirty = False

        for e in log_entries:
            if e.get("id") in returned_ids:
                e["retrieval_count"] = int(e.get("retrieval_count") or 0) + 1
                log_dirty = True

        for e in seed_entries:
            if e.get("id") in returned_ids:
                e["retrieval_count"] = int(e.get("retrieval_count") or 0) + 1
                seed_dirty = True

        # Strip the internal routing tag before saving back to disk
        for e in log_entries:
            e.pop("_src", None)
        for e in seed_entries:
            e.pop("_src", None)

        if log_dirty:
            _save_log(log_entries)
        if seed_dirty:
            _save_seeds(seed_entries)

    # Strip tag from returned entries too (in case no save ran)
    for e in results:
        e.pop("_src", None)

    return results


# ── Pending evaluation ────────────────────────────────────────────────────────

def get_pending_entry() -> Optional[Dict]:
    """Return the most recent reply that hasn't been scored yet."""
    entries = _load_log()
    for entry in reversed(entries):
        if not entry.get("evaluated"):
            return entry
    return None
