# brain/cognition/quality_standard/ratify.py
#
# P4 — the human-ratification path.  THE CORE GUARDRAIL.
#
# The one direction that is gameable — LOOSEN / REMOVE an exemplar, RELAX the
# predicate, RESOLVE a suspect — NEVER auto-applies. Everything here is invoked from
# a HUMAN action (a CLI command / UI button), never from cognition. The component is
# not importable from selection (import-guard test), so Orrin has no path to call it.
#
# approve(id) is the only code in the whole component that applies a loosening. It
# performs the removal/edit, then RE-RUNS the regression as the gate (here the test
# has real teeth: a removal/edit CAN turn it red), and rolls back on red — "rejected,
# not forced." Every applied change is reversible from its logged provenance row
# (the removed exemplar's text is stored on the row before deletion).
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain.cognition.quality_standard import revisions
from brain.cognition.quality_standard.gate import regression_smoke
from brain.utils.log import log_activity, log_private
from brain.utils.failure_counter import record_failure
from brain.utils.timeutils import now_iso_z


def _prior_for_ordering(row: Dict[str, Any]) -> float:
    """Order the queue by signal_prior — explicitly a PRIORITIZER of what gets
    reviewed first, NEVER a vote on the outcome (guardrail: emotions don't decide
    the standard). None sorts last."""
    sp = ((row.get("evidence") or {}).get("signal_prior"))
    try:
        return float(sp) if sp is not None else -1.0
    except (TypeError, ValueError):
        return -1.0


def review_queue() -> List[Dict[str, Any]]:
    """Everything awaiting a human decision: pending loosenings (direction=lower),
    suspect flags, and promotions the predicate rejected (needs_rule_review).
    Ordered by signal_prior (prioritization only)."""
    out = [
        r for r in revisions.load()
        if r.get("status") == "pending" and (
            r.get("direction") == "lower"
            or r.get("kind") == "suspect"
            or r.get("needs_rule_review")
        )
    ]
    out.sort(key=_prior_for_ordering, reverse=True)
    return out


def reject(candidate_id: str, *, reviewer: str = "human", reason: str = "") -> Optional[Dict[str, Any]]:
    """Decline a candidate. No change to the golden set; logged for the audit trail."""
    row = revisions.mark(
        candidate_id, "rejected",
        reviewer=reviewer, review_reason=reason, reviewed_ts=now_iso_z(),
    )
    if row is not None:
        log_activity(f"[quality_standard] candidate {candidate_id} REJECTED by {reviewer}.")
    return row


def approve(candidate_id: str, *, reviewer: str = "human") -> Tuple[bool, str]:
    """Apply a human-ratified change. The ONLY code that loosens the bar.

    - suspect / direction=lower → REMOVE the named exemplar (store its text on the
      row first, for reversibility), then re-run the regression. Red → restore the
      file and refuse ("rejected, not forced").
    - needs_rule_review (a promote the predicate rejected) → re-run the regression
      as the gate. It passes only if a human has ALREADY edited the predicate rule
      so the exemplar now conforms; until then the regression stays red and approve
      refuses. approve never edits rule code itself.

    Returns (applied, message)."""
    row = revisions.get(candidate_id)
    if row is None:
        return False, f"unknown candidate {candidate_id}"
    if row.get("status") != "pending":
        return False, f"candidate {candidate_id} is not pending (status={row.get('status')})"

    kind = row.get("kind")
    ref = row.get("artifact_ref") or {}

    # ── Loosening: remove an exemplar (suspect / explicit lower) ────────────────
    if kind == "suspect" or row.get("direction") == "lower":
        path_str = ref.get("artifact_path")
        if not path_str:
            return False, "suspect candidate has no artifact_path to remove"
        p = Path(path_str)
        if not p.is_file():
            # Already gone; record as applied (idempotent, still reversible via row).
            revisions.mark(candidate_id, "applied", reviewer=reviewer,
                           reviewed_ts=now_iso_z(), removed_text=row.get("removed_text"))
            return True, f"exemplar already absent: {path_str}"
        try:
            removed_text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return False, f"cannot read exemplar before removal: {exc}"
        try:
            p.unlink()
        except OSError as exc:
            return False, f"cannot remove exemplar: {exc}"

        ok, reason = regression_smoke()
        if not ok:
            # Red → restore and refuse. The invariant rules: rejected, not forced.
            try:
                p.write_text(removed_text, encoding="utf-8")
            except OSError as exc:
                record_failure("quality_standard.ratify.restore", exc)
            return False, f"regression red after removal ({reason}) → restored, not applied"

        revisions.mark(
            candidate_id, "applied",
            reviewer=reviewer, reviewed_ts=now_iso_z(),
            removed_text=removed_text, removed_path=path_str,
        )
        log_activity(f"[quality_standard] exemplar REMOVED via ratify: {p.name} (by {reviewer}).")
        log_private(f"[quality_standard] reversible: removed_text stored on candidate {candidate_id}.")
        return True, f"removed exemplar {p.name}; regression green"

    # ── needs_rule_review: a promote the predicate rejected ─────────────────────
    if kind == "promote" and row.get("needs_rule_review"):
        # Gate on THIS artifact's own text, not the golden-set smoke check (the
        # artifact isn't in the set yet). It conforms only if a human has edited the
        # predicate rule so it now passes; until then, refuse — never force.
        from brain.agency import effect_artifacts
        from brain.cognition.quality_predicate import assess_quality
        chash = ref.get("content_hash")
        text = effect_artifacts.load(chash) if chash else None
        if not text:
            return False, "artifact text unavailable; cannot re-check predicate"
        verdict = assess_quality(text)
        if not verdict.ok:
            return False, (
                f"predicate still rejects this artifact ({verdict.reason}); "
                f"edit the predicate rule first, then approve again"
            )
        # The human edited the rule and it conforms now; clear the flag and let the
        # gate (P2) do the add-only write + its own regression smoke check.
        revisions.mark(candidate_id, "pending", needs_rule_review=False,
                       rule_reviewed_by=reviewer, rule_reviewed_ts=now_iso_z())
        from brain.cognition.quality_standard.gate import apply_pending_promotions
        applied = apply_pending_promotions()
        for r in applied:
            if r.get("id") == candidate_id and r.get("status") == "applied":
                return True, "rule conforms now; exemplar promoted"
        return True, "rule review cleared; re-queued for the gate"

    return False, f"candidate {candidate_id} is not a loosening/review action"


def restore(candidate_id: str, *, reviewer: str = "human") -> Tuple[bool, str]:
    """Reverse an applied removal from its logged provenance (re-write the removed
    exemplar text). Makes every loosening reversible (acceptance §5)."""
    row = revisions.get(candidate_id)
    if row is None:
        return False, f"unknown candidate {candidate_id}"
    text = row.get("removed_text")
    path_str = row.get("removed_path") or (row.get("artifact_ref") or {}).get("artifact_path")
    if not text or not path_str:
        return False, "candidate has no removed_text/path to restore"
    try:
        Path(path_str).write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, f"restore failed: {exc}"
    revisions.mark(candidate_id, "rejected", restored_by=reviewer, restored_ts=now_iso_z())
    log_activity(f"[quality_standard] exemplar RESTORED from provenance: {path_str} (by {reviewer}).")
    return True, f"restored {path_str}"
