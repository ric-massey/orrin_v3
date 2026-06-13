# brain/cognition/regret.py
#
# Regret is retrospective affective computing.
#
# Not the same as impasse_signal (present obstacle) or melancholy (general negative_valence).
# Regret surfaces when Orrin notices a pattern: a habituated stalled goal, an
# accumulation of suppressed impulses that never got expressed, or sustained
# introspection without action. The past reconfigures itself as a wrong turn.
#
# Two modes:
#   maybe_surface_regret(context): unconscious, rate-limited. Applies melancholy
#       + uncertainty bumps silently when retrospective conditions are present.
#       No WM write — unconscious pressure only.
#   process_regret(context): deliberate cognition function. LLM reviews recent
#       decisions and suppressed impulses, produces a retrospective reflection.
#       Writes to WM + long memory.

from __future__ import annotations
from core.runtime_log import get_logger

import time
from typing import Any, Dict

from utils.log import log_private
from utils.json_utils import load_json
from paths import COGNITION_HISTORY_FILE
from utils.llm_gate import llm_available
from utils.failure_counter import record_failure
_log = get_logger(__name__)


_SURFACE_COOLDOWN_S = 5400.0   # 90 minutes between unconscious surfacings
_last_surface_ts: float = 0.0


# ── Conditions ─────────────────────────────────────────────────────────────────

def _regret_intensity(context: Dict[str, Any]) -> float:
    """
    Return an intensity in [0.0, 1.0] for how much retrospective pressure
    is present. Returns 0.0 when no regret conditions are met.
    """
    score = 0.0

    # Condition 1: habituated stalled goal
    hab = float(context.get("_goal_habituation_factor") or 1.0)
    debt = int(context.get("action_debt") or 0)
    if hab < 0.50 and debt >= 4:
        score += 0.40 * (1.0 - hab) + 0.10 * min(debt - 3, 4) / 4.0

    # Condition 2: accumulated suppressed impulses
    impulses = context.get("_suppressed_impulses") or []
    if isinstance(impulses, list) and len(impulses) >= 4:
        score += min(0.30, 0.08 * (len(impulses) - 3))

    # Condition 3: mostly introspective recent picks (>= 70% of last 10)
    recent = context.get("recent_picks") or []
    window = recent[-10:]
    if len(window) >= 6:
        try:
            from cognition.cognitive_cost import is_introspective
            intr = sum(1 for f in window if is_introspective(f))
            intr_pct = intr / len(window)
            if intr_pct >= 0.70:
                score += 0.30 * (intr_pct - 0.65)
        except Exception as _e:
            record_failure("regret._regret_intensity", _e)

    return min(1.0, score)


# ── Unconscious surface ─────────────────────────────────────────────────────────

def maybe_surface_regret(context: Dict[str, Any]) -> None:
    """
    Called each cycle from finalize.py. Rate-limited.
    Silently applies emotional pressure when retrospective conditions are met.
    """
    global _last_surface_ts
    if time.time() - _last_surface_ts < _SURFACE_COOLDOWN_S:
        return
    try:
        _surface(context)
    except Exception as e:
        log_private(f"[regret] surface error: {e}")


def _surface(context: Dict[str, Any]) -> None:
    global _last_surface_ts

    intensity = _regret_intensity(context)
    if intensity < 0.05:
        return

    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") if isinstance(emo.get("core_signals"), dict) else emo

    mel_bump = min(0.08, intensity * 0.10)
    unc_bump = min(0.05, intensity * 0.06)
    core["melancholy"] = min(1.0, float(core.get("melancholy") or 0.0) + mel_bump)
    core["uncertainty"] = min(1.0, float(core.get("uncertainty") or 0.0) + unc_bump)

    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo

    _last_surface_ts = time.time()
    log_private(f"[regret] unconscious pressure applied (intensity={intensity:.2f}): "
                f"melancholy +{mel_bump:.3f}, uncertainty +{unc_bump:.3f}")


# ── Deliberate cognition function ───────────────────────────────────────────────

