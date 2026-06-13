# brain/utils/llm_router.py
# LLM routing layer: content-hash cache + complexity routing + cost tracking.
#
# Usage (drop-in for generate_response):
#   from utils.llm_router import routed_response, routed_reasoning
#
# routed_response(prompt, caller, complexity="auto")
#   - complexity="simple"   → cheap/fast model (gpt-4o-mini or configured fast_model)
#   - complexity="standard" → default thinking model
#   - complexity="auto"     → router classifies by prompt length + keywords
#
# routed_reasoning(topic, context_text, caller)
#   - Single-call structured JSON reasoning (questions+reasoning+plan in one call)
#   - Wraps generate_reasoning_chain() but adds cache + cost tracking
#
# Cache:
#   - In-memory, keyed by SHA-256(model + prompt_text), TTL = 300s
#   - Skips cache for prompts containing "now", "current", "today", "just"
#   - Max 500 entries — LRU eviction when full
#
# Cost tracking:
#   - Rough token estimate (chars / 4) stored in data/llm_cost_log.json
#   - Per-caller totals, updated atomically
from __future__ import annotations
from core.runtime_log import get_logger

import hashlib
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from utils.generate_response import (
    generate_response,
    generate_reasoning_chain,
    llm_ok,
)
from utils.failure_counter import record_failure
from utils.json_utils import load_json, save_json
from core.config.settings import model_roles
_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_FAST_MODEL    = model_roles.get("fast", model_roles.get("thinking", "gpt-4o-mini"))
_MAIN_MODEL    = model_roles.get("thinking", "gpt-4.1")
_DEEP_MODEL    = model_roles.get("deep", model_roles.get("thinking", "gpt-4o"))


def get_deep_model() -> str:
    """Return the strongest configured model name (used by escalation paths)."""
    return _DEEP_MODEL


_CACHE_TTL_S   = 300          # 5-minute TTL
_CACHE_MAX     = 500          # max in-memory entries
_COST_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "llm_cost_log.json"

# Keywords that make a prompt time-sensitive — bypass cache.
# Matched on word boundaries: substring matching made common words like
# "knowledge" (contains "now") or "adjust" (contains "just") bypass the cache,
# driving the hit rate toward zero. "just" is dropped entirely — as a temporal
# marker it's too common in ordinary prose to be a useful volatility signal.
_VOLATILE_KEYWORDS = frozenset({"now", "current", "currently", "today", "latest", "recently"})
_VOLATILE_RE = re.compile(r"\b(?:" + "|".join(sorted(_VOLATILE_KEYWORDS)) + r")\b")

# Complexity-routing thresholds
_SIMPLE_MAX_CHARS  = 400    # prompts under this always go to fast model
_COMPLEX_MIN_CHARS = 1200   # prompts over this always go to main model

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_cache: Dict[str, Tuple[float, str]] = {}  # key → (timestamp, content)


def _cache_key(model: str, prompt_text: str) -> str:
    raw = f"{model}||{prompt_text}"
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _is_volatile(prompt_text: str) -> bool:
    return bool(_VOLATILE_RE.search(prompt_text.lower()))


def _cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL_S:
        return entry[1]
    if entry:
        _cache.pop(key, None)
    return None


def _cache_set(key: str, content: str) -> None:
    if len(_cache) >= _CACHE_MAX:
        # Evict oldest entry
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.time(), content)


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

def _rough_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# Daily token budget — hard backstop so a selector rut (e.g. a fetch_and_read
# loop) can't become a billing incident. 0 or negative disables the cap.
_DAILY_TOKEN_BUDGET = int(os.environ.get("ORRIN_LLM_DAILY_TOKEN_BUDGET", "2000000"))

_budget_lock = threading.Lock()
_daily_date:   str = ""
_daily_tokens: int = 0
_budget_trip_announced = False


def _restore_daily_usage() -> None:
    """Restore today's token count from the cost log so restarts don't reset the cap."""
    global _daily_date, _daily_tokens
    try:
        counts = load_json(_COST_LOG_PATH, default_type=dict) or {}
        daily = counts.get("_daily", {})
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if isinstance(daily, dict) and daily.get("date") == today:
            _daily_date   = today
            _daily_tokens = int(daily.get("est_tokens", 0))
    except Exception as _e:
        _log.warning("llm_router._restore_daily_usage: %s", _e)


_restore_daily_usage()


def _budget_exceeded(caller: str) -> bool:
    """True if today's estimated token usage is over the daily budget."""
    global _daily_date, _daily_tokens, _budget_trip_announced
    if _DAILY_TOKEN_BUDGET <= 0:
        return False
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with _budget_lock:
        if _daily_date != today:
            _daily_date   = today
            _daily_tokens = 0
            _budget_trip_announced = False
        if _daily_tokens < _DAILY_TOKEN_BUDGET:
            return False
        announce = not _budget_trip_announced
        _budget_trip_announced = True
    if announce:
        _log.error(
            "llm_router: daily token budget exhausted (%d est tokens >= %d) — "
            "refusing LLM calls until UTC midnight (caller=%s)",
            _daily_tokens, _DAILY_TOKEN_BUDGET, caller,
        )
    # record_failure rate-limits per site, so repeated trips don't flood telemetry.
    record_failure(
        "llm_router.daily_budget",
        RuntimeError(f"daily token budget {_DAILY_TOKEN_BUDGET} exhausted (caller={caller})"),
    )
    return True


