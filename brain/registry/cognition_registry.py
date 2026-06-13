# registry/cognition_registry.py
from __future__ import annotations
from core.runtime_log import get_logger
import inspect

from typing import Dict, Callable, List, Tuple
from registry.utils import iter_modules, safe_import, extract_callables
from paths import COGNITIVE_FUNCTIONS_LIST_FILE
from utils.json_utils import save_json
from utils.log import log_error, log_activity
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# Narrow, intentional entry-point prefixes for cognition functions
_ALLOWED_PREFIXES: Tuple[str, ...] = (
    "reflect_",
    "plan_",
    "summarize_",
    "repair_",
    "analyze_",
    "decide_",
    "dream_",
    "introspect_",
)

def _is_cognition(fn: Callable) -> bool:
    """
    Prefer an explicit manifest flag if you use one (e.g., via a decorator).
    Defaults to True to keep things simple/forgiving.
    """
    mf = getattr(fn, "__manifest__", None)
    if mf and hasattr(mf, "is_cognition"):
        try:
            return bool(mf.is_cognition)
        except Exception as _e:
            record_failure("cognition_registry._is_cognition", _e)
    return True


def _requires_llm(name: str, fn: Callable) -> bool:
    """Does this function need the LLM tool? (@needs_llm or central name-set.)"""
    if getattr(fn, "_requires_llm", False):
        return True
    try:
        from utils.llm_gate import REQUIRES_LLM_FUNCTIONS
        return name in REQUIRES_LLM_FUNCTIONS
    except Exception:
        return False

