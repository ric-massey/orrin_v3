# brain/behavior/presence_notify.py
#
# P1 (Companion & Presence plan): the budget-gated OS-notification channel for
# SPONTANEOUS speech. face_bridge.deliver_reply() used to drop utterances with
# no pending Face message; now that branch lands here. Rarity is the entire
# game (§0.2): nothing reaches the OS unless its source cycle IGNITED (the
# existing salience gate — the flag is plumbed in by the caller, never
# re-decided here) AND it fits a hard budget:
#
#   * ≥ ORRIN_NOTIFY_MIN_INTERVAL_S between notifications (default 45 min)
#   * ≤ ORRIN_NOTIFY_DAILY_CAP per rolling 24 h (default 3)
#   * quiet hours respected (ORRIN_NOTIFY_QUIET, local "22-8" by default)
#
# Delivery: the tray sink first (backend/server/tray.py — pystray Icon.notify),
# then the cross-platform notify_user skill (osascript / PowerShell /
# notify-send). Every outward act leaves a record (§0.6): delivered
# notifications are appended to the budget ledger, the activity log, and —
# when should_speak() hasn't already written it — chat_log.json, so the Face
# shows what he said while you were away.
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import List

from brain.paths import CHAT_LOG_FILE, PRESENCE_NOTIFY_FILE
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity


def _min_interval_s() -> float:
    return float(os.environ.get("ORRIN_NOTIFY_MIN_INTERVAL_S", 45 * 60))


def _daily_cap() -> int:
    return int(os.environ.get("ORRIN_NOTIFY_DAILY_CAP", 3))


def _quiet_hours() -> tuple[int, int] | None:
    """Local quiet window as (start_hour, end_hour), possibly wrapping midnight.
    ORRIN_NOTIFY_QUIET="22-8" (default) → no notifications from 22:00 to 07:59.
    "off" disables the window."""
    raw = os.environ.get("ORRIN_NOTIFY_QUIET", "22-8").strip().lower()
    if raw in ("", "off", "none", "0"):
        return None
    try:
        start_s, end_s = raw.split("-", 1)
        start, end = int(start_s) % 24, int(end_s) % 24
        return (start, end) if start != end else None
    except ValueError:
        return None


def _in_quiet_hours(now: float) -> bool:
    window = _quiet_hours()
    if window is None:
        return False
    start, end = window
    hour = datetime.fromtimestamp(now).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps midnight


def _load_sent() -> List[float]:
    sent: list = load_json(PRESENCE_NOTIFY_FILE, default_type=list)
    return [float(t) for t in sent if isinstance(t, (int, float))] if isinstance(sent, list) else []


def budget_allows(now: float | None = None) -> bool:
    """True when the rarity budget has room right now (does not consume it)."""
    now = time.time() if now is None else now
    if _in_quiet_hours(now):
        return False
    sent = [t for t in _load_sent() if now - t < 24 * 3600.0]
    if len(sent) >= _daily_cap():
        return False
    if sent and now - max(sent) < _min_interval_s():
        return False
    return True


def _record_sent(now: float) -> None:
    sent = [t for t in _load_sent() if now - t < 24 * 3600.0]
    sent.append(now)
    save_json(PRESENCE_NOTIFY_FILE, sent)


def _deliver(text: str) -> bool:
    """Tray sink first; fall back to the cross-platform notify_user skill."""
    try:
        from backend.server.tray import notify as tray_notify
        if tray_notify("Orrin", text):
            return True
    except ImportError:  # intentional: backend absent — skill fallback below
        pass
    except Exception as exc:
        record_failure("presence_notify.tray", exc)
    try:
        from brain.agency.skills.notify_user import notify_user
        r = notify_user({"message": text, "title": "Orrin"})
        return bool(r.get("success")) if isinstance(r, dict) else False
    except Exception as exc:
        record_failure("presence_notify.skill", exc)
        return False


def _append_chat_log(text: str, now: float) -> None:
    """Keep the conversation record complete — unless the speech pipeline
    (should_speak → log_dialogue_pair) already wrote this exact utterance
    moments ago, in which case appending again would duplicate it."""
    try:
        recent: list = load_json(CHAT_LOG_FILE, default_type=list)
        if isinstance(recent, list):
            for entry in recent[-5:]:
                if not (isinstance(entry, dict) and entry.get("role") == "assistant"):
                    continue
                if str(entry.get("content", "")).strip() != text:
                    continue
                try:
                    ts = datetime.fromisoformat(str(entry.get("ts", "")).replace("Z", "+00:00"))
                    if abs(now - ts.timestamp()) < 120.0:
                        return  # already logged by the speech pipeline
                except ValueError:
                    continue
        from brain.cog_memory.chat_log import log_dialogue_pair
        log_dialogue_pair("", text)
    except Exception as exc:  # record trail is best-effort — record the failure
        record_failure("presence_notify.chat_log", exc)


def notify_spontaneous(text: str, *, ignited: bool) -> bool:
    """Offer a spontaneous utterance to the OS. Returns True only when a
    notification was actually shown (and therefore budget was consumed)."""
    text = (text or "").strip()
    if not text:
        return False
    if not ignited:
        return False  # the salience gate is a hard precondition, not a hint
    now = time.time()
    if not budget_allows(now):
        return False
    if not _deliver(text[:240]):
        return False  # delivery failed → budget not consumed; a later try may land
    _record_sent(now)
    _append_chat_log(text, now)
    log_activity(f"[presence] OS notification: {text[:120]}")
    return True
