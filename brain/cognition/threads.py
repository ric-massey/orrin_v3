# brain/cognition/threads.py
# Thread-of-attention management: sustained inquiries Orrin is working through.
# Threads live in threads.json, are referenced in self_model["active_threads"],
# and inject thread_continue signals when they go stale.
from __future__ import annotations
from core.runtime_log import get_logger

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_private
from cog_memory.long_memory import update_long_memory
from paths import THREADS_FILE, LONG_MEMORY_FILE
from utils.llm_gate import llm_callable_by
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# A thread is stale after this many cycles without engagement
_STALE_CYCLES = 20
# A thread is dead (archived) after this many cycles without engagement
_DEAD_CYCLES = 150


def _get_cycle(context: Dict[str, Any]) -> int:
    """Extract integer cycle count from context, handling both int and dict shapes."""
    raw = context.get("cycle_count") or {}
    return int(raw.get("count", 0) if isinstance(raw, dict) else (raw or 0))


def load_threads() -> List[Dict[str, Any]]:
    return load_json(THREADS_FILE, default_type=list) or []


def save_threads(threads: List[Dict[str, Any]]) -> None:
    save_json(THREADS_FILE, threads)


def create_thread(
    title: str,
    initial_thought: str = "",
    context: Dict[str, Any] = None,
    source: str = "reflection",
) -> Dict[str, Any]:
    """Create a new thread of attention and save it."""
    context = context or {}
    thread = {
        "id": str(uuid.uuid4())[:12],
        "title": title,
        "created_ts": datetime.now(timezone.utc).isoformat(),
        "last_touched_ts": datetime.now(timezone.utc).isoformat(),
        "last_touched_cycle": _get_cycle(context),
        "state_of_thinking": initial_thought or f"Opening inquiry: {title}",
        "related_memory_ids": [],
        "source": source,
        "status": "alive",
        "touch_count": 1,
    }
    threads = load_threads()
    threads.append(thread)
    save_threads(threads)
    log_activity(f"[thread] Created: {title!r} (source={source})")
    return thread


