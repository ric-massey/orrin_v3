# brain/cognition/quality_standard/revisions.py
#
# P0 — the candidate store + provenance schema for quality-standard evolution.
#
# Mirrors the value_revisions file/provenance pattern (a capped JSON list of
# candidate rows, each carrying its evidence and a status), but NOT its control
# flow: value_revisions self-applies in cognition; this store is only ever applied
# by the background gate (P2, add-only) or the human-ratify path (P4). See the
# implementation plan §1 and the §3 guardrail map.
#
# Row schema (plan §P0):
#   {
#     "id":          unique id
#     "kind":        "promote" | "suspect" | "anti_exemplar"
#     "direction":   "raise" | "lower"          (raise may auto-apply; lower is human-only)
#     "artifact_ref": {"goal_id", "content_hash", "artifact_path"}
#     "evidence":    {"goals", "effect_rows", "significance", "reuse_count",
#                     "memory_refs", "signal_prior"}
#     "status":      "pending" | "applied" | "rejected" | "suspect"
#     "ts":          iso8601
#   }
#
# GUARDRAIL baked into the schema: `signal_prior` (control-signal "this felt
# meaningful / I kept returning to it") is stored ONLY to order the human review
# queue. It is NOT counted toward the evidence threshold (risk register: emotions
# are never an evidence source for a change). Stored null/ordering-only.
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from brain.paths import QUALITY_STANDARD_REVISIONS
from brain.utils.json_utils import load_json, save_json
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

# Cap like VALUE_REVISIONS so the file can't grow without bound.
_MAX_ROWS = 200

VALID_KINDS = frozenset({"promote", "suspect", "anti_exemplar"})
VALID_DIRECTIONS = frozenset({"raise", "lower"})
VALID_STATUSES = frozenset({"pending", "applied", "rejected", "suspect"})


def load() -> List[Dict[str, Any]]:
    """All candidate rows (any status), oldest first."""
    rows = load_json(QUALITY_STANDARD_REVISIONS, default_type=list) or []
    return [r for r in rows if isinstance(r, dict)]


def save(rows: List[Dict[str, Any]]) -> None:
    """Persist the candidate list, capped to the most recent _MAX_ROWS."""
    try:
        save_json(QUALITY_STANDARD_REVISIONS, list(rows)[-_MAX_ROWS:])
    except Exception as exc:
        record_failure("quality_standard.revisions.save", exc)


def _new_id(kind: str, artifact_ref: Optional[Dict[str, Any]]) -> str:
    seed = f"{kind}|{(artifact_ref or {}).get('content_hash','')}|{now_iso_z()}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _validate(row: Dict[str, Any]) -> None:
    if row.get("kind") not in VALID_KINDS:
        raise ValueError(f"bad kind {row.get('kind')!r}")
    if row.get("direction") not in VALID_DIRECTIONS:
        raise ValueError(f"bad direction {row.get('direction')!r}")
    if row.get("status") not in VALID_STATUSES:
        raise ValueError(f"bad status {row.get('status')!r}")
    ev = row.get("evidence")
    if not isinstance(ev, dict):
        raise ValueError("evidence must be a dict")
    # Guardrail: signal_prior must be ordering-only — never a number the threshold
    # could read as evidence weight. Stored, but explicitly not part of the count.
    if "signal_prior" not in ev:
        raise ValueError("evidence.signal_prior must be present (ordering-only, may be null)")


def make_candidate(
    *,
    kind: str,
    direction: str,
    artifact_ref: Optional[Dict[str, Any]] = None,
    goals: Optional[List[str]] = None,
    effect_rows: Optional[List[str]] = None,
    significance: float = 0.0,
    reuse_count: int = 0,
    memory_refs: Optional[List[str]] = None,
    signal_prior: Optional[float] = None,
    status: str = "pending",
    note: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a schema-valid candidate row (does not persist it)."""
    artifact_ref = dict(artifact_ref or {})
    row: Dict[str, Any] = {
        "id": _new_id(kind, artifact_ref),
        "kind": kind,
        "direction": direction,
        "artifact_ref": {
            "goal_id": artifact_ref.get("goal_id"),
            "content_hash": artifact_ref.get("content_hash"),
            "artifact_path": artifact_ref.get("artifact_path"),
        },
        "evidence": {
            "goals": list(goals or []),
            "effect_rows": list(effect_rows or []),
            "significance": float(significance or 0.0),
            "reuse_count": int(reuse_count or 0),
            "memory_refs": list(memory_refs or []),
            # ordering-only; never summed into the evidence threshold
            "signal_prior": (float(signal_prior) if signal_prior is not None else None),
        },
        "status": status,
        "note": note,
        "ts": now_iso_z(),
    }
    if extra:
        row.update(extra)
    _validate(row)
    return row


def append(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + persist a candidate. Idempotent on a pending promote for the same
    content_hash — a re-run of the proposer must not pile up duplicate candidates."""
    _validate(candidate)
    rows = load()
    chash = (candidate.get("artifact_ref") or {}).get("content_hash")
    if chash and candidate.get("kind") == "promote":
        for r in rows:
            if (
                r.get("kind") == "promote"
                and (r.get("artifact_ref") or {}).get("content_hash") == chash
                and r.get("status") in ("pending", "applied")
            ):
                return r  # already queued/applied — don't duplicate
    rows.append(candidate)
    save(rows)
    return candidate


def mark(candidate_id: str, status: str, **fields: Any) -> Optional[Dict[str, Any]]:
    """Set a row's status (+ any extra provenance fields) and persist. Returns the
    updated row, or None if the id is unknown."""
    if status not in VALID_STATUSES and status not in (
        # gate/ratify also use these explicit terminal sub-states
        "needs_rule_review",
    ):
        # allow needs_rule_review to ride on status while keeping it queryable
        pass
    rows = load()
    updated = None
    for r in rows:
        if r.get("id") == candidate_id:
            r["status"] = status
            for k, v in fields.items():
                r[k] = v
            r["updated_ts"] = now_iso_z()
            updated = r
            break
    if updated is not None:
        save(rows)
    return updated


def pending(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Pending rows, optionally filtered by kind."""
    out = [r for r in load() if r.get("status") == "pending"]
    if kind:
        out = [r for r in out if r.get("kind") == kind]
    return out


def get(candidate_id: str) -> Optional[Dict[str, Any]]:
    for r in load():
        if r.get("id") == candidate_id:
            return r
    return None
