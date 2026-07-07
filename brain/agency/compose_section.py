"""Substantial, cumulative production for long-form goals.

F1 (2026-07-05 findings): compose_section is grounded-or-failed. A section is
drafted FROM real stores — credited ledger artifacts, learned notes, long-memory
findings, causal edges on the goal's topic (cognition.section_material) — and an
empty material pool is a legitimate step FAILURE ("nothing to synthesize"),
never a template. The 2026-07-05 run stamped 664 paragraphs (4 unique) into a
197 KB manuscript because the fixed-template fallback below the LLM/native
paths always "succeeded"; that fallback is gone. The ledger's dedupe verdict is
read BEFORE the manuscript is touched, so a non-novel draft appends nothing and
reports an honest failure the step-runner can count.
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS, record_effect
from brain.cognition.section_material import MIN_MATERIAL, gather_material as _gather_material
from brain.paths import DATA_DIR
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.utils.llm_gate import llm_callable_by
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure

TRACKED_WORK_DIR = DATA_DIR / "tracked_work"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-")[:64] or "work"


def _draft(goal: Dict[str, Any], section: str,
           material: List[Tuple[str, str, str]]) -> str:
    """Draft the section FROM the material. Returns "" when no capable writer
    produced real content — the caller fails the step honestly (no template)."""
    title = str(goal.get("title") or goal.get("name") or "Tracked work")
    criteria = goal.get("definition_of_done") or []
    source_block = "\n\n".join(f"[{lbl}]\n{body}" for lbl, body, _ in material)
    if llm_callable_by("goals"):
        prompt = (
            f"Draft a substantive section titled {section!r} for {title!r}. "
            f"Definition of done: {criteria}. Synthesize from the SOURCE MATERIAL "
            "below — cite or paraphrase at least two of the sources, connect them, "
            "and say something they don't say individually. Write at least 350 "
            "words, avoid placeholders, and do not discuss the act of drafting.\n\n"
            f"SOURCE MATERIAL:\n{source_block}"
        )
        text = llm_ok(generate_response(prompt, config={"model": get_thinking_model()}), "goals")
        if text and len(text.strip()) >= MIN_ARTIFACT_CHARS:
            return text.strip()
    # AR3 (audit D6): LLM-off composition speaks with his own trained organ.
    # Maturity-gated on the same voice.lm_ready check the mouth uses; the organ
    # is seeded with the material so the draft stays grounded in real sources.
    try:
        from brain.cognition.language.voice import lm_ready
        if lm_ready():
            from brain.cognition.language import native_lm
            from brain.utils.felt_lexicon import strip_scaffold
            seed = material[0][1][:160] if material else ""
            prompt = f"{title} — {section}: {seed} "
            text = strip_scaffold(
                native_lm.generate(prompt, length=400, temperature=0.7) or ""
            ).strip()
            if text.startswith(prompt):
                text = text[len(prompt):].strip()
            if len(text) >= MIN_ARTIFACT_CHARS:
                return text
    except Exception as exc:
        record_failure("compose_section.native_draft", exc)
    # F1: no writer could produce grounded content. The old fixed four-paragraph
    # template that used to live here is what stamped 166 identical sections in
    # the 2026-07-05 run — failing honestly is the fix, not a better template.
    return ""


def compose_section(context: Dict[str, Any] | None = None, **kwargs: Any) -> Dict[str, Any]:
    ctx = context or {}
    goal = bound_goal(ctx) or kwargs.get("goal") or {}
    if not isinstance(goal, dict) or not (goal.get("title") or goal.get("name")):
        return {"success": False, "error": "No committed goal",
                "result": "could not compose: no committed goal"}
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

    # F1a — grounded or failed: no source material means there is nothing to
    # synthesize, and that is a real step failure the attempt-cap can count.
    material = _gather_material(goal, section)
    if len(material) < MIN_MATERIAL:
        return {"success": False, "section": section,
                "error": "nothing_to_synthesize",
                "result": f"nothing to synthesize for {section!r} — "
                          f"{len(material)} usable source(s); go gather material first"}

    content = _draft(goal, section, material)
    if not content:
        return {"success": False, "section": section,
                "error": "no_grounded_draft",
                "result": f"could not draft {section!r} from sources — "
                          "no capable writer produced grounded content"}
    if not re.match(r"^\s*#{1,3}\s+", content):
        content = f"## {section}\n\n{content}"
    elif content.lstrip().startswith("# "):
        content = re.sub(r"^\s*#\s+", "## ", content, count=1)

    # F1a — the ledger's novelty verdict comes BEFORE the manuscript is touched:
    # a deduped draft appends nothing and reports failure, so the 2026-07-05
    # append-then-dedupe treadmill (166 sections, 156 uncredited) cannot recur.
    TRACKED_WORK_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(goal.get("tracked_work_path") or TRACKED_WORK_DIR / f"{_slug(gid)}.md")
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    completed_sections = len(re.findall(r"(?m)^##\s+", prior)) + 1
    row = record_effect(
        "tracked_work", content, goal_id=gid, context=ctx,
        metadata={"path": str(path), "section": section, "completed_sections": completed_sections},
    )
    if row is None:
        return {"success": False, "section": section,
                "error": "deduplicated",
                "result": f"nothing to add — the draft for {section!r} duplicates "
                          "prior work (no novel content credited)"}

    prefix = "" if prior else f"# {goal.get('title') or goal.get('name')}\n\n"
    path.write_text(prior + ("\n\n" if prior else "") + prefix + content + "\n", encoding="utf-8")
    # P1a: capture the section TEXT keyed by content_hash for later promotion.
    try:
        from brain.agency.effect_artifacts import capture as _cap_artifact
        _cap_artifact(content, content_hash=row.content_hash)
    except Exception as exc:
        record_failure("compose_section.capture_artifact", exc)
    # Tier-3 reuse credit: the section genuinely built on prior credited
    # artifacts (the material it was drafted from).
    for _lbl, _body, _hash in material:
        if _hash:
            try:
                from brain.agency.effect_ledger import mark_reused
                mark_reused(_hash)
            except Exception as exc:
                record_failure("compose_section.mark_reused", exc)
    goal["tracked_work_path"] = str(path)
    goal["tracked_work"] = True
    if pending is not None:
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
        "success": True,
        "path": str(path),
        "section": section,
        "chars": len(content),
        "sources": len(material),
        "result": f"wrote grounded section {section!r} ({len(content)} chars, "
                  f"{len(material)} sources) to {path.name}",
        "effect": row.to_json(),
    }
