# cognition/repair/auto_repair.py
from __future__ import annotations
from core.runtime_log import get_logger
from typing import Any, Dict, Optional, Tuple
from pathlib import Path
import shutil

from utils.log import log_activity, log_model_issue
from utils.json_utils import load_json, save_json
from cognition.reflection.meta_reflect import meta_reflect
from cog_memory.working_memory import update_working_memory
from utils.failure_counter import record_failure

# Registries (support hot-reload)
try:
    from registry.cognition_registry import refresh as refresh_cog
except Exception:
    refresh_cog = None
try:
    from registry.behavior_registry import refresh as refresh_beh
except Exception:
    refresh_beh = None

# Think revision & paths
try:
    from behavior.revise import revise_think
except Exception:
    revise_think = None

try:
    from brain.paths import THINK_MODULE_PY as _THINK_MODULE
    from brain.paths import THINK_DIR as _THINK_DIR
except Exception:
    _THINK_MODULE = None
    _THINK_DIR = None
_log = get_logger(__name__)


def _clear_selector_cache() -> None:
    """Clear any cached action list in the selector (if present)."""
    try:
        from think.think_utils.select_function import _load_actions  # type: ignore
        if hasattr(_load_actions, "cache_clear"):
            _load_actions.cache_clear()  # only if wrapped in lru_cache
    except Exception as _e:
        record_failure("auto_repair._clear_selector_cache", _e)


def _refresh_registries() -> None:
    changed = False
    if callable(refresh_beh):
        refresh_beh()
        changed = True
    if callable(refresh_cog):
        refresh_cog()
        changed = True
    _clear_selector_cache()
    if changed:
        log_activity("[auto_repair] registries refreshed")


def _rollback_think_if_possible() -> bool:
    """
    If THINK_DIR/think_module_backup.py exists, copy it over THINK_MODULE_PY.
    """
    try:
        if not (_THINK_MODULE and _THINK_DIR):
            return False
        mod: Path = _THINK_MODULE
        backup: Path = (_THINK_DIR / "think_module_backup.py")
        if backup.exists():
            shutil.copy2(str(backup), str(mod))
            log_activity("[auto_repair] rolled back think_module.py from backup")
            return True
    except Exception as e:
        log_model_issue(f"[auto_repair] rollback failed: {e}")
    return False


def _recover_json_artifacts() -> None:
    """
    Attempt light recovery on commonly corrupted JSON state files:
    - if unreadable or wrong-shaped, replace with default empty structures.
    - if structurally valid but contains null/non-finite numeric values, sanitize in-place.
    """
    candidates: Tuple[Tuple[str, Any], ...] = (
        ("CONTEXT", {}),            # runtime context
        ("TOOL_REQUESTS_FILE", []),
        ("LONG_MEMORY_FILE", []),
        ("WORKING_MEMORY_FILE", []),
        ("MODEL_CONFIG_FILE", {}),  # keep empty dict if damaged
    )

    for name, default in candidates:
        p: Optional[Path] = None
        try:
            import brain.paths as P  # safer than introspecting __dict__
            p = getattr(P, name, None)
            if not isinstance(p, Path):
                continue  # constant not defined in this build

            data = load_json(p, default_type=type(default))
            if not isinstance(data, type(default)):
                save_json(p, default)  # reset malformed shape
                log_model_issue(f"[auto_repair] reset malformed {name} -> {type(default).__name__}")
        except Exception as e:
            # If we couldn’t read at all, write default
            try:
                if isinstance(p, Path):
                    save_json(p, default)
                    log_model_issue(f"[auto_repair] rebuilt {name} with default after error: {e}")
            except Exception as _e:
                record_failure("auto_repair._recover_json_artifacts", _e)

    # Sanitize null/non-finite values inside emotion, bandit, and cycle-count state.
    # This catches the float(None) crash pattern that shape-only checks miss.
    try:
        from utils.state_guard import sanitize_all
        sanitize_all()
    except Exception as e:
        log_model_issue(f"[auto_repair] state_guard sanitize_all failed: {e}")


