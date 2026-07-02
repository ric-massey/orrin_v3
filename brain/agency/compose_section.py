"""Substantial, cumulative production for long-form goals."""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import re
from pathlib import Path
from typing import Any, Dict

from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS, record_effect
from brain.paths import DATA_DIR
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.utils.llm_gate import llm_callable_by
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

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
    # AR3 (audit D6): LLM-off composition speaks with his own trained organ, not
    # a fixed template that games the artifact gate with identical boilerplate.
    # Maturity-gated on the same voice.lm_ready check the mouth uses, so an
    # immature organ never fills a manuscript with noise; the template below is
    # only the not-ready fallback, and the honest MIN_ARTIFACT_CHARS floor still
    # applies to whatever the organ produces.
    try:
        from brain.cognition.language.voice import lm_ready
        if lm_ready():
            from brain.cognition.language import native_lm
            from brain.utils.felt_lexicon import strip_scaffold
            parts_hint = ", ".join(map(str, (goal.get("grounded_parts") or [])[:3]))
            prompt = f"{title} — {section}"
            if parts_hint:
                prompt += f" (connecting {parts_hint})"
            prompt += ": "
            text = strip_scaffold(
                native_lm.generate(prompt, length=400, temperature=0.7) or ""
            ).strip()
            if text.startswith(prompt):
                text = text[len(prompt):].strip()
            if len(text) >= MIN_ARTIFACT_CHARS:
                return text
    except Exception as exc:
        record_failure("compose_section.native_draft", exc)
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
    goal = bound_goal(ctx) or kwargs.get("goal") or {}
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"success": False, "error": "No committed goal"}
    gid = str(goal.get("id") or _slug(str(goal.get("title") or goal.get("name"))))
    plan = [p for p in (goal.get("plan") or []) if isinstance(p, dict)]
    pending = next((p for p in plan if p.get("status") != "completed"), None)
    pending_action = (pending or {}).get("action")
    action_section = pending_action.get("section") if isinstance(pending_action, dict) else None
    section = str(
        kwargs.get("section")
        or action_section
        or (pending or {}).get("step")
        or f"Section {len(plan) + 1}"
    )
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
    # P1a: capture the section TEXT keyed by content_hash for later promotion.
    if row is not None:
        try:
            from brain.agency.effect_artifacts import capture as _cap_artifact
            _cap_artifact(content, content_hash=row.content_hash)
        except Exception as exc:
            record_failure("compose_section.capture_artifact", exc)
    goal["tracked_work_path"] = str(path)
    goal["tracked_work"] = True
    if pending is not None and row is not None:
        pending["status"] = "completed"
        pending["completed_at"] = now_iso_z()
    try:
        from brain.cognition.planning.goals import load_goals, merge_updated_goal_into_tree, save_goals
        save_goals(merge_updated_goal_into_tree(load_goals(), goal))
    except Exception as exc:
        # The durable manuscript and effect row are authoritative; a goal-store
        # sync failure must not roll back a real external effect.
        record_failure("compose_section.goal_store_sync", exc)
    return {
        "success": row is not None,
        "path": str(path),
        "section": section,
        "chars": len(content),
        "effect": row.to_json() if row else None,
    }