def _merge_custom(funcs: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """
    Optionally merge user-defined cognition from core.manager.load_custom_cognition().
    Accepts either {name: callable} or {name: {"function": callable, ...}}.
    """
    try:
        from core.manager import load_custom_cognition  # type: ignore
    except Exception:
        return funcs

    try:
        custom = load_custom_cognition()
        if isinstance(custom, dict):
            for name, obj in custom.items():
                # Skip private helpers from custom too
                if isinstance(name, str) and name.startswith("_"):
                    continue
                if callable(obj):
                    funcs[name] = {"function": obj, "is_cognition": True}
                elif isinstance(obj, dict) and callable(obj.get("function")):
                    funcs[name] = {
                        "function": obj["function"],
                        "is_cognition": bool(obj.get("is_cognition", True)),
                    }
        return funcs
    except Exception as e:
        try:
            log_error(f"[cognition discover] Failed merging custom cognition: {e}")
        except Exception as _e:
            record_failure("cognition_registry._merge_custom", _e)
        return funcs

# ---------------------------------------------------------------------------
# Router integration — maps discovered function names to introspection triggers
# ---------------------------------------------------------------------------

# Functions discovered here that should be routed through the introspection
# cooldown system.  The lambda wrappers are zero-arg so _invoke_cognition's
# no-arg fallback path picks them up cleanly.
_ROUTER_FN_MAP: Dict[str, str] = {
    "reflect_on_cognition_patterns":   "cognition",
    "reflect_on_cognition_schedule":   "cognition_schedule",
    "reflect_on_conversation_patterns":"conversation",
    "reflect_on_effectiveness":        "effectiveness",
    "reflect_on_internal_agents":      "internal_agents",
    "reflect_on_missed_goals":         "missed_goals",
    "reflect_on_outcomes":             "outcome",
    "introspective_planning":          "planning",
    "reflect_on_cognition_rhythm":     "repair",
    "reflect_on_rules_used":           "rules",
    "reflect_on_self_beliefs":         "self_belief",
    "reflect_on_think":                "think",
    "update_world_model":              "world_model",
}

# Router utility symbols auto-discovered from cognition.introspection.router —
# they need args or are infra-only; remove from the action-gate callable set.
_ROUTER_UTILS: frozenset[str] = frozenset({
    "introspect", "reset_cooldown", "cooldown_status",
})


def _patch_with_router(funcs: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """
    Replace reflection function slots with router-wrapped lambdas and remove
    router utility symbols that are not directly dispatchable.

    After this patch, calling COGNITIVE_FUNCTIONS["reflect_on_self_beliefs"]["function"]()
    goes through the introspection router's cooldown tracker, preventing
    duplicate reflection cycles when both the action gate and meta_reflect
    trigger the same handler within the same cooldown window.
    """
    try:
        from cognition.introspection.router import introspect as _ir
        for fn_name, trigger in _ROUTER_FN_MAP.items():
            if fn_name in funcs:
                _t = trigger  # capture for closure
                funcs[fn_name]["function"] = lambda t=_t: _ir(t)
    except Exception as e:
        # Router not yet available (early import) — leave functions unwrapped.
        log_error(f"[cognition_registry] router patch skipped: {e}")

    for util in _ROUTER_UTILS:
        funcs.pop(util, None)

    return funcs


def discover_cognitive_functions() -> Dict[str, Dict[str, object]]:
    """
    Scan ALL cognition.* modules (including subpackages) and return:
        { name: { "function": callable, "is_cognition": bool } }

    First collects functions that match _ALLOWED_PREFIXES via extract_callables(...),
    then adds ANY other *public* functions defined in the module (keep-first on duplicates).
    Private helpers (names starting with '_') are excluded.
    """
    funcs: Dict[str, Dict[str, object]] = {}
    for mod_name in iter_modules("cognition"):
        mod = safe_import(mod_name)
        if not mod:
            continue

        # 1) Prefix-based discovery
        try:
            found = extract_callables(mod, _ALLOWED_PREFIXES)  # {name: callable}
        except Exception:
            found = {}

        for name, fn in found.items():
            if not isinstance(name, str) or name.startswith("_"):
                continue  # drop private helpers
            if name in funcs:
                try:
                    log_error(f"[cognition discover] Duplicate '{name}' from {mod_name} ignored (keeping first).")
                except Exception as _e:
                    record_failure("cognition_registry.discover_cognitive_functions", _e)
                continue
            funcs[name] = {"function": fn, "is_cognition": _is_cognition(fn),
                           "requires_llm": _requires_llm(name, fn)}

        # 2) Include other public functions defined in this module (no underscores)
        try:
            for name, fn in inspect.getmembers(mod, inspect.isfunction):
                if getattr(fn, "__module__", None) != getattr(mod, "__name__", None):
                    continue  # only functions defined in this module
                if not isinstance(name, str) or name.startswith("_"):
                    continue  # skip private helpers
                if name in funcs:
                    continue  # keep-first
                funcs[name] = {"function": fn, "is_cognition": _is_cognition(fn),
                               "requires_llm": _requires_llm(name, fn)}
        except Exception as _e:
            # best-effort; don't fail discovery because of one bad module
            record_failure("cognition_registry.discover_cognitive_functions.2", _e)

    # Wrap reflection functions with the introspection router and remove
    # router utility symbols that are not directly dispatchable.
    funcs = _patch_with_router(funcs)

    # Merge any custom cognition last (also skips private)
    funcs = _merge_custom(funcs)
    return funcs

def persist_names(funcs: Dict[str, Dict[str, object]]) -> List[str]:
    """
    Write a list of {name, definition} so the LLM can read meanings.
    Still returns the plain list of names for code that uses it.
    Private helpers (names starting with '_') are filtered out here as well.
    """
    names = sorted(
        n for n in funcs.keys()
        if isinstance(n, str)
        and not n.startswith("_")
        and not n.startswith("explore_")  # don't persist corrupted auto-generated goal-exploration stubs
    )
    try:
        items: List[Dict[str, str]] = []
        for name in names:
            meta = funcs.get(name, {})
            fn = meta.get("function") if isinstance(meta, dict) else None
            definition = name  # fallback
            if callable(fn):
                try:
                    sig = str(inspect.signature(fn))
                except Exception:
                    sig = "()"
                doc = (fn.__doc__ or "").strip()
                definition = f"{name}{sig}\n{doc}" if doc else f"{name}{sig}"
            items.append({"name": name, "definition": definition})
        save_json(COGNITIVE_FUNCTIONS_LIST_FILE, items)
        try:
            log_activity(f"[cognition discover] Persisted {len(names)} cognitive function names + definitions.")
        except Exception as _e:
            record_failure("cognition_registry.persist_names", _e)
    except Exception as e:
        try:
            log_error(f"[cognition discover] Failed to persist names/definitions: {e}")
        except Exception as _e:
            record_failure("cognition_registry.persist_names.2", _e)
    return names

# -------- Global cache (mirrors behavior_registry) --------
COGNITIVE_FUNCTIONS: Dict[str, Dict[str, object]] = discover_cognitive_functions()
persist_names(COGNITIVE_FUNCTIONS)

def refresh() -> Dict[str, Dict[str, object]]:
    """
    Optional hot-reload entry point if you add/remove cognition at runtime.
    Re-discovers, persists names, and updates the global IN PLACE.

    Must not rebind: ORRIN_loop (and anyone who did `from … import
    COGNITIVE_FUNCTIONS`) holds a reference to this dict and registers
    runtime functions into it (attempt_regulation, look_outward, agency
    fns). Rebinding split the registry — the loop's registrations lived in
    a stale copy invisible to every fresh import, so the typo-detector
    flagged real functions and late importers saw an incomplete registry.
    """
    COGNITIVE_FUNCTIONS.update(discover_cognitive_functions())
    persist_names(COGNITIVE_FUNCTIONS)
    return COGNITIVE_FUNCTIONS

# -------- Convenience accessors --------
def as_callables() -> Dict[str, Callable]:
    """
    Flatten to a simple {name: function} mapping.
    Useful for callers that prefer direct callables instead of metadata dicts.
    Private helpers (underscore names) are excluded for safety.
    """
    out: Dict[str, Callable] = {}
    for name, meta in COGNITIVE_FUNCTIONS.items():
        if not isinstance(name, str) or name.startswith("_"):
            continue
        fn = meta.get("function") if isinstance(meta, dict) else None
        if callable(fn):
            out[name] = fn
    return out

def discover() -> Dict[str, Callable]:
    """
    Compatibility helper to mirror newer 'registry.cognition_registry.discover()' usage
    found elsewhere in the codebase. Returns {name: callable}.
    """
    return as_callables()
