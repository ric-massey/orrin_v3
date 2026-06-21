# think/speech_generator.py
#
# Orchestrator — runs Stages 1-4 in sequence to produce a reply with no LLM.
#
# Usage (called from behavior/speech_pipeline.py):
#
#   from think.speech_generator import generate_speech
#   reply = generate_speech(user_input, inner, affect_state, context,
#                           comprehension=..., memories=...)
#
# Stages:
#   1. speech_comprehension.parse_input   — parse what the user said
#   2. speech_memory.retrieve_relevant    — find relevant memories
#   3. speech_planner.plan_response       — decide what kind of reply to give
#   4. speech_builder.build_reply         — fill templates with real content
#
# Stages 1 and 2 are skipped when the caller passes pre-computed results.
# speech_pipeline.py computes both before calling here so the work is never
# duplicated — intent classification and memory retrieval each happen once.
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Any, Dict, List, Optional

from brain.utils.log import log_activity, log_error
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def generate_speech(
    user_input:    str,
    inner:         str,
    affect_state:  Dict[str, Any],
    context:       Dict[str, Any],
    *,
    comprehension:  Optional[Dict[str, Any]] = None,
    memories:       Optional[List[Dict]]     = None,
    theory_of_mind: Optional[Dict[str, Any]] = None,
    register:       str                      = "neutral",
) -> str:
    """
    Full non-LLM speech pipeline.

    user_input   — raw text the user typed
    inner        — Orrin's inner-loop monologue from this cycle (may be "")
    affect_state — current affect dict (core_signals, resource_deficit, etc.)
    context      — full cycle context (committed_goal, working_memory, etc.)
    comprehension — pre-computed Stage 1 result (skip re-parsing if supplied)
    memories      — pre-computed Stage 2 result (skip re-retrieval if supplied)

    Returns a reply string.  Returns "" on failure so the caller can fall back.
    """
    try:
        # ── Stage 1: Comprehension ────────────────────────────────────────────
        if comprehension is None:
            from brain.think.speech_comprehension import parse_input
            comprehension = parse_input(user_input, context)
        log_activity(
            f"[speech] S1 intent={comprehension['intent']} "
            f"topics={comprehension['topics'][:3]}"
        )

        # ── Stage 2: Memory Retrieval ─────────────────────────────────────────
        if memories is None:
            from brain.think.speech_memory import retrieve_relevant
            memories = retrieve_relevant(
                comprehension["topics"], n=5, affect_state=affect_state
            )
        top_score = round(memories[0].get("_relevance", 0), 3) if memories else 0
        log_activity(f"[speech] S2 retrieved={len(memories)} top_score={top_score}")

        # ── Stage 3: Response Planning ────────────────────────────────────────
        from brain.think.speech_planner import plan_response
        goal = context.get("committed_goal") or {}
        plan = plan_response(
            comprehension, memories, inner, affect_state, goal,
            theory_of_mind=theory_of_mind,
            register=register,
        )
        log_activity(
            f"[speech] S3 type={plan['response_type']} "
            f"tone={plan['tone']} src={plan['source']}"
        )

        # ── Stage 4: Sentence Construction ────────────────────────────────────
        exemplars: list = []
        try:
            from brain.think.speech_log import get_exemplars
            exemplars = get_exemplars(
                topics    = comprehension["topics"],
                min_score = 0.40,
                n         = 12,
            )
            log_activity(
                f"[speech] S4 exemplars={len(exemplars)} "
                f"(construction path {'active' if len(exemplars) >= 4 else 'cold'})"
            )
        except Exception as _e:
            record_failure("speech_generator.generate_speech", _e)

        from brain.think.speech_builder import build_reply
        reply = build_reply(plan, comprehension, exemplars=exemplars)
        log_activity(f"[speech] S4 → {reply[:80]}")

        # ── Handoff: let his own native language organ speak, once it's ready ──
        # Gated on maturity + a symbolic coherence check (see voice.lm_draft). A
        # no-op until schooling makes the organ fluent; then he speaks in his own
        # learned voice, with the template reply as the safe fallback.
        try:
            from brain.cognition.language.voice import lm_draft
            own = lm_draft(context, plan, comprehension)
            if own:
                reply = own
        except Exception as _ve:
            record_failure("speech_generator.generate_speech.2", _ve)

        # Stash plan + comprehension on context so speak_text can log them
        context["_last_speech_plan"]          = plan
        context["_last_speech_comprehension"] = comprehension

        return reply

    except Exception as e:
        log_error(f"[speech_generator] pipeline failed: {e}")
        return ""
