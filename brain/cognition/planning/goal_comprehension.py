"""Turn a goal label into a checkable, actionable goal model."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from utils.generate_response import generate_response, get_thinking_model, llm_ok
from utils.json_utils import extract_json
from utils.llm_gate import llm_callable_by
from utils.timeutils import now_iso_z

_LONG_FORM = re.compile(r"\b(book|manuscript|paper|essay|article|report|guide|chapter)\b", re.I)
_OUTPUT = re.compile(r"\b(write|build|create|make|compose|publish|implement|produce|draft)\b", re.I)


def _text(goal: Dict[str, Any]) -> str:
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    return " ".join(str(v or "") for v in (
        goal.get("title"), goal.get("name"), goal.get("description"), spec.get("description")
    )).strip()


def _criterion(text: str, *, kind: str = "quality", target: Any = True) -> Dict[str, Any]:
    return {"criterion": text[:240], "kind": kind, "target": target, "met": False}


def _fallback(goal: Dict[str, Any]) -> Dict[str, Any]:
    text = _text(goal) or "Complete the stated goal"
    long_form = bool(_LONG_FORM.search(text))
    output = bool(_OUTPUT.search(text) or long_form)
    if long_form:
        parts = ["purpose and thesis", "outline", "substantive sections", "coherence review", "final manuscript"]
        criteria = [
            _criterion("A persistent manuscript exists and contains a clear purpose or thesis.", kind="artifact"),
            _criterion("The manuscript has an explicit outline with at least three substantive sections.", kind="sections", target=3),
            _criterion("Each completed section advances the stated purpose without placeholder text.", kind="quality"),
        ]
    elif output:
        parts = ["intended outcome", "required components", "implementation", "validation", "durable result"]
        criteria = [
            _criterion("A durable artifact exists for this goal.", kind="artifact"),
            _criterion("The artifact directly addresses the goal rather than merely describing intent.", kind="quality"),
            _criterion("The result has been checked against the stated outcome.", kind="validation"),
        ]
    else:
        parts = ["question or desired change", "relevant evidence", "reasoned conclusion", "observable consequence"]
        criteria = [
            _criterion("Relevant evidence or observations have been recorded.", kind="evidence"),
            _criterion("A reasoned conclusion directly answers the goal.", kind="quality"),
            _criterion("At least one observable consequence or next decision is identified.", kind="outcome"),
        ]
    plan = [
        {"step": f"Establish {part}", "status": "pending", "generated_at": now_iso_z()}
        for part in parts
    ]
    milestones = [
        {"milestone": row["criterion"], "criterion_kind": row["kind"], "met": False}
        for row in criteria
    ]
    return {
        "definition_of_done": criteria,
        "grounded_parts": parts,
        "plan": plan,
        "milestones": milestones,
        "requires_artifact": output,
        "tracked_work": long_form,
        "comprehension_source": "symbolic",
    }


def _llm_comprehension(goal: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        "Convert this goal into a grounded, checkable goal model. Return JSON only with: "
        "grounded_parts (3-7 concrete component strings), definition_of_done "
        "(3-6 objects with criterion, kind, target), plan (ordered step strings), "
        "milestones (checkable milestone strings), requires_artifact (boolean), "
        "tracked_work (boolean). Criteria must be objectively checkable and must not "
        "use self-report as evidence.\nGoal: " + _text(goal)
    )
    raw = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "goals")
    data = extract_json(raw or "")
    return data if isinstance(data, dict) else {}


def comprehend_goal(goal: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return a copy enriched with a definition of done, grounded parts and derived plan."""
    if not isinstance(goal, dict):
        return goal
    out = dict(goal)
    model = _fallback(out)
    if llm_callable_by("goals"):
        try:
            proposed = _llm_comprehension(out)
            parts = [str(x).strip() for x in proposed.get("grounded_parts", []) if str(x).strip()]
            criteria: List[Dict[str, Any]] = []
            for item in proposed.get("definition_of_done", []):
                if isinstance(item, dict) and str(item.get("criterion") or "").strip():
                    row = dict(item)
                    row.setdefault("met", False)
                    criteria.append(row)
            plan_text = [str(x).strip() for x in proposed.get("plan", []) if str(x).strip()]
            milestone_text = [str(x).strip() for x in proposed.get("milestones", []) if str(x).strip()]
            if parts and criteria and plan_text:
                model.update({
                    "grounded_parts": parts[:7],
                    "definition_of_done": criteria[:6],
                    "plan": [{"step": x, "status": "pending", "generated_at": now_iso_z()} for x in plan_text[:8]],
                    "milestones": [{"milestone": x, "met": False} for x in milestone_text[:8]],
                    "requires_artifact": bool(proposed.get("requires_artifact")),
                    "tracked_work": bool(proposed.get("tracked_work")),
                    "comprehension_source": "llm",
                })
        except Exception:
            pass
    for key, value in model.items():
        if key in {"plan", "milestones"} and out.get(key):
            continue
        out.setdefault(key, value)
    out["comprehended_at"] = now_iso_z()
    return out
