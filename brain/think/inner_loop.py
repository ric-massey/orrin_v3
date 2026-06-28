# brain/think/inner_loop.py
# Iteration controller: draft → (critique ×3) → revise → [escalate] rounds.
#
# Architecture
# ────────────
# 1.  ThinkingDepthBandit (depth_bandit.py) chooses max_rounds in [4, 8].
# 2.  Each round:
#       a. Draft       — context-aware prompt with scratchpad history
#       b. Meta-decide — meta_controller.decide() → "think_more"|"act"|"output"|"defer"
#       c. Critique ×3 — if think_more:
#            i.  reflect_on_internal_agents  (primary)
#            ii. contradiction_detector      (secondary)
#            iii.value_alignment_checker     (tertiary)
#       d. Revise      — synthesise all critiques into improved draft
# 3.  Escalation (round ≥ 4 AND confidence < 0.65):
#       - Switch to main model (no fast-model routing)
#       - Tree-of-Thought: generate 3 alternative drafts in parallel threads
#       - Judge selects best, which becomes the revised draft for this round
# 4.  Sub-agent debate (optional, triggered by meta_controller or caller):
#       - simulate.run_debate(topic, context) generates proponent + skeptic
#       - Synthesis injected as a revision
# 5.  Time budget: INNER_LOOP_MAX_S = 50s.  Emergency defer if exceeded.
# 6.  At end: report final confidence + rounds_used to depth_bandit.record_outcome().
#
# Returns:
#   {
#     "content":          str   — final draft / revision,
#     "rounds_used":      int,
#     "meta_decision":    str   — last meta_controller decision,
#     "critique_applied": bool,
#     "escalated":        bool,
#     "confidence":       float,
#   }
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
import time
from typing import Any, Dict, List, Optional

from brain.utils.llm_router import routed_response, get_deep_model
from brain.utils.llm_gate import llm_callable_by
from brain.utils.log import log_activity, log_error
from brain.think.scratchpad import scratchpad_append, scratchpad_latest
from brain.think.meta_controller import decide as meta_decide
from brain.think.thought_stream import emit_thought
from brain.utils.failure_counter import record_failure
# Draft critique stage, extracted to inner_loop_critique.py (Phase 4.5C).
from brain.think.inner_loop_critique import _full_critique  # noqa: F401
_log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
INNER_LOOP_MAX_S:    float = 50.0    # hard wall-clock budget per call
_ESCALATION_ROUND:   int   = 4       # escalate if confidence < threshold at this round
_ESCALATION_CONF:    float = 0.65    # confidence threshold for escalation
_DEEP_DEBATE_CONF:   float = 0.45    # below this after escalation → 3-voice debate
_EMERGENCY_CONF:     float = 0.10    # below this after max_rounds → emit "defer"
_REFLECT_BUDGET_S:   float = 35.0    # skip self-reflection if elapsed exceeds this
_TOT_BRANCHES:       int   = 3       # Tree-of-Thought parallel alternatives
_DEFAULT_ROUNDS:     int   = 4       # used when bandit not yet initialized

_UNCERTAINTY_SIGNALS = frozenset({
    "maybe", "might", "unclear", "not sure", "unsure", "perhaps",
    "could be", "i think", "possibly", "uncertain", "hard to say",
    "i'm not sure", "i am not", "difficult to say", "i don't know",
    "depends on", "it varies", "not certain",
})


# ── Confidence ────────────────────────────────────────────────────────────────

def _draft_confidence(draft: str) -> float:
    """0.0=very uncertain, 1.0=very confident based on uncertainty signal density."""
    lower = draft.lower()
    hits = sum(1 for s in _UNCERTAINTY_SIGNALS if s in lower)
    # Two-token signals count more
    multi = sum(1 for s in _UNCERTAINTY_SIGNALS if " " in s and s in lower)
    return max(0.0, min(1.0, 1.0 - hits * 0.10 - multi * 0.05))


def _should_critique(draft: str, resource_deficit: float = 0.0) -> bool:
    # Lower the confidence threshold when fatigued — tired reasoning skips self-critique.
    # Returns True (do critique) when draft confidence is below the threshold.
    # At full resource_deficit the bar drops so critique is skipped more easily.
    threshold = 0.85 - resource_deficit * 0.10   # 0.85 at rest → 0.75 at full resource_deficit
    return _draft_confidence(draft) < threshold


