# brain/cognition/perception/look_outward.py
# Cognition function: Orrin reaches outward to the world with exploration_drive.
# Generates a search query from current state of mind (active threads,
# exploration_drive targets, unresolved questions), queues a web_search via
# tool_runner. The result arrives asynchronously and gets tagged
# kind="world_perception" source="outward" in long memory.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import re
from typing import Dict, Any

from brain.utils.log import log_activity, log_private
from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import THREADS_FILE, LONG_MEMORY_FILE
_log = get_logger(__name__)

def look_outward(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: generate a exploration_drive-driven web search and queue it
    through tool_runner. Returns the query that was queued.

    Rate is no longer governed by a wall-clock cooldown — select_function scores
    look_outward by its explore/exploit value (cognition.exploration_value), which
    self-suppresses the drive when reaches stop being informative and keeps it live
    when they aren't. See EXPLORE_EXPLOIT_VALUE_PLAN_2026-06-16.
    """
    import os
    from brain.cognition.exploration_value import ReachOutcome

    context = context or {}
    if not os.environ.get("SERPER_API_KEY"):
        # No SERPER key: reach the WORLD via the keyless Wikipedia/research path
        # (real new knowledge + honest reward), not an echo of our own files.
        # search_own_files is only the last-resort fallback. The reach still
        # habituates via reach_value, so an unconfigured outward drive can't dominate.
        log_private("[look_outward] No SERPER_API_KEY — reaching outward via Wikipedia/research.")
        _result = None
        _realized_fn = ""
        for _fn_name, _import in (
            ("wikipedia_search", "brain.cognition.wikipedia_search.wikipedia_search"),
            ("research_topic", "brain.cognition.web_research.research_topic"),
        ):
            try:
                _mod, _attr = _import.rsplit(".", 1)
                _fn = getattr(__import__(_mod, fromlist=[_attr]), _attr)
                _result = _fn(context)
                if _result and not str(_result).lower().startswith(("❌", "⚠️")):
                    _realized_fn = _fn_name
                    break
            except Exception as _e:
                log_private(f"[look_outward] {_fn_name} fallback failed: {_e}")
                _result = None
        if not _result:
            try:
                from brain.cognition.search_own_files import search_own_files
                _result = search_own_files(context)
                _realized_fn = "search_own_files"
            except Exception as _sof_e:
                log_private(f"[look_outward] search_own_files fallback failed: {_sof_e}")
                _result = "No web search configured — tried searching own files."
        # The realized inner action owns the single consummation event.
        _inner = context.get("_last_reach_outcome")
        if isinstance(_inner, ReachOutcome) and _inner.inner_fn == _realized_fn:
            _gain = _inner.info_gain
        else:
            try:
                from brain.cognition.exploration_value import record_reach_outcome
                _gain = record_reach_outcome("look_outward", str(_result), None, context)
            except Exception:
                _gain = 0.0
        _acted = bool(
            _result
            and not str(_result).lstrip().startswith(("❌", "⚠️"))
            and "Couldn't form" not in str(_result)
        )
        context["_last_reach_outcome"] = ReachOutcome(
            mode="world" if _realized_fn != "search_own_files" else "home",
            acted=_acted,
            is_external=_realized_fn != "search_own_files",
            info_gain=float(_gain),
            created_memory=False,
            satisfied_curiosity=_acted and float(_gain) > 0.0,
            inner_fn=_realized_fn,
            text=str(_result or ""),
        )
        return _result

    query = _form_query(context)
    if not query:
        text = "Couldn't form a query to look outward with."
        context["_last_reach_outcome"] = ReachOutcome(
            mode="world", acted=False, is_external=True, inner_fn="web_search", text=text,
        )
        return text

    # Queue through tool_runner — result arrives on next drain (~30s).
    # The ingest_handler is the full dotted Python path to ingest_outward_result;
    # drain_queue() will call it when the search result arrives so the result is
    # written to long memory as event_type="world_perception", not "tool_use".
    try:
        from brain.agency.tool_runner import request as _request
        _request(
            tool_name="web_search",
            reason=f"[look_outward] exploration_drive-driven: {query}",
            args={"query": query},
            origin="look_outward",
            intent="world_perception",
            ingest_handler="cognition.perception.look_outward.ingest_outward_result",
            context_kwargs={"query": query},
        )
        log_activity(f"[look_outward] Queued search: {query!r}")
    except Exception as e:
        log_activity(f"[look_outward] tool_runner queue failed: {e}")
        text = f"Wanted to search for '{query}' but tool_runner unavailable."
        context["_last_reach_outcome"] = ReachOutcome(
            mode="world", acted=False, is_external=True, inner_fn="web_search", text=text,
        )
        return text

    # Write the outward intent to long memory now (before the result arrives)
    # so the query itself is part of Orrin's record and queryable.
    update_long_memory(
        f"[world_perception] I reached outward with a question: {query}",
        emotion="exploration_drive",
        event_type="world_perception",
        importance=2,
        context=context,
        extra={"source": "outward", "query": query, "phase": "intent"},
    )

    log_private(f"[look_outward] query={query!r}")
    text = f"Searching: {query}"
    context["_last_reach_outcome"] = ReachOutcome(
        mode="world",
        acted=True,
        is_external=True,
        info_gain=0.0,
        created_memory=True,
        satisfied_curiosity=False,
        inner_fn="web_search",
        text=text,
    )
    return text


def ingest_outward_result(result_text: str, query: str, context: Dict[str, Any] = None) -> None:
    """
    Called by tool_runner drain when a web_search result returns.
    Writes the result back as a world_perception long memory entry
    and feeds the knowledge graph for continuous world-model updates.
    """
    context = context or {}
    if not result_text:
        return
    update_long_memory(
        f"[world_perception] From searching '{query}': {result_text[:400]}",
        emotion="exploration_drive",
        event_type="world_perception",
        importance=3,
        context=context,
        extra={"source": "outward", "query": query},
    )
    log_private(f"[look_outward:result] {result_text[:200]}")
    # Feed knowledge graph — extract entities/relations from web result — and use the
    # graph delta as the information-gain signal that updates look_outward's
    # habituation (reach_value). A result that grows the graph keeps the outward drive
    # live; one that adds nothing satiates it.
    _kg_delta = None
    try:
        from brain.cognition.knowledge_graph import observe as _kg_observe
        _kg_delta = _kg_observe(query + " " + result_text[:600], source="web_search", context=context)
    except Exception as _e:
        record_failure("look_outward.ingest_outward_result", _e)
    try:
        from brain.cognition.exploration_value import record_reach_outcome
        record_reach_outcome("look_outward", result_text, _kg_delta, context)
    except Exception:
        pass


_QUERY_FILLER = re.compile(
    r"^\s*(i wonder|i want to know|i'm curious about|tell me about|"
    r"what is the relationship between|why does orrin|i should investigate)\s*",
    re.IGNORECASE,
)
_QUERY_STOPCHARS = str.maketrans("", "", "\"'[]")


def _clean_seed(seed: str) -> str:
    """Strip filler phrases and tidy a seed into a search-engine-ready query."""
    s = seed.translate(_QUERY_STOPCHARS).strip()
    s = _QUERY_FILLER.sub("", s).strip()
    # Capitalise first letter, drop trailing punctuation except '?'
    if s and s[-1] in ".,:;":
        s = s[:-1]
    return s[:120] if s else seed[:80]


def _form_query(context: Dict[str, Any]) -> str:
    """Build a search query from active threads, exploration_drive, unresolved questions."""
    self_model = context.get("self_model") or {}

    # Gather seed material
    seeds = []

    # Active thread titles
    try:
        threads = load_json(THREADS_FILE, default_type=list) or []
        for t in threads:
            if isinstance(t, dict) and t.get("status") == "alive":
                seeds.append(t.get("title", ""))
    except Exception as e:
        record_failure("look_outward.load_threads", e)

    # Recent stagnation_signal questions from long memory
    try:
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        for e in reversed(long_mem[-20:]):
            if not isinstance(e, dict):
                continue
            if e.get("event_type") == "stagnation_signal_question":
                content = str(e.get("content", ""))
                if content.startswith("[self-question"):
                    content = content.replace("[self-question from stagnation_signal]", "").strip()
                seeds.append(content[:100])
                break
    except Exception as e:
        record_failure("look_outward.load_long_mem", e)

    # Working memory unresolved questions — skip internal state entries
    _WM_SKIP = ("🌓", "🧠", "✅", "⚠️", "[question_answered]", "Shadow question",
                "Chose:", "Rewarded", "Cognition action", "Spoke:", "User response",
                "[metacog", "[Chunk", "[Pattern", "[Incubation", "[done]",
                "[memory]", "[fs_perception]", "[signal_router]", "[consciousness]",
                "[wm_overflow]", "decision:", "[energy]", "[body_sense]",
                "[temporal_state]", "[state_processor]", "[goal_competition]",
                "[inhibition]", "[associative_memory]", "[working_memory]")
    # Also skip the committed goal's own title — searching for that just finds
    # the goal back in our own files and produces zero new information.
    committed = context.get("committed_goal") or context.get("focus_goal") or {}
    _committed_title = ""
    if isinstance(committed, dict):
        _committed_title = (committed.get("title") or committed.get("name") or "").strip().lower()

    wm = context.get("working_memory") or []
    for e in reversed(wm[-5:]):
        content = str(e.get("content", e) if isinstance(e, dict) else e)
        if "?" not in content:
            continue
        if any(content.startswith(p) for p in _WM_SKIP):
            continue
        if _committed_title and _committed_title in content.lower():
            continue
        seeds.append(content[:100])
        break

    # Drop any seeds that are exactly the committed goal title (threads can
    # also mirror the active goal).
    if _committed_title:
        seeds = [s for s in seeds if s and _committed_title not in s.lower()]

    if not seeds:
        values = self_model.get("core_values", [])
        if values:
            v = values[0]
            seeds.append(v["value"] if isinstance(v, dict) else str(v))

    if not seeds:
        return ""

    # Pick best seed: prefer question-containing seeds, then first seed.
    # Seeds are already goal-relevant phrases from threads, WM questions, or values —
    # no LLM reformulation needed, just clean them up.
    best = next((s for s in seeds if s and "?" in s), seeds[0])
    return _clean_seed(best)
