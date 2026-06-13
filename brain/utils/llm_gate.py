from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List

from paths import DATA_DIR as _DATA_DIR

_MODEL_CONFIG = _DATA_DIR / "model_config.json"

# ── Single availability predicate ──────────────────────────────────────────────
#
# The LLM is a tool in the registry, with the same standing as Wikipedia or web
# search. This is the ONE place that decides whether that tool is currently
# reachable. Callers never catch their own LLM failures and silently degrade;
# they ask here, and an unavailable tool is a normal fact ("tool unavailable"),
# not an error to escalate or ruminate on.


# Last successfully parsed value of llm_enabled, keyed by config mtime.
# A torn/concurrent read of model_config.json must reuse the last known value
# instead of falling through to "allow" — fail-open here is how a disabled LLM
# still produced live API calls (4-call 401 bursts in model_failures.txt).
_cfg_cache: dict = {"mtime": None, "enabled": False}  # fail-closed until first good read


def _llm_enabled_in_config() -> bool:
    try:
        st = _MODEL_CONFIG.stat()
        if _cfg_cache["mtime"] == st.st_mtime:
            return _cfg_cache["enabled"]
        cfg = json.loads(_MODEL_CONFIG.read_text(encoding="utf-8"))
        enabled = cfg.get("llm_enabled") is not False
        _cfg_cache["mtime"] = st.st_mtime
        _cfg_cache["enabled"] = enabled
        return enabled
    except Exception:
        return _cfg_cache["enabled"]


def llm_available() -> bool:
    """
    Return True if the LLM tool is enabled and currently reachable.

    Checks, in order:
    1. brain/data/model_config.json — llm_enabled explicitly False → deny.
       Torn/unreadable config reuses the last good value (fail-closed before
       the first good read).
    2. OPENAI_API_KEY present in the environment — missing → deny.
    3. Circuit breaker in utils.generate_response — open (recent hard
       network failures or auth failures) → deny.
    4. utils.llm_router importable — missing → deny.
    """
    if not _llm_enabled_in_config():
        return False

    if not os.getenv("OPENAI_API_KEY"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        if not os.getenv("OPENAI_API_KEY"):
            return False

    try:
        from utils.generate_response import _cb_is_open
        if _cb_is_open():
            return False
    except Exception:
        pass  # breaker unreadable → don't block

    try:
        from utils.llm_router import routed_response as _rr  # noqa: F401
        return True
    except ImportError:
        return False


# ── requires_llm tagging ───────────────────────────────────────────────────────
#
# Cognitive functions that produce nothing useful without the LLM declare it —
# either with the @needs_llm decorator on the function itself, or by name in
# REQUIRES_LLM_FUNCTIONS below (for functions we can't easily decorate).
# select_function filters these out of the candidate pool when llm_available()
# is False: they are skipped cleanly (not selected, no error, no half-output),
# never degraded to a template that pretends to be generative output.

# NOTE: self_supervised_repair is NOT here — its primary path is symbolic and
# works without the LLM; only its last-resort branch is internally gated.
REQUIRES_LLM_FUNCTIONS: frozenset = frozenset({
    "simulate_future_selves",
    "plan_self_evolution",
    "reflect_on_cognition_rhythm",
    "ask_llm",
    "ask_llm_for_research",
    "ask_llm_about_conversation",
})


def needs_llm(fn):
    """Decorator: mark a cognitive function as requiring the LLM tool."""
    fn._requires_llm = True
    return fn


def fn_requires_llm(name: str, fn=None) -> bool:
    """True if the named function is tagged as requiring the LLM."""
    if name in REQUIRES_LLM_FUNCTIONS:
        return True
    if fn is None:
        try:
            from registry.cognition_registry import COGNITIVE_FUNCTIONS
            meta = COGNITIVE_FUNCTIONS.get(name)
            if isinstance(meta, dict):
                if meta.get("requires_llm"):
                    return True
                fn = meta.get("function")
        except Exception:
            pass
    return bool(getattr(fn, "_requires_llm", False))


def filter_llm_dependent(names: Iterable[str]) -> List[str]:
    """
    Remove requires_llm functions from a candidate pool when the LLM tool is
    unavailable. No-op (full list back) when the tool is up.
    """
    names = list(names)
    if llm_available():
        return names
    return [n for n in names if not fn_requires_llm(n)]
