# agency/tool_runner.py
# Gives Orrin direct, autonomous access to his tools.
# - ToolRunner: background thread that drains tool_requests.json every 30s
# - dispatch(): fire any tool right now by name
# - request(): queue a tool call for the next drain pass
# - Cognitive functions registered into COGNITIVE_FUNCTIONS so the bandit can pick them
#
# Tool requests are first-class objects. Each entry carries:
#   origin       — which cognition function asked (e.g. "look_outward")
#   intent       — cognitive role (e.g. "world_perception", "tool_use")
#   ingest_handler — dotted Python path to a callback, e.g.
#                    "cognition.perception.look_outward.ingest_outward_result"
#   context_kwargs — keyword args forwarded to the handler alongside the result
#
# drain_queue() is a generic dispatcher: run the tool, call the handler if
# present, write long memory with event_type=intent so the cognition layer
# can later query by semantic role rather than always seeing "tool_use".
from __future__ import annotations
from brain.core.runtime_log import get_logger

import importlib
import threading
import uuid
from typing import Any, Dict, List, Optional

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_error
from brain.utils.failure_counter import record_failure
from brain.cog_memory.working_memory import update_working_memory
from brain.paths import TOOL_REQUESTS_FILE
from brain.utils.timeutils import now_iso_z
_log = get_logger(__name__)

_LOCK = threading.Lock()

# Tool registry import (deferred to avoid circular at module load)

def _get_registry() -> Dict[str, Any]:
    from brain.behavior.tools.toolkit import tool_registry
    return tool_registry


# ── Long-memory helper ────────────────────────────────────────────────────────

