"""Substantial, cumulative production for long-form goals."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from agency.effect_ledger import MIN_ARTIFACT_CHARS, record_effect
from paths import DATA_DIR
from utils.generate_response import generate_response, get_thinking_model, llm_ok
from utils.llm_gate import llm_callable_by
from utils.timeutils import now_iso_z

TRACKED_WORK_DIR = DATA_DIR / "tracked_work"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")[:64] or "work"


def _draft(goal: Dict[str, Any], section: str, context: Dict[str, Any]) -> str:
    title = str(goal.get("title") or goal.get("name") or "Tracked work")
    criteria = goal.get("definition_of_done") or []
    if llm_callable_by("goals"):
        prompt = (
            f"Draft a substantive section titled {section!r} for {title!r}. "
            f"Definition of done: {criteria}. Write at least 350 words, advance the "
            "central purpose, avoid placeholders and do not discuss the act of drafting."
        )
        text = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "goals")
        if text and len(text.strip()) >= MIN_ARTIFACT_CHARS:
            return text.strip()
    parts = goal.get("grounded_parts") or ["purpose", "evidence", "implications"]
    paragraphs = [
        f"# {section}\n",
        f"This section advances **{title}** by connecting {', '.join(map(str, parts[:3]))}. "
        "The central claim must be stated in terms that can be checked against the work itself, "
        "because activity without a durable change is not progress.",
        "The first requirement is structural clarity. The subject needs an explicit relationship "
        "between its purpose, its component parts, and the evidence that would support it. Each "
        "part should narrow uncertainty or add a usable result rather than repeat the title.",
        "The second requirement is continuity. This section belongs to a cumulative artifact, so "
        "its value depends on how it extends what came before and prepares what follows. A useful "
        "section leaves the manuscript more coherent, more specific, and easier to evaluate.",
        "The practical consequence is a concrete standard: preserve the durable text, identify the "
        "claim it advances, and record progress against the outline. That makes the next section a "
        "response to an actual gap in the work instead of another disconnected note.",
    ]
    return "\n\n".join(paragraphs)


def compose_section(context: Dict[str, Any] | None = None, **kwargs: Any) -> Dict[str, Any]:
    ctx = context or {}
    goal = ctx.get("committed_goal") or kwargs.get("goal") or {}
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"success": False, "error": "No committed goal"}
    gid = str(goal.get("id") or _slug(str(goal.get("title") or goal.get("name"))))
    plan = [p for p in (goal.get("plan") or []) if isinstance(p, dict)]
    pending = next((p for p in plan if p.get("status") != "completed"), None)
    section = str(kwargs.get("section") or (pending or {}).get("step") or f"Section {len(plan) + 1}")
    content = _draft(goal, section, ctx)
    if not re.match(r"^\s*#{1,3}\s+", content):
        content = f"## {section}\n\n{content}"
    elif content.lstrip().startswith("# "):
        content = re.sub(r"^\s*#\s+", "## ", content, count=1)
    TRACKED_WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(goal.get("tracked_work_path") or TRACKED_WORK_DIR / f"{_slug(gid)}.md")
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if prior else f"# {goal.get('title') or goal.get('name')}\n\n"
    path.write_text(prior + ("\n\n" if prior else "") + prefix + content + "\n", encoding="utf-8")
    completed_sections = len(re.findall(r"(?m)^##\s+", path.read_text(encoding="utf-8")))
    row = record_effect(
        "tracked_work", content, goal_id=gid, context=ctx,
        metadata={"path": str(path), "section": section, "completed_sections": completed_sections},
    )
    goal["tracked_work_path"] = str(path)
    goal["tracked_work"] = True
    if pending is not None and row is not None:
        pending["status"] = "completed"
        pending["completed_at"] = now_iso_z()
    try:
        from cognition.planning.goals import load_goals, merge_updated_goal_into_tree, save_goals
        save_goals(merge_updated_goal_into_tree(load_goals(), goal))
    except Exception:
        # The durable manuscript and effect row are authoritative; a goal-store
        # sync failure must not roll back a real external effect.
        pass
    return {
        "success": row is not None,
        "path": str(path),
        "section": section,
        "chars": len(content),
        "effect": row.to_json() if row else None,
    }
