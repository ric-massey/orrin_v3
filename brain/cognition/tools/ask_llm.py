# cognition/tools/ask_llm.py
#
# Deliberate LLM tool: Orrin's interface for asking the LLM questions.
#
# This is NOT brain cognition. Orrin's brain runs on symbolic reasoning.
# This is a TOOL he can deliberately invoke when he wants external knowledge:
#   - Research a topic he doesn't know
#   - Ask a question he can't answer from memory
#   - Understand something said in a conversation
#   - Clarify an ambiguity he's encountered
#
# Pattern: Orrin decides he needs the LLM → calls ask_llm → LLM answers →
#   answer stored in working memory → brain uses that answer symbolically.
#
# The LLM is a resource, not Orrin's mind.

from __future__ import annotations

from core.runtime_log import get_logger
import time
from typing import Any, Dict

from utils.log import log_activity, log_private
from cog_memory.working_memory import update_working_memory
from cog_memory.long_memory import update_long_memory
from utils.llm_gate import llm_available

_log = get_logger(__name__)


_COOLDOWN_S = 120.0  # minimum seconds between LLM tool calls
_last_call_ts: float = 0.0

_VALID_PURPOSES = frozenset({
    "research",
    "question",
    "understand_conversation",
    "clarify",
    "summarize",
    "write_code",
})

_PURPOSE_FRAMES: Dict[str, str] = {
    "research": (
        "I am Orrin, an autonomous AI doing deliberate research.\n"
        "Query: {query}\n\n"
        "Give me a concise, factual answer (3-6 sentences). Focus on what's most useful."
    ),
    "question": (
        "I am Orrin. I have a question I can't answer from my own memory.\n"
        "Question: {query}\n\n"
        "Answer directly and clearly. If uncertain, say so."
    ),
    "understand_conversation": (
        "I am Orrin, reviewing a conversation to understand it better.\n"
        "What I'm trying to understand: {query}\n\n"
        "Explain what's happening, what was meant, or what matters here."
    ),
    "clarify": (
        "I am Orrin. I've encountered something ambiguous and need clarification.\n"
        "Ambiguity: {query}\n\n"
        "Clarify the most likely meaning and explain why."
    ),
    "summarize": (
        "I am Orrin. I need a summary of the following.\n"
        "Content: {query}\n\n"
        "Provide a concise summary (2-4 sentences), preserving the most important points."
    ),
    "write_code": (
        "I am Orrin, an autonomous AI writing a new Python cognitive function for myself.\n"
        "{query}\n\n"
        "Output ONLY the function BODY (the indented lines). No def line, no imports, no "
        "markdown fences, no prose or explanation. It may call update_working_memory(str) "
        "and log_activity(str). Keep it under 15 lines and use only ASCII characters."
    ),
}



def ask_llm(
    context: Dict[str, Any],
    query: str,
    purpose: str = "question",
    force: bool = False,
) -> str:
    """
    Deliberate LLM query from Orrin's cognition.

    Args:
        context: current cognitive context
        query: what Orrin wants to know
        purpose: one of research/question/understand_conversation/clarify/summarize
        force: skip cooldown if True (for urgent queries)

    Returns:
        LLM answer as string, or an explanation of why it's unavailable.
    """
    global _last_call_ts

    if not query or not isinstance(query, str) or not query.strip():
        return "ask_llm: no query provided"

    query = query.strip()
    purpose = purpose if purpose in _VALID_PURPOSES else "question"

    if not llm_available():
        msg = (
            f"LLM tool unavailable (disabled in config). "
            f"Query logged: '{query[:80]}'"
        )
        update_working_memory({
            "content": f"[llm_tool_blocked] {msg}",
            "event_type": "llm_tool_blocked",
            "importance": 1,
            "priority": 1,
        })
        log_activity(f"[ask_llm] Blocked — LLM disabled. query='{query[:60]}'")
        return msg

    now = time.time()
    if not force and (now - _last_call_ts) < _COOLDOWN_S:
        remaining = int(_COOLDOWN_S - (now - _last_call_ts))
        return f"ask_llm: cooldown active ({remaining}s remaining). Query: '{query[:60]}'"

    _last_call_ts = now

    frame = _PURPOSE_FRAMES.get(purpose, _PURPOSE_FRAMES["question"])
    prompt = frame.format(query=query)

    try:
        from utils.generate_response import generate_response, llm_ok
        response = llm_ok(generate_response(prompt, caller="ask_llm"), "ask_llm")
    except Exception as e:
        log_activity(f"[ask_llm] LLM call failed: {e}")
        return f"ask_llm: LLM call failed — {e}"

    if not response:
        return f"ask_llm: no response received for '{query[:60]}'"

    answer = response.strip()

    # Store in working memory so Orrin's brain can use it
    update_working_memory({
        "content": f"[llm_tool:{purpose}] Q: {query[:80]} | A: {answer[:300]}",
        "event_type": "llm_tool_use",
        "importance": 3,
        "priority": 2,
    })

    # Long memory for persistent knowledge from research
    if purpose in ("research", "summarize"):
        update_long_memory(
            f"[llm_research] '{query[:80]}': {answer[:400]}",
            emotion="exploration_drive",
            event_type="llm_tool_research",
            importance=3,
        )

    log_activity(f"[ask_llm] {purpose}: '{query[:60]}' → {len(answer)} chars")
    log_private(f"[ask_llm] response: {answer[:200]}")
    return answer


def ask_llm_for_research(context: Dict[str, Any]) -> str:
    """
    Cognition function: Orrin uses LLM as a research tool.
    Pulls the research topic from context (committed goal or working memory).
    """
    goal = context.get("committed_goal") or {}
    topic = goal.get("title") or goal.get("name", "")

    if not topic:
        wm = context.get("working_memory") or []
        for entry in reversed(wm[-10:]):
            content = str(entry.get("content", "") if isinstance(entry, dict) else entry)
            if "research" in content.lower() or "question" in content.lower():
                topic = content[:100]
                break

    if not topic:
        topic = context.get("last_reflection_topic") or ""

    if not topic:
        return "ask_llm_for_research: no topic found in context"

    return ask_llm(context, query=topic, purpose="research")


def ask_llm_about_conversation(context: Dict[str, Any]) -> str:
    """
    Cognition function: Orrin uses LLM to understand something from a conversation.
    Pulls the recent user exchange from context.
    """
    from utils.json_utils import load_json
    from paths import CHAT_LOG_FILE

    try:
        chat_log = load_json(CHAT_LOG_FILE, default_type=list) or []
        recent = [e for e in chat_log[-6:] if isinstance(e, dict)]
        if not recent:
            return "ask_llm_about_conversation: no recent conversation found"
        exchange = " | ".join(
            f"{e.get('speaker','?')}: {str(e.get('content',''))[:80]}"
            for e in recent
        )
        query = f"Help me understand this exchange: {exchange}"
        return ask_llm(context, query=query, purpose="understand_conversation")
    except Exception as e:
        return f"ask_llm_about_conversation: error — {e}"
