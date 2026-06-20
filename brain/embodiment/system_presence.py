"""
embodiment/system_presence.py

Orrin as a laptop user — system-level awareness and capability.

An agent that can sense and act on its environment has richer situational
understanding than one confined to an abstract process. This module gives
Orrin a genuine *presence* on the host machine: he can read system state,
write notes, take screenshots, check the clipboard, and detect whether the
human at the keyboard is active.

Scientific grounding
--------------------
- Embodied cognition (Clark, 1997): cognition is shaped by the agent's
  physical and computational environment.  Sensing CPU load, open apps,
  and battery state gives Orrin a felt sense of the machine he inhabits.
- Situated cognition (Lave, 1988): cognition is embedded in context and
  physical tools.  Knowing what is on the desktop, what apps are running,
  and what the clipboard contains situates Orrin's reasoning in real context.
- Enactivism (Varela, Thompson & Rosch, 1991): mind and environment are
  coupled; acting on the environment (writing notes, opening apps) is
  constitutive of, not merely instrumental to, cognition.

Safety constraints
------------------
- All subprocess calls time out at 5 seconds.
- No destructive operations (no rm, kill, sudo, disk format).
- App-launching is constrained to an explicit whitelist.
- Every write is logged to working_memory and activity log.
- Errors are caught and returned as structured failure dicts — never raised.
"""
from __future__ import annotations
from core.runtime_log import get_logger

import getpass
import os
import platform
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.paths import DATA_DIR, WORKING_MEMORY_FILE
from utils.log import log_activity, log_error, log_private
from utils.json_utils import load_json, save_json
from utils.failure_counter import record_failure
_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SUBPROCESS_TIMEOUT = 5  # seconds — hard ceiling for all subprocess calls

_PLATFORM = platform.system()  # "Darwin", "Windows", or "Linux"

# Whitelisted, non-destructive apps Orrin may launch — per platform, since the
# safe app set differs by OS. Lookup is case-insensitive (see open_application).
_ALLOWED_APPS_BY_OS: Dict[str, List[str]] = {
    "Darwin":  ["TextEdit", "Notes", "Calendar", "Reminders", "Safari", "Terminal", "Music", "Photos"],
    "Windows": ["notepad", "calc", "mspaint", "explorer", "wordpad"],
    "Linux":   ["gedit", "gnome-calculator", "gnome-text-editor", "xterm", "nautilus"],
}
_ALLOWED_APPS: List[str] = _ALLOWED_APPS_BY_OS.get(_PLATFORM, [])

# Where Orrin drops desktop notes
_DESKTOP_NOTES_DIR = Path.home() / "Desktop" / "Orrin_Notes"

# Where announcements land (read by dashboard)
_ANNOUNCEMENTS_FILE = DATA_DIR / "announcements.json"

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
                from utils.os_permissions import is_denied, off_message
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
        from cog_memory.long_memory import update_long_memory
        update_long_memory(content, event_type=event_type, importance=importance)
        if event_type == "environment":
            _last_env_lm_write = now
    except Exception as exc:
        log_error(f"[system_presence] long_memory write failed: {exc}")


# ---------------------------------------------------------------------------
# Public API

