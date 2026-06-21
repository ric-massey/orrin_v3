# utils/token_meter.py
# Per-call and per-function token accounting.
#
# Usage:
#   from utils.token_meter import record_call
#   record_call("pursue_goal", "gpt-4.1", input_tokens=1200, output_tokens=300)
#
# record_call():
#   - Increments in-memory counters by caller and by model (always).
#   - Appends one compact line to data/token_log.jsonl for every call.
#   - Rotates token_log.jsonl → token_log.jsonl.1 at 10 MB.
#
# dump_summary():
#   - Writes data/token_summary.json with totals, tokens/hour, and
#     per-function breakdown sorted by input_tokens desc.
#   - Called periodically from ORRIN_loop (same cadence as failure dump).
#
# Never raises; all internal errors are swallowed.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_JSONL_MAX_BYTES = 10 * 1024 * 1024   # 10 MB before rotation

_lock          : threading.Lock                    = threading.Lock()
_by_fn         : Dict[str, Dict[str, int]]         = {}   # fn → {calls, in, out}
_by_model      : Dict[str, Dict[str, int]]         = {}   # model → {calls, in, out}
_total         : Dict[str, int]                    = {"calls": 0, "in": 0, "out": 0}
_session_start : float                             = time.time()
_active_calls  : int                               = 0    # in-flight LLM requests

_data_dir_cache: Optional[Path] = None


def _data_dir() -> Path:
    global _data_dir_cache
    if _data_dir_cache is None:
        try:
            from brain.paths import DATA_DIR
            _data_dir_cache = DATA_DIR
        except Exception:
            _data_dir_cache = Path(__file__).resolve().parent.parent / "data"
    return _data_dir_cache


def _increment(bucket: Dict[str, Dict[str, int]], key: str, inp: int, out: int) -> None:
    if key not in bucket:
        bucket[key] = {"calls": 0, "in": 0, "out": 0}
    b = bucket[key]
    b["calls"] += 1
    b["in"]    += inp
    b["out"]   += out


def record_call(
    caller: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """
    Record one LLM call.  Thread-safe, never raises.

    caller        — cognition function name, e.g. "pursue_goal"
    model         — model identifier, e.g. "gpt-4.1"
    input_tokens  — prompt tokens from usage
    output_tokens — completion tokens from usage
    """
    fn_key    = caller or "unknown"
    model_key = model  or "unknown"
    inp       = max(0, int(input_tokens  or 0))
    out       = max(0, int(output_tokens or 0))
    now_iso   = datetime.now(timezone.utc).isoformat()

    with _lock:
        _increment(_by_fn,    fn_key,    inp, out)
        _increment(_by_model, model_key, inp, out)
        _total["calls"] += 1
        _total["in"]    += inp
        _total["out"]   += out

    # Write one JSONL line outside the lock
    try:
        path = _data_dir() / "token_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() and path.stat().st_size > _JSONL_MAX_BYTES:
                path.replace(path.with_suffix(".jsonl.1"))
        except Exception as _e:
            record_failure("token_meter.record_call", _e)
        line = json.dumps(
            {"ts": now_iso, "fn": fn_key, "model": model_key, "in": inp, "out": out},
            ensure_ascii=False,
        ) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as _e:
        record_failure("token_meter.record_call.2", _e)


def get_summary() -> Dict[str, Any]:
    """Return current in-memory stats snapshot."""
    with _lock:
        elapsed_h = max((time.time() - _session_start) / 3600, 1 / 3600)
        total_in  = _total["in"]
        total_out = _total["out"]
        total_tok = total_in + total_out
        tph       = total_tok / elapsed_h

        by_fn_list: List[Dict[str, Any]] = []
        for fn, b in _by_fn.items():
            fn_tok = b["in"] + b["out"]
            by_fn_list.append({
                "fn":           fn,
                "calls":        b["calls"],
                "input_tokens": b["in"],
                "output_tokens":b["out"],
                "total_tokens": fn_tok,
                "pct":          round(100 * fn_tok / total_tok, 1) if total_tok else 0.0,
            })
        by_fn_list.sort(key=lambda x: -x["total_tokens"])

        by_model_list: List[Dict[str, Any]] = []
        for m, b in _by_model.items():
            by_model_list.append({
                "model":        m,
                "calls":        b["calls"],
                "input_tokens": b["in"],
                "output_tokens":b["out"],
                "total_tokens": b["in"] + b["out"],
            })
        by_model_list.sort(key=lambda x: -x["total_tokens"])

        return {
            "updated":        datetime.now(timezone.utc).isoformat(),
            "session_start":  datetime.fromtimestamp(_session_start, tz=timezone.utc).isoformat(),
            "elapsed_hours":  round(elapsed_h, 3),
            "tokens_per_hour":round(tph, 1),
            "total": {
                "calls":         _total["calls"],
                "input_tokens":  total_in,
                "output_tokens": total_out,
                "total_tokens":  total_tok,
            },
            "by_function": by_fn_list,
            "by_model":    by_model_list,
        }


def enter_call() -> None:
    """Increment the in-flight call counter. Call before each LLM request."""
    global _active_calls
    with _lock:
        _active_calls += 1


def exit_call() -> None:
    """Decrement the in-flight call counter. Call after each LLM request completes."""
    global _active_calls
    with _lock:
        _active_calls = max(0, _active_calls - 1)


def active_call_count() -> int:
    """Return the number of currently in-flight LLM calls."""
    with _lock:
        return _active_calls


def dump_summary() -> None:
    """
    Write the current summary to data/token_summary.json.
    No-op if no calls recorded yet.  Never raises.
    """
    with _lock:
        if _total["calls"] == 0:
            return
    summary = get_summary()
    try:
        path = _data_dir() / "token_summary.json"
        tmp  = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as _e:
        record_failure("token_meter.dump_summary", _e)
