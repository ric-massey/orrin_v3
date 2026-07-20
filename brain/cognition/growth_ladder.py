# brain/cognition/growth_ladder.py
#
# G1 + G3 (Run 11 §3, anchored on RUN9_DEEP_ANALYSIS §7e: "the ladder already
# exists in pieces — they are just not connected"). Six runs proved REGULATORY
# learning (stay healthy); this module is the growth axis (do harder things):
#
#   G1 — the difficulty ladder. A streak of VERIFIED successes (a close-out
#   question actually answered; an exemplar actually promoted) climbs the rung;
#   the rung hardens every new making-goal's definition_of_done — build-on-prior
#   required first, novelty-beyond-prior next — so difficulty rises with
#   demonstrated competence, not volume. Promoted exemplars are stamped with the
#   rung they were earned at, so the bar ratchets FROM demonstrated work.
#   A failed making-attempt resets the streak (the rung itself stays: one bad
#   day is not evidence the competence was fake).
#
#   G3 — frontier generation consumes mastery. `mastery_weight(text)` scores a
#   candidate's adjacency to what is already mastered (answered questions,
#   promoted exemplars), so generators sample the zone next to competence
#   instead of flat.
#
# `ORRIN_LADDER` flag (default ON for Run 11); OFF restores flat generation for
# bisection. Symbolic throughout — term overlap, counters, no LLM.
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, Optional, Set

from brain.paths import DATA_DIR, QUALITY_EXEMPLARS_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

_LADDER_ON = os.environ.get("ORRIN_LADDER", "1") != "0"
_STATE_FILE = DATA_DIR / "growth_ladder.json"
_STREAK_TO_CLIMB = 3     # verified successes at the current rung before the bar rises
_MAX_RUNG = 5
_MASTERY_CACHE_TTL = 300.0

_mastery_cache: Optional[Set[str]] = None
_mastery_cache_ts = 0.0


def _state() -> Dict[str, Any]:
    d = load_json(_STATE_FILE, default_type=dict) or {}
    return d if isinstance(d, dict) else {}


def rung() -> int:
    return int(_state().get("rung", 0) or 0) if _LADDER_ON else 0


def note_verified_success(kind: str, ref: str = "") -> None:
    """A VERIFIED success (answered question / promoted exemplar) advances the
    streak; a full streak climbs the rung and re-arms."""
    if not _LADDER_ON:
        return
    try:
        d = _state()
        d["streak"] = int(d.get("streak", 0) or 0) + 1
        d.setdefault("history", []).append(
            {"kind": kind, "ref": str(ref)[:120], "ts": round(time.time(), 1)})
        d["history"] = d["history"][-50:]
        if d["streak"] >= _STREAK_TO_CLIMB and int(d.get("rung", 0) or 0) < _MAX_RUNG:
            d["rung"] = int(d.get("rung", 0) or 0) + 1
            d["streak"] = 0
            log_activity(f"[growth_ladder] rung climbed to {d['rung']} "
                         f"({_STREAK_TO_CLIMB} verified successes) — the bar rises")
        save_json(_STATE_FILE, d)
    except Exception as exc:
        record_failure("growth_ladder.note_verified_success", exc)


def note_failed_attempt(ref: str = "") -> None:
    """A failed making-attempt resets the streak; the rung stands."""
    if not _LADDER_ON:
        return
    try:
        d = _state()
        if int(d.get("streak", 0) or 0):
            d["streak"] = 0
            save_json(_STATE_FILE, d)
    except Exception as exc:
        record_failure("growth_ladder.note_failed_attempt", exc)


def record_exemplar_difficulty(exemplar_name: str) -> None:
    """Stamp a freshly-promoted exemplar with the rung it was earned at —
    difficulty carried on demonstrated work, the ratchet's memory."""
    if not exemplar_name:
        return
    try:
        d = _state()
        d.setdefault("exemplar_difficulty", {})[str(exemplar_name)] = rung()
        save_json(_STATE_FILE, d)
    except Exception as exc:
        record_failure("growth_ladder.record_exemplar_difficulty", exc)


def harden_goal(goal: Dict[str, Any]) -> None:
    """G1: apply the current rung's requirements to a new MAKING goal, in
    place. Rung 0 = no extra bar (the pre-ladder world)."""
    if not _LADDER_ON or not isinstance(goal, dict):
        return
    try:
        r = rung()
        if r <= 0 or not goal.get("requires_artifact"):
            return
        dod = goal.setdefault("definition_of_done", [])
        if not isinstance(dod, list):
            return
        dod.append({
            "criterion": "Builds on prior work: cites or extends an earlier "
                         "artifact, memo, or answered question instead of restarting",
            "kind": "quality", "met": False, "ladder_rung": r,
        })
        goal.setdefault("spec", {})["build_on_prior"] = True
        if r >= 2:
            dod.append({
                "criterion": "States explicitly what is NEW beyond the prior "
                             "work it builds on",
                "kind": "quality", "met": False, "ladder_rung": r,
            })
        goal["ladder_rung"] = r
    except Exception as exc:
        record_failure("growth_ladder.harden_goal", exc)


# ── G3: mastery, for generators to consume ───────────────────────────────────

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{3,}")
_STOP = frozenset({
    "this", "that", "with", "from", "what", "when", "where", "which", "have",
    "does", "about", "more", "deeply", "understand", "into", "their", "them",
})


def _terms(text: str) -> Set[str]:
    return {w.lower() for w in _TOKEN_RE.findall(text) if w.lower() not in _STOP}


def mastered_terms() -> Set[str]:
    """Subject vocabulary of demonstrated competence: answered questions +
    promoted exemplars. Cached — generators call this in loops."""
    global _mastery_cache, _mastery_cache_ts
    now = time.time()
    if _mastery_cache is not None and (now - _mastery_cache_ts) < _MASTERY_CACHE_TTL:
        return _mastery_cache
    terms: Set[str] = set()
    try:
        from brain.cognition.answer_citation import _rows as _answered_rows
        for r in _answered_rows():
            terms |= _terms(str(r.get("question", "")))
    except Exception as exc:
        record_failure("growth_ladder.mastered_terms.answers", exc)
    try:
        if QUALITY_EXEMPLARS_DIR.is_dir():
            for p in sorted(QUALITY_EXEMPLARS_DIR.glob("*.md"))[:40]:
                try:
                    terms |= _terms(p.read_text(encoding="utf-8")[:2000])
                except OSError:
                    continue
    except Exception as exc:
        record_failure("growth_ladder.mastered_terms.exemplars", exc)
    _mastery_cache, _mastery_cache_ts = terms, now
    return terms


def mastery_weight(text: str) -> float:
    """G3 sampling multiplier: 1.0 for territory with no mastered footholds,
    rising (capped ×1.5) with adjacency to demonstrated competence — the zone
    next to what he can already do, not a flat map."""
    if not _LADDER_ON:
        return 1.0
    mastered = mastered_terms()
    if not mastered:
        return 1.0
    overlap = len(_terms(text) & mastered)
    return 1.0 + min(0.5, 0.15 * overlap)
