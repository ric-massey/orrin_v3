# tests/brain/test_companion_phase6.py
#
# Phase 6 of the Companion & Presence plan:
#   P4 — real-world note traces are consent-first (prefs "trace_folder",
#        default OFF) with a ≤1/day rarity budget
#   R8 — the bridge fans telemetry to secondary (widget) windows and can
#        dismiss them without touching the main window

from __future__ import annotations

import time

from brain.runtime_coupling import system_presence as sp
from brain.utils.json_utils import load_json, save_json


# ── P4: consent + budget on write_to_desktop_note ────────────────────────────

def _reset_trace_ledger() -> None:
    save_json(sp._TRACE_LEDGER, [])


def test_trace_refused_without_consent(monkeypatch, tmp_path):
    _reset_trace_ledger()
    from brain.utils import prefs
    monkeypatch.setattr(prefs, "get", lambda k, d=None: "" if k == "trace_folder" else d)
    r = sp.write_to_desktop_note("hello", "a first trace")
    assert r["success"] is False
    assert "consent" in r["error"]
    assert load_json(sp._TRACE_LEDGER, default_type=list) == []  # no budget spent


def test_trace_writes_only_into_consented_folder(monkeypatch, tmp_path):
    _reset_trace_ledger()
    folder = tmp_path / "from Orrin"
    from brain.utils import prefs
    monkeypatch.setattr(prefs, "get", lambda k, d=None: str(folder) if k == "trace_folder" else d)
    r = sp.write_to_desktop_note("a thought", "something that moved him")
    assert r["success"] is True
    written = list(folder.glob("*.txt"))
    assert len(written) == 1
    assert "something that moved him" in written[0].read_text()
    # the budget row landed (→ visible discipline, and /actions shows the effect)
    assert len(load_json(sp._TRACE_LEDGER, default_type=list)) == 1


def test_trace_budget_is_one_per_day(monkeypatch, tmp_path):
    _reset_trace_ledger()
    folder = tmp_path / "notes"
    from brain.utils import prefs
    monkeypatch.setattr(prefs, "get", lambda k, d=None: str(folder) if k == "trace_folder" else d)
    assert sp.write_to_desktop_note("one", "first")["success"] is True
    r2 = sp.write_to_desktop_note("two", "second")
    assert r2["success"] is False
    assert "budget" in r2["error"]
    assert len(list(folder.glob("*.txt"))) == 1


def test_trace_budget_reopens_after_a_day(monkeypatch, tmp_path):
    folder = tmp_path / "notes"
    save_json(sp._TRACE_LEDGER, [time.time() - 25 * 3600])
    from brain.utils import prefs
    monkeypatch.setattr(prefs, "get", lambda k, d=None: str(folder) if k == "trace_folder" else d)
    assert sp.write_to_desktop_note("fresh", "a new day")["success"] is True


# ── R8: bridge secondary windows ─────────────────────────────────────────────

class _FakeWindow:
    def __init__(self) -> None:
        self.js: list[str] = []
        self.destroyed = False

    def evaluate_js(self, js: str) -> None:
        self.js.append(js)

    def destroy(self) -> None:
        self.destroyed = True


def _fresh_bridge():
    # __new__ like test_bridge_rebind: constructing the real bridge would spin
    # the FastAPI TestClient (whose lifespan boots cognition).
    from backend.server.bridge import OrrinBridge
    b = OrrinBridge.__new__(OrrinBridge)
    b._window = None
    b._extra_windows = []
    b._subscribed = False
    return b


def test_push_fans_out_to_extra_windows():
    b = _fresh_bridge()
    main, widget = _FakeWindow(), _FakeWindow()
    b.attach_window(main)
    b.attach_extra_window(widget)
    b._push({"type": "delta", "frame": {"cycle": 7}})
    assert len(main.js) == 1 and len(widget.js) == 1


def test_dismiss_widget_destroys_only_extras():
    b = _fresh_bridge()
    main, widget = _FakeWindow(), _FakeWindow()
    b.attach_window(main)
    b.attach_extra_window(widget)
    out = b.dismiss_widget()
    assert out == {"ok": True}
    assert widget.destroyed is True and main.destroyed is False
    # widget gone → pushes reach only the main window
    b._push({"type": "delta", "frame": {}})
    assert len(main.js) == 1 and widget.js == []


def test_detach_main_window_keeps_widget_fed():
    b = _fresh_bridge()
    main, widget = _FakeWindow(), _FakeWindow()
    b.attach_window(main)
    b.attach_extra_window(widget)
    b.detach_window()  # main hidden (Always-thinking) — widget stays live
    b._push({"type": "delta", "frame": {}})
    assert main.js == [] and len(widget.js) == 1