# ── Draft prompt ──────────────────────────────────────────────────────────────

def _draft_prompt(
    topic: str,
    context_text: str,
    context: Dict[str, Any],
    round_num: int,
) -> str:
    prior_critique  = scratchpad_latest(context, "critique")  if round_num > 1 else ""
    prior_revision  = scratchpad_latest(context, "revision")  if round_num > 1 else ""

    try:
        from brain.control_signals.signal_summary import format_goal_state as _gfo
        goal_line = _gfo(context.get("committed_goal") or {})
        goal_line = (goal_line + "\n") if goal_line else ""
    except Exception:
        goal_title = (context.get("committed_goal") or {}).get("title", "")
        goal_line  = f"Active goal: {goal_title}\n" if goal_title else ""
    tensions     = context.get("active_tensions") or []
    tension_line = f"Unresolved tension: {tensions[0].get('title', '')}\n" if tensions else ""
    mem_pattern  = context.get("memory_pattern") or {}
    pattern_line = ""
    if mem_pattern.get("type"):
        pattern_line = (
            f"Memory pattern: {mem_pattern['count']} recent events involve "
            f"'{mem_pattern['type']}'\n"
        )

    felt_line = ""
    try:
        from brain.control_signals.signal_summary import describe_dominant_affect as _dfs
        _sense = _dfs(context.get("affect_state") or {})
        if _sense:
            felt_line = f"Right now I notice: {_sense}\n"
    except Exception as _e:
        record_failure("inner_loop._draft_prompt", _e)

    urge_lines = ""
    urges = context.get("motivational_urges") or []
    if urges:
        urge_lines = "Active drives: " + "; ".join(
            f"{u.get('type')} ({u.get('strength', 0):.2f})" for u in urges[:2]
        ) + "\n"

    blocks = [f"{goal_line}{tension_line}{pattern_line}{felt_line}{urge_lines}"
              f"Topic: {topic}\n\nContext:\n{context_text}"]
    if prior_critique:
        blocks.append(f"Previous critique:\n{prior_critique}")
    if prior_revision:
        blocks.append(f"Previous revision:\n{prior_revision}")

    round_prefix = f"Round {round_num} revision: " if round_num > 1 else ""
    body = "\n\n".join(b for b in blocks if b.strip())

    return (
        f"You are Orrin, an evolving autonomous AI.\n\n"
        f"{body}\n\n"
        f"{round_prefix}Think through this topic and produce your best current response. "
        f"Be concrete and specific. 2-4 sentences."
    )



def _revise_prompt(draft: str, critique: str, topic: str, context: Dict[str, Any]) -> str:
    goal_title = (context.get("committed_goal") or {}).get("title", "")
    goal_line  = f"Active goal: {goal_title}\n" if goal_title else ""
    return (
        f"You are Orrin, an evolving autonomous AI.\n\n"
        f"{goal_line}Topic: {topic}\n\n"
        f"Your draft:\n{draft}\n\n"
        f"Critique:\n{critique}\n\n"
        "Revise to address the critique. Keep what was right; fix what wasn't. "
        "2-4 sentences. No preamble — start the revision directly."
    )


# ── Tree-of-Thought branching ─────────────────────────────────────────────────

