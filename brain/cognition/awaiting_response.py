# brain/cognition/awaiting_response.py
# Manages the awaiting_response state set by speak.py when Orrin asks a question.
#
# Three functions called from the loop:
#   check_for_answer(context)   — when user input arrives, bind it to the question's thread
#   decay_awaiting(context)     — each cycle, age the unanswered question; resolve after N cycles
#   inject_await_signal(context) — signal_router boost: bump priority of user_input when awaiting
from __future__ import annotations
from core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Dict, Any

from utils.log import log_activity, log_private
from cog_memory.long_memory import update_long_memory
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_DECAY_CYCLES    = 8    # mark unanswered after this many cycles without reply
_DECAY_COUNTER_KEY = "_await_cycles_elapsed"


def check_for_answer(context: Dict[str, Any]) -> bool:
    """
    Call when user input arrives. If awaiting_response is set, bind the answer
    to the question's thread and clear the state.
    Returns True if an answer was bound.
    """
    ar = context.get("awaiting_response")
    if not isinstance(ar, dict) or ar.get("status") != "awaiting":
        return False

    user_input = (context.get("latest_user_input") or "").strip()
    if not user_input:
        return False

    question  = ar.get("question", "")
    thread_id = ar.get("thread_id")

    # Bind answer to thread if one exists
    if thread_id:
        try:
            from cognition.threads import load_threads, save_threads
            threads = load_threads()
            for t in threads:
                if t.get("id") == thread_id:
                    prev = t.get("state_of_thinking", "")
                    t["state_of_thinking"] = (
                        f"{prev}\n\n[Q: {question[:120]}]\n[A: {user_input[:200]}]"
                    ).strip()
                    t["last_touched_ts"] = datetime.now(timezone.utc).isoformat()
                    raw_cc = context.get("cycle_count") or {}
                    t["last_touched_cycle"] = int(raw_cc.get("count", 0) if isinstance(raw_cc, dict) else (raw_cc or 0))
                    break
            save_threads(threads)
        except Exception as e:
            log_activity(f"[awaiting] thread bind failed: {e}")

    update_long_memory(
        f"[question_answered] I asked: '{question[:100]}' — they replied: '{user_input[:150]}'",
        emotion="exploration_drive",
        event_type="question_answered",
        importance=3,
        context=context,
    )
    log_private(f"[awaiting] answered: Q={question[:60]!r} A={user_input[:60]!r}")

    # Inject immediately into working_memory so this cycle's cognition can act on the answer
    try:
        from cog_memory.working_memory import update_working_memory
        update_working_memory(
            f"[answer_received] I asked: '{question[:100]}' — they said: '{user_input[:150]}'"
        )
    except Exception as _e:
        log_activity(f"[awaiting] WM inject failed: {_e}")

    context["awaiting_response"] = {"status": "answered", "question": question}
    return True


def decay_awaiting(context: Dict[str, Any]) -> None:
    """
    Call each cycle. If awaiting_response has been pending too long, resolve
    as 'unanswered' and write a memory entry.
    """
    ar = context.get("awaiting_response")
    if not isinstance(ar, dict) or ar.get("status") != "awaiting":
        return

    elapsed = int(ar.get(_DECAY_COUNTER_KEY, 0)) + 1
    ar[_DECAY_COUNTER_KEY] = elapsed

    if elapsed >= _DECAY_CYCLES:
        question = ar.get("question", "")
        ar["status"] = "unanswered"
        context["awaiting_response"] = ar

        update_long_memory(
            f"[unanswered_question] I asked '{question[:120]}' — no reply came.",
            emotion="negative_valence",
            event_type="unanswered_question",
            importance=2,
            context=context,
        )
        log_activity(f"[awaiting] question went unanswered after {elapsed} cycles: {question[:60]!r}")


def inject_await_signal(context: Dict[str, Any]) -> None:
    """
    If awaiting_response is set, boost any incoming user_input signal so
    the signal_router prioritises it as the answer.
    """
    ar = context.get("awaiting_response")
    if not isinstance(ar, dict) or ar.get("status") != "awaiting":
        return

    user_input = (context.get("latest_user_input") or "").strip()
    if not user_input:
        return

    # Inject a high-priority signal tagging this as an answer
    try:
        from utils.signal_utils import create_signal
        sig = create_signal(
            source="awaiting_response",
            content=f"answer_received: {user_input[:120]}",
            signal_strength=0.85,
            tags=["answer", "user_input", "awaiting_response"],
        )
        context.setdefault("raw_signals", []).append(sig)
    except Exception as _e:
        record_failure("awaiting_response.inject_await_signal", _e)
