"""Crash + uncaught-exception logging install (Phase 4B, from main.py).

`install()` arms three things, all of which must persist for the process lifetime:
  • a faulthandler writing native crashes (SIGSEGV/SIGABRT/…) to brain/logs/crash.log
    — the file handle is kept open here; closing it would disarm the handler;
  • sys.excepthook → uncaught main-thread exceptions logged at CRITICAL (not just to a
    terminal that may be gone by morning);
  • threading.excepthook → same for daemon-thread exceptions (the brain loop runs in
    one), which the default hook would only print to a possibly-lost stderr.
"""
from __future__ import annotations

import datetime as _datetime
import faulthandler
import os
import sys
import threading
import traceback as _traceback
from pathlib import Path

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[1]

# Kept open for the process lifetime — closing it disarms faulthandler.
_crash_fp = None


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    tb_text = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
    _log.critical("UNCAUGHT EXCEPTION (main thread):\n%s", tb_text)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _log_thread_uncaught(args) -> None:
    if args.exc_type is SystemExit:
        return
    tb_text = "".join(
        _traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    name = args.thread.name if args.thread is not None else "<unknown>"
    _log.critical("UNCAUGHT EXCEPTION in thread %r:\n%s", name, tb_text)


def install() -> None:
    """Open the crash log, arm faulthandler, and route uncaught exceptions to the log."""
    global _crash_fp
    # Route to the RESOLVED logs dir (honors ORRIN_LOGS_DIR) — defaults to brain/logs
    # in a dev checkout, but a packaged app's program folder is read-only, so the
    # crash log must follow the relocated state tree (Group C). Falls back to the
    # in-repo path if brain.paths can't be imported this early.
    try:
        from brain.paths import LOGS_DIR as _logs_dir
    except Exception:
        _logs_dir = _REPO_ROOT / "brain" / "logs"
    crash_path = _logs_dir / "crash.log"
    crash_path.parent.mkdir(parents=True, exist_ok=True)
    _crash_fp = open(crash_path, "a")
    _crash_fp.write(f"--- session start {_datetime.datetime.now().isoformat()} pid={os.getpid()} ---\n")
    _crash_fp.flush()
    faulthandler.enable(file=_crash_fp, all_threads=True)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_thread_uncaught