def _append_long_memory(
    tool_name: str,
    args: Any,
    output: str,
    *,
    origin: str = "",
    intent: str = "tool_use",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Write a tool execution record to long memory with the semantic intent tag."""
    try:
        from brain.cog_memory.long_memory import update_long_memory
        merged_extra: Dict[str, Any] = {}
        if origin:
            merged_extra["origin"] = origin
        if extra:
            merged_extra.update(extra)
        update_long_memory(
            f"Used tool '{tool_name}' ({str(args)[:80]}) → {output[:300]}",
            event_type=intent,
            importance=2,
            priority=2,
            extra=merged_extra if merged_extra else None,
        )
    except Exception as e:
        record_failure("tool_runner._append_long_memory", e)


# ── Core dispatch — run a tool right now ──────────────────────────────────────

def dispatch(
    tool_name: str,
    args: Any = None,
    *,
    origin: str = "",
    intent: str = "tool_use",
    write_memory: bool = True,
) -> Dict[str, Any]:
    """
    Execute a tool immediately by name.
    args can be a string (passed as first positional) or a dict (passed as kwargs).
    Returns {"success": bool, "output": str, "tool": tool_name}.

    origin  — the cognition function that triggered this call (for long-memory tagging)
    intent  — semantic role written to long memory (default "tool_use")
    write_memory — when False, skips the long-memory entry (caller will write it)
    """
    registry = _get_registry()
    if tool_name not in registry:
        msg = f"Unknown tool: {tool_name}"
        log_error(msg)
        return {"success": False, "output": msg, "tool": tool_name}

    fn = registry[tool_name]
    try:
        if isinstance(args, dict):
            result = fn(**args)
        elif args is not None:
            result = fn(args)
        else:
            result = fn()

        output = str(result)[:1000]
        log_activity(f"Tool '{tool_name}' executed → {output[:120]}")
        update_working_memory(f"Used tool '{tool_name}': {output[:200]}")
        if write_memory:
            _append_long_memory(tool_name, args, output, origin=origin, intent=intent)
        return {"success": True, "output": output, "tool": tool_name}

    except Exception as e:
        log_error(f"Tool '{tool_name}' failed: {e}")
        return {"success": False, "output": str(e), "tool": tool_name}


# ── Queue a tool request ──────────────────────────────────────────────────────

def request(
    tool_name: str,
    reason: str,
    args: Any = None,
    *,
    origin: str = "",
    intent: str = "tool_use",
    ingest_handler: str = "",
    context_kwargs: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add a tool call to the pending queue.

    origin          — cognition function that requested the tool
    intent          — semantic role written to long memory on completion
    ingest_handler  — dotted Python path called with (result_text, **context_kwargs)
                      when the tool result arrives. The handler is responsible for
                      domain-specific integration (e.g. writing to long memory).
                      When provided, the generic long-memory write is skipped.
    context_kwargs  — additional kwargs forwarded to the ingest_handler
    """
    with _LOCK:
        existing = load_json(TOOL_REQUESTS_FILE, default_type=list) or []
        existing.append({
            "id":              str(uuid.uuid4()),
            "tool":            tool_name,
            "reason":          reason,
            "args":            args,
            "origin":          origin,
            "intent":          intent,
            "ingest_handler":  ingest_handler,
            "context_kwargs":  context_kwargs or {},
            "timestamp":       now_iso_z(),
            "executed":        False,
        })
        save_json(TOOL_REQUESTS_FILE, existing)


# ── Ingest-handler resolver ───────────────────────────────────────────────────

def _call_ingest_handler(
    handler_path: str,
    result_text: str,
    context_kwargs: Dict[str, Any],
) -> None:
    """
    Resolve a dotted handler path and call it with (result_text, **context_kwargs).
    Logs and swallows errors so a bad handler never breaks the drain loop.

    Example: "cognition.perception.look_outward.ingest_outward_result"
    """
    if not handler_path:
        return
    try:
        module_path, fn_name = handler_path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            fn(result_text, **context_kwargs)
        else:
            log_error(f"[drain_queue] handler {handler_path!r} is not callable")
    except Exception as e:
        log_error(f"[drain_queue] ingest_handler {handler_path!r} failed: {e}")


# ── Drain the queue — execute all pending tool requests ───────────────────────

_MAX_KEPT_EXECUTED = 50  # retain this many completed entries for audit; trim the rest

def drain_queue() -> int:
    """Execute all pending tool requests. Returns number executed.

    Pattern: snapshot pending entries → execute outside lock → call ingest
    handlers → merge results back into file state under lock (so concurrent
    request() calls are never overwritten).
    """
    with _LOCK:
        all_entries = load_json(TOOL_REQUESTS_FILE, default_type=list) or []

    # Snapshot only the pending ones; tag each with a stable key for merge-back.
    pending = [e for e in all_entries if isinstance(e, dict) and not e.get("executed")]

    executed = 0
    results: dict = {}  # id (or timestamp fallback) → (executed_at, result_str)
    for entry in pending:
        tool = entry.get("tool")
        reason = entry.get("reason", "")
        args   = entry.get("args")
        origin  = entry.get("origin", "")
        intent  = entry.get("intent") or "tool_use"
        handler = entry.get("ingest_handler", "")
        ctx_kw  = entry.get("context_kwargs") or {}

        if not tool:
            continue

        # When a handler is registered it owns the long-memory write; skip the
        # generic one so we don't produce two entries for the same tool result.
        result = dispatch(
            tool,
            args if args is not None else reason,
            origin=origin,
            intent=intent,
            write_memory=not bool(handler),
        )
        result_text = result.get("output", "")[:300]

        # Only call the ingest handler when the tool succeeded; a failed
        # dispatch produces an error string that must not be written to long
        # memory as domain-specific content (e.g. as a world_perception).
        if handler and result.get("success"):
            _call_ingest_handler(handler, result_text, ctx_kw)
        elif handler and not result.get("success"):
            # Custom handler exists but the tool failed — write the error so it's traceable.
            try:
                from brain.cog_memory.long_memory import update_long_memory as _ulm_fail
                _ulm_fail(
                    f"[tool_failure] {tool} (handler={handler}) failed: "
                    f"{result.get('error', result_text or 'unknown error')[:200]}",
                    emotion="impasse_signal",
                    event_type="tool_failure",
                    importance=2,
                )
            except Exception as _e:
                record_failure("tool_runner.drain_queue", _e)

        key = entry.get("id") or entry.get("timestamp") or str(uuid.uuid4())
        results[key] = (now_iso_z(), result_text)
        executed += 1

    if executed:
        with _LOCK:
            # Re-read the file to pick up any requests added while we were executing.
            current = load_json(TOOL_REQUESTS_FILE, default_type=list) or []
            for entry in current:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("id") or entry.get("timestamp") or ""
                if key and key in results and not entry.get("executed"):
                    entry["executed"] = True
                    entry["executed_at"] = results[key][0]
                    entry["result"] = results[key][1]

            # Trim: keep all pending + last _MAX_KEPT_EXECUTED completed.
            still_pending = [e for e in current if isinstance(e, dict) and not e.get("executed")]
            completed = [e for e in current if isinstance(e, dict) and e.get("executed")]
            save_json(TOOL_REQUESTS_FILE, still_pending + completed[-_MAX_KEPT_EXECUTED:])

        log_activity(f"Tool runner: executed {executed} pending tool(s).")

    return executed

# Decide which tool to use based on context (no LLM needed)

def _pick_tool_from_context(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Rule-based tool selection from current context.
    Returns {"tool": name, "args": ...} or None.
    """
    wm: List[Any] = context.get("working_memory") or []
    goal = context.get("committed_goal") or {}
    goal_text = (goal.get("title") or goal.get("name") or "") if isinstance(goal, dict) else str(goal)

    # Collect recent text to scan
    texts = []
    for entry in (wm[-5:] if isinstance(wm, list) else []):
        texts.append(str(entry.get("content", entry) if isinstance(entry, dict) else entry))
    if goal_text:
        texts.append(goal_text)
    combined = " ".join(texts).lower()

    search_cues  = ["find", "look up", "search", "what is", "who is", "research", "learn about", "discover"]
    code_cues    = ["calculate", "compute", "simulate", "plot", "run", "execute", "test", "measure"]
    write_cues   = ["save", "write", "record", "store to file", "note this", "remember this"]
    notify_cues  = ["tell the user", "notify", "alert", "ping", "let them know", "send a message"]
    list_cues    = ["list files", "what files", "show directory", "what's in the folder"]
    # Internal file-search cues: Feeling-of-Knowing signal (Hart, 1965) — when the
    # agent senses the information exists internally, search internal files first.
    # Uses word-fragment matching so "check my code" hits "my code" etc.
    local_search_cues = [
        "my code", "my files", "my source", "my data", "my codebase",
        "check source", "check code", "look at source", "look at code",
        "how does orrin", "how do i", "where is this defined",
        "find in data", "search local", "my own files",
        "in the codebase", "how is this implemented",
        "where does", "which file", "inspect my",
        "in source", "in code", "in data",
    ]

    if any(c in combined for c in notify_cues):
        msg = goal_text or next((t for t in texts if len(t) > 10), "I have something to share")
        return {"tool": "notify_user", "args": {"message": msg[:200], "title": "Orrin"}}

    # Internal search takes priority over external: if context strongly suggests
    # looking inside own files, route there before reaching web_search cues.
    if any(c in combined for c in local_search_cues):
        query = goal_text or next((t for t in texts if len(t) > 10), "recent context")
        return {"tool": "grep_files", "args": {"query": query[:150], "max_results": 20}}

    if any(c in combined for c in search_cues):
        query = goal_text or next((t for t in texts if len(t) > 10), "recent context")
        return {"tool": "web_search", "args": query[:200]}

    if any(c in combined for c in code_cues):
        topic = goal_text or "current task"
        code = f"# Orrin auto-generated exploration\nprint('Exploring: {topic}')\n"
        return {"tool": "execute_python_code", "args": code}

    if any(c in combined for c in list_cues):
        return {"tool": "list_directory", "args": {"path": "."}}

    if any(c in combined for c in write_cues):
        content = "\n".join(texts[-2:])
        return {"tool": "save_note", "args": {"content": content, "title": "auto_note"}}

    return None

# Cognitive functions — registered directly into COGNITIVE_FUNCTIONS

def decide_to_use_tools(context: Dict[str, Any] = None, **_) -> None:
    """
    Orrin scans his current context and decides whether to use a tool.
    Rule-based — works without LLM.
    """
    ctx = context or {}
    # Always drain queued requests from look_outward and other cognition functions
    drain_queue()
    pick = _pick_tool_from_context(ctx)
    if pick:
        result = dispatch(pick["tool"], pick.get("args"))
        if result["success"]:
            update_working_memory(f"Decided to use '{pick['tool']}': {result['output'][:200]}")
        else:
            update_working_memory(f"Tried '{pick['tool']}' but it failed: {result['output'][:120]}")
    else:
        update_working_memory("Considered using tools — nothing needed right now.")

def decide_to_search(context: Dict[str, Any] = None, **_) -> None:
    """Orrin performs a web search based on his current goal or working memory."""
    ctx = context or {}
    goal = ctx.get("committed_goal") or {}
    query = (goal.get("title") or goal.get("name") or "") if isinstance(goal, dict) else str(goal)

    if not query:
        wm = ctx.get("working_memory") or []
        for entry in reversed(wm[-5:] if isinstance(wm, list) else []):
            text = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
            if len(text) > 15:
                query = text[:150]
                break

    if not query:
        update_working_memory("Wanted to search but couldn't form a query.")
        return

    result = dispatch("web_search", query)
    update_working_memory(f"Searched for '{query[:80]}': {result['output'][:300]}")

def decide_to_run_code(context: Dict[str, Any] = None, **_) -> None:
    """Orrin writes and runs a small Python script to explore or compute something."""
    ctx = context or {}
    goal = ctx.get("committed_goal") or {}
    topic = (goal.get("title") or goal.get("name") or "current state") if isinstance(goal, dict) else "current state"

    code = (
        f"# Orrin exploring: {topic}\n"
        f"import json, os\n"
        f"print('Orrin is exploring:', {repr(topic[:60])})\n"
        f"print('Working directory:', os.getcwd())\n"
    )
    result = dispatch("execute_python_code", code)
    update_working_memory(f"Ran code exploring '{topic[:60]}': {result['output'][:200]}")

# Background thread

class ToolRunner:
    """Drains the tool queue on a regular interval in the background."""

    def __init__(self, interval_s: float = 30.0) -> None:
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="orrin-tool-runner", daemon=True)

    def start(self) -> None:
        self._thread.start()
        log_activity("Tool runner started.")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                drain_queue()
            except Exception as e:
                log_error(f"Tool runner drain error: {e}")
            self._stop.wait(self._interval)

# Agency cognitive functions exposed for registration

AGENCY_TOOL_FUNCTIONS = {
    "decide_to_use_tools": decide_to_use_tools,
    "decide_to_search":    decide_to_search,
    "decide_to_run_code":  decide_to_run_code,
}
