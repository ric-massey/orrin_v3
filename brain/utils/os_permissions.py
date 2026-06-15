"""
utils/os_permissions.py — OS capability grant-state for Orrin's body (§10.6).

Orrin has a body (embodiment/system_presence.py): he surveys running apps, reads
idle time, takes screenshots, reads the clipboard, opens allow-listed apps, and
sends notifications. In a signed/notarized macOS app the OS gates exactly these
(TCC); Windows is laxer and Linux varies. Without honest grant-state, a denied
capability would fail silently — the plan's failure mode.

This module gives the Trust screen (§9.4) a per-capability picture: is it granted,
denied, not-needed-on-this-platform, or unknown — plus a deep-link to the right
System Settings pane, and an honest "permission off" sentence the body tools use so
a denial reads as "Orrin can't see your screen (permission off)" instead of a crash
or a cryptic error. Probes are non-prompting where the OS allows it (macOS screen
recording via CGPreflightScreenCaptureAccess); nothing here triggers a TCC prompt.
"""
from __future__ import annotations

import platform
import shutil
from typing import Any, Dict, List

_PLATFORM = platform.system()

# Grant states. "not_required" = the platform doesn't gate this (so it's effectively
# granted); "unknown" = can't be probed without prompting, so we don't guess.
GRANTED = "granted"
DENIED = "denied"
UNKNOWN = "unknown"
NOT_REQUIRED = "not_required"

# macOS System Settings deep-links (open the exact Privacy pane).
_MAC_PANES = {
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
    "automation": "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
}


def _mac_screen_recording_state() -> str:
    """Non-prompting probe of Screen Recording (TCC). Returns granted/denied/unknown.
    CGPreflightScreenCaptureAccess reports the current grant WITHOUT prompting."""
    try:
        import Quartz  # pyobjc; present in the bundle
        return GRANTED if Quartz.CGPreflightScreenCaptureAccess() else DENIED
    except Exception:
        return UNKNOWN


def _screen_recording() -> Dict[str, Any]:
    state = _mac_screen_recording_state() if _PLATFORM == "Darwin" else NOT_REQUIRED
    return {
        "key": "screen_recording",
        "label": "See your screen",
        "why": "Orrin can glance at your screen to notice what you're working on.",
        "state": state,
        "deep_link": _MAC_PANES["screen_recording"] if _PLATFORM == "Darwin" else "",
        "off_message": "Orrin can't see your screen (screen-recording permission is off).",
    }


def _automation() -> Dict[str, Any]:
    # Apple Events / automation can't be preflighted without potentially prompting, so
    # we report "unknown" on macOS rather than guess. Opening allow-listed apps uses
    # `open -a` (ungated); only scripting other apps would trip this.
    state = UNKNOWN if _PLATFORM == "Darwin" else NOT_REQUIRED
    return {
        "key": "automation",
        "label": "Control other apps",
        "why": "Orrin opens apps you allow-list; some actions ask macOS for automation.",
        "state": state,
        "deep_link": _MAC_PANES["automation"] if _PLATFORM == "Darwin" else "",
        "off_message": "Orrin can't control other apps (automation permission is off).",
    }


def _notifications() -> Dict[str, Any]:
    # Notifications work without a TCC prompt on macOS (display notification) and via
    # toast/notify-send elsewhere; treat as not-gated, but flag if the Linux tool is
    # missing so the Trust screen can be honest.
    state = NOT_REQUIRED
    why = "Orrin sends you a notification when he wants to reach you while unwatched."
    if _PLATFORM == "Linux" and not shutil.which("notify-send"):
        state = DENIED
        return {
            "key": "notifications", "label": "Notify you", "why": why, "state": state,
            "deep_link": "",
            "off_message": "Orrin can't notify you (install libnotify-bin / notify-send).",
        }
    return {
        "key": "notifications", "label": "Notify you", "why": why, "state": state,
        "deep_link": "", "off_message": "Orrin can't notify you (notifications are off).",
    }


_CAPABILITIES = (_screen_recording, _automation, _notifications)


def status() -> Dict[str, Any]:
    """Per-capability grant-state for the Trust screen (§9.4)."""
    caps: List[Dict[str, Any]] = [fn() for fn in _CAPABILITIES]
    return {"platform": _PLATFORM, "capabilities": caps}


def capability(key: str) -> Dict[str, Any]:
    for fn in _CAPABILITIES:
        cap = fn()
        if cap["key"] == key:
            return cap
    return {}


def is_denied(key: str) -> bool:
    """True only when we positively know the capability is off — never on 'unknown',
    so the body still tries (and the OS can prompt) rather than refusing pre-emptively."""
    return capability(key).get("state") == DENIED


def off_message(key: str) -> str:
    """The honest 'permission off' sentence for a body tool to surface when a gated
    capability is unavailable. Empty if the capability is unknown."""
    return capability(key).get("off_message", "")