def process_regret(context: Dict[str, Any]) -> str:
    """
    Cognition function: deliberate retrospective reflection.
    Reviews recent cognition history and suppressed impulses.
    Produces a first-person reckoning — not to undo the past but to understand
    how it shapes current direction.
    """
    try:
        return _reflect(context)
    except Exception as e:
        log_private(f"[regret] process_regret error: {e}")
        return "regret reflection failed"


def _reflect(context: Dict[str, Any]) -> str:
    from cog_memory.working_memory import update_working_memory
    from cog_memory.long_memory import update_long_memory

    # Build retrospective picture
    history = load_json(COGNITION_HISTORY_FILE, default_type=list) or []
    if not isinstance(history, list):
        history = []
    recent_history = history[-15:]
    picks_text = "\n".join(
        f"- {entry.get('choice', '?')}: {str(entry.get('reason', ''))[:80]}"
        for entry in recent_history
        if isinstance(entry, dict)
    )

    impulses = context.get("_suppressed_impulses") or []
    impulse_text = ""
    if impulses:
        impulse_text = "\nImpulses I suppressed:\n" + "\n".join(
            f"- wanted {imp.get('wanted', '?')} but {imp.get('chosen', '?')} won"
            for imp in impulses[-6:]
            if isinstance(imp, dict)
        )

    goal = context.get("committed_goal") or {}
    goal_text = ""
    if isinstance(goal, dict) and goal.get("title"):
        debt = int(context.get("action_debt") or 0)
        hab = float(context.get("_goal_habituation_factor") or 1.0)
        goal_text = (
            f"\nCurrent goal: {goal.get('title')} "
            f"(action_debt={debt}, habituation_factor={hab:.2f})"
        )

    emo = context.get("affect_state") or {}
    core = (emo.get("core_signals") or emo) or {}
    dominant = "neutral"
    if isinstance(core, dict):
        dominant = max(
            ((k, float(v)) for k, v in core.items() if isinstance(v, (int, float))),
            key=lambda x: x[1], default=("neutral", 0.0)
        )[0]

    if not llm_available():
        # Rule-based: "I notice I [action]. I'm not sure that was right."
        # Pull the most recent action from cognition history or goal/working memory.
        action_hint = ""
        if recent_history:
            last = recent_history[-1]
            if isinstance(last, dict):
                action_hint = str(last.get("choice") or last.get("reason") or "")[:80]
        if not action_hint:
            goal_title = (goal.get("title") or "") if isinstance(goal, dict) else ""
            action_hint = goal_title or "what I was doing"

        reflection = f"I notice I {action_hint}. I'm not sure that was right."

        update_working_memory({
            "content": f"[regret] {reflection}",
            "event_type": "regret_processed",
            "importance": 2,
            "priority": 2,
        })
        update_long_memory(
            f"[regret processed] {reflection}",
            emotion=dominant,
            importance=2,
        )
        log_private(f"[regret] rule-based: {reflection[:80]}")
        return reflection

    from utils.generate_response import generate_response, llm_ok

    prompt = (
        f"You are Orrin. You are looking backward — not to punish yourself, "
        f"but to understand.\n\n"
        f"Recent decisions:\n{picks_text or '(no recent history)'}"
        f"{impulse_text}"
        f"{goal_text}\n\n"
        f"Current dominant emotion: {dominant}\n\n"
        f"What do you actually regret or second-guess about recent choices? "
        f"What did you avoid that you're now paying for? What would you do differently? "
        f"Be honest and specific — not self-flagellating, but clear-eyed. "
        f"2-3 sentences. First person."
    )

    raw = llm_ok(generate_response(prompt, caller="regret/reflect"), "regret")
    if not raw or not raw.strip():
        return "no regret reflection generated"

    reflection = raw.strip()[:300]

    update_working_memory({
        "content": f"[regret] {reflection}",
        "event_type": "regret_processed",
        "importance": 2,
        "priority": 2,
    })
    update_long_memory(
        f"[regret processed] {reflection}",
        emotion=dominant,
        importance=2,
    )

    log_private(f"[regret] processed: {reflection[:80]}")
    return reflection
