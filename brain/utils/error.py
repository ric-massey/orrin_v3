# utils/errors.py
from __future__ import annotations
from core.runtime_log import get_logger
import traceback
import uuid
from typing import Any, Dict, Optional

from utils.log import log_error, log_model_issue, utc_now as _utc_now
from utils.path_redact import redact as _redact
from utils.json_utils import append_jsonl
from paths import INCIDENTS_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)


def _safe_str(x: Any, limit: int = 20000) -> str:
    try:
        s = str(x)
    except Exception:
        s = repr(x)
    # keep lines controllable in JSONL
    return s[:limit]


def build_error_event(
    exc: BaseException,
    *,
    phase: str,  # "think" | "action" | "cognition" | "tool" | "loop" | etc.
    context: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a rich, serializable error event Orrin can learn from.
    """
    ctx = context or {}
    try:
        trace = traceback.format_exc()
    except Exception:
        trace = ""

    # keep context lightweight to avoid dumping secrets / huge blobs
    ctx_keys = sorted(list(ctx.keys()))[:50]
    ctx_focus = {
        k: ctx.get(k)
        for k in ["mode", "attention_mode", "focus_goal", "committed_goal", "action_debt", "last_action_ts"]
        if k in ctx
    }

    ev: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "ts": _utc_now(),
        "phase": str(phase),
        "type": exc.__class__.__name__,
        "msg": _redact(_safe_str(exc, limit=2000)),
        "trace": _redact(_safe_str(trace, limit=20000)),
        "context_keys": ctx_keys,
        "context_focus": ctx_focus,
        "extra": extra or {},
    }
    return ev


def record_error(ev: Dict[str, Any]) -> None:
    """
    Persist an error event to incidents.jsonl and log a concise, operator-friendly line.
    """
    try:
        append_jsonl(INCIDENTS_FILE, ev)
    except Exception as e:
        # never crash on logging; at least surface a model issue
        log_model_issue(f"[record_error] append failed: {e}")

    # brief console/operator line
    try:
        phase = ev.get("phase", "?")
        etype = ev.get("type", "Exception")
        msg = ev.get("msg", "")[:300]
        log_error(f"[{phase}] {etype}: {msg}")
    except Exception as _e:
        # swallow final logging failures silently
        record_failure("error.record_error", _e)


def record_exception(
    exc: BaseException,
    *,
    phase: str,
    context: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience: build + record in one call. Returns the event dict for further use.
    """
    ev = build_error_event(exc, phase=phase, context=context, extra=extra)
    record_error(ev)
    return ev
