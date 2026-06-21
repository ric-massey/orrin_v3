# §10.6 — OS capability grant-state for the Trust screen + graceful degradation.
# These exercise the cross-platform state logic and the honest-failure contract
# without touching real TCC (the macOS probe is monkeypatched).
from brain.utils import os_permissions as op


def test_status_lists_the_body_capabilities():
    caps = {c["key"] for c in op.status()["capabilities"]}
    assert {"screen_recording", "automation", "notifications"} <= caps
    # Every capability carries what the Trust screen renders.
    for c in op.status()["capabilities"]:
        assert c["label"] and c["why"] and c["state"] and "off_message" in c


def test_unknown_is_not_treated_as_denied(monkeypatch):
    # is_denied must be True only when we POSITIVELY know it's off — otherwise the body
    # still tries and lets the OS prompt, rather than refusing pre-emptively.
    monkeypatch.setattr(op, "_PLATFORM", "Darwin")
    monkeypatch.setattr(op, "_mac_screen_recording_state", lambda: op.UNKNOWN)
    assert op.is_denied("screen_recording") is False


def test_denied_screen_recording_reports_off(monkeypatch):
    monkeypatch.setattr(op, "_PLATFORM", "Darwin")
    monkeypatch.setattr(op, "_mac_screen_recording_state", lambda: op.DENIED)
    assert op.is_denied("screen_recording") is True
    assert "screen" in op.off_message("screen_recording").lower()


def test_granted_screen_recording(monkeypatch):
    monkeypatch.setattr(op, "_PLATFORM", "Darwin")
    monkeypatch.setattr(op, "_mac_screen_recording_state", lambda: op.GRANTED)
    cap = op.capability("screen_recording")
    assert cap["state"] == op.GRANTED
    assert cap["deep_link"].startswith("x-apple.systempreferences:")


def test_non_macos_screen_recording_not_required(monkeypatch):
    monkeypatch.setattr(op, "_PLATFORM", "Linux")
    cap = op.capability("screen_recording")
    assert cap["state"] == op.NOT_REQUIRED
    assert cap["deep_link"] == ""
    assert op.is_denied("screen_recording") is False


def test_off_message_empty_for_unknown_key():
    assert op.off_message("no_such_capability") == ""
