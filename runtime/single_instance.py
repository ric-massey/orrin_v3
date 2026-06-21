"""Single-instance guard (Phase 4B, extracted from main.py).

A POSIX flock on a lock file in the resolved data dir keeps two brains from running
against the same mind (which would corrupt shared state). The lock fd is owned by
this module — closing it releases the lock, so it's held for the process lifetime
and only released deliberately around a re-exec.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from brain.core.runtime_log import get_logger

_log = get_logger(__name__)

# Keep the lock file object alive — closing it would release the flock.
_lock_fd = None


def acquire() -> None:
    """Take the single-instance flock, or exit(3) if another brain already holds it."""
    global _lock_fd
    try:
        import fcntl
    except Exception:
        return  # non-POSIX: skip the guard rather than block startup
    # The lock lives WITH the mind (the resolved data dir), not in the program
    # folder — so the packaged app locks per-install in its writable dir.
    try:
        from brain.paths import DATA_DIR as _lock_data_dir
    except Exception:
        _lock_data_dir = Path(__file__).resolve().parents[1] / "brain" / "data"
    lock_path = _lock_data_dir / ".orrin.instance.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = open(lock_path, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _lock_fd = fd  # keep alive — closing would release the lock
        print(f"[boot] single-instance lock acquired (pid {os.getpid()})")
    except BlockingIOError:
        # Another Orrin already holds the lock. The common reason for a relaunch is
        # "I closed his window and want it back" — but in Always-thinking mode he's
        # still alive in the background, and pywebview can't open a second window in a
        # new process for the SAME mind. Warn clearly (and notify on a GUI launch where
        # stderr is invisible) instead of dying with a cryptic refusal.
        holder = ""
        try:
            holder = lock_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        always = False
        try:
            from brain.utils import prefs as _prefs
            always = _prefs.get("existence_mode", "sleep") == "always"
        except Exception:
            pass

        who = f" (pid {holder})" if holder else ""
        if always:
            headline = "Orrin is already thinking in the background."
            detail = (
                "He's in 'Always thinking' mode, so he keeps living after his window "
                "closes. Re-opening his window from a new launch isn't supported yet "
                "(one window per process). To see him again, quit the running Orrin"
                f"{(' — e.g. kill ' + holder) if holder else ''} and start him again, "
                "or switch to 'Sleep when closed' in Settings so closing the window "
                "stops him cleanly."
            )
        else:
            headline = f"Orrin is already running{who}."
            detail = "Refusing to start a second brain — two would corrupt his shared state."

        print(f"[boot] {headline}\n[boot] {detail}\n[boot] (lock: {lock_path})", file=sys.stderr)
        # Best-effort desktop notification so a double-click launch isn't a silent exit.
        try:
            from brain.agency.skills.notify_user import notify_user
            notify_user({"title": "Orrin is already running", "message": headline})
        except Exception:
            pass
        sys.exit(3)
    except Exception as _e:
        print(f"[boot] single-instance lock skipped ({_e})")


def release() -> None:
    """Release the single-instance flock so a re-exec'd process can re-acquire it.
    flock is tied to the open file description, and execv inherits open fds, so the
    new image would otherwise deadlock against the lock this process still holds."""
    global _lock_fd
    try:
        if _lock_fd is not None:
            _lock_fd.close()
    except Exception as _e:
        _log.warning("silent except: %s", _e)
    _lock_fd = None
