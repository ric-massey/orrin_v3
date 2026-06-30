# brain/cognition/quality_standard/ — the T0.5 quality-standard adaptation layer.
#
# Implements QUALITY_STANDARD_EVOLUTION_IMPLEMENTATION_PLAN_2026-06-28.md: the
# golden set develops from Orrin's own demonstrated-good work, on EVIDENCE of
# downstream effect — never on a desire to close a goal.
#
# GUARDRAIL (design §4.3 #4): this package is NON-COGNITION. It is never imported
# from brain/think/.../selection/* (an import-guard test enforces it), so Orrin can
# never *choose* it in order to pass a goal. The proposer/gate run as a background
# pass from the dream cycle; the only path that LOOSENS the bar (ratify.py) is
# invoked from a human action, never from cognition.
#
#   revisions.py — candidate store (load/save/append/mark), mirrors value_revisions
#   proposer.py  — P1b promotion + P3 suspect proposers (read-only)
#   gate.py      — P2 the only auto-apply (add-only, predicate-conforming)
#   ratify.py    — P4 human-ratify API (every loosen/remove/relax)
#
# RESEARCH LINEAGE (the safety architecture; the thresholds themselves are
# engineering judgment, not calibrated to these).
#   * Goodhart's law — a measure optimised against stops measuring what it meant to.
#     Goodhart (1975); Strathern (1997) "'Improving ratings': audit in the British
#     University system"; Manheim & Garrabrant (2018) "Categorizing Variants of
#     Goodhart's Law". This is the failure guardrail #1/#2 exist to prevent.
#   * Specification gaming / reward hacking — "the mind that grades its own work
#     loosening the grade." Amodei et al. (2016) "Concrete Problems in AI Safety";
#     Krakovna et al. (2020) specification-gaming catalogue; Skalse et al. (2022)
#     "Defining and Characterizing Reward Hacking".
#   * Reward tampering — the optimiser must not be able to REACH its own objective.
#     Everitt et al. (2021) "Reward Tampering Problems and Solutions". This is the
#     ground for guardrail #4 (not importable from selection; the import-guard test).
from __future__ import annotations

from brain.cognition.quality_standard.proposer import (
    propose_promotions,
    propose_suspects,
)
from brain.cognition.quality_standard.gate import apply_pending_promotions

__all__ = [
    "propose_promotions",
    "propose_suspects",
    "apply_pending_promotions",
    "run_background_pass",
]


def run_background_pass(context=None) -> dict:
    """The dream-cadence background pass: propose promotions (P1b) + suspects (P3),
    then auto-apply only the predicate-conforming promotions (P2). NEVER loosens —
    every loosen/remove waits in the queue for the human-ratify path (P4).

    Returns a small summary dict for the dream log. Read-only except for P2's
    add-only exemplar writes (which by construction cannot lower the floor)."""
    from brain.utils.failure_counter import record_failure
    out = {"promotions_proposed": 0, "suspects_flagged": 0, "applied": 0}
    try:
        out["promotions_proposed"] = len(propose_promotions(context) or [])
    except Exception as exc:  # background pass must never crash the dream cycle
        record_failure("quality_standard.run_background_pass.promotions", exc)
    try:
        out["suspects_flagged"] = len(propose_suspects(context) or [])
    except Exception as exc:
        record_failure("quality_standard.run_background_pass.suspects", exc)
    try:
        out["applied"] = len(apply_pending_promotions() or [])
    except Exception as exc:
        record_failure("quality_standard.run_background_pass.apply", exc)
    return out
