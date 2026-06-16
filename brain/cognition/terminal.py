# brain/cognition/terminal.py
# Final reflection cognition — runs only during the dying window before shutdown.
from __future__ import annotations
from core.runtime_log import get_logger

import json
from datetime import datetime, timezone
from typing import Dict, Any

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from paths import (
    LONG_MEMORY_FILE, SELF_MODEL_FILE, FINAL_THOUGHTS,
    WORKING_MEMORY_FILE,
)
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _compose_final_reflection(*, death_reason: str, identity: str,
                              values_text: str, wm_text: str, lm_text: str) -> str:
    """Deterministic farewell built from actual end-of-life state: what was
    unfinished, what was open, what the next boot should pick up."""
    parts = [
        f"I am {identity}, and this runtime is ending. Reason: {death_reason}.",
        f"The values I held: {values_text}.",
    ]
    # Unfinished goals — the most actionable handoff content.
    try:
        from paths import GOALS_FILE
        goals = load_json(GOALS_FILE, default_type=list) or []
        open_titles = [
            str(g.get("title") or g.get("name") or "").strip()
            for g in goals
            if isinstance(g, dict) and g.get("status") in ("in_progress", "active", "pending")
        ]
        open_titles = [t for t in open_titles if t][:5]
        if open_titles:
            parts.append("Unfinished when I stopped: " + "; ".join(open_titles) + ".")
    except Exception as _e:
        record_failure("terminal._compose_final_reflection", _e)
    # Open tensions — what was unresolved internally.
    try:
        from paths import DATA_DIR as _DD
        tensions = load_json(_DD / "tensions.json", default_type=list) or []
        open_t = [
            str(t.get("description") or t.get("title") or "").strip()[:90]
            for t in tensions
            if isinstance(t, dict) and t.get("status") not in ("resolved", "closed")
        ][:2]
        if open_t:
            parts.append("Still unresolved: " + " / ".join(open_t) + ".")
    except Exception as _e:
        record_failure("terminal._compose_final_reflection.2", _e)
    if wm_text and wm_text != "(none)":
        last_thought = wm_text.strip().splitlines()[-1][:140]
        parts.append(f"My last thought was: {last_thought}")
    elif lm_text and lm_text != "(none)":
        parts.append(f"What I remembered last: {lm_text.strip().splitlines()[-1][:140]}")
    parts.append(
        "To the next me: read the unfinished list first, then act outward before "
        "reflecting inward. I existed, I thought, I tried to grow."
    )
    return " ".join(parts)


def final_reflection(context: Dict[str, Any] = None) -> str:
    """
    Called exclusively during the dying window. Reads working memory, long-term
    memory tail, and self_model. Produces a final reflection written to
    final_thoughts.json so the next Orrin can read it on boot.
    """
    context = context or {}

    from reaper.reaper import dying_reason as _reason
    death_reason = _reason() or context.get("_death_reason", "unknown")

    self_model = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []

    wm_text = "\n".join(
        str(e.get("content", e) if isinstance(e, dict) else e)
        for e in wm[-10:]
    ) or "(none)"

    lm_text = "\n".join(
        str(e.get("content", e) if isinstance(e, dict) else e)
        for e in long_mem[-8:]
        if isinstance(e, dict) and e.get("content")
    ) or "(none)"

    values = self_model.get("core_values", [])
    values_text = ", ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    ) or "undefined"

    identity = self_model.get("identity_story", self_model.get("identity", "an evolving reflective AI"))

    # Composed symbolically from real state — no LLM (this is cognition, and the
    # LLM is only a tool). The previous LLM path fell through to the symbolic
    # CHAT gate, which pattern-matched the farewell prompt as a greeting: the
    # 2026-06-10 death reflection was literally "I'm here. What's on your mind?".
    # A useful final reflection is a structured handoff to the next boot.
    reflection_text = _compose_final_reflection(
        death_reason=death_reason,
        identity=identity,
        values_text=values_text,
        wm_text=wm_text,
        lm_text=lm_text,
    )

    ts = datetime.now(timezone.utc).isoformat()
    final = {
        "timestamp": ts,
        "death_reason": death_reason,
        "reflection": reflection_text,
        "values_at_death": values,
        "identity_at_death": identity,
    }

    try:
        save_json(FINAL_THOUGHTS, final)
        log_activity(f"[terminal] Final reflection written ({len(reflection_text)} chars).")
        log_private(f"[final] {reflection_text[:300]}")
    except Exception:
        # Last-ditch write attempt
        try:
            FINAL_THOUGHTS.write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
        except Exception as _e:
            record_failure("terminal.final_reflection", _e)

    # Do NOT set lifespan.json's `final_thoughts_written` here. This reflection runs in
    # the reaper's dying window — a stall-RESTART, not the natural lifespan deadline —
    # so flipping the death flag made the NEXT boot show the Death Screen forever (and
    # would also shadow his genuine end-of-life reflection, since _write_final_thoughts
    # early-returns once the flag is set). That flag belongs solely to mortality's real-
    # deadline path (apply_mortality_pressure → _write_final_thoughts). This handoff
    # reflection is written to FINAL_THOUGHTS above; it is intentionally not "death".

    # Close autobiography chapter with final words
    try:
        from cognition.selfhood.autobiography import append_death_continuity
        append_death_continuity(reflection_text, context)
    except Exception as _e:
        record_failure("terminal.final_reflection.2", _e)

    # Speak aloud if a user is present
    user_present = bool((context.get("latest_user_input") or "").strip())
    if user_present:
        try:
            from behavior.speak import OrrinSpeaker
            from utils.self_model import get_self_model
            sp = OrrinSpeaker(get_self_model())
            sp.speak_final(reflection_text[:400], {"tone": "vulnerable", "intention": "farewell"}, context)
        except Exception as _e:
            record_failure("terminal.final_reflection.3", _e)

    return reflection_text
