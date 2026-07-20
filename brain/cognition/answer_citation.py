# brain/cognition/answer_citation.py
#
# G2 (Run 11 §3, QUALITY_GROUNDING rung 0 — strong form). Epistemic close-out
# stamps whether an artifact ANSWERED a goal's question; Run 10 showed the
# stamps firing (10×, all unanswered) but nothing downstream ever consumed an
# answer — "answered" changed no later decision, so the grounded-consequence
# loop stayed open. This module closes it mechanically:
#
#   note_answered()   — close-out files every answered question in a small
#                       rolling index (question, answer excerpt, goal id).
#   annotate_reason() — at selection time, if the deciding context (bound-goal
#                       title / focus) shares subject terms with an answered
#                       question, the DECISION REASON PAYLOAD cites it and the
#                       index row is stamped consumed — "the answer changed a
#                       later decision" becomes a readable, countable event
#                       (the §10 gate reads `cited` rows).
#
# F-LN4a/b (memo filing + authoritative close-out stamps) are this module's
# floor; scoring stays symbolic — term overlap, no LLM.
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

_FILE = DATA_DIR / "answered_questions.json"
_MAX_ROWS = 100
_MIN_TERM_OVERLAP = 2   # question-subject terms that must appear in the deciding context


def _rows() -> List[Dict[str, Any]]:
    d = load_json(_FILE, default_type=list) or []
    return [r for r in d if isinstance(r, dict)] if isinstance(d, list) else []


def note_answered(question: str, answer: str, goal_id: Optional[str]) -> None:
    """File an answered question so later selections can be traced to it."""
    q = str(question or "").strip()
    if not q:
        return
    try:
        rows = _rows()
        for r in rows:
            if r.get("question") == q:
                r["answer"] = str(answer or "")[:280]
                r["ts"] = round(time.time(), 1)
                break
        else:
            rows.append({
                "question": q[:280],
                "answer": str(answer or "")[:280],
                "goal_id": goal_id,
                "ts": round(time.time(), 1),
                "cited": 0,
            })
        save_json(_FILE, rows[-_MAX_ROWS:])
    except Exception as exc:
        record_failure("answer_citation.note_answered", exc)


def _deciding_text(context: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("focus_goal", "bound_goal"):
        g = context.get(key)
        if isinstance(g, dict):
            parts.append(str(g.get("title") or g.get("name") or ""))
        elif g:
            parts.append(str(g))
    ws = context.get("workspace_snapshot") or context.get("global_workspace") or ""
    if isinstance(ws, dict):
        parts.append(str(ws.get("content", ""))[:400])
    else:
        parts.append(str(ws)[:400])
    return " ".join(p for p in parts if p).lower()


def annotate_reason(reason: Dict[str, Any], context: Dict[str, Any], chosen: str) -> None:
    """If this decision's driving context carries an answered question's
    subject, cite it in the reason payload and stamp the index row consumed."""
    if not chosen or not isinstance(reason, dict):
        return
    try:
        deciding = _deciding_text(context)
        if len(deciding) < 8:
            return
        from brain.cognition.epistemic_closeout import _subject_terms
        rows = _rows()
        hit = None
        for r in rows:
            terms = _subject_terms(str(r.get("question", "")))
            if not terms:
                continue
            overlap = sum(1 for t in terms if t.lower() in deciding)
            if overlap >= min(_MIN_TERM_OVERLAP, len(terms)):
                hit = (r, overlap)
                break
        if hit is None:
            return
        row, overlap = hit
        row["cited"] = int(row.get("cited", 0) or 0) + 1
        row["last_cited_ts"] = round(time.time(), 1)
        row["last_cited_fn"] = chosen
        save_json(_FILE, rows[-_MAX_ROWS:])
        reason["cites_answer"] = {
            "question": str(row.get("question", ""))[:120],
            "goal_id": row.get("goal_id"),
            "term_overlap": overlap,
        }
        log_activity(
            f"[answer_citation] decision '{chosen}' cites answered question "
            f"\"{str(row.get('question', ''))[:80]}\" — the answer changed a later decision"
        )
    except Exception as exc:
        record_failure("answer_citation.annotate_reason", exc)


def cited_rows() -> List[Dict[str, Any]]:
    """Rows whose answers have been consumed by at least one decision (§10 gate)."""
    return [r for r in _rows() if int(r.get("cited", 0) or 0) > 0]
