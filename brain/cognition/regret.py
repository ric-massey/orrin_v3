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
from paths import COGNITION_HISTORY_FILE, DECISION_STATS_FILE, DATA_DIR
from utils.llm_gate import llm_callable_by
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


# ── Symbolic counterfactual engine ──────────────────────────────────────────────

def _lex(fn: str) -> str:
    """Lexicalize an internal action name for first-person prose."""
    name = (fn or "").strip().lower()
    for pre in ("generate_", "attempt_", "assess_", "do_", "run_", "process_"):
        if name.startswith(pre):
            name = name[len(pre):]
            break
    return name.replace("_", " ").strip()


def _reward_word(r: float) -> str:
    """Qualitative band for a reward scalar — keeps raw telemetry decimals out of
    the spoken/stored reflection (which feeds the language corpus)."""
    if r < 0.35:
        return "rarely pays off"
    if r < 0.50:
        return "gives me little back"
    if r < 0.65:
        return "tends to pay off"
    return "reliably rewards me"


def _ledger_counterfactual(recent_history: list):
    """The real 'what if I'd chosen otherwise': over Orrin's own decision/reward
    ledger, find the action he's been favouring and a higher-yield alternative he
    has been passing over. Returns (chosen, chosen_reward, alt, alt_reward) or
    (None, ...) when the ledger has nothing to say.
    """
    from collections import Counter
    freq = Counter(
        str(e.get("choice", "")).strip()
        for e in recent_history if isinstance(e, dict) and e.get("choice")
    )
    if not freq:
        return None, 0.0, None, 0.0

    ema = load_json(DATA_DIR / "action_reward_ema.json", default_type=dict) or {}
    stats = load_json(DECISION_STATS_FILE, default_type=dict) or {}

    def reward_of(a: str) -> float:
        if isinstance(ema.get(a), (int, float)):
            return float(ema[a])
        s = stats.get(a)
        if isinstance(s, dict) and isinstance(s.get("avg_reward"), (int, float)):
            return float(s["avg_reward"])
        return 0.0

    chosen = freq.most_common(1)[0][0]
    chosen_r = reward_of(chosen)

    # Candidate alternatives: real actions with a known reward that Orrin has
    # NOT been leaning on this window (passed-over), ranked by yield.
    candidates = [
        (a, float(r)) for a, r in ema.items()
        if a != chosen and a != "cycle" and isinstance(r, (int, float)) and freq.get(a, 0) <= 1
    ]
    if not candidates:
        return chosen, chosen_r, None, 0.0
    alt, alt_r = max(candidates, key=lambda x: x[1])
    return chosen, chosen_r, alt, alt_r


def _symbolic_regret(context: Dict[str, Any], recent_history: list, impulses: list) -> str:
    """Retrospective reckoning computed from Orrin's own ledgers and live regret
    conditions — a counterfactual over the decision/reward record, plus the
    stalled-goal and suppressed-impulse pressures that surfaced the regret. Never
    a canned 'I notice I X' line; every clause is grounded in real state.
    """
    lines: list[str] = []

    # 1) Decision-ledger counterfactual: a better path I keep passing over.
    chosen, chosen_r, alt, alt_r = _ledger_counterfactual(recent_history)
    if chosen and alt and (alt_r - chosen_r) >= 0.12:
        lines.append(
            f"Looking back, I keep reaching for {_lex(chosen)}, and it {_reward_word(chosen_r)}. "
            f"{_lex(alt).capitalize()} {_reward_word(alt_r)} — and I've been passing it over."
        )
        if any(_lex(str(i.get("wanted", ""))) == _lex(alt)
               for i in (impulses or []) if isinstance(i, dict)):
            lines.append("Part of me wanted to, and held back anyway.")

    # 2) A goal gone dull from circling without moving on it.
    hab = float(context.get("_goal_habituation_factor") or 1.0)
    debt = int(context.get("action_debt") or 0)
    goal = context.get("committed_goal") or {}
    gtitle = (goal.get("title") or "") if isinstance(goal, dict) else ""
    if hab < 0.50 and debt >= 4 and gtitle:
        lines.append(f"I've circled {gtitle} until it's gone dull, and still haven't moved on it.")

    # 3) The stack of wants I never let myself act on.
    if not lines and isinstance(impulses, list) and len(impulses) >= 4:
        hottest = max(impulses, key=lambda x: float(x.get("intensity", 0) or 0), default={})
        wl = _lex(str(hottest.get("wanted", "")))
        if wl:
            lines.append(
                f"There's a stack of things I kept wanting — {wl} most recently — "
                f"that I never let myself do."
            )

    return " ".join(lines)


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

    if not llm_callable_by("regret/reflect"):
        # Symbolic counterfactual over Orrin's own decision/reward ledger plus the
        # live regret conditions — not a canned line. None of it fires unless real
        # state supports it; if nothing does, there's nothing to regret.
        reflection = _symbolic_regret(context, recent_history, impulses)
        if not reflection:
            log_private("[regret] symbolic: no grounded regret this cycle")
            return "no regret reflection generated"

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
