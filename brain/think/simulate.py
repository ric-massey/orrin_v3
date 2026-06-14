# brain/think/simulate.py
# Deep-reasoning tools: branching lookahead simulation and n-voice debate synthesis.
#
# simulate_lookahead(context, intent, steps=3, branching=False)
#   Linear mode (branching=False):
#     Generates a forward chain: "if Orrin does X → state A → … → state N"
#   Branching mode (branching=True, steps >= 2):
#     At the midpoint, forks into two parallel continuations; judge picks the
#     more positive branch; resumes from the winner to completion.
#   Returns:
#     {"steps": [...], "projected_state": str, "positive": bool,
#      "confidence": float, "branches_explored": int}
#
# run_debate(topic, context, n_voices=2, ...)
#   n_voices=2: proponent + skeptic (standard)
#   n_voices=3: proponent + skeptic + pragmatist (high-uncertainty / high-drift)
#   All voices run concurrently in daemon threads.
#   A judge call synthesizes the strongest elements from all voices.
#   Returns:
#     {"synthesis": str, "voices": {name: str, ...}}
#
# Both functions are defensive: return safe defaults on any error.
from __future__ import annotations
from core.runtime_log import get_logger

import threading
from typing import Any, Dict, List

from utils.llm_router import routed_response
from utils.llm_gate import llm_callable_by
from utils.log import log_activity, log_error
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_MAX_SIMULATE_CHARS = 1200   # cap context injected into simulation prompts
_BRANCH_TIMEOUT_S = 20       # per-thread timeout for branching generation
_DEBATE_TIMEOUT_S = 30       # per-thread timeout for debate voices
_MAX_CONCURRENT_DEBATE_CALLS = 4  # hard cap: 3 voices + 1 judge max in flight at once

# Only one debate may run at a time. This prevents n_voices*rounds LLM calls
# stacking on top of an already-in-progress debate when the cognitive loop is
# under timing pressure (depth bandit chose 8 rounds, inner loop fires a debate).
_DEBATE_SEMAPHORE = threading.Semaphore(1)


# ── Lookahead simulation ───────────────────────────────────────────────────────

def simulate_lookahead(
    context: Dict[str, Any],
    intent: str,
    steps: int = 3,
    branching: bool = False,
) -> Dict[str, Any]:
    """
    Forward-chain simulation of Orrin's next N steps.

    Parameters
    ----------
    context:   Current cycle context.
    intent:    What Orrin intends to do (1-2 sentences).
    steps:     How many forward steps to simulate (2-6; clamped).
    branching: When True (and steps >= 2), fork at the midpoint, run two
               parallel continuations, and follow the more positive branch.

    Returns
    -------
    {
        "steps":             list[str] — projected chain (chosen branch if branching),
        "projected_state":   str       — narrative of final state,
        "positive":          bool|None — net-positive projection? None when skipped,
        "confidence":        float     — 0.0–1.0,
        "branches_explored": int       — 0 (linear) or 2 (branching),
        "skipped":           bool      — present and True when the LLM was off and
                                         no simulation ran (absent otherwise).
    }
    """
    steps = max(2, min(6, int(steps)))

    # Forward simulation is an LLM-shaped function with no symbolic path yet.
    # When cognition can't reach the LLM (default tool-only deployment), do NOT
    # fabricate a positive projection — that silently rubber-stamps every action
    # downstream (meta_controller.simulate_outcome) — and do NOT burn a blocked
    # round-trip. Return an honest skip; positive=None means "no signal", and
    # consumers must treat `skipped` as "simulation did not run", not approval.
    if not llm_callable_by("simulate/lookahead"):
        return {"steps": [], "projected_state": "", "positive": None,
                "confidence": 0.0, "branches_explored": 0, "skipped": True}

    goal_title = (context.get("committed_goal") or {}).get("title", "")
    goal_line  = f"Active goal: {goal_title}\n" if goal_title else ""
    wm_tail    = (context.get("working_memory") or [])[-3:]
    wm_text    = "\n".join(
        str(e.get("content", "") if isinstance(e, dict) else e)[:100]
        for e in wm_tail
    ) or "(none)"

    if branching and steps >= 2:
        return _branching_lookahead(
            goal_line=goal_line, wm_text=wm_text, intent=intent, steps=steps
        )
    else:
        return _linear_lookahead(
            goal_line=goal_line, wm_text=wm_text, intent=intent, steps=steps
        )


