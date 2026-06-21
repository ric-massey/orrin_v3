"""Lifecycle-handler registry: stop / reset / restart.

The orchestrator (main.py) registers these handlers at startup and the control
routes invoke them. They live here (not app.py) so the control router can reach
them without importing app.py.

Crucially, the handlers are reached through `has_*()` / `safe_*()` functions, never
by importing the module-level globals: main.py rebinds them at runtime, so a
`from lifecycle import _stop_handler` would freeze the old (None) value. app.py
re-exports the set_*_handler functions, since main.py and tests import them from
`backend.server.app`.
"""
from __future__ import annotations

import contextlib
from typing import Callable, Optional

# A "stop Orrin" handler. When present, the Stop button halts ONLY cognition (loop +
# daemons) and leaves the UI/window up; absent (standalone backend) → caller falls
# back to a full-process SIGINT.
_stop_handler: Optional[Callable[[], None]] = None
# A "reset Orrin" handler — wipes his state to a newborn and re-launches. Absent →
# reset is unavailable (reported honestly) rather than a silent no-op.
_reset_handler: Optional[Callable[[], None]] = None
# A "restart Orrin" handler (stop + re-launch, NO wipe) — used after a Mind Restore
# swaps his state on disk so the new mind loads clean.
_restart_handler: Optional[Callable[[], None]] = None


def set_stop_handler(fn: "Callable[[], None]") -> None:
    global _stop_handler
    _stop_handler = fn


def set_reset_handler(fn: "Callable[[], None]") -> None:
    global _reset_handler
    _reset_handler = fn


def set_restart_handler(fn: "Callable[[], None]") -> None:
    global _restart_handler
    _restart_handler = fn


def has_stop_handler() -> bool:
    return _stop_handler is not None


def has_reset_handler() -> bool:
    return _reset_handler is not None


def has_restart_handler() -> bool:
    return _restart_handler is not None


def safe_stop() -> None:
    """Invoke the registered stop handler, swallowing any error."""
    with contextlib.suppress(Exception):
        if _stop_handler is not None:
            _stop_handler()


def safe_reset() -> None:
    with contextlib.suppress(Exception):
        if _reset_handler is not None:
            _reset_handler()


def safe_restart() -> None:
    with contextlib.suppress(Exception):
        if _restart_handler is not None:
            _restart_handler()
