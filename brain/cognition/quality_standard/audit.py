# brain/cognition/quality_standard/audit.py
#
# P6 — the read-only audit surface. Backs the Learning-page / Settings review queue:
# what is pending human ratification, and the full applied-history with provenance so
# drift is inspectable (design §4.3 #3: provenance + reversibility). Read-only — it
# never applies anything (that is ratify.py, behind a human action).
from __future__ import annotations

from typing import Any, Dict, List

from brain.cognition.quality_standard import ratify, revisions


def _row_view(r: Dict[str, Any]) -> Dict[str, Any]:
    ev = r.get("evidence") or {}
    ref = r.get("artifact_ref") or {}
    return {
        "id": r.get("id"),
        "kind": r.get("kind"),
        "direction": r.get("direction"),
        "status": r.get("status"),
        "needs_rule_review": bool(r.get("needs_rule_review")),
        "failing_reason": r.get("failing_reason"),
        "reason": r.get("reason"),
        "note": r.get("note"),
        "artifact_path": ref.get("artifact_path") or r.get("exemplar_path"),
        "goal_id": ref.get("goal_id"),
        "evidence": {
            "goals": ev.get("goals") or [],
            "significance": ev.get("significance"),
            "reuse_count": ev.get("reuse_count"),
            "memory_refs": ev.get("memory_refs") or [],
            # ordering-only — surfaced as a sort hint, labelled as not-a-vote.
            "signal_prior": ev.get("signal_prior"),
        },
        "ts": r.get("ts"),
        "updated_ts": r.get("updated_ts"),
        "reviewer": r.get("reviewer"),
        "reversible": bool(r.get("removed_text")),
    }


def summary() -> Dict[str, Any]:
    """Everything the UI needs: the human-ratify queue (ordered by signal_prior, a
    prioritizer not a vote) and the applied-change audit trail with provenance."""
    rows = revisions.load()
    queue = [_row_view(r) for r in ratify.review_queue()]
    applied = [_row_view(r) for r in rows if r.get("status") == "applied"]
    rejected = [_row_view(r) for r in rows if r.get("status") == "rejected"]
    return {
        "queue": queue,
        "applied": applied,
        "rejected": rejected,
        "counts": {
            "pending_review": len(queue),
            "applied": len(applied),
            "rejected": len(rejected),
            "total": len(rows),
        },
        "note": "signal_prior orders the queue only — it is never a vote on the outcome.",
    }


def queue() -> List[Dict[str, Any]]:
    return [_row_view(r) for r in ratify.review_queue()]
