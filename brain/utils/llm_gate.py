from __future__ import annotations

import json
import os
from typing import Iterable, List

from brain.paths import DATA_DIR as _DATA_DIR
from brain.utils.failure_counter import record_failure

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
    except Exception as exc:  # torn/unreadable config — record, reuse last good (fail-closed)
        record_failure("llm_gate._llm_enabled_in_config", exc)
        return _cfg_cache["enabled"]


def llm_available() -> bool:
    """
    Return True if the LLM tool is enabled and currently reachable.

    Checks, in order:
    1. brain/data/model_config.json — llm_enabled explicitly False → deny.
       Torn/unreadable config reuses the last good value (fail-closed before
       the first good read).
    2. The user-selected provider (Part 11) is configured — "none", or a
       provider with no key/endpoint → deny. (For OpenAI this is the same
       OPENAI_API_KEY check as before.)
    3. Circuit breaker in utils.generate_response — open (recent hard
       network failures or auth failures) → deny.
    4. utils.llm_router importable — missing → deny.
    """
    if not _llm_enabled_in_config():
        return False

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:  # intentional: python-dotenv optional — env already in os.environ
        pass
    try:
        from brain.utils import llm_providers as _providers
        _prov = _providers.resolve()
        if _prov is None or not _prov.is_configured():
            return False
    except Exception:
        # If the provider layer is somehow unimportable, fall back to the historical
        # OpenAI check so a misconfiguration fails closed, not open.
        if not os.getenv("OPENAI_API_KEY"):
            return False

    try:
        from brain.utils.generate_response import _cb_is_open
        if _cb_is_open():
            return False
    except Exception as exc:  # breaker unreadable → record, don't block
        record_failure("llm_gate.llm_available.breaker", exc)

    try:
        from brain.utils.llm_router import routed_response as _rr  # noqa: F401
        return True
    except ImportError:
        return False


def llm_callable_by(caller: str) -> bool:
    """True only if `caller` could actually reach the API right now —
    i.e. the LLM is available AND (tool-only is off OR caller is allowlisted).

    This is the gate cognition should use to decide 'LLM path vs symbolic
    path', because llm_available() ignores tool-only mode and over-reports:
    in the default deployment (llm_enabled: true, key present,
    ORRIN_LLM_TOOL_ONLY=1) it returns True even though every non-allowlisted
    caller gets 'tool unavailable' past the symbolic gate in generate_response.
    """
    if not llm_available():
        return False
    try:
        from brain.utils.generate_response import _llm_tool_only, _LLM_TOOL_CALLERS
        if _llm_tool_only() and caller not in _LLM_TOOL_CALLERS:
            return False
    except Exception as exc:  # tool-only refinement unreadable — record, fall through
        record_failure("llm_gate.llm_callable_by", exc)
    return True


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
    # Phase 5 — open-vocabulary creativity with no symbolic path. These are kept
    # as the LLM's job, not converted; they're filtered from the candidate pool in
    # tool-only mode so they're cleanly never selected (no run-and-degrade).
    # NOTE: decide_to_write_code is deliberately NOT here — it reaches the LLM via
    # the allow-listed ask_llm tool path, which works in tool-only mode.
    "check_projection_against_reality",   # #8 future-self projection
    "run_experiment_cycle",               # #9 hypothesis generation / experiment design
    "run_active_experiment",
    "bootstrap_self",                     # #9 invent a new cognitive tool
    "evaluate_new_abstractions",
    "assess_innovation_outcomes",
    "propose_extension",                  # #21 propose/review code self-extension
    "review_extension",
    "run_sandbox_experiments",            # #22 value invention / mutation (sandbox)
    "generate_absurd_goal",
    "invent_new_value",
    "mutate_directive",
    "reflect_on_sandbox_experiment",
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
            from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
            meta = COGNITIVE_FUNCTIONS.get(name)
            if isinstance(meta, dict):
                if meta.get("requires_llm"):
                    return True
                fn = meta.get("function")
        except Exception as exc:  # registry lookup failed — record, fall back to attr check
            record_failure("llm_gate.fn_requires_llm", exc)
    return bool(getattr(fn, "_requires_llm", False))


def filter_llm_dependent(names: Iterable[str]) -> List[str]:
    """
    Remove requires_llm functions from a candidate pool when the LLM tool is
    unavailable. No-op (full list back) when the tool is up.
    """
    names = list(names)
    # requires_llm functions reach the API as ordinary cognition (non-allowlisted
    # callers), so they are usable only when the LLM is available AND tool-only
    # mode is off. In the default tool-only deployment they can never run, so they
    # must be filtered here too — otherwise (the old llm_available()-only check)
    # they stayed in the pool, got selected, and ran-and-degraded every cycle.
    try:
        from brain.utils.generate_response import _llm_tool_only
        cognition_can_call = llm_available() and not _llm_tool_only()
    except Exception:
        cognition_can_call = llm_available()
    if cognition_can_call:
        return names
    return [n for n in names if not fn_requires_llm(n)]
