# brain/embodiment/system_presence_probes.py
#
# Low-level OS probes for system_presence.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. The sandboxed
# subprocess runner (_run) plus the read-only environment probes — battery,
# network, running apps, screen capture, clipboard, idle time — and the
# working-memory / long-memory observation writers. system_presence.py re-imports
# these for its public action API.
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from brain.paths import WORKING_MEMORY_FILE
from brain.utils.log import log_error
from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SUBPROCESS_TIMEOUT = 5  # seconds — hard ceiling for all subprocess calls

_PLATFORM = platform.system()  # "Darwin", "Windows", or "Linux"


# ---------------------------------------------------------------------------
# Internal helpers

def _run(cmd: List[str], *, timeout: int = _SUBPROCESS_TIMEOUT) -> Optional[str]:
    """
    Run a subprocess and return its stdout as a stripped string.
    Returns None on any error (timeout, missing binary, non-zero exit).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cross-platform sensing helpers (psutil + stdlib, no OS-specific binaries)

def _battery() -> tuple[Optional[int], Optional[bool]]:
    """Return (percent, on_ac_power). (None, None) on desktops or if unavailable."""
    try:
        import psutil
        batt = psutil.sensors_battery()
    except Exception:
        return None, None
    if batt is None:
        return None, None
    pct = int(round(batt.percent)) if batt.percent is not None else None
    return pct, bool(batt.power_plugged)


def _network_ok() -> bool:
    """True if a TCP connection to a public DNS server succeeds (no ping needed)."""
    import socket
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=2):
            return True
    except Exception:
        return False


def _running_apps() -> List[str]:
    """Distinct user-facing application/process names, capped at 30."""
    # macOS: parse .app bundles from `ps` for clean, human-facing app names.
    if _PLATFORM == "Darwin":
        ps_out = _run(["ps", "aux"])
        if ps_out:
            names: List[str] = []
            seen: set = set()
            for line in ps_out.splitlines():
                if ".app/Contents/MacOS/" in line:
                    try:
                        name = line.split(".app/Contents/MacOS/")[0].split("/")[-1]
                        if name and name not in seen:
                            names.append(name)
                            seen.add(name)
                    except Exception as _e:
                        record_failure("system_presence._running_apps", _e)
            return names[:30]
    # Windows / Linux (and macOS fallback): distinct process names via psutil.
    try:
        import psutil
    except Exception:
        return []
    names = []
    seen = set()
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").strip()
        except Exception:
            continue
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names[:30]


def _capture_screen(path: str) -> tuple[bool, str]:
    """Capture the full screen to `path` (PNG). Returns (success, error_message)."""
    try:
        if _PLATFORM == "Darwin":
            # §10.6 graceful degradation: if Screen Recording is positively off, say so
            # honestly instead of shelling out and writing a black/empty image.
            try:
                from brain.utils.os_permissions import is_denied, off_message
                if is_denied("screen_recording"):
                    return False, off_message("screen_recording")
            except Exception:
                pass
            r = subprocess.run(["screencapture", "-x", path],
                               capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
            if r.returncode == 0 and Path(path).exists():
                return True, ""
            return False, (r.stderr.strip() or "screencapture returned non-zero")
        if _PLATFORM == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
                "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
                f"$bmp.Save('{path}','Png');$g.Dispose();$bmp.Dispose()"
            )
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
            if r.returncode == 0 and Path(path).exists():
                return True, ""
            return False, (r.stderr.strip() or "powershell screen capture failed")
        # Linux — try common screenshot tools in order of preference
        for tool, args in (("gnome-screenshot", ["-f", path]),
                           ("scrot", [path]),
                           ("import", ["-window", "root", path])):  # import = ImageMagick
            exe = shutil.which(tool)
            if exe:
                r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
                if r.returncode == 0 and Path(path).exists():
                    return True, ""
        return False, "no screenshot tool available (install gnome-screenshot, scrot, or imagemagick)"
    except Exception as exc:
        return False, str(exc)


def _read_clipboard_text() -> tuple[bool, str]:
    """Read clipboard text cross-platform. Returns (success, text)."""
    try:
        if _PLATFORM == "Darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
            return True, r.stdout  # pbpaste exits 0 even when empty
        if _PLATFORM == "Windows":
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                               capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
            if r.returncode == 0:
                # Get-Clipboard appends a trailing newline; strip one level only
                return True, r.stdout.rstrip("\r\n")
            return False, ""
        # Linux — xclip then xsel
        for tool, args in (("xclip", ["-selection", "clipboard", "-o"]),
                           ("xsel", ["--clipboard", "--output"])):
            exe = shutil.which(tool)
            if exe:
                r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
                if r.returncode == 0:
                    return True, r.stdout
        return False, ""
    except Exception:
        return False, ""


def _idle_seconds() -> Optional[float]:
    """Seconds since the last user input (keyboard/mouse), or None if unknown."""
    try:
        if _PLATFORM == "Darwin":
            out = _run(["ioreg", "-c", "IOHIDSystem", "-d", "4", "-k", "HIDIdleTime", "-r"])
            if out:
                import re
                m = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', out)
                if m:
                    return int(m.group(1)) / 1_000_000_000.0  # nanoseconds → seconds
            # Fallback: screensaver running ⇒ treat as long idle
            if _run(["pgrep", "-x", "ScreenSaverEngine"]):
                return 999.0
            return None
        if _PLATFORM == "Windows":
            import ctypes
            class _LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            info = _LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
                millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime  # type: ignore[attr-defined]
                return max(0.0, millis / 1000.0)
            return None
        # Linux — xprintidle reports idle milliseconds (X11 only)
        exe = shutil.which("xprintidle")
        if exe:
            out = _run([exe])
            if out and out.strip().isdigit():
                return int(out.strip()) / 1000.0
        return None
    except Exception:
        return None


def _append_to_working_memory(content: str) -> None:
    """Append a single entry to working_memory.json."""
    try:
        entries = load_json(WORKING_MEMORY_FILE, default_type=list)
        if not isinstance(entries, list):
            entries = []
        entries.append({
            "content": content,
            "source": "system_presence",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        entries = entries[-200:]
        save_json(WORKING_MEMORY_FILE, entries)
    except Exception as exc:
        log_error(f"[system_presence] working_memory write failed: {exc}")


# Throttle: only write environment observations to long_memory every 5 minutes
_last_env_lm_write: float = 0.0
_ENV_LM_INTERVAL: float = 300.0


def _persist_observation(content: str, event_type: str = "environment", importance: int = 2) -> None:
    """Write a significant environmental observation to long-term memory.
    Throttled so routine system polls don't flood the memory store."""
    global _last_env_lm_write
    now = time.time()
    if event_type == "environment" and (now - _last_env_lm_write) < _ENV_LM_INTERVAL:
        return
    try:
        from brain.cog_memory.long_memory import update_long_memory
        update_long_memory(content, event_type=event_type, importance=importance)
        if event_type == "environment":
            _last_env_lm_write = now
    except Exception as exc:
        log_error(f"[system_presence] long_memory write failed: {exc}")