def _tot_branch(topic: str, context_text: str, context: Dict[str, Any]) -> str:
    """
    Generate _TOT_BRANCHES alternative drafts in parallel (different angles),
    then use a judge call to select the best.
    Returns the best draft, or "" on complete failure.
    """
    values = (context.get("self_model") or {}).get("core_values") or []
    values_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values[:3]
    ) or "growth, honesty, understanding"
    goal_title = (context.get("committed_goal") or {}).get("title", "")
    goal_line  = f"Active goal: {goal_title}\n" if goal_title else ""

    angles = [
        ("direct",       "Answer directly and concretely. Prioritise the single most important insight."),
        ("first_principles", f"Reason from first principles and Orrin's values ({values_text}). What would be truest?"),
        ("contrarian",   "Challenge the framing. What is being missed or assumed? Offer an unexpected but honest view."),
    ][:_TOT_BRANCHES]

    branches: List[str] = [""] * len(angles)
    errors: List[Exception] = []

    deep_model = get_deep_model()

    def _run_branch(idx: int, angle_desc: str) -> None:
        prompt = (
            f"You are Orrin, an evolving autonomous AI.\n"
            f"{goal_line}Topic: {topic}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Angle: {angle_desc}\n\n"
            "2-3 sentences. Be concrete."
        )
        try:
            # Branches use the standard model; only the judge uses deep
            result = (routed_response(prompt, f"inner_loop/tot/{idx}", complexity="standard") or "").strip()
            branches[idx] = result
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=_run_branch, args=(i, desc), daemon=True)
        for i, (_, desc) in enumerate(angles)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)

    valid = [(i, b) for i, b in enumerate(branches) if b]
    if not valid:
        log_error(f"[inner_loop/ToT] all branches failed: {errors}")
        return ""
    if len(valid) == 1:
        return valid[0][1]

    # Judge selection — deep model for authoritative pick
    options_block = "\n\n".join(f"Option {i+1}:\n{b}" for i, b in valid)
    judge_prompt = (
        f"You are judging {len(valid)} alternative responses to: {topic[:200]}\n\n"
        f"{options_block}\n\n"
        "Which option is most concrete, honest, and useful? "
        f"Reply with ONLY the option number (1–{len(valid)})."
    )
    try:
        choice_raw = (
            routed_response(judge_prompt, "inner_loop/tot/judge", model=deep_model) or "1"
        ).strip()
        choice = int("".join(c for c in choice_raw if c.isdigit()) or "1")
        choice = max(1, min(len(valid), choice)) - 1
        winner = valid[choice][1]
        log_activity(f"[inner_loop/ToT] judge (deep model) chose option {choice+1}")
        return winner
    except Exception as _e:
        record_failure("inner_loop.tot_judge", _e)
        return valid[0][1]


# ── Self-reflection on loop quality ──────────────────────────────────────────

def _reflect_on_loop_quality(
    rounds_used: int,
    critique_applied: bool,
    escalated: bool,
    content_snippet: str,
    topic: str,
) -> float:
    """
    Ask a fast LLM call to score how useful the multi-round reasoning was.
    Returns a quality score in [0.0, 1.0].

    This feeds the depth bandit so it learns whether additional rounds
    (and escalation) actually improved the output rather than just wasting time.
    """
    prompt = (
        f"You are Orrin's inner-loop quality assessor.\n\n"
        f"Topic: {topic[:150]}\n"
        f"Rounds used: {rounds_used}\n"
        f"Critique was applied: {critique_applied}\n"
        f"Escalated to deep model + ToT: {escalated}\n"
        f"Final output:\n{content_snippet}\n\n"
        "Was the multi-round reasoning genuinely valuable? "
        "Did additional rounds produce meaningful improvement, or was it repeated effort?\n"
        "Rate the quality of the thinking process from 0.0 (pure waste) to 1.0 "
        "(clearly improved the output). "
        "Reply with ONLY a decimal number, e.g. 0.75"
    )
    try:
        raw = (routed_response(prompt, "inner_loop/meta_reflect", complexity="simple") or "").strip()
        # Extract first float from response
        score_str = "".join(c for c in raw.split()[0] if c.isdigit() or c == ".")
        score = float(score_str)
        return max(0.0, min(1.0, score))
    except Exception as _e:
        record_failure("inner_loop._reflect_on_loop_quality", _e)
        return 0.5   # neutral fallback


# ── Main entry ────────────────────────────────────────────────────────────────

