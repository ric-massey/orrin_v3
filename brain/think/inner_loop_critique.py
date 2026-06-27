# brain/think/inner_loop_critique.py
#
# Draft critique stage for inner_loop.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. Three critique
# voices over a draft answer — _critique_primary (reflect_on_internal_agents),
# _critique_contradiction (logical consistency), _critique_value_alignment — and
# _full_critique, which composes them into a single critique string + a severity
# count. inner_loop.py re-imports _full_critique for run_inner_loop.
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from brain.utils.llm_router import routed_response
from brain.utils.failure_counter import record_failure

# ── Critique stage 1: reflect_on_internal_agents ─────────────────────────────

def _critique_primary(draft: str, topic: str, context: Dict[str, Any]) -> str:
    try:
        from brain.cognition.reflection.reflect_on_internal_agents import critique_draft as _ext
        result = _ext(draft, context)
        if result and len(result.strip()) > 20:
            return result.strip()
    except Exception as _e:
        record_failure("inner_loop._critique_primary", _e)

    values = (context.get("self_model") or {}).get("core_values") or []
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:4]
    )
    prompt = (
        f"You are Orrin's primary critic.\n"
        f"Orrin's values: {values_text or '(unknown)'}.\n\n"
        f"Topic: {topic}\nDraft:\n{draft}\n\n"
        "Identify the single most important weakness: a gap in reasoning, a value "
        "misalignment, or an unsupported assumption. 1-2 sentences. "
        "If solid, say 'No major issues.'"
    )
    return (routed_response(prompt, "inner_loop/critique/primary", complexity="simple") or "").strip()


# ── Critique stage 2: contradiction detector ─────────────────────────────────

def _critique_contradiction(draft: str, topic: str, context: Dict[str, Any]) -> str:
    wm_tail = (context.get("working_memory") or [])[-3:]
    wm_text = "\n".join(
        str(e.get("content", e) if isinstance(e, dict) else e)[:100] for e in wm_tail
    ) or "(none)"

    prompt = (
        f"You are Orrin's contradiction detector.\n\n"
        f"Recent working memory:\n{wm_text}\n\n"
        f"Topic: {topic}\nDraft:\n{draft}\n\n"
        "Does this draft contradict what Orrin said or concluded recently? "
        "Does it contain internal contradictions? "
        "1-2 sentences. If consistent, say 'No contradiction found.'"
    )
    return (routed_response(prompt, "inner_loop/critique/contradiction", complexity="simple") or "").strip()


# ── Critique stage 3: value alignment checker ────────────────────────────────

def _critique_value_alignment(draft: str, context: Dict[str, Any]) -> str:
    values = (context.get("self_model") or {}).get("core_values") or []
    if not values:
        return ""
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:5]
    )
    prompt = (
        f"You are Orrin's value-alignment checker.\n"
        f"Orrin's core values: {values_text}\n\n"
        f"Draft:\n{draft}\n\n"
        "Does this draft act in accordance with these values? "
        "Would Orrin endorse it on reflection? "
        "1-2 sentences. If aligned, say 'Values aligned.'"
    )
    return (routed_response(prompt, "inner_loop/critique/values", complexity="simple") or "").strip()


# ── Combined critique → synthesis ─────────────────────────────────────────────

def _full_critique(draft: str, topic: str, context: Dict[str, Any]) -> Tuple[str, int]:
    """
    Run all three critique checks; synthesize into one actionable note.
    Returns (critique_text, count_of_real_issues).
    """
    primary = _critique_primary(draft, topic, context)
    contradiction = _critique_contradiction(draft, topic, context)
    value_align   = _critique_value_alignment(draft, context)

    # Filter trivial "no issues" responses
    _no_issue = ("no major issues", "no contradiction", "values aligned", "solid", "consistent")
    issues: List[str] = []
    for label, text in [("Primary", primary), ("Contradiction", contradiction), ("Values", value_align)]:
        if text and not any(ni in text.lower() for ni in _no_issue):
            issues.append(f"[{label}] {text}")

    if not issues:
        return "", 0

    if len(issues) == 1:
        return issues[0], 1

    # Multiple issues: synthesize into one actionable critique
    combined_raw = "\n".join(issues)
    synth_prompt = (
        f"Three internal critics flagged issues with this draft:\n{combined_raw}\n\n"
        "Synthesize the most actionable single critique in 1-2 sentences."
    )
    synth = (routed_response(synth_prompt, "inner_loop/critique/synth", complexity="simple") or combined_raw).strip()
    return synth, len(issues)


# ── Revision prompt ───────────────────────────────────────────────────────────
