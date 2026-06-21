# F1 — the Always-thinking tray (backend.server.tray). These cover the parts that are
# safe to assert without bringing up a real status-bar item: the generated icon image
# and the best-effort contract (start() must return False, never raise, when the tray
# can't run — that's what lets main.py fall back to headless-on-close instead of
# trapping the user with a hidden window). The live GUI behavior needs a real desktop.
import pytest

from backend.server.tray import Tray, _make_image


def test_make_image_is_a_64px_rgba_icon():
    img = _make_image()
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_start_returns_false_when_backend_fails(monkeypatch):
    # Simulate the platform integration blowing up: Icon(...).run_detached() raises.
    # Needs the real pystray installed (desktop extra); skip where it's absent so the
    # core suite stays deterministically green without the optional GUI dependency.
    pystray = pytest.importorskip("pystray")

    class _BoomIcon:
        def __init__(self, *a, **k):
            pass

        def run_detached(self, *a, **k):
            raise RuntimeError("no display / platform refused")

    monkeypatch.setattr(pystray, "Icon", _BoomIcon)
    t = Tray()
    assert t.start(on_show=lambda: None, on_quit=lambda: None) is False


def test_start_returns_false_when_pystray_missing(monkeypatch):
    # Simulate pystray not installed: importing it raises → start() returns False.
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *a, **k):
        if name == "pystray":
            raise ImportError("no pystray")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    t = Tray()
    assert t.start(on_show=lambda: None, on_quit=lambda: None) is False


def test_stop_is_safe_when_never_started():
    Tray().stop()  # must not raise
