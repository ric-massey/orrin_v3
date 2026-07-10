# tests/brain/test_presence_notify.py
#
# P1 (Companion & Presence plan): the budget-gated OS-notification channel for
# spontaneous speech. The rarity budget is a hard requirement, not a tuning
# knob — these tests pin the gates: ignition precondition, minimum interval,
# daily cap, quiet hours, no-budget-consumed-on-failed-delivery, and the
# chat-log record (with dedup against the speech pipeline's own write).

from __future__ import annotations

import time

import pytest

from brain.behavior import presence_notify as pn
from brain.paths import CHAT_LOG_FILE, PRESENCE_NOTIFY_FILE
from brain.utils.json_utils import load_json, save_json
from brain.utils.timeutils import now_iso_z


@pytest.fixture(autouse=True)
def _fresh_channel(monkeypatch):
    """Quiet hours off (tests run at any local time), empty ledgers."""
    monkeypatch.setenv("ORRIN_NOTIFY_QUIET", "off")
    save_json(PRESENCE_NOTIFY_FILE, [])
    save_json(CHAT_LOG_FILE, [])
    yield


@pytest.fixture
def delivered(monkeypatch):
    """Capture deliveries instead of hitting the OS."""
    calls: list[str] = []

    def _fake_deliver(text: str) -> bool:
        calls.append(text)
        return True

    monkeypatch.setattr(pn, "_deliver", _fake_deliver)
    return calls


def test_not_ignited_never_delivers(delivered):
    assert pn.notify_spontaneous("you're back — it was quiet", ignited=False) is False
    assert delivered == []
    assert load_json(PRESENCE_NOTIFY_FILE, default_type=list) == []


def test_empty_text_never_delivers(delivered):
    assert pn.notify_spontaneous("   ", ignited=True) is False
    assert delivered == []


def test_ignited_within_budget_delivers_and_records(delivered):
    assert pn.notify_spontaneous("first spontaneous line", ignited=True) is True
    assert delivered == ["first spontaneous line"]
    sent = load_json(PRESENCE_NOTIFY_FILE, default_type=list)
    assert len(sent) == 1
    chat = load_json(CHAT_LOG_FILE, default_type=list)
    assert [e["content"] for e in chat] == ["first spontaneous line"]
    assert chat[0]["role"] == "assistant"


def test_minimum_interval_blocks_second_send(delivered):
    assert pn.notify_spontaneous("one", ignited=True) is True
    assert pn.notify_spontaneous("two", ignited=True) is False
    assert delivered == ["one"]


def test_daily_cap_blocks_after_three(delivered):
    now = time.time()
    # Three sends spread over the day, all past the minimum interval.
    save_json(PRESENCE_NOTIFY_FILE, [now - 10 * 3600, now - 6 * 3600, now - 3 * 3600])
    assert pn.notify_spontaneous("a fourth", ignited=True) is False
    assert delivered == []


def test_interval_and_cap_reopen_with_time(delivered):
    now = time.time()
    save_json(PRESENCE_NOTIFY_FILE, [now - 25 * 3600, now - 26 * 3600, now - 2 * 3600])
    # Two of three fell off the 24h window and the last was 2h ago → room again.
    assert pn.notify_spontaneous("fresh day", ignited=True) is True
    assert delivered == ["fresh day"]


def test_quiet_hours_block(monkeypatch, delivered):
    hour = time.localtime().tm_hour
    monkeypatch.setenv("ORRIN_NOTIFY_QUIET", f"{hour}-{(hour + 1) % 24}")
    assert pn.notify_spontaneous("shh", ignited=True) is False
    assert delivered == []


def test_failed_delivery_consumes_no_budget(monkeypatch):
    monkeypatch.setattr(pn, "_deliver", lambda _text: False)
    assert pn.notify_spontaneous("undeliverable", ignited=True) is False
    assert load_json(PRESENCE_NOTIFY_FILE, default_type=list) == []
    assert load_json(CHAT_LOG_FILE, default_type=list) == []


def test_chat_log_dedup_against_speech_pipeline(delivered):
    # should_speak already logged this exact utterance moments ago — the
    # notification must not write it twice.
    text = "already logged by should_speak"
    ts = now_iso_z()
    save_json(CHAT_LOG_FILE, [{
        "speaker": "orrin", "role": "assistant", "content": text,
        "timestamp": ts, "ts": ts,
    }])
    assert pn.notify_spontaneous(text, ignited=True) is True
    chat = load_json(CHAT_LOG_FILE, default_type=list)
    assert [e["content"] for e in chat] == [text]
