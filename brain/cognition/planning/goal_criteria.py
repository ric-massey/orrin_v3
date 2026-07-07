# brain/cognition/planning/goal_criteria.py
# Artifact / completion-criteria gating for goals (Phase 4.5C, from goals.py).
# Whether a goal is artifact-gated (may complete ONLY when a real durable effect
# was recorded for it), its definition-of-done criteria, and whether that
# criteria evidence is met. Self-contained leaf (reads the effect ledger via a
# lazy import); imported by the pursuit + outcome logic and re-exported from
# goals.py.
from __future__ import annotations

import re
from typing import Any, List, Dict

from brain.utils.json_utils import load_json


# P2 — production goals are artifact-gated and fail-able. The unit is *cycles*
# (the diagnosed run did ~10⁴ cycles at cycle_sleep≈20s). 200 is long enough that
# a genuine plan→execute→write attempt isn't guillotined, short enough that a full
# life surfaces many deadline evaluations so goals_failed actually moves off 0.
# Reuses the same epoch as the P6 reconciler so there is one cadence constant.
PRODUCTION_DEADLINE_CYCLES = 200


def is_aspiration(goal: Any) -> bool:
    """F2 (2026-07-05 findings) — a standing value, not a task. Aspirations are
    directional: they persist for the whole life, are never pursued/committed
    directly, and can be EDITED but never failed or completed. The 2026-07-05
    run failed aspiration nodes round-robin all life ("objective unmet after 2
    attempts") and `output_producing` was dead at death. One shared definition
    so the failure paths, the executive queue, and the deadline walker agree."""
    if not isinstance(goal, dict):
        return False
    if goal.get("_aspiration") or str(goal.get("kind") or "").lower() == "aspiration":
        return True
    if str(goal.get("tier") or "").lower() in ("aspiration", "long_term"):
        return True
    return str(goal.get("id") or "").startswith("aspiration-")


def _is_artifact_gated(goal: Dict[str, Any]) -> bool:
    """A goal that may complete ONLY when a real durable effect was recorded for it."""
    if not isinstance(goal, dict):
        return False
    spec_raw = goal.get("spec")
    spec: Dict[str, Any] = spec_raw if isinstance(spec_raw, dict) else {}
    if bool(goal.get("requires_artifact") or spec.get("requires_artifact")):
        return True
    if str(goal.get("driven_by") or spec.get("driven_by") or "").lower() == "output_producing":
        return True
    text = " ".join(str(goal.get(k) or spec.get(k) or "") for k in ("title", "name", "description")).lower()
    return any(word in text for word in (
        "write ", "build ", "create ", "make ", "compose ", "publish ",
        "implement ", "produce ", "draft ",
    ))


_MAKE_SHAPED_KINDS = {"coding", "code_edit"}


def goal_is_make_shaped(goal: Dict[str, Any]) -> bool:
    """RUN4_FIX_PLAN §B4/§A2 — a goal that exists to PRODUCE: a coding kind, a
    generic goal carrying a synthesize/make spec, or an explicitly output-driven
    goal. A research/intake goal is NOT make-shaped even though it writes a memo
    file, so it can't wear the making hat and inflate output_producing credit.
    Shared home so step_execution (handoff) and intrinsic_objectives (credit)
    agree on one definition."""
    if not isinstance(goal, dict):
        return False
    if str(goal.get("kind") or "").lower() in _MAKE_SHAPED_KINDS:
        return True
    if str(goal.get("driven_by") or "").lower() == "output_producing":
        return True
    spec_raw = goal.get("spec")
    spec: Dict[str, Any] = spec_raw if isinstance(spec_raw, dict) else {}
    return bool(spec.get("synthesize") or spec.get("make")
                or str(spec.get("driven_by") or "").lower() == "output_producing")


def _definition_of_done(goal: Dict[str, Any]) -> List[Dict[str, Any]]:
    spec_raw = goal.get("spec")
    spec: Dict[str, Any] = spec_raw if isinstance(spec_raw, dict) else {}
    raw = goal.get("definition_of_done") or spec.get("definition_of_done") or []
    out: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("criterion"):
            out.append(item)
        elif str(item or "").strip():
            out.append({"criterion": str(item).strip(), "kind": "quality", "met": False})
    return out


def _criteria_evidence_met(goal: Dict[str, Any]) -> bool:
    """Check persisted evidence, never a bare model assertion."""
    criteria = _definition_of_done(goal)
    if not criteria:
        return False
    gid = str(goal.get("id") or "")
    produced = False
    if gid:
        try:
            from brain.agency.effect_ledger import has_qualifying_effect
            produced = has_qualifying_effect(gid, goal)
        except ImportError:  # intentional: effect ledger optional → produced stays False
            pass
    milestones = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    all_milestones = bool(milestones) and all(bool(m.get("met")) for m in milestones)
    evidence = goal.get("completion_evidence") or {}
    checks = evidence.get("criteria") if isinstance(evidence, dict) else []

    def _observed(text: str) -> bool:
        words = {w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())}
        if len(words) < 2:
            return False
        try:
            from brain.paths import WORKING_MEMORY_FILE
            memory: List[Any] = load_json(WORKING_MEMORY_FILE, default_type=list) or []
        except Exception:
            memory = []
        for entry in memory[-40:] if isinstance(memory, list) else []:
            content = str(entry.get("content", entry) if isinstance(entry, dict) else entry).lower()
            if len(words & set(re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", content))) >= 2:
                return True
        return False

    checked = {
        str(row.get("criterion") or ""): (
            bool(row.get("met"))
            and bool(row.get("evidence"))
            and _observed(str(row.get("evidence") or ""))
        )
        for row in checks or [] if isinstance(row, dict)
    }
    for criterion in criteria:
        kind = str(criterion.get("kind") or "").lower()
        text = str(criterion.get("criterion") or "")
        met = bool(criterion.get("met"))
        if kind in {"artifact", "sections", "validation"} and produced:
            met = True
        if all_milestones:
            met = True
        if checked.get(text):
            met = True
        if not met:
            return False
    return True

