# brain/cognition/seek_novelty.py
# Triggered by stagnation_signal_seek signal — Orrin acts on stagnation_signal with genuine exploration_drive,
# not just a decay reset. Logs what it chose to the stagnation_signal log.
from __future__ import annotations
from core.runtime_log import get_logger

import json
import random
from datetime import datetime, timezone
from typing import Dict, Any

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from cog_memory.long_memory import update_long_memory
from paths import LONG_MEMORY_FILE, STAGNATION_SIGNAL_LOG, DATA_DIR
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_VOCAB_PATH = DATA_DIR / "vocabulary.json"
_SELF_TYPES = frozenset({
    "dream_insight",
    "refusal",
    "stagnation_signal_reflection",
    "stagnation_signal_question",
    "stagnation_signal_goal_review",
})


# Built-in fallback pools. vocabulary.json shipped without these sections, so
# every seek_novelty mode returned "" — which the no-novelty reward cap then
# floored at ~0.1, teaching the bandit that exploration is worthless
# (avg_reward 0.086 over the first 2.7k cycles). Symbolic, no LLM involved.
_DEFAULT_PHRASES = {
    "memory_revisit_phrases": [
        "Revisiting an old memory I never examined: {content}",
        "This sat unexamined until now — looking again: {content}",
        "First real look at an old trace: {content}",
    ],
    "goal_revisit_phrases": [
        "A dormant goal worth re-evaluating: {goal}",
        "I set this aside — does it still matter? {goal}",
        "Re-opening a stalled intention: {goal}",
    ],
    "question_seeds": [
        "What in my environment have I never actually inspected?",
        "Which of my beliefs has the least evidence behind it?",
        "What did I fail at most recently, and what exactly failed?",
        "What capability do I have that I've never once used?",
        "What changed in my files since yesterday that I haven't looked at?",
    ],
}


def _vocab_phrase(section: str, **fmt) -> str:
    """Pick a random phrase from the vocabulary database, formatting {placeholders} if given."""
    try:
        vocab = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
        pool = vocab.get(section) or _DEFAULT_PHRASES.get(section) or []
        if not pool:
            return ""
        phrase = random.choice(pool)
        if fmt:
            try:
                phrase = phrase.format(**fmt)
            except KeyError as _e:
                record_failure("seek_novelty._vocab_phrase", _e)
        return phrase
    except Exception:
        pool = _DEFAULT_PHRASES.get(section) or []
        if not pool:
            return ""
        phrase = random.choice(pool)
        if fmt:
            try:
                phrase = phrase.format(**fmt)
            except KeyError:
                pass
        return phrase


def seek_novelty(context: Dict[str, Any] = None) -> str:
    """
    Called when stagnation_signal drives action. Picks the most self-revealing available mode:
    1. Underexplored memory (low recall) — reflect on it
    2. Dormant goal — re-evaluate it
    3. Self-generated question — pursue it
    4. Ask alive_brain for an exploration goal
    """
    context = context or {}
    from cognition.exploration_value import ReachOutcome

    mode = _pick_mode(context)
    result = ""

    if mode == "memory":
        result = _explore_old_memory(context)
        outcome = ReachOutcome(
            "memory", acted=False, is_external=False,
            created_memory=bool(result), text=str(result or ""),
        )
    elif mode == "dormant_goal":
        result = _reeval_dormant_goal(context)
        outcome = ReachOutcome(
            "dormant_goal", acted=False, is_external=False,
            created_memory=bool(result), text=str(result or ""),
        )
    elif mode == "question":
        result = _generate_question(context)
        outcome = ReachOutcome(
            "question", acted=False, is_external=False,
            created_memory=bool(result), text=str(result or ""),
        )
    else:
        result = _trigger_exploration_goal(context)
        outcome = context.get("_last_reach_outcome")
        if not isinstance(outcome, ReachOutcome):
            outcome = ReachOutcome(
                "world", acted=False, is_external=True, text=str(result or ""),
            )

    context["_last_reach_outcome"] = outcome
    _log_stagnation_signal_action(mode, result, context)
    return result