def _track_cost(caller: str, prompt_text: str, response_text: str) -> None:
    global _daily_date, _daily_tokens
    tokens = _rough_tokens(prompt_text) + _rough_tokens(response_text)
    today  = time.strftime("%Y-%m-%d", time.gmtime())
    with _budget_lock:
        if _daily_date != today:
            _daily_date   = today
            _daily_tokens = 0
        _daily_tokens += tokens
        daily_snapshot = {"date": _daily_date, "est_tokens": _daily_tokens}
    try:
        counts: Dict[str, Any] = load_json(_COST_LOG_PATH, default_type=dict) or {}
        entry = counts.get(caller, {"calls": 0, "est_tokens": 0})
        entry["calls"]      = int(entry.get("calls", 0)) + 1
        entry["est_tokens"] = int(entry.get("est_tokens", 0)) + tokens
        counts[caller] = entry
        counts["_daily"] = daily_snapshot
        save_json(_COST_LOG_PATH, counts)
    except Exception as _e:
        record_failure("llm_router._track_cost", _e)


# ---------------------------------------------------------------------------
# Complexity classifier
# ---------------------------------------------------------------------------

_REASONING_KEYWORDS = frozenset({
    "reason", "think", "explain", "analyze", "assess", "evaluate",
    "why", "how", "plan", "strategy", "consider", "reflect",
})

def _classify(prompt_text: str) -> str:
    """Returns 'simple' | 'standard'."""
    n = len(prompt_text)
    if n <= _SIMPLE_MAX_CHARS:
        return "simple"
    if n >= _COMPLEX_MIN_CHARS:
        return "standard"
    lower = prompt_text.lower()
    hits = sum(1 for kw in _REASONING_KEYWORDS if kw in lower)
    return "standard" if hits >= 2 else "simple"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def routed_response(
    prompt: Any,
    caller: str,
    complexity: str = "auto",
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Route a prompt through the LLM, with cache and complexity-based model selection.
    Returns the content string on success, None on error (same contract as llm_ok).
    """
    prompt_text = str(prompt) if not isinstance(prompt, str) else prompt

    if _budget_exceeded(caller):
        return None

    # Model selection
    if model:
        selected_model = model
    elif complexity == "simple":
        selected_model = _FAST_MODEL
    elif complexity == "standard":
        selected_model = _MAIN_MODEL
    elif complexity == "deep":
        selected_model = _DEEP_MODEL
    else:  # auto
        selected_model = _MAIN_MODEL if _classify(prompt_text) == "standard" else _FAST_MODEL

    # Cache check (skip for volatile prompts)
    key = None
    if not _is_volatile(prompt_text):
        key = _cache_key(selected_model, prompt_text)
        cached = _cache_get(key)
        if cached is not None:
            return cached

    result  = generate_response(prompt_text, model=selected_model)
    content = llm_ok(result, caller)

    # Primary model failed — fall back to fast model before giving up
    if not content and selected_model != _FAST_MODEL:
        result  = generate_response(prompt_text, model=_FAST_MODEL)
        content = llm_ok(result, f"{caller}/fallback")

    if content:
        if key is not None:
            _cache_set(key, content)
        _track_cost(caller, prompt_text, content)

    return content


def routed_reasoning(
    topic: str,
    context_text: str,
    caller: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single-call structured reasoning with cache + cost tracking.
    Returns the same dict shape as generate_reasoning_chain().
    """
    if _budget_exceeded(caller):
        return {
            "status":     "error",
            "content":    None,
            "scratchpad": None,
            "error":      "daily LLM token budget exhausted",
        }

    cache_input = f"reasoning::{topic}::{context_text[:500]}"
    selected_model = model or _MAIN_MODEL

    key = None
    if not _is_volatile(cache_input):
        key    = _cache_key(selected_model, cache_input)
        cached = _cache_get(key)
        if cached is not None:
            # Reconstruct the expected shape from cached plan string
            return {
                "status":    "ok",
                "content":   cached,
                "scratchpad": {"questions": "(cached)", "reasoning": "(cached)"},
                "error":     None,
            }

    result = generate_reasoning_chain(
        topic=topic,
        context_text=context_text,
        caller=caller,
        model=selected_model,
    )

    if result.get("status") == "ok" and result.get("content"):
        if key is not None:
            _cache_set(key, result["content"])
        _track_cost(caller, f"{topic}\n{context_text[:500]}", result["content"])

    return result


def cache_stats() -> Dict[str, Any]:
    """Return live cache stats — useful for the dashboard /api/depth endpoint."""
    now = time.time()
    live  = sum(1 for ts, _ in _cache.values() if now - ts < _CACHE_TTL_S)
    stale = len(_cache) - live
    return {"entries": len(_cache), "live": live, "stale": stale, "ttl_s": _CACHE_TTL_S}
