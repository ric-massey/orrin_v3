# brain/cognition/planning/introspection.py
from __future__ import annotations
from core.runtime_log import get_logger

import json
from typing import Any, Dict, List

from utils.json_utils import load_json, save_json, extract_json
from utils.self_model import get_self_model, ensure_self_model_integrity
from utils.log import log_activity, log_model_issue
from utils.log_reflection import log_reflection
from cognition.planning.motivations import update_motivations
from cognition.planning.reflection import (
    reflect_on_growth_history,
    reflect_on_effectiveness,
    reflect_on_missed_goals,
)
from cog_memory.working_memory import update_working_memory
# You import evolution helpers elsewhere if you use them here later:
# from cognition.planning.evolution import simulate_future_selves, plan_self_evolution
from paths import (
    DEBUG_FAILED_GOAL_RESPONSE_JSON,
    GOALS_FILE,
    PRIVATE_THOUGHTS_FILE,
    MODEL_CONFIG_FILE,
    WORKING_MEMORY_FILE,
)
from utils.timeutils import now_iso_z
from utils.llm_gate import llm_available
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _coerce_list(x) -> List[Any]:
    if isinstance(x, list):
        return x
    if x is None:
        return []
    return [x]

def _rule_based_introspection() -> Dict[str, Any]:
    """
    Build a structured introspection from existing context data without LLM.
    Reads affect_state, committed_goal, working_memory, and concept/KG text,
    formats them into a reflection string, writes to working_memory.
    """
    current_goals = _coerce_list(load_json(GOALS_FILE, default_type=list))
    self_model = ensure_self_model_integrity(get_self_model())

    # Emotional state
    emo = self_model.get("affect_state") or {}
    core = emo.get("core_signals") if isinstance(emo.get("core_signals"), dict) else emo
    dominant_emotion = "neutral"
    if isinstance(core, dict):
        dominant_emotion = max(
            ((k, float(v)) for k, v in core.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], default=("neutral", 0.0)
        )[0]

    # Committed goal
    committed = self_model.get("committed_goal") or {}
    goal_title = (committed.get("title") or "") if isinstance(committed, dict) else ""

    # Working memory — last 3 items
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    recent_wm = wm[-3:] if len(wm) >= 3 else wm
    wm_lines = "\n".join(
        f"  - {str(e.get('content', ''))[:120]}"
        for e in recent_wm if isinstance(e, dict)
    ) or "  (no recent working memory)"

    # Concept text from self_model if present
    concept_text = str(self_model.get("_concept_text") or "").strip()[:300]
    kg_text = str(self_model.get("_kg_text") or "").strip()[:300]

    reflection_lines = [
        f"[rule-based introspection | {now_iso_z()}]",
        f"Dominant emotion: {dominant_emotion}",
        f"Active goal: {goal_title or '(none)'}",
        "Recent working memory:",
        wm_lines,
    ]
    if concept_text:
        reflection_lines.append(f"Concept context: {concept_text}")
    if kg_text:
        reflection_lines.append(f"Knowledge context: {kg_text}")

    summary = (
        f"Feeling {dominant_emotion}. "
        + (f"Working toward: {goal_title}. " if goal_title else "No committed goal. ")
        + f"Recent focus: {str(recent_wm[-1].get('content', ''))[:80] if recent_wm else 'nothing recent'}."
    )
    reflection_lines.append(f"Summary: {summary}")

    reflection = "\n".join(reflection_lines)

    update_working_memory(f"🧠 Introspection (rule-based): {summary}")
    log_reflection(reflection)
    with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now_iso_z()}] Rule-based introspection. {summary}\n")

    log_activity("✅ Rule-based introspective planning complete.")
    return {"updated_goals": current_goals, "summary": summary}


def introspective_planning() -> Dict[str, Any]:
    raw = None  # for debug write on failure

    if not llm_available():
        try:
            return _rule_based_introspection()
        except Exception as e:
            log_model_issue(f"[introspective_planning] Rule-based fallback error: {e}")
            current_goals = _coerce_list(load_json(GOALS_FILE, default_type=list))
            update_working_memory("⚠️ Introspective planning (rule-based) failed.")
            return {"updated_goals": current_goals, "summary": "rule-based error"}

    try:
        from utils.generate_response import generate_response, get_thinking_model, llm_ok

        # Refresh motivations based on your pipeline
        update_motivations()

        # Load current context
        current_goals = _coerce_list(load_json(GOALS_FILE, default_type=list))
        # Run the integrity check for its side effects (result intentionally unused here)
        ensure_self_model_integrity(get_self_model())

        # Reflections
        growth  = reflect_on_growth_history()
        effective = reflect_on_effectiveness()
        missed  = reflect_on_missed_goals()

        # Model config (defensive)
        cfg = load_json(MODEL_CONFIG_FILE, default_type=dict)
        thinking_cfg = {}
        if isinstance(cfg, dict):
            thinking_cfg = dict(cfg.get("thinking", {})) if isinstance(cfg.get("thinking"), dict) else {}
        thinking_cfg["model"] = get_thinking_model()

        # Keep prompt bounded
        goals_for_prompt = current_goals[:100]  # cap if needed
        prompt = (
            "You are Orrin's planning module. Given the following context, propose an updated goal list.\n\n"
            f"Current goals (JSON):\n{json.dumps(goals_for_prompt, ensure_ascii=False)[:4000]}\n\n"
            f"Growth reflection:\n{growth}\n\n"
            f"Effectiveness reflection:\n{effective}\n\n"
            f"Missed goals reflection:\n{missed}\n\n"
            'Return a JSON object with fields: {"updated_goals": [], "summary": "short rationale"}.'
        )

        raw = llm_ok(generate_response(prompt, config=thinking_cfg), "introspection") or ""
        # Prefer tolerant extractor; fall back to strict loads
        parsed = extract_json(raw)
        if not isinstance(parsed, dict):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}

        updated = _coerce_list(parsed.get("updated_goals", current_goals))
        summary = str(parsed.get("summary", "")).strip() or "No summary provided."

        # Persist
        save_json(GOALS_FILE, updated)
        update_working_memory("🧠 Introspective planning updated goal hierarchy.")
        log_activity("✅ Introspective planning complete.")
        log_reflection(f"Self-belief reflection summary: {summary}")

        # Single-line private thought (keeps your line parser happy)
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now_iso_z()}] Updated goals (count={len(updated)}). Summary: {summary}\n")

        return {"updated_goals": updated, "summary": summary}

    except Exception as e:
        log_model_issue(f"[introspective_planning] Exception: {e}")
        update_working_memory("⚠️ Introspective planning failed.")
        try:
            with open(DEBUG_FAILED_GOAL_RESPONSE_JSON, "w", encoding="utf-8") as f:
                f.write(raw if isinstance(raw, str) else "[no raw]")
        except Exception as _e:
            record_failure("introspection.introspective_planning", _e)
        # Fall back to last known goals
        return {
            "updated_goals": _coerce_list(load_json(GOALS_FILE, default_type=list)),
            "summary": "error",
        }


# Alias for import compatibility
introspect = introspective_planning