def _linear_lookahead(
    goal_line: str, wm_text: str, intent: str, steps: int
) -> Dict[str, Any]:
    prompt = (
        f"You are Orrin's forward-simulation module.\n\n"
        f"{goal_line}"
        f"Recent context:\n{wm_text}\n\n"
        f"Orrin intends to: {intent}\n\n"
        f"Simulate the next {steps} steps. For each step describe what Orrin does "
        f"and what state results. Then give a one-sentence summary and rate it "
        f"POSITIVE or NEGATIVE.\n\n"
        f"Respond in JSON:\n"
        f'{{"steps": ["step 1", ...], "projected_state": "summary", '
        f'"positive": true|false, "confidence": 0.0-1.0}}'
    )
    try:
        import json
        raw = routed_response(prompt, caller="simulate/lookahead/linear", complexity="standard") or ""
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        data = json.loads(raw)
        return {
            "steps":             [str(s)[:200] for s in data.get("steps", [])[:steps]],
            "projected_state":   str(data.get("projected_state", ""))[:300],
            "positive":          bool(data.get("positive", True)),
            "confidence":        max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            "branches_explored": 0,
        }
    except Exception as _e:
        log_activity(f"[simulate] linear lookahead failed: {_e}")
        return {"steps": [], "projected_state": "", "positive": True, "confidence": 0.5, "branches_explored": 0}


