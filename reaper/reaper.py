# reaper/reaper.py
# the kill switch for the main loop

from __future__ import annotations
from core.runtime_log import get_logger
import os
import signal
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Callable

# METRICS: count reaper triggers
try:
    from observability.metrics import reaper_trips_total
except Exception:
    reaper_trips_total = None  # type: ignore
_log = get_logger(__name__)

KillFn = Callable[[str], None]

# Module-level dying state — readable by the cognitive loop
_dying: bool = False
_dying_reason: str = ""
_dying_since: float = 0.0


def is_dying() -> bool:
    return _dying

def dying_reason() -> str:
    return _dying_reason

def dying_since() -> float:
    return _dying_since


def _log_durably(message: str) -> None:
    """
    Persist a reaper event to disk before the process can die. stderr alone is
    not enough: kill is os._exit(), so unflushed/console-only output vanishes
    (the 2026-06-11 deaths were untraceable for exactly this reason).
    """
    try:
        _log.error(message)  # rotating file handler flushes per record
    except Exception:
        pass
    try:
        from utils.log import log_activity
        log_activity(message)
    except Exception:
        pass


@dataclass
class Reaper:
    kill: KillFn
    # How long (seconds) to wait in terminal mode before executing the kill.
    # Set to 0 for immediate kill (original behaviour).
    dying_window_s: float = 45.0

    # Internal: set by trigger(), read by the cognitive loop via module globals
    _triggered: bool = field(default=False, init=False, repr=False)

    def trigger(self, reason: str) -> None:
        global _dying, _dying_reason, _dying_since

        if reaper_trips_total is not None:
            try:
                reaper_trips_total.labels(reason=reason.split()[0]).inc()
            except Exception as _e:
                _log.warning("silent except: %s", _e)

        print(f"[REAPER] Shutdown triggered: {reason}", file=sys.stderr)

        if self._triggered:
            return  # don't double-fire
        self._triggered = True

        _log_durably(f"[REAPER] Shutdown triggered: {reason}")

        if self.dying_window_s <= 0:
            self.kill(reason)
            return

        # Enter dying window — cognitive loop reads _dying and enters terminal mode
        _dying = True
        _dying_reason = reason
        _dying_since = time.time()

        def _deferred_kill():
            time.sleep(self.dying_window_s)
            print(f"[REAPER] Dying window elapsed — executing kill ({reason})", file=sys.stderr)
            _log_durably(f"[REAPER] Dying window elapsed — executing kill ({reason})")
            self.kill(reason)

        t = threading.Thread(target=_deferred_kill, name="reaper-kill", daemon=True)
        t.start()


# --- ready-to-use kill strategies ---

def kill_current_process(_: str) -> None:
    os._exit(1)

def signal_pid(pid: int, sig: int = signal.SIGTERM) -> KillFn:
    def _kill(reason: str) -> None:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            print(f"[REAPER] PID {pid} not found", file=sys.stderr)
    return _kill
