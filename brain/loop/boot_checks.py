"""Cognitive-loop boot preflight checks (Phase 4.5B, from boot.py).

Two startup validators that run before context construction: `_validate_boot_files`
self-heals on-disk state files whose JSON shape has drifted, and
`_verify_production_capability` confirms the full `compose_section` route is
reachable end-to-end after runtime registration. boot.py re-exports both (so
existing `from brain.loop.boot import _verify_production_capability` callers keep
working); `_boot_context` calls `_validate_boot_files` once before the loop.
"""
from __future__ import annotations

from typing import Any, Dict

from brain.core.runtime_log import get_logger
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_error, log_activity
from brain.utils.failure_counter import record_failure
from brain.paths import (
    WORKING_MEMORY_FILE, LONG_MEMORY_FILE, AFFECT_STATE_FILE, BANDIT_STATE_FILE,
    REFLECTION as REFLECTION_LOG_FILE, CHAT_LOG_FILE,
    COGNITIVE_FUNCTIONS_LIST_FILE,
)

_log = get_logger(__name__)


def _validate_boot_files() -> None:
    """
    Check critical state files for schema correctness at startup.
    Logs a loud warning and reinitialises to safe defaults if a file is wrong type.
    """
    checks = [
        (LONG_MEMORY_FILE,      list,  []),
        (WORKING_MEMORY_FILE,   list,  []),
        # reflection_log / chat_log are list-typed too; previously they only
        # logged "does not contain a list" and were skipped (never self-healed),
        # so a bad shape persisted across boots (run audit #5).
        (REFLECTION_LOG_FILE,   list,  []),
        (CHAT_LOG_FILE,         list,  []),
        (AFFECT_STATE_FILE,  dict,  {}),
        (BANDIT_STATE_FILE,     dict,  {}),
    ]
    for path, expected_type, safe_default in checks:
        try:
            data = load_json(path, default_type=expected_type)
            if not isinstance(data, expected_type):
                log_error(
                    f"[boot] SCHEMA ERROR: {path.name} should be {expected_type.__name__}, "
                    f"got {type(data).__name__}. Reinitialising to safe default."
                )
                save_json(path, safe_default)
        except Exception as e:
            log_error(f"[boot] Could not validate {path.name}: {e}")

    # Emotion keyword model: an empty affect_model.json silently turns all
    # affect detection neutral. Seed it from the packaged defaults (logs once).
    try:
        from brain.affect.model import seed_default_emotion_keywords
        seed_default_emotion_keywords()
    except Exception as e:
        log_error(f"[boot] Could not seed emotion keywords: {e}")

    # Sweep orphaned atomic-write temp files (tmp* / *.tmp) older than a day —
    # hard kills strand them and they accumulate in brain/data/ (audit §11).
    try:
        import time as _t
        from brain.paths import DATA_DIR as _dd
        _cutoff = _t.time() - 86400
        _swept = 0
        for _p in list(_dd.glob("tmp*")) + list(_dd.glob("*.tmp")):
            try:
                if _p.is_file() and _p.stat().st_mtime < _cutoff:
                    _p.unlink()
                    _swept += 1
            except Exception:
                pass
        if _swept:
            log_activity(f"[boot] Swept {_swept} stale temp file(s) from data dir.")
    except Exception as e:
        log_error(f"[boot] Temp-file sweep failed: {e}")


def _verify_production_capability(functions: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the complete compose_section route after runtime registration."""
    checks: Dict[str, Any] = {}
    try:
        meta = functions.get("compose_section")
        fn = meta.get("function") if isinstance(meta, dict) else meta
        checks["callable_registry"] = callable(fn)

        manifest = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list) or []
        names = {
            str(item.get("name"))
            for item in manifest
            if isinstance(item, dict) and item.get("name")
        }
        checks["persisted_manifest"] = "compose_section" in names

        from brain.cognition.planning.step_execution import recognise_step_action
        checks["plan_resolver"] = recognise_step_action({
            "step": "Draft the thesis section",
            "action": {"function": "compose_section"},
        }) == "compose_section"

        from brain.think.think_utils.select_function import (
            _CAPS_PATH,
            _is_dispatchable,
            _load_actions,
        )
        checks["dispatchable"] = _is_dispatchable("compose_section")
        checks["selector_pool"] = "compose_section" in _load_actions()

        import json as _json
        capabilities = _json.loads(_CAPS_PATH.read_text(encoding="utf-8"))
        checks["capability_metadata"] = bool(capabilities.get("compose_section"))
    except Exception as exc:
        record_failure("ORRIN_loop.production_capability_check", exc)
        checks["check_error"] = f"{type(exc).__name__}: {exc}"

    checks["reachable"] = all(value is True for key, value in checks.items()
                              if key != "check_error") and "check_error" not in checks
    if not checks["reachable"]:
        missing = [key for key, value in checks.items()
                   if key != "reachable" and value is not True]
        exc = RuntimeError(f"production_capability_unreachable: {', '.join(missing)}")
        record_failure("ORRIN_loop.production_capability_unreachable", exc)
        log_error(f"[boot] {exc}")
    else:
        log_activity("[boot] compose_section production capability reachable end-to-end.")
    return checks
