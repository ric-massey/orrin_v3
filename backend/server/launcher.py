"""
backend/server/launcher.py — spawn the Vite UI as a child process.

Pure helpers with no dependency on the FastAPI app, so they can be reused by any
launcher (the standalone `backend/main.py` entry, or the repo-root `main.py` that
also runs the cognitive loop).
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .config import UI_DEV_URL, open_browser_enabled, ui_enabled

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def launch_ui(host: str, port: int) -> Optional[subprocess.Popen]:
    """
    Start the Vite dev server as a child process. Installs npm deps on first run.
    Returns the Popen handle, or None if disabled / unavailable.
    """
    if not ui_enabled():
        print("[orrin] ORRIN_UI=0 → skipping UI launch")
        return None
    if not (_FRONTEND_DIR / "package.json").exists():
        print(f"[orrin] no frontend at {_FRONTEND_DIR} — skipping UI launch")
        return None

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    # The browser's telemetry/API host. Honor an explicit VITE_TELEMETRY_HOST so
    # the backend can bind all interfaces (host=0.0.0.0) while the page still
    # points at a reachable LAN/Tailscale IP. Otherwise derive it from `host`
    # (0.0.0.0/:: → 127.0.0.1, which is only reachable on the server itself).
    safe_host = host if host not in ("0.0.0.0", "::") else "127.0.0.1"
    vite_host = os.environ.get("VITE_TELEMETRY_HOST") or f"{safe_host}:{port}"
    env = {**os.environ, "VITE_TELEMETRY_HOST": vite_host}

    if not (_FRONTEND_DIR / "node_modules").exists():
        print("[orrin] installing UI dependencies (first run)…")
        try:
            subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=str(_FRONTEND_DIR), check=True)
        except Exception as e:
            print(f"[orrin] npm install failed ({e}); run `cd frontend && npm run dev` manually")
            return None

    # Put the child in its own process group/session so we can reliably take down
    # the whole tree (npm → node → vite/esbuild) on shutdown. npm does not forward
    # signals to its grandchildren, so killing the bare npm pid orphans the dev
    # server. See stop_ui() for the matching group-kill.
    if sys.platform == "win32":
        popen_kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        popen_kwargs = {"start_new_session": True}

    try:
        proc = subprocess.Popen([npm, "run", "dev"], cwd=str(_FRONTEND_DIR), env=env, **popen_kwargs)
        print(f"[orrin] UI starting → {UI_DEV_URL}")
        return proc
    except Exception as e:
        print(f"[orrin] could not start UI ({e}); run `cd frontend && npm run dev` manually")
        return None


def stop_ui(proc: Optional[subprocess.Popen], timeout: float = 5.0) -> None:
    """
    Terminate the Vite UI child *and its whole process group* (npm spawns node →
    vite → esbuild grandchildren that a bare proc.terminate() would orphan).
    Escalates SIGTERM → SIGKILL. Safe to call with None or an already-dead proc.
    """
    if proc is None or proc.poll() is not None:
        return

    def _signal_group(sig: int) -> None:
        if sys.platform == "win32":
            # No POSIX process groups; CTRL_BREAK reaches the new group, fall back
            # to terminate()/kill() on the wrapper.
            if sig == signal.SIGKILL:
                proc.kill()
            else:
                proc.terminate()
            return
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            # Group already gone, or we couldn't reach it — fall back to the pid.
            with contextlib.suppress(Exception):
                proc.send_signal(sig)

    _signal_group(signal.SIGTERM)
    try:
        proc.wait(timeout=timeout)
        return
    except Exception:
        pass

    # Still alive after the grace period — hard kill the group.
    _signal_group(signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.wait(timeout=timeout)


def maybe_open_browser(url: str = UI_DEV_URL, delay: float = 2.5) -> None:
    """Open a browser tab to the UI after a short delay, unless disabled."""
    if not open_browser_enabled():
        return
    import threading
    import webbrowser

    threading.Timer(delay, lambda: webbrowser.open(url)).start()
