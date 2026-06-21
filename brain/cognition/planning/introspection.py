# brain/cognition/planning/introspection.py
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
from typing import Any, Dict, List

from brain.utils.json_utils import load_json, save_json, extract_json
from brain.utils.self_model import get_self_model, ensure_self_model_integrity
from brain.utils.log import log_activity, log_model_issue
from brain.utils.log_reflection import log_reflection
from brain.cognition.planning.motivations import update_motivations
from brain.cognition.planning.reflection import (
    reflect_on_growth_history,
    reflect_on_effectiveness,
    reflect_on_missed_goals,
)
from brain.cog_memory.working_memory import update_working_memory
# You import evolution helpers elsewhere if you use them here later:
# from cognition.planning.evolution import simulate_future_selves, plan_self_evolution
from brain.paths import (
    DEBUG_FAILED_GOAL_RESPONSE_JSON,
    GOALS_FILE,
    PRIVATE_THOUGHTS_FILE,
    MODEL_CONFIG_FILE,
)
from brain.utils.timeutils import now_iso_z
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def _coerce_list(x) -> List[Any]:
    if isinstance(x, list):
        return x
    if x is None:
        return []
    return [x]

def _symbolic_self_summary() -> str:
    """A real self-assessment from the symbolic self-model — strong/weak knowledge
    domains and rule health — instead of a templated 'Feeling X, working toward Y'
    line. Returns '' when the model has nothing to say."""
    parts: List[str] = []
    try:
        from brain.symbolic.symbolic_self_model import get_symbolic_self_model
        model = get_symbolic_self_model()
        strong = [s for s in (model.get("strong_areas") or []) if s]
        weak   = [w for w in (model.get("weak_areas") or []) if w]
        health = model.get("rule_health") or {}
        if strong:
            parts.append(f"I'm on firmer ground in {', '.join(strong[:3])}")
        if weak:
            parts.append(f"shakier in {', '.join(weak[:3])}")
        mc = health.get("mean_confidence")
        if isinstance(mc, (int, float)):
            band = "low" if mc < 0.45 else "moderate" if mc < 0.70 else "solid"
            parts.append(f"my rules hold together at {band} confidence")
    except Exception as e:
        record_failure("introspection._symbolic_self_summary", e)
    return "; ".join(parts)


def _rule_based_introspection() -> Dict[str, Any]:
    """
    Symbolic introspective planning — no LLM, no templated mood report.

    Does two real things from current state:
      1. Goal maintenance (an actual update, not a no-op): drop terminal goals and
         flag goals whose last recorded event was a failed attempt for review.
      2. Self-assessment from the symbolic self-model (strong/weak domains, rule
         health), which replaces the old slot-filled 'Feeling X. Working toward Y.'
    """
    current_goals = _coerce_list(load_json(GOALS_FILE, default_type=list))

    # ── 1) Goal maintenance — a real, conservative update driven by goal state ──
    kept: List[Dict] = []
    pruned = 0
    flagged = 0
    for g in current_goals:
        if not isinstance(g, dict):
            kept.append(g)
            continue
        status = str(g.get("status", "")).lower()
        if status in ("completed", "abandoned"):
            pruned += 1
            continue
        hist = g.get("history") or []
        if isinstance(hist, list) and hist and isinstance(hist[-1], dict):
            if hist[-1].get("event") == "failed_attempt" and not g.get("needs_review"):
                g["needs_review"] = True
                flagged += 1
        kept.append(g)

    # ── 2) Self-assessment from the symbolic self-model ──
    sm = _symbolic_self_summary()

    goal_bits: List[str] = []
    if kept:
        goal_bits.append(f"{len(kept)} live goal" + ("s" if len(kept) != 1 else ""))
    if pruned:
        goal_bits.append(f"set down {pruned} finished or abandoned")
    if flagged:
        goal_bits.append(f"flagged {flagged} that keep stalling")

    pieces = ([sm] if sm else []) + goal_bits
    summary = ("Looking inward: " + "; ".join(pieces) + ".") if pieces else \
              "Looking inward: nothing is clearly pulling for change right now."

    # Persist the maintained goal list (the actual update).
    save_json(GOALS_FILE, kept)
    update_working_memory(f"🧠 Introspection (symbolic): {summary}")
    log_reflection(summary)
    with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now_iso_z()}] Symbolic introspection. {summary}\n")

    log_activity("✅ Symbolic introspective planning complete.")
    return {"updated_goals": kept, "summary": summary}


def introspective_planning() -> Dict[str, Any]:
    raw = None  # for debug write on failure

    if not llm_callable_by("introspection"):
        try:
            return _rule_based_introspection()
        except Exception as e:
            log_model_issue(f"[introspective_planning] Rule-based fallback error: {e}")
            current_goals = _coerce_list(load_json(GOALS_FILE, default_type=list))
            update_working_memory("⚠️ Introspective planning (rule-based) failed.")
            return {"updated_goals": current_goals, "summary": "rule-based error"}

    try:
        from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok

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