def run_inner_loop(
    topic: str,
    context_text: str,
    context: Dict[str, Any],
    max_rounds: Optional[int] = None,
    use_debate: bool = False,
) -> Dict[str, Any]:
    """
    Reasoning tool: think through a specific problem or topic.

    This is a tool Orrin uses for complex sub-problems — goal planning,
    decision evaluation, understanding something difficult. It is NOT the
    source of his speech. Its output goes to reasoning_conclusion in the
    CycleState, which the expression layer may draw from.

    The architecture (state_processor) determines what needs to be said.
    This determines what was worked out about a specific question.

    Returns
    -------
    {
        "content":          str   — reasoning conclusion (not speech),
        "rounds_used":      int,
        "meta_decision":    str,
        "critique_applied": bool,
        "escalated":        bool,
        "confidence":       float,
    }
    """
    cycle_start = time.time()

    # ── No LLM path? Deliberate symbolically (Fix D), else defer honestly (Fix E)
    # Every routed_response-driven step below needs the LLM tool. When it isn't
    # callable by inner_loop (default tool-only deployment), run the symbolic
    # System-2 path instead: draft from the symbolic stack, critique + revise with
    # symbolic critics, escalate by widening search. If that's disabled or fails,
    # fall back to Fix E's honest typed defer so nothing silently no-ops.
    if not llm_callable_by("inner_loop"):
        try:
            from brain.think.inner_loop_symbolic import (
                run_inner_loop_symbolic, symbolic_inner_loop_enabled,
            )
            if symbolic_inner_loop_enabled():
                return run_inner_loop_symbolic(topic, context_text, context, max_rounds=max_rounds)
        except Exception as _se:
            record_failure("inner_loop.run_inner_loop.symbolic_dispatch", _se)
        log_activity("[inner_loop] deferred: deliberation requires the llm tool "
                     "(symbolic mode unavailable)")
        return {
            "content": "",
            "rounds_used": 0,
            "meta_decision": "defer",
            "critique_applied": False,
            "escalated": False,
            "confidence": 0.0,
            "reason": "deliberation requires llm tool",
        }

    # ── Round count ────────────────────────────────────────────────────────────
    _caller_specified = max_rounds is not None
    if max_rounds is None:
        try:
            from brain.think.depth_bandit import choose_rounds as _cr
            max_rounds = _cr()
        except Exception:
            max_rounds = _DEFAULT_ROUNDS

    # ── Energy-aware round adjustment ──────────────────────────────────────────
    # Only modify rounds when the caller didn't specify (i.e. bandit-chosen).
    # think_module passes max_rounds=1 or 2 for quick brainstorming — those are
    # honoured exactly. Energy still sets debate/early-exit flags regardless.
    energy_state = str(context.get("energy_state") or "medium")
    action_bias  = float(context.get("action_vs_reflect_bias") or 0.5)
    rest_mode    = bool(context.get("_rest_mode"))
    if not _caller_specified:
        if energy_state == "high" or action_bias > 0.65:
            max_rounds = min(max_rounds, 3)
            use_debate = False
            log_activity(f"[inner_loop] energy=high → max_rounds capped at {max_rounds}")
        elif energy_state == "low" or rest_mode or action_bias < 0.35:
            max_rounds = max(max_rounds, 5)
            use_debate = True
            log_activity(f"[inner_loop] energy=low/rest → max_rounds floored at {max_rounds}, debate=True")

        # resource_deficit degrades reasoning capacity: cap rounds and raise critique threshold
        _emo = context.get("affect_state") or {}
        _resource_deficit = float((_emo.get("resource_deficit") or _emo.get("core_signals", {}).get("resource_deficit")) or 0.0)
        if _resource_deficit > 0.72:
            max_rounds = min(max_rounds, 2)
            use_debate = False
            log_activity(f"[inner_loop] high resource_deficit ({_resource_deficit:.2f}) → max_rounds capped at {max_rounds}")
        elif _resource_deficit > 0.48:
            max_rounds = min(max_rounds, 4)
            log_activity(f"[inner_loop] moderate resource_deficit ({_resource_deficit:.2f}) → max_rounds capped at {max_rounds}")
        context["_resource_deficit_level"] = _resource_deficit

    context["_max_rounds"] = max_rounds

    content:          str   = ""
    critique_applied: bool  = False
    escalated:        bool  = False
    meta_decision:    str   = "output"
    round_num:        int   = 0
    final_confidence: float = 0.5
    goal_title: str = (context.get("committed_goal") or {}).get("title", "")

    for round_num in range(1, max_rounds + 1):

        # ── Time budget guard ─────────────────────────────────────────────────
        if time.time() - cycle_start > INNER_LOOP_MAX_S:
            log_activity(f"[inner_loop] time budget exceeded at round {round_num} — emergency exit")
            meta_decision = "defer"
            if not content:
                content = scratchpad_latest(context, "revision") or scratchpad_latest(context, "draft") or ""
            break

        # ── Draft ─────────────────────────────────────────────────────────────
        draft_prompt = _draft_prompt(topic, context_text, context, round_num)
        draft = (routed_response(draft_prompt, f"inner_loop/draft/r{round_num}") or "").strip()
        if not draft:
            break

        scratchpad_append(context, "draft", draft, phase=f"inner_loop_r{round_num}_draft")
        final_confidence = _draft_confidence(draft)
        log_activity(f"[inner_loop] r={round_num} draft ({len(draft)}ch) conf={final_confidence:.2f}")
        emit_thought(
            "drafting", f"r{round_num}: {draft[:100]}",
            full_trace=draft, scratchpad_snippet=draft[:400],
            depth=round_num, goal=goal_title,
        )

        # ── Meta decision ─────────────────────────────────────────────────────
        meta_decision = meta_decide(context, round_num, max_rounds)
        log_activity(f"[inner_loop] r={round_num} meta={meta_decision}")

        if meta_decision in ("act", "output", "defer"):
            content = draft
            break

        # ── High-energy early exit: r=1 adequate confidence → act now ────────
        if round_num == 1 and (energy_state == "high" or action_bias > 0.65):
            if final_confidence > 0.38:
                meta_decision = "act" if context.get("committed_goal") else "output"
                content = draft
                log_activity(
                    f"[inner_loop] high-energy early exit r=1 "
                    f"conf={final_confidence:.2f} → {meta_decision}"
                )
                break

        # ── Escalation check (round ≥ _ESCALATION_ROUND, low confidence) ─────
        if round_num >= _ESCALATION_ROUND and final_confidence < _ESCALATION_CONF and not escalated:
            escalated = True
            log_activity(
                f"[inner_loop] escalating at r={round_num} "
                f"conf={final_confidence:.2f} < {_ESCALATION_CONF}"
            )
            emit_thought("escalating", f"r{round_num} conf={final_confidence:.2f} → ToT",
                         depth=round_num, goal=goal_title)

            tot_draft = _tot_branch(topic, context_text, context)
            if tot_draft:
                # Run one deep-model revision pass on the ToT winner
                deep_model = get_deep_model()
                rev_p = _revise_prompt(
                    tot_draft,
                    "Refine this for clarity, concreteness, and value alignment. "
                    "Keep what is right; strengthen what is weak.",
                    topic, context,
                )
                deep_revision = (
                    routed_response(rev_p, "inner_loop/tot/deep_revision", model=deep_model) or tot_draft
                ).strip()
                final_draft = deep_revision if deep_revision else tot_draft

                scratchpad_append(context, "revision", final_draft, phase=f"inner_loop_r{round_num}_tot")
                emit_thought("revising", f"ToT+deep: {final_draft[:80]}", full_trace=final_draft,
                             depth=round_num, goal=goal_title)
                critique_applied = True
                content = final_draft
                final_confidence = _draft_confidence(final_draft)
                log_activity(
                    f"[inner_loop] ToT+deep_revision conf={final_confidence:.2f} "
                    f"(deep model={deep_model})"
                )

                # If confidence is still very low after escalation → 3-voice debate
                if final_confidence < _DEEP_DEBATE_CONF and not use_debate:
                    log_activity(
                        f"[inner_loop] conf={final_confidence:.2f} < {_DEEP_DEBATE_CONF} "
                        f"after escalation → spawning 3-voice debate"
                    )
                    emit_thought("debating", "3-voice sub-agent debate triggered",
                                 depth=round_num, goal=goal_title)
                    try:
                        from brain.think.simulate import run_debate as _rd
                        debate_result = _rd(topic, context, n_voices=3)
                        synthesis = debate_result.get("synthesis", "")
                        if synthesis and len(synthesis) > 20:
                            scratchpad_append(context, "revision", synthesis,
                                              phase=f"inner_loop_r{round_num}_3voice_debate")
                            content = synthesis
                            final_confidence = _draft_confidence(synthesis)
                            log_activity(
                                f"[inner_loop] 3-voice debate synthesis applied "
                                f"conf={final_confidence:.2f}"
                            )
                    except Exception as _dbe:
                        log_error(f"[inner_loop] 3-voice debate failed: {_dbe}")

                # After escalation + debate, re-evaluate
                meta_decision = meta_decide(context, round_num, max_rounds)
                if meta_decision in ("act", "output", "defer"):
                    break
                draft = content  # continue with best result if more rounds

        # ── Critique + revise (only when think_more and uncertainty present) ──
        if not _should_critique(draft, resource_deficit=context.get("_resource_deficit_level", 0.0)):
            content = draft
            break

        critique, issue_count = _full_critique(draft, topic, context)

        if not critique or issue_count == 0:
            content = draft
            break

        scratchpad_append(context, "critique", critique, phase=f"inner_loop_r{round_num}_critique")
        emit_thought("critiquing", critique[:100], full_trace=critique,
                     depth=round_num, goal=goal_title)

        rev_prompt = _revise_prompt(draft, critique, topic, context)
        revision = (routed_response(rev_prompt, "inner_loop/revision",
                                    complexity="standard") or draft).strip()
        scratchpad_append(context, "revision", revision, phase=f"inner_loop_r{round_num}_revise")
        emit_thought("revising", revision[:100], full_trace=revision,
                     scratchpad_snippet=f"Critique: {critique[:150]}\n→ {revision[:200]}",
                     depth=round_num, goal=goal_title)
        critique_applied = True
        content = revision
        final_confidence = _draft_confidence(revision)
        log_activity(f"[inner_loop] r={round_num} critique+revise done conf={final_confidence:.2f}")

    # ── Self-reflection on loop quality ───────────────────────────────────────
    # Runs a fast LLM call to score "was multi-round thinking worth it?"
    # Skipped if we've already burned most of the time budget.
    elapsed_so_far = time.time() - cycle_start
    loop_quality: float = final_confidence   # default: use confidence if reflection skipped
    if elapsed_so_far < _REFLECT_BUDGET_S and round_num > 1:
        loop_quality = _reflect_on_loop_quality(
            rounds_used=round_num,
            critique_applied=critique_applied,
            escalated=escalated,
            content_snippet=content[:300],
            topic=topic,
        )
        log_activity(f"[inner_loop] meta-reflection quality={loop_quality:.2f}")

    # ── Optional debate enrichment ─────────────────────────────────────────────
    if use_debate and content:
        try:
            from brain.think.simulate import run_debate
            debate_result = run_debate(topic, context)
            synthesis = debate_result.get("synthesis", "")
            if synthesis and len(synthesis) > 20:
                scratchpad_append(context, "revision", synthesis, phase="inner_loop_debate_synth")
                content = synthesis
                critique_applied = True
                log_activity("[inner_loop] debate synthesis applied")
        except Exception as _de:
            log_error(f"[inner_loop] debate failed: {_de}")

    # ── Fallback ───────────────────────────────────────────────────────────────
    if not content:
        content = (scratchpad_latest(context, "revision")
                   or scratchpad_latest(context, "draft") or "")

    # ── Emergency defer on catastrophically low confidence ────────────────────
    if final_confidence < _EMERGENCY_CONF and meta_decision not in ("act",):
        log_activity(f"[inner_loop] emergency defer: conf={final_confidence:.2f} < {_EMERGENCY_CONF}")
        meta_decision = "defer"

    # ── Report to depth bandit ─────────────────────────────────────────────────
    elapsed = time.time() - cycle_start
    try:
        from brain.think.depth_bandit import record_outcome as _ro
        # Reward uses self-reflected quality score + efficiency bonus.
        # loop_quality comes from the LLM meta-reflection (or falls back to confidence).
        eff_bonus     = max(0.0, 1.0 - elapsed / INNER_LOOP_MAX_S) * 0.15
        bandit_reward = min(1.0, loop_quality + eff_bonus) * 2 - 1.0   # → [-1, 1]
        _ro(round_num, bandit_reward)
    except Exception as _e:
        record_failure("inner_loop.run_inner_loop", _e)

    log_activity(
        f"[inner_loop] done: rounds={round_num}/{max_rounds} "
        f"meta={meta_decision} conf={final_confidence:.2f} quality={loop_quality:.2f} "
        f"escalated={escalated} elapsed={elapsed:.1f}s"
    )

    return {
        "content":          content[:800],
        "rounds_used":      round_num,
        "meta_decision":    meta_decision,
        "critique_applied": critique_applied,
        "escalated":        escalated,
        "confidence":       round(final_confidence, 3),
        "loop_quality":     round(loop_quality, 3),
    }