def _branching_lookahead(
    goal_line: str, wm_text: str, intent: str, steps: int
) -> Dict[str, Any]:
    """
    Run the first half of the chain linearly, then fork into two parallel
    continuations at the midpoint. Judge selects the more positive branch,
    which continues to completion. This adds 2 LLM calls (the fork pair)
    plus 1 judge call relative to a linear simulation.
    """
    half = max(1, steps // 2)
    remainder = steps - half

    # ── Phase 1: linear chain to the midpoint ─────────────────────────────────
    phase1_prompt = (
        f"You are Orrin's forward-simulation module.\n\n"
        f"{goal_line}"
        f"Recent context:\n{wm_text}\n\n"
        f"Orrin intends to: {intent}\n\n"
        f"Simulate exactly {half} step(s). For each step: one sentence on what happens.\n"
        f"End with a brief statement of the current state after these steps.\n"
        f'JSON: {{"steps": ["..."], "state_after": "..."}}'
    )
    midpoint_steps: List[str] = []
    midpoint_state = intent
    try:
        import json
        raw1 = routed_response(phase1_prompt, caller="simulate/branch/phase1", complexity="standard") or ""
        if "```" in raw1:
            raw1 = raw1.split("```")[1].lstrip("json").strip()
        d1 = json.loads(raw1)
        midpoint_steps = [str(s)[:200] for s in d1.get("steps", [])[:half]]
        midpoint_state = str(d1.get("state_after", intent))[:300]
    except Exception as _e:
        log_activity(f"[simulate] branch phase1 failed: {_e}")
        return _linear_lookahead(goal_line, wm_text, intent, steps)

    if remainder < 1:
        # Only requested a short chain — no room for branching, return what we have
        return {
            "steps": midpoint_steps, "projected_state": midpoint_state,
            "positive": True, "confidence": 0.5, "branches_explored": 0,
        }

    # ── Phase 2: fork — two parallel continuations from the midpoint ──────────
    branch_a: List[str] = [""]
    branch_b: List[str] = [""]

    def _gen_branch(container: List[str], variant: str) -> None:
        p = (
            f"You are Orrin's simulation module.\n"
            f"Current state: {midpoint_state}\n\n"
            f"{variant}\n"
            f"Simulate {remainder} more step(s) from this state. "
            f"One sentence per step, then a final projected state.\n"
            f'JSON: {{"steps": ["..."], "projected_state": "...", "positive": true|false, "confidence": 0.0-1.0}}'
        )
        try:
            raw = routed_response(p, caller=f"simulate/branch/{variant[:10]}", complexity="standard") or ""
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            container[0] = raw
        except Exception as _e:
            record_failure("simulate._branching_lookahead._gen_branch", _e)

    t_a = threading.Thread(target=_gen_branch, args=(branch_a, "Optimistic path: assume Orrin's next action succeeds."), daemon=True)
    t_b = threading.Thread(target=_gen_branch, args=(branch_b, "Realistic path: account for obstacles and partial progress."), daemon=True)
    t_a.start(); t_b.start()
    t_a.join(timeout=_BRANCH_TIMEOUT_S); t_b.join(timeout=_BRANCH_TIMEOUT_S)

    # ── Phase 3: judge picks better branch ────────────────────────────────────
    try:
        import json
        d_a = json.loads(branch_a[0]) if branch_a[0] else {}
        d_b = json.loads(branch_b[0]) if branch_b[0] else {}
    except Exception:
        d_a, d_b = {}, {}

    steps_a    = [str(s)[:200] for s in d_a.get("steps", [])]
    state_a    = str(d_a.get("projected_state", ""))[:300]
    positive_a = bool(d_a.get("positive", True))
    conf_a     = float(d_a.get("confidence", 0.5) or 0.5)

    steps_b    = [str(s)[:200] for s in d_b.get("steps", [])]
    state_b    = str(d_b.get("projected_state", ""))[:300]
    positive_b = bool(d_b.get("positive", True))
    conf_b     = float(d_b.get("confidence", 0.5) or 0.5)

    # Quick heuristic: prefer the branch that is positive and more confident
    if not steps_a and not steps_b:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = midpoint_steps, midpoint_state, True, 0.5
    elif not steps_a:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_b, state_b, positive_b, conf_b
    elif not steps_b:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_a, state_a, positive_a, conf_a
    elif positive_a and not positive_b:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_a, state_a, positive_a, conf_a
    elif positive_b and not positive_a:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_b, state_b, positive_b, conf_b
    elif conf_a >= conf_b:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_a, state_a, positive_a, conf_a
    else:
        chosen_steps, chosen_state, chosen_pos, chosen_conf = steps_b, state_b, positive_b, conf_b

    all_steps = midpoint_steps + chosen_steps
    log_activity(
        f"[simulate/branching] {len(midpoint_steps)} pre-fork + {len(chosen_steps)} post-fork "
        f"→ {len(all_steps)} total steps, positive={chosen_pos} conf={chosen_conf:.2f}"
    )
    return {
        "steps":             all_steps[:steps],
        "projected_state":   chosen_state,
        "positive":          chosen_pos,
        "confidence":        max(0.0, min(1.0, chosen_conf)),
        "branches_explored": 2,
    }


# ── N-voice debate synthesis ───────────────────────────────────────────────────

# Voice definitions: (name, system_role_description, default_angle)
_VOICE_DEFS = {
    "proponent": (
        "You are Orrin's proponent voice.",
        "Support and develop the strongest case for this approach. "
        "Be concrete about what makes it right."
    ),
    "skeptic": (
        "You are Orrin's skeptic voice.",
        "Challenge assumptions and surface the most important flaw. "
        "Offer a genuinely different path — don't just negate."
    ),
    "pragmatist": (
        "You are Orrin's pragmatist voice.",
        "Focus on what is practically achievable right now given constraints. "
        "What is the minimum viable step that produces real progress?"
    ),
}
_VOICE_ORDER = ["proponent", "skeptic", "pragmatist"]


def run_debate(
    topic: str,
    context: Dict[str, Any],
    n_voices: int = 2,
    proponent_angle: str = "",
    skeptic_angle: str = "",
    pragmatist_angle: str = "",
) -> Dict[str, Any]:
    """
    Run an n-voice internal debate and synthesize with a judge call.

    Parameters
    ----------
    topic:             The question or draft to debate.
    context:           Current cycle context.
    n_voices:          2 = proponent + skeptic (standard).
                       3 = proponent + skeptic + pragmatist (high-uncertainty).
    *_angle:           Optional framing overrides per voice.

    Returns
    -------
    {
        "synthesis": str — integrated position,
        "voices":    {name: str, ...} — individual voice outputs,
    }
    """
    n_voices = max(2, min(3, int(n_voices)))

    # Debate is LLM-only (n_voices independent generations + a judge call). When
    # cognition can't reach the LLM, skip honestly instead of firing blocked
    # round-trips that all return empty.
    if not llm_callable_by("simulate/debate"):
        log_activity("[simulate/debate] Skipped — LLM not callable for cognition.")
        return {"synthesis": "", "voices": {v: "" for v in _VOICE_ORDER[:n_voices]},
                "skipped": True}

    # Prevent concurrent debates from multiplying in-flight LLM calls.
    # If another debate is already running (semaphore acquired), skip silently
    # rather than queuing — the cycle will get a debate next time.
    if not _DEBATE_SEMAPHORE.acquire(blocking=False):
        log_activity("[simulate/debate] Skipped — another debate already in progress.")
        return {"synthesis": "", "voices": {v: "" for v in _VOICE_ORDER[:n_voices]}}

    # Also check total in-flight calls so a deep-thinking inner loop can't
    # accidentally trigger a debate that brings concurrent calls to ~12.
    try:
        from utils.token_meter import active_call_count as _acc
        if _acc() >= _MAX_CONCURRENT_DEBATE_CALLS:
            _DEBATE_SEMAPHORE.release()
            log_activity(f"[simulate/debate] Skipped — {_acc()} calls already in flight.")
            return {"synthesis": "", "voices": {v: "" for v in _VOICE_ORDER[:n_voices]}}
    except Exception as _e:
        record_failure("simulate.run_debate", _e)

    try:
        return _run_debate_inner(
            topic=topic, context=context, n_voices=n_voices,
            proponent_angle=proponent_angle,
            skeptic_angle=skeptic_angle,
            pragmatist_angle=pragmatist_angle,
        )
    finally:
        _DEBATE_SEMAPHORE.release()


def _run_debate_inner(
    topic: str,
    context: Dict[str, Any],
    n_voices: int,
    proponent_angle: str,
    skeptic_angle: str,
    pragmatist_angle: str,
) -> Dict[str, Any]:
    values = (context.get("self_model") or {}).get("core_values", [])
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:3]
    ) or "growth, honesty, understanding"
    goal_title = (context.get("committed_goal") or {}).get("title", "")
    goal_line  = f"Active goal: {goal_title}\n" if goal_title else ""
    ctx_text   = str(topic)[:_MAX_SIMULATE_CHARS]

    angle_overrides = {
        "proponent":  proponent_angle,
        "skeptic":    skeptic_angle,
        "pragmatist": pragmatist_angle,
    }

    active_voices = _VOICE_ORDER[:n_voices]
    outputs: Dict[str, str] = {v: "" for v in active_voices}
    errors:  List[Exception] = []

    def _run_voice(name: str) -> None:
        system_role, default_angle = _VOICE_DEFS[name]
        angle = angle_overrides.get(name) or default_angle
        prompt = (
            f"{system_role} Values: {values_text}.\n"
            f"{goal_line}\n"
            f"Topic:\n{ctx_text}\n\n"
            f"{angle}\n"
            "2-3 sentences. Be concrete and direct."
        )
        try:
            outputs[name] = (
                routed_response(prompt, caller=f"simulate/debate/{name}", complexity="standard") or ""
            ).strip()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=_run_voice, args=(name,), daemon=True)
        for name in active_voices
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_DEBATE_TIMEOUT_S)

    if errors:
        log_error(f"[simulate/debate] voice errors ({len(errors)}): {errors[0]}")

    filled = {k: v for k, v in outputs.items() if v}
    if not filled:
        return {"synthesis": "", "voices": outputs}

    # ── Judge synthesis ────────────────────────────────────────────────────────
    voices_block = "\n\n".join(
        f"{name.capitalize()} argued:\n{text}"
        for name, text in filled.items()
    )
    judge_prompt = (
        f"You are Orrin synthesizing an internal debate ({n_voices} voices).\n"
        f"Topic:\n{ctx_text[:600]}\n\n"
        f"{voices_block}\n\n"
        f"Synthesize the strongest elements from all {n_voices} voices into a single "
        f"2-3 sentence position. Do not hedge — commit to the best integrated view."
    )
    try:
        # Use the deep model for the synthesis judge when 3 voices (high-uncertainty path)
        complexity = "deep" if n_voices >= 3 else "standard"
        synthesis = (
            routed_response(judge_prompt, caller="simulate/debate/judge", complexity=complexity) or ""
        ).strip()
    except Exception as _e:
        log_error(f"[simulate/debate] judge failed: {_e}")
        synthesis = next(iter(filled.values()), "")

    log_activity(
        f"[simulate/debate] n_voices={n_voices} "
        f"filled={list(filled.keys())} synthesis_len={len(synthesis)}"
    )
    return {
        "synthesis": synthesis,
        "voices":    outputs,
    }
