"""
backend/server/tray.py — menu-bar / system-tray presence for Always-thinking (F1).

When the window is closed in Always-thinking mode, Orrin keeps living on his daemon
threads. This status-bar icon is how the user gets the view back ("Show Orrin") or
ends him for real ("Quit Orrin") instead of being stranded with no window.

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

from typing import Any, Callable

from brain.utils.failure_counter import record_failure


def _make_image():
    """A small generated icon (a filled indigo dot) — no asset file to ship/resolve."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=(99, 102, 241, 255))
    return img


class Tray:
    """A best-effort status-bar icon. `start()` returns True only if it came up."""

    def __init__(self) -> None:
        self._icon: Any = None

    def start(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        title: str = "Orrin",
    ) -> bool:
        """Bring up the icon with Show/Quit items. Returns False (no exception) if the
        tray can't run, so the caller can fall back to the safe headless path."""
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
            self._icon = Icon("orrin", _make_image(), title=title, menu=menu)
            # Non-blocking: integrate with the GUI run loop instead of owning it.
            self._icon.run_detached()
            return True
        except Exception:
            self._icon = None
            return False

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception as exc:  # best-effort tray teardown — record
                record_failure("tray.stop", exc)
            self._icon = None