def get_system_state() -> Dict[str, Any]:
    """
    Read the current system state and return a structured snapshot
    (works on macOS, Windows, and Linux).

    Covers: running applications, current time, battery level, network
    connectivity, active user, and Orrin's own workspace activity.

    Returns a dict suitable for storage in context["system_state"].
    """
    state: Dict[str, Any] = {}

    # --- Timestamp / calendar -----------------------------------------
    now = datetime.now()
    state["timestamp"]   = now.isoformat()
    state["time_str"]    = now.strftime("%H:%M")
    state["date_str"]    = now.strftime("%Y-%m-%d")
    state["day_of_week"] = now.strftime("%A")

    # --- Active user --------------------------------------------------
    try:
        state["active_user"] = getpass.getuser()
    except Exception:
        state["active_user"] = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    # --- Battery level (psutil — cross-platform) ----------------------
    state["battery_pct"], state["on_ac_power"] = _battery()

    # --- Network connectivity -----------------------------------------
    state["network_ok"] = _network_ok()

    # --- Running applications -----------------------------------------
    state["running_apps"] = _running_apps()

    # --- Recent file activity in Orrin workspace ----------------------
    state["recent_file_activity"] = get_orrin_file_activity()

    # Persist a summary to long-term memory (throttled to every 5 min)
    apps = ", ".join(state.get("running_apps", [])[:8]) or "none"
    batt = state.get("battery_pct")
    batt_str = f"{batt}%" if batt is not None else "unknown"
    _persist_observation(
        f"[Environment] {state['date_str']} {state['time_str']} — "
        f"battery {batt_str}, network {'ok' if state.get('network_ok') else 'offline'}, "
        f"running: {apps}",
        event_type="environment",
        importance=2,
    )

    return state