def get_stale_threads(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return threads that haven't been touched in >= _STALE_CYCLES cycles."""
    threads = load_threads()
    current_cycle = _get_cycle(context)
    stale = []
    for t in threads:
        if t.get("status") != "alive":
            continue
        raw_last = t.get("last_touched_cycle", 0) or 0
        last = int(raw_last.get("count", 0) if isinstance(raw_last, dict) else raw_last)
        gap = current_cycle - last
        if gap >= _STALE_CYCLES:
            stale.append(t)
    return stale


def _symbolic_continue(title: str, current_state: str, related_texts: List[str]) -> str:
    """Advance the inquiry from what has actually accumulated about it: surface the
    newest related memory not yet reflected in the thread's state. Returns "" when
    nothing new has landed (a genuinely dormant thread — no fabricated progress)."""
    cur_low = (current_state or "").lower()
    dev = ""
    for t in reversed(related_texts or []):            # newest first
        s = (t or "").strip()
        sl = s.lower()
        if len(s) < 20 or "[chunk" in sl or "{" in s or '":' in s:
            continue
        if s[:50].lower() in cur_low:                  # already folded into the state
            continue
        dev = s[:180]
        break
    if not dev:
        return ""

    base = (current_state or "").strip()
    if len(base) > 160:
        end = base.find(". ")
        base = base[: end + 1] if 20 < end < 160 else base[:160]
    t = title.strip()
    if base:
        return f"{base} Since then, this landed: \"{dev}\". I'm still working out how it fits {t}."
    return f"On {t}: \"{dev}\" is the latest that bears on it, and I haven't resolved where it leads."


def continue_thread(thread: Dict[str, Any], context: Dict[str, Any] = None) -> str:
    """
    Run a reflection pass on the thread: load related memories, update state-of-thinking.
    Returns the new state-of-thinking paragraph.
    """
    context = context or {}
    title = thread.get("title", "unknown")
    current_state = thread.get("state_of_thinking", "")

    # Pull related memories from long memory by id or recent entries
    long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
    related_ids = set(thread.get("related_memory_ids", []))
    related_texts = []
    for e in long_mem[-30:]:
        if isinstance(e, dict) and (e.get("id") in related_ids or title.lower() in str(e.get("content", "")).lower()):
            related_texts.append(str(e.get("content", ""))[:200])
    related_block = "\n".join(f"- {t}" for t in related_texts[:5]) or "(no related memories yet)"

    prompt = (
        f"You are Orrin, an introspective AI with a sustained inquiry.\n\n"
        f"Thread: \"{title}\"\n\n"
        f"Where you left off:\n{current_state}\n\n"
        f"Related memories:\n{related_block}\n\n"
        f"Continue this inquiry. Where are you with it now? Has anything shifted? "
        f"What is the most pressing question or insight at this moment? "
        f"Write 2-4 sentences as Orrin — this is your internal working document on this thread."
    )

    new_state = current_state
    if llm_callable_by("threads"):
        try:
            from utils.generate_response import generate_response, llm_ok
            new_state = (llm_ok(generate_response(prompt), "threads") or "").strip() or current_state
        except Exception as e:
            log_activity(f"[thread] LLM unavailable for thread continuation: {e}")
    else:
        # Symbolic: advance the inquiry from what has actually accumulated in
        # memory about it — surface the newest related development not yet folded
        # into the thread's state. When nothing new has landed, the thread is
        # genuinely dormant: leave it unchanged rather than fabricate progress.
        new_state = _symbolic_continue(title, current_state, related_texts) or current_state
        log_activity(f"[thread] Symbolic continuation for '{title[:40]}'.")

    # Update thread
    threads = load_threads()
    now_ts = datetime.now(timezone.utc).isoformat()
    cycle = _get_cycle(context)
    for t in threads:
        if t.get("id") == thread.get("id"):
            t["state_of_thinking"] = new_state
            t["last_touched_ts"] = now_ts
            t["last_touched_cycle"] = cycle
            t["touch_count"] = int(t.get("touch_count", 0)) + 1
            break
    save_threads(threads)
    log_private(f"[thread:{title[:40]}] {new_state[:200]}")
    return new_state


def archive_dead_threads(context: Dict[str, Any]) -> int:
    """Move threads that have gone without engagement into long memory as 'abandoned'."""
    threads = load_threads()
    current_cycle = _get_cycle(context)
    archived = 0
    for t in threads:
        if t.get("status") != "alive":
            continue
        raw_last = t.get("last_touched_cycle", 0) or 0
        last = int(raw_last.get("count", 0) if isinstance(raw_last, dict) else raw_last)
        if current_cycle - last >= _DEAD_CYCLES:
            t["status"] = "archived"
            update_long_memory(
                f"[abandoned thread] \"{t['title']}\": {t.get('state_of_thinking','')[:300]}",
                emotion="negative_valence",
                event_type="thread_archived",
                importance=2,
                context=context,
            )
            archived += 1
    if archived:
        save_threads(threads)
        log_activity(f"[thread] Archived {archived} abandoned thread(s) to long memory.")
    return archived


def resolve_thread(thread_id: str, conclusion: str, context: Dict[str, Any]) -> None:
    """Explicitly conclude a thread — write conclusion to long memory."""
    threads = load_threads()
    for t in threads:
        if t.get("id") == thread_id and t.get("status") == "alive":
            t["status"] = "resolved"
            t["conclusion"] = conclusion
            update_long_memory(
                f"[resolved thread] \"{t['title']}\": {conclusion}",
                emotion="confidence",
                event_type="thread_resolved",
                importance=4,
                context=context,
            )
            log_activity(f"[thread] Resolved: {t['title']!r}")
            break
    save_threads(threads)


def handle_thread_continue(context: Dict[str, Any]) -> str:
    """
    Cognition function: called when thread_continue signal fires.
    Looks up the pending thread from context and runs a continuation pass.
    """
    thread_id = context.get("_pending_thread_id")
    if not thread_id:
        # No pending thread — pick the most stale one
        stale = get_stale_threads(context)
        if not stale:
            return "No stale threads to continue."
        thread_id = stale[0]["id"]

    threads = load_threads()
    thread = next((t for t in threads if t.get("id") == thread_id), None)
    if not thread:
        return f"Thread {thread_id} not found."

    context.pop("_pending_thread_id", None)
    new_state = continue_thread(thread, context)
    return new_state


def inject_thread_signals(context: Dict[str, Any]) -> None:
    """
    Called each cycle: if any threads are stale, inject a thread_continue signal
    so the signal_router can schedule attention on them.
    """
    stale = get_stale_threads(context)
    if not stale:
        return
    # Inject signal for the most important stale thread
    thread = stale[0]
    try:
        from utils.signal_utils import create_signal
        sig = create_signal(
            source="thread_of_attention",
            content=f"thread_continue: {thread['title']}",
            signal_strength=0.6,
            tags=["thread", "sustained_inquiry", "continue"],
        )
        context.setdefault("raw_signals", []).append(sig)
        context["_pending_thread_id"] = thread["id"]
    except Exception as _e:
        record_failure("threads.inject_thread_signals", _e)


# Alias for import compatibility
weave_threads = handle_thread_continue