def _pick_mode(context: Dict[str, Any]) -> str:
    try:
        from cognition.exploration_value import curiosity_gap
        if curiosity_gap(context) >= 0.6:
            return "explore"
    except Exception:
        pass

    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    # Old memories with low recall are underexplored
    unexamined = [
        e for e in long_mem
        if isinstance(e, dict)
        and e.get("content")
        and int(e.get("recall_count", 0) or 0) == 0
        and e.get("event_type", "") not in _SELF_TYPES
    ]
    if unexamined:
        return "memory"

    # Dormant goals in context
    goals = context.get("working_memory") or []
    dormant = [
        g for g in goals
        if isinstance(g, dict)
        and g.get("event_type") in ("goal", "set_goal")
        and str(g.get("status", "")) in ("pending", "", "deferred")
    ]
    if dormant:
        return "dormant_goal"

    # Random tiebreak between question and exploration
    return random.choice(["question", "explore"])


def _explore_old_memory(context: Dict[str, Any]) -> str:
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    unexamined = [
        e for e in long_mem
        if isinstance(e, dict)
        and e.get("content")
        and int(e.get("recall_count", 0) or 0) == 0
        and e.get("event_type", "") not in _SELF_TYPES
    ]
    if not unexamined:
        return _generate_question(context)

    target = random.choice(unexamined[-20:])
    content = target.get("content", "")
    # Mark as recalled
    target["recall_count"] = int(target.get("recall_count") or 0) + 1
    try:
        save_json(LONG_MEMORY_FILE, long_mem)
    except Exception as _e:
        record_failure("seek_novelty._explore_old_memory", _e)

    reflection = _vocab_phrase("memory_revisit_phrases", content=content[:100])

    if reflection:
        recent_reflections = [
            str(e.get("content") or "").strip().lower()
            for e in long_mem[-40:]
            if isinstance(e, dict)
            and e.get("event_type") == "stagnation_signal_reflection"
        ]
        normalized = reflection.strip().lower()
        if any(
            normalized == prior
            or (normalized[:120] and normalized[:120] == prior[:120])
            for prior in recent_reflections
        ):
            return reflection
        update_long_memory(
            reflection, emotion="exploration_drive",
            event_type="stagnation_signal_reflection", importance=2, context=context,
        )
        log_private(f"[stagnation_signal:memory] {reflection[:200]}")
    return reflection


def _reeval_dormant_goal(context: Dict[str, Any]) -> str:
    goals = context.get("working_memory") or []
    dormant = [
        g for g in goals
        if isinstance(g, dict) and g.get("event_type") in ("goal", "set_goal")
        and str(g.get("status", "")) in ("pending", "", "deferred")
    ]
    if not dormant:
        return _generate_question(context)

    goal = random.choice(dormant)
    goal_name = goal.get("content") or goal.get("name") or "(unnamed goal)"
    reflection = _vocab_phrase("goal_revisit_phrases", goal=goal_name[:80])

    if reflection:
        update_long_memory(
            reflection, emotion="motivation",
            event_type="stagnation_signal_goal_review", importance=2, context=context,
        )
    return reflection


def _generate_question(context: Dict[str, Any]) -> str:
    question = _vocab_phrase("question_seeds")

    if question:
        update_long_memory(
            f"[self-question from stagnation_signal] {question}",
            emotion="exploration_drive", event_type="stagnation_signal_question",
            importance=3, context=context,
        )
        log_private(f"[stagnation_signal:question] {question}")
    return question


def _trigger_exploration_goal(context: Dict[str, Any]) -> str:
    # Try look_outward as the primary exploration path
    try:
        from cognition.perception.look_outward import look_outward
        result = look_outward(context)
        outcome = context.get("_last_reach_outcome")
        reached = bool(outcome and getattr(outcome, "acted", False)) if outcome else bool(
            result
            and not str(result).lstrip().startswith(("❌", "⚠️"))
            and "Couldn't form" not in str(result)
        )
        if reached:
            log_activity(f"[stagnation_signal] Exploration via look_outward: {result[:80]}")
            return result
    except Exception as _e:
        record_failure("seek_novelty._trigger_exploration_goal", _e)
    # Fallback: generate a question to pursue
    return _generate_question(context)


def _log_stagnation_signal_action(mode: str, result: str, context: Dict[str, Any]) -> None:
    try:
        existing = load_json(STAGNATION_SIGNAL_LOG, default_type=list) or []
        existing.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "action_summary": str(result)[:120],
            "cycle": (context.get("cycle_count") or {}).get("count", 0) if isinstance(context.get("cycle_count"), dict) else int(context.get("cycle_count") or 0),
        })
        save_json(STAGNATION_SIGNAL_LOG, existing[-200:])  # rolling 200-entry log
    except Exception as _e:
        record_failure("seek_novelty._log_stagnation_signal_action", _e)
    log_activity(f"[stagnation_signal] Acted on stagnation_signal via mode={mode}.")