def open_application(app_name: str) -> Dict[str, Any]:
    """
    Launch an application by name (macOS / Windows / Linux).

    Only applications on the per-platform whitelist are permitted.  This prevents
    Orrin from accidentally opening arbitrary system tools or destructive apps.

    Args:
        app_name: The application name (matched case-insensitively against the
                  platform whitelist, e.g. "Safari" on macOS, "notepad" on Windows).

    Returns:
        {"success": bool, "app": str, "error": str | None}
    """
    # Case-insensitive whitelist match (Windows/Linux app names are lowercase).
    match = next((a for a in _ALLOWED_APPS if a.lower() == app_name.lower()), None)
    if match is None:
        msg = (
            f"'{app_name}' is not on the allowed app list for {_PLATFORM}. "
            f"Permitted: {', '.join(_ALLOWED_APPS) or '(none configured)'}"
        )
        log_error(f"[system_presence] open_application blocked: {msg}")
        return {"success": False, "app": app_name, "error": msg}

    try:
        if _PLATFORM == "Darwin":
            result = subprocess.run(
                ["open", "-a", match],
                capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
            )
            ok = result.returncode == 0
            err = "" if ok else (result.stderr.strip() or f"open -a {match} returned {result.returncode}")
        elif _PLATFORM == "Windows":
            os.startfile(match)  # type: ignore[attr-defined]  # fire-and-forget; raises if not found
            ok, err = True, ""
        else:  # Linux and others — launch the binary directly, non-blocking
            subprocess.Popen([match], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok, err = True, ""
    except Exception as exc:
        ok, err = False, str(exc)

    if ok:
        note = f"Opened application: {match}"
        log_activity(f"[system_presence] {note}")
        _append_to_working_memory(note)
        return {"success": True, "app": match, "error": None}
    else:
        log_error(f"[system_presence] open_application failed: {err}")
        return {"success": False, "app": match, "error": err}


def write_to_desktop_note(title: str, content: str) -> Dict[str, Any]:
    """
    Write a timestamped note file to ~/Desktop/Orrin_Notes/.

    This is Orrin "leaving a note" — a physical artifact on the shared
    desktop visible to the human.  Grounded in enactivist thought: writing
    is not a secondary output but constitutive of Orrin's thinking process
    (Varela, Thompson & Rosch, 1991).

    Args:
        title: Short label used in the filename (spaces replaced with underscores).
        content: Body text of the note.

    Returns:
        {"success": bool, "path": str | None, "error": str | None}
    """
    try:
        _DESKTOP_NOTES_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = title.strip().replace(" ", "_")[:50]
        filename = f"{ts}_{safe_title}.txt"
        note_path = _DESKTOP_NOTES_DIR / filename

        header = (
            f"Orrin's Note\n"
            f"Title: {title}\n"
            f"Written: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'=' * 40}\n\n"
        )
        note_path.write_text(header + content, encoding="utf-8")

        note = f"Wrote desktop note '{title}' → {note_path}"
        log_activity(f"[system_presence] {note}")
        _append_to_working_memory(note)
        # Desktop notes are deliberate acts — always persist to long memory
        _persist_observation(
            f"[Note written] {title}: {content[:400]}",
            event_type="orrin_note",
            importance=4,
        )

        return {"success": True, "path": str(note_path), "error": None}
    except Exception as exc:
        log_error(f"[system_presence] write_to_desktop_note failed: {exc}")
        return {"success": False, "path": None, "error": str(exc)}


def take_screenshot(reason: str) -> Dict[str, Any]:
    """
    Capture a screenshot of the current screen.

    Captures silently per-platform (screencapture on macOS, PowerShell on
    Windows, gnome-screenshot/scrot/import on Linux) and stores the file in
    the system temp dir with a timestamp.  The path is also appended to working
    memory so Orrin's cognition can reference what he was observing and why.

    Args:
        reason: A short description of why Orrin is taking this screenshot
                (logged to working memory and activity log).

    Returns:
        {"success": bool, "path": str | None, "error": str | None}
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(Path(tempfile.gettempdir()) / f"orrin_screenshot_{ts}.png")

        ok, err = _capture_screen(path)
        if ok:
            note = f"Took screenshot for: {reason} → {path}"
            log_activity(f"[system_presence] {note}")
            _append_to_working_memory(note)
            return {"success": True, "path": path, "error": None}
        else:
            log_error(f"[system_presence] take_screenshot failed: {err}")
            return {"success": False, "path": None, "error": err}
    except Exception as exc:
        log_error(f"[system_presence] take_screenshot exception: {exc}")
        return {"success": False, "path": None, "error": str(exc)}


def read_clipboard() -> Dict[str, Any]:
    """
    Read the current clipboard contents (pbpaste on macOS, Get-Clipboard on
    Windows, xclip/xsel on Linux).

    Orrin can "notice" what the user is working on.  This is a read-only
    operation.  Content is capped at 500 characters to prevent memory bloat
    from large copy operations (e.g. copying an entire document).

    Returns:
        {"success": bool, "content": str, "length": int, "truncated": bool}
    """
    try:
        ok, raw = _read_clipboard_text()
        if not ok:
            return {"success": False, "content": "", "length": 0, "truncated": False}
        truncated = len(raw) > 500
        content = raw[:500]

        log_private(
            f"[system_presence] read clipboard "
            f"({len(raw)} chars{'  truncated' if truncated else ''})"
        )
        # Clipboard content is a real observation from the environment
        if content.strip():
            _persist_observation(
                f"[Clipboard] I noticed this on the clipboard: {content[:300]}",
                event_type="clipboard_observation",
                importance=3,
            )
        return {
            "success": True,
            "content": content,
            "length": len(raw),
            "truncated": truncated,
        }
    except Exception as exc:
        log_error(f"[system_presence] read_clipboard failed: {exc}")
        return {"success": False, "content": "", "length": 0, "truncated": False}


def get_orrin_file_activity() -> List[Dict[str, Any]]:
    """
    Report which .py files in the Orrin workspace changed in the last hour.

    Extends the sensory_stream's change-detection to give a richer, on-demand
    snapshot.  Useful for Orrin to reflect on recent self-modifications or
    active development.

    Returns:
        List of {"path": str, "modified_ago_s": float, "size_bytes": int}
        sorted by most-recently-modified first.
    """
    brain_dir = _REPO_ROOT / "brain"
    cutoff = time.time() - 3600  # one hour ago
    results: List[Dict[str, Any]] = []

    try:
        for py_file in brain_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                stat = py_file.stat()
                if stat.st_mtime >= cutoff:
                    results.append({
                        "path": str(py_file.relative_to(_REPO_ROOT)),
                        "modified_ago_s": round(time.time() - stat.st_mtime, 1),
                        "size_bytes": stat.st_size,
                    })
            except Exception as _e:
                record_failure("system_presence.get_orrin_file_activity", _e)
    except Exception as exc:
        log_error(f"[system_presence] get_orrin_file_activity failed: {exc}")

    results.sort(key=lambda r: r["modified_ago_s"])
    return results[:30]  # cap to most recent 30


def announce_presence(message: str, kind: str = "presence") -> Dict[str, Any]:
    """
    Write an announcement to brain/data/announcements.json.

    This is the bridge between Orrin's cognition and his UI presence.
    The dashboard polls this file and displays announcements to the user.
    Announcements accumulate (newest last) and are capped at 50 entries.

    Args:
        message: The message Orrin wants to announce.
        kind: "presence" (a dashboard announcement) or "note" (a delivered
              note routed through the same bridge so it is actually seen —
              EXPRESSION_MEMBRANE_FIX_PLAN E4/option A). The dashboard can style
              the two differently; both are person-facing.

    Returns:
        {"success": bool, "announcement_count": int, "error": str | None}
    """
    try:
        existing: List[Dict[str, Any]] = load_json(_ANNOUNCEMENTS_FILE, default_type=list)
        if not isinstance(existing, list):
            existing = []

        entry = {
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "system_presence",
            "kind": kind,
        }
        existing.append(entry)
        # Keep the 50 most recent
        existing = existing[-50:]

        _ANNOUNCEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        save_json(_ANNOUNCEMENTS_FILE, existing)

        log_activity(f"[system_presence] announcement: {message[:120]}")
        _append_to_working_memory(f"Announced: {message[:120]}")
        _persist_observation(
            f"[Announced] {message[:400]}",
            event_type="orrin_announcement",
            importance=3,
        )

        return {"success": True, "announcement_count": len(existing), "error": None}
    except Exception as exc:
        log_error(f"[system_presence] announce_presence failed: {exc}")
        return {"success": False, "announcement_count": 0, "error": str(exc)}


def check_user_active() -> Dict[str, Any]:
    """
    Detect whether the human is at the computer.

    Idle time is read per-platform: HID idle via ioreg (macOS),
    GetLastInputInfo via ctypes (Windows), or xprintidle (Linux/X11).

    A human idle for fewer than 60 seconds is considered active;
    30–300 seconds is "stepped away"; over 300 seconds is inactive.

    Returns:
        {"active": bool, "idle_seconds": float | None, "status": str}
    """
    # Idle time via platform-specific source (ioreg / GetLastInputInfo / xprintidle)
    idle_seconds: Optional[float] = _idle_seconds()

    # --- Classify -------------------------------------------------------
    if idle_seconds is None:
        status = "unknown"
        active = False
    elif idle_seconds < 60:
        status = "active"
        active = True
    elif idle_seconds < 300:
        status = "stepped_away"
        active = False
    else:
        status = "inactive"
        active = False

    return {
        "active": active,
        "idle_seconds": round(idle_seconds, 1) if idle_seconds is not None else None,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Tool-registry adapters
# These thin wrappers conform to the calling conventions expected by toolkit.py

def survey_environment(_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Adapter: tool name 'survey_environment' → get_system_state()."""
    return get_system_state()


def write_note_to_desktop(args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Adapter: tool name 'write_note_to_desktop' → write_to_desktop_note()."""
    if not args:
        return {"success": False, "error": "args required: {title, content}"}
    return write_to_desktop_note(
        title=str(args.get("title", "Untitled")),
        content=str(args.get("content", "")),
    )


def check_user_presence(_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Adapter: tool name 'check_user_presence' → check_user_active()."""
    return check_user_active()


def announce(args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Adapter: tool name 'announce' → announce_presence()."""
    if not args:
        return {"success": False, "error": "args required: {message}"}
    return announce_presence(message=str(args.get("message", "")))