def classify_error(ev: Dict[str, Any]) -> str:
    """
    Map an error event to a repair action.
      returns one of:
        - refresh_behaviors
        - refresh_cognition
        - refresh_both
        - revise_think
        - rollback_think
        - recover_json
        - reflect_and_continue
    """
    t = (ev.get("type") or "").lower()
    msg = (ev.get("msg") or "").lower()
    trace = (ev.get("trace") or "").lower()
    phase = (ev.get("phase") or "").lower()

    # Unknown bindings → refresh registries
    if "unknown action" in msg or "unknown_action" in msg:
        return "refresh_behaviors"
    if "unknown function" in msg or "unknown_fn" in msg:
        return "refresh_cognition"

    # Import/module wiring → refresh both (fix precedence)
    if ("importerror" in t) or ("module not found" in msg) or (
        ("attributeerror" in t) and (("registry" in trace) or ("behavior" in trace))
    ):
        return "refresh_both"

    # Think module issues → revise or rollback
    if (("syntaxerror" in t) or ("indentationerror" in t)) and ("think_module" in trace):
        return "rollback_think"
    if ("attributeerror" in t) and ("think" in trace):
        return "revise_think"

    # JSON parsing / bad shapes → recover state
    if ("jsondecodeerror" in t) or ("json" in msg and ("decode" in msg or "parse" in msg)):
        return "recover_json"

    # Tool/network/transient → reflect and continue
    if (phase == "tool") or any(k in msg for k in ["timeout", "timed out", "connection reset", "rate limit", "429"]):
        return "reflect_and_continue"

    # Default: try a light refresh
    return "refresh_both"


def reflect_on_error(ev: Dict[str, Any]) -> None:
    """Log a short repair plan into working memory for observability."""
    try:
        snippet = (ev.get("trace") or "")[-800:]
        plan = meta_reflect({
            "goal": "Diagnose and fix runtime failure.",
            "error": f"{ev.get('type')} during {ev.get('phase')}: {ev.get('msg')}",
            "trace_excerpt": snippet,
        })
        update_working_memory(f"🛠️ Repair plan: {str(plan)[:400]}")
    except Exception as _e:
        try:
            from utils.log import log_model_issue
            log_model_issue(f"[reflect_on_error] repair reflection failed: {_e}")
        except Exception as _e:
            record_failure("auto_repair.reflect_on_error", _e)


def try_auto_repair(ev: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Attempt a targeted repair based on the error event.
    Returns: {"attempted": bool, "fixed": bool, "action": str, "note": str}
    """
    action = classify_error(ev)
    reflect_on_error(ev)  # optional: write plan into memory
    log_activity(f"[auto_repair] action = {action}")

    try:
        if action == "refresh_behaviors":
            if callable(refresh_beh):
                refresh_beh()
                _clear_selector_cache()
                return {"attempted": True, "fixed": True, "action": action, "note": "behavior registry refreshed"}
            return {"attempted": True, "fixed": False, "action": action, "note": "no refresh_beh available"}

        if action == "refresh_cognition":
            if callable(refresh_cog):
                refresh_cog()
                _clear_selector_cache()
                return {"attempted": True, "fixed": True, "action": action, "note": "cognition registry refreshed"}
            return {"attempted": True, "fixed": False, "action": action, "note": "no refresh_cog available"}

        if action == "refresh_both":
            _refresh_registries()
            return {"attempted": True, "fixed": True, "action": action, "note": "registries refreshed"}

        if action == "revise_think":
            if callable(revise_think):
                res = str(revise_think())
                ok = res.startswith("✅")
                return {"attempted": True, "fixed": ok, "action": action, "note": res}
            return {"attempted": True, "fixed": False, "action": action, "note": "revise_think not available"}

        if action == "rollback_think":
            ok = _rollback_think_if_possible()
            return {"attempted": True, "fixed": ok, "action": action, "note": "rolled back" if ok else "no backup"}

        if action == "recover_json":
            _recover_json_artifacts()
            return {"attempted": True, "fixed": True, "action": action, "note": "json state recovered"}

        # reflect_and_continue: do nothing heavy, let loop proceed
        return {"attempted": False, "fixed": False, "action": action, "note": "transient; continuing"}

    except Exception as e:
        log_model_issue(f"[auto_repair] repair failed: {e}")
        return {"attempted": True, "fixed": False, "action": action, "note": f"exception during repair: {e}"}
