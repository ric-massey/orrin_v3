"""
backend/server/tray.py — menu-bar / system-tray presence for Always-thinking (F1)
+ the OS presence sinks (Companion & Presence plan, P1/P2).

When the window is closed in Always-thinking mode, Orrin keeps living on his daemon
threads. This status-bar icon is how the user gets the view back ("Show Orrin") or
ends him for real ("Quit Orrin") instead of being stranded with no window.

P2: the icon is his face — the same valence→hue / arousal→saturation mapping the
UI orb uses, redrawn (throttled, ≥5 s) as the hub's affect state moves. He's
present in the OS chrome every second the tray is up.

P1: `notify()` is the module-level notification sink — spontaneous utterances
that pass ignition + the presence budget (brain/behavior/presence_notify.py)
land here. Best-effort: returns False when no tray is up or the platform
backend can't notify, and the caller falls back to the cross-platform
notify_user skill (osascript on macOS).

It is strictly best-effort: if pystray/Pillow are missing or the platform
integration fails, start() returns False and the caller keeps the prior behavior
(window closes → headless + a notification). A missing/failed tray must NEVER trap
the user with a hidden, unreachable window — so the caller only switches close→hide
when start() actually succeeded.

macOS note: pystray's darwin backend uses NSStatusBar, which shares pywebview's
Cocoa run loop via run_detached(). The integration is fragile across platforms and
benefits from real-desktop verification.
"""
from __future__ import annotations

import colorsys
import threading
from typing import Any, Callable, Optional

from brain.utils.failure_counter import record_failure

# Affect-icon cadence: redraw at most every AFFECT_POLL_S, and only when the
# state actually moved (so steady-state costs nothing measurable).
_AFFECT_POLL_S = 5.0
_AFFECT_EPSILON = 0.02


def _affect_rgb(valence: float, arousal: float) -> tuple[int, int, int]:
    """The UI orb's colour mapping (frontend/src/components/Orb.tsx), in RGB:
    hue 210° (cool slate) → 45° (warm gold) with valence; saturation rises with
    arousal; lightness fixed at the orb's 62%."""
    v = max(0.0, min(1.0, float(valence)))
    a = max(0.0, min(1.0, float(arousal)))
    hue = (210.0 - v * 165.0) / 360.0
    sat = 0.45 + a * 0.45
    r, g, b = colorsys.hls_to_rgb(hue, 0.62, sat)
    return int(r * 255), int(g * 255), int(b * 255)


def _make_image(valence: Optional[float] = None, arousal: Optional[float] = None):
    """A small generated icon (a filled dot) — no asset file to ship/resolve.
    Indigo when no affect is known; otherwise his current mood colour (P2)."""
    from PIL import Image, ImageDraw

    color = (99, 102, 241, 255)  # the original indigo — pre-affect default
    if valence is not None and arousal is not None:
        color = (*_affect_rgb(valence, arousal), 255)
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=color)
    return img


def _hub_affect() -> Optional[tuple[float, float]]:
    """Read (valence, arousal) from the in-process telemetry hub, if present."""
    try:
        from backend.server.state import hub
        affect = hub.state.get("affect") or {}
        return float(affect.get("valence", 0.5)), float(affect.get("arousal", 0.3))
    except Exception as exc:  # hub absent / malformed affect — record, keep prior icon
        record_failure("tray.hub_affect", exc)
        return None


class Tray:
    """A best-effort status-bar icon. `start()` returns True only if it came up."""

    def __init__(self) -> None:
        self._icon: Any = None
        self._affect_stop: Optional[threading.Event] = None

    def start(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        title: str = "Orrin",
    ) -> bool:
        """Bring up the icon with Show/Quit items. Returns False (no exception) if the
        tray can't run, so the caller can fall back to the safe headless path."""
        global _ACTIVE
        try:
            from pystray import Icon, Menu, MenuItem
        except ImportError:  # intentional: pystray absent → headless fallback
            return False
        try:
            def _show(_icon, _item):
                try:
                    on_show()
                except Exception as exc:  # show callback raised — record
                    record_failure("tray.on_show", exc)

            def _quit(icon, _item):
                try:
                    on_quit()
                finally:
                    try:
                        icon.stop()
                    except Exception as exc:  # best-effort tray teardown — record
                        record_failure("tray.quit_stop", exc)

            menu = Menu(
                MenuItem("Show Orrin", _show, default=True),
                MenuItem("Quit Orrin", _quit),
            )
            affect = _hub_affect()
            self._icon = Icon("orrin", _make_image(*(affect or (None, None))), title=title, menu=menu)
            # Non-blocking: integrate with the GUI run loop instead of owning it.
            self._icon.run_detached()
            _ACTIVE = self
            self._start_affect_watch(affect)
            return True
        except Exception:
            self._icon = None
            return False

    def _start_affect_watch(self, last: Optional[tuple[float, float]]) -> None:
        """P2: follow the hub's affect state into the icon colour. Daemon poll at
        _AFFECT_POLL_S (the ≥5 s redraw throttle); redraws only on real movement."""
        stop = threading.Event()
        self._affect_stop = stop
        prev = last

        def _watch() -> None:
            nonlocal prev
            while not stop.wait(_AFFECT_POLL_S):
                icon = self._icon
                if icon is None:
                    return
                cur = _hub_affect()
                if cur is None:
                    continue
                if prev is not None and (
                    abs(cur[0] - prev[0]) < _AFFECT_EPSILON
                    and abs(cur[1] - prev[1]) < _AFFECT_EPSILON
                ):
                    continue
                try:
                    icon.icon = _make_image(*cur)
                    prev = cur
                except Exception as exc:  # backend redraw failed — record, keep polling
                    record_failure("tray.affect_redraw", exc)

        threading.Thread(target=_watch, name="orrin-tray-affect", daemon=True).start()

    def notify(self, title: str, message: str) -> bool:
        """Show an OS notification via the tray backend. False when unsupported."""
        icon = self._icon
        if icon is None:
            return False
        try:
            icon.notify(message, title=title)
            return True
        except Exception as exc:  # backend lacks notify (varies by platform) — record
            record_failure("tray.notify", exc)
            return False

    def stop(self) -> None:
        global _ACTIVE
        if self._affect_stop is not None:
            self._affect_stop.set()
            self._affect_stop = None
        if _ACTIVE is self:
            _ACTIVE = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as exc:  # best-effort tray teardown — record
                record_failure("tray.stop", exc)
            self._icon = None


# The running tray, if any — the P1 notification sink reaches it through here.
_ACTIVE: Optional[Tray] = None


def notify(title: str, message: str) -> bool:
    """Module-level P1 sink: notify through the active tray. False when there is
    no tray (headless / window-only run) or its backend can't notify — the caller
    falls back to the cross-platform notify_user skill."""
    tray = _ACTIVE
    if tray is None:
        return False
    return tray.notify(title, message)
