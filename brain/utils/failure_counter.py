# utils/failure_counter.py
# Lightweight failure telemetry.
#
# Usage:
#   from utils.failure_counter import record_failure
#   except Exception as e: record_failure("module.site", e)
#
# record_failure():
#   - Increments an in-memory per-site counter (always).
#   - Appends one compact line to data/failures.jsonl, rate-limited to at most
#     once per 60 s per site so a hot error path never floods the file.
#   - Rotates failures.jsonl when it exceeds 10 MB (renames to .jsonl.1).
#
# dump_summary():
#   - Writes data/failure_summary.json with all per-site counts and last errors.
#   - Call this periodically (e.g. every 100 cycles in ORRIN_loop).
#
# No log output on the hot path — just counter ticks and compact JSONL lines.
# Never raises in normal operation; all internal errors are swallowed so the
# caller is never blocked.
#
# Strict development mode (ORRIN_STRICT env var):
#   ORRIN_STRICT=1    — record_failure() re-raises programmer errors (NameError,
#                       AttributeError, etc.) so typos and refactor breakage fail
#                       loudly instead of becoming ignorable warnings.
#   ORRIN_STRICT=all  — record_failure() re-raises every exception it is handed.
#
# guard(site) — context manager for wrapping a fallible block:
#   with guard("module.operation"):
#       risky_io()
# Records any exception under `site` and swallows it (or re-raises per strict mode).
from __future__ import annotations
from core.runtime_log import get_logger

import contextlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
_log = get_logger(__name__)

_STRICT = os.environ.get("ORRIN_STRICT", "").strip().lower()

# Exception types that almost always mean a code bug, not an environmental
# failure — these are what ORRIN_STRICT=1 refuses to swallow.
_PROGRAMMER_ERRORS = (
    NameError,          # includes UnboundLocalError
    AttributeError,
    ImportError,        # includes ModuleNotFoundError
    SyntaxError,        # includes IndentationError
    TypeError,
)

# ValueError is usually environmental (bad data), but a tuple-unpack mismatch is
# a shape bug at a module boundary — the exact class that crashed the coherence
# check for months while record_failure swallowed it.
_UNPACK_PATTERNS = ("too many values to unpack", "not enough values to unpack")


class ContractViolation(Exception):
    """A named boundary-contract failure (wrong shape/arity at a module seam).

    record_failure() re-raises this under any strict mode regardless of type —
    a contract that fires silently would defeat its purpose.
    """


def strict_should_reraise(exc: BaseException) -> bool:
    """True if the current ORRIN_STRICT setting says `exc` must propagate."""
    if not _STRICT or _STRICT in ("0", "false", "no"):
        return False
    if _STRICT == "all":
        return True
    if isinstance(exc, ContractViolation):
        return True
    if isinstance(exc, ValueError) and any(p in str(exc) for p in _UNPACK_PATTERNS):
        return True
    return isinstance(exc, _PROGRAMMER_ERRORS)

_JSONL_MAX_BYTES = 10 * 1024 * 1024   # 10 MB before rotation
_LOG_COOLDOWN_S  = 60.0                # max one JSONL write per site per minute

_lock         : threading.Lock            = threading.Lock()
_counters     : Dict[str, Dict[str, Any]] = {}   # site → {count, first_seen, last_seen, last_error}
_last_logged  : Dict[str, float]          = {}   # site → epoch of last JSONL write

_data_dir_cache: Optional[Path] = None


def _data_dir() -> Path:
    global _data_dir_cache
    if _data_dir_cache is None:
        try:
            from paths import DATA_DIR
            _data_dir_cache = DATA_DIR
        except Exception:
            _data_dir_cache = Path(__file__).resolve().parent.parent / "data"
    return _data_dir_cache


def record_failure(site: str, exc: Exception) -> None:
    """
    Record a failure at `site`.  Thread-safe; never raises in normal operation.
    Under ORRIN_STRICT (see module docstring) re-raises `exc` after recording,
    so development runs fail loudly on programmer errors.

    site  — stable short identifier, e.g. "env_snapshot._lm_total"
    exc   — the caught exception
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    now_t   = time.monotonic()
    err_str = f"{type(exc).__name__}: {str(exc)}"[:200]

    with _lock:
        if site not in _counters:
            _counters[site] = {
                "count":      0,
                "first_seen": now_iso,
                "last_seen":  now_iso,
                "last_error": err_str,
            }
        rec = _counters[site]
        rec["count"]      += 1
        rec["last_seen"]   = now_iso
        rec["last_error"]  = err_str

        # Decide whether to write to JSONL this tick
        last_t = _last_logged.get(site, 0.0)
        should_log = (now_t - last_t) >= _LOG_COOLDOWN_S
        if should_log:
            _last_logged[site] = now_t

    if should_log:
        # Surface the failure on the dashboard's Live Console (UI_FIXES Fix 10.5).
        # We're already inside the rate-limited branch (≤1/min per site), so this
        # can't flood the socket. Fail-safe like every other telemetry emit — a
        # missing/dead bridge must never block the caller.
        try:
            from backend.telemetry_bridge import get_bridge
            get_bridge().log("error", site, err_str)
        except Exception:
            pass

        # Append to JSONL outside the lock (file IO)
        try:
            path = _data_dir() / "failures.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)

            # Rotate if over size limit
            try:
                if path.exists() and path.stat().st_size > _JSONL_MAX_BYTES:
                    path.replace(path.with_suffix(".jsonl.1"))
            except Exception as _e:
                _log.warning("silent except: %s", _e)

            line = json.dumps(
                {"ts": now_iso, "site": site, "error": err_str},
                ensure_ascii=False,
            ) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

    if strict_should_reraise(exc):
        raise exc


@contextlib.contextmanager
def guard(site: str) -> Iterator[None]:
    """
    Wrap a fallible block: record any exception under `site` and swallow it.
    Under ORRIN_STRICT the exception propagates instead (via record_failure).

        with guard("module.operation"):
            risky_io()
    """
    try:
        yield
    except Exception as e:
        record_failure(site, e)


def get_summary() -> Dict[str, Any]:
    """Return a copy of the current in-memory failure counters, sorted by count desc."""
    with _lock:
        return {
            site: dict(data)
            for site, data in sorted(
                _counters.items(), key=lambda x: -x[1]["count"]
            )
        }


def dump_summary() -> None:
    """
    Write the current failure summary to data/failure_summary.json.
    No-op if there are no recorded failures.  Never raises.
    """
    summary = get_summary()
    if not summary:
        return
    try:
        path = _data_dir() / "failure_summary.json"
        tmp  = path.with_suffix(".json.tmp")
        payload = json.dumps(
            {
                "updated": datetime.now(timezone.utc).isoformat(),
                "total_sites": len(summary),
                "sites": summary,
            },
            indent=2,
            ensure_ascii=False,
        )
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except Exception as _e:
        _log.warning("silent except: %s", _e)
