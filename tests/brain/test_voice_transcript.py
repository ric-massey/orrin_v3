"""The voice transcript (brain/cognition/voice.py) — the separated stream of
what Orrin himself says, as opposed to what the runtime says about him.

The invariants worth locking: only real kinds get through, an utterance is
veiled before it is recorded (no raw signal identifier reaches the transcript),
anything still carrying backend markers is DROPPED rather than cleaned up, a
repeat of the same line doesn't stutter the room, and the ring drains once.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def voice():
    from brain.cognition import voice as mod
    importlib.reload(mod)          # fresh ring + dedupe table per test
    mod.drain()
    return mod


def test_an_utterance_is_recorded_and_drains_once(voice):
    rec = voice.utter("felt", "a strong sense of being stuck", cycle=7)
    assert rec is not None and rec["kind"] == "felt" and rec["cycle"] == 7
    assert [u["text"] for u in voice.drain()] == ["a strong sense of being stuck"]
    assert voice.drain() == []


def test_only_the_declared_kinds_are_his_voice(voice):
    assert voice.utter("narration", "Orrin pruned 2 long memories.") is None
    assert voice.drain() == []


def test_repeats_do_not_stutter_but_alternation_still_speaks(voice):
    assert voice.utter("felt", "weariness") is not None
    assert voice.utter("felt", "weariness") is None
    assert voice.utter("felt", "loneliness") is not None
    assert voice.utter("felt", "weariness") is not None


def test_signal_identifiers_are_veiled_not_quoted(voice):
    rec = voice.utter("prediction", "I thought 'expect impasse_signal rises' — and it felt true.")
    assert rec is not None
    assert "impasse_signal" not in rec["text"]
    assert "being stuck" in rec["text"]


def test_function_identifiers_read_as_words(voice):
    rec = voice.utter("intent", "Find out why look_around keeps winning")
    assert rec is not None and "look around" in rec["text"]


@pytest.mark.parametrize("text", [
    "[goal] internal bookkeeping line",
    "wrote brain/cognition/voice.py",
    "",
    "   ",
])
def test_unspeakable_lines_are_dropped_not_patched(voice, text):
    assert voice.utter("speech", text) is None
    assert voice.drain() == []


def test_the_transcript_is_durable(voice):
    voice.utter("closeout", "Answered: what is a control signal for?")
    rows = voice.recent(10)
    assert rows and rows[-1]["kind"] == "closeout"


def test_utter_never_raises_on_bad_input(voice):
    assert voice.utter("felt", None) is None          # type: ignore[arg-type]
    voice.utter("felt", 12345)                        # coerced, never raised


# ── the emitter: loop/telemetry._emit_voice ──────────────────────────────────

class _StubBridge:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    def update(self, **frame) -> None:
        self.frames.append(frame)


def _emitter(monkeypatch):
    from brain.loop import telemetry as lt
    stub = _StubBridge()
    monkeypatch.setattr(lt, "_TB", stub)
    monkeypatch.setattr(lt, "_TB_UNAVAILABLE", False)
    monkeypatch.setattr(lt, "_LAST_VOICED_GOAL", "")
    return lt, stub


def test_emit_voice_ships_what_was_said(monkeypatch, voice):
    lt, stub = _emitter(monkeypatch)
    voice.utter("felt", "a strong sense of curiosity")
    lt._emit_voice({})
    assert [u["text"] for u in stub.frames[0]["voice"]] == ["a strong sense of curiosity"]
    stub.frames.clear()
    lt._emit_voice({})                       # ring drained — nothing to send
    assert stub.frames == []


def test_committing_to_a_goal_is_an_utterance_once(monkeypatch, voice):
    lt, stub = _emitter(monkeypatch)
    ctx = {"committed_goal": {"id": "g1", "title": "Find out why the same step keeps failing"}}
    lt._emit_voice(ctx)
    said = stub.frames[0]["voice"]
    assert said[0]["kind"] == "intent"
    assert said[0]["text"] == "Find out why the same step keeps failing"
    stub.frames.clear()
    lt._emit_voice(ctx)                      # same goal still committed — not re-said
    assert stub.frames == []


# ── the wiring: real call sites, not just the module ─────────────────────────

def test_the_felt_workspace_winner_reaches_the_transcript(voice):
    """The whole point of the room: what actually won the global workspace is
    what shows up, with no second authoring step in between."""
    from brain.cognition.global_workspace import update_workspace
    ctx = {"affect_state": {"core_signals": {"impasse_signal": 0.82, "motivation": 0.3}},
           "_cycle_index": 41}
    moment = update_workspace(ctx)
    assert moment and moment["content"] == "a strong sense of being stuck"
    said = voice.drain()
    assert [(u["kind"], u["text"], u["cycle"]) for u in said] == [
        ("felt", "a strong sense of being stuck", 41)
    ]


def test_a_structural_winner_is_not_an_utterance(voice):
    """He is aware of a retrieved signal without saying it — only felt content
    (carrying focus_signal) is speech."""
    from brain.cognition.global_workspace import update_workspace
    ctx = {"top_signals": [{"content": "a file changed on disk", "signal_strength": 0.9}]}
    moment = update_workspace(ctx)
    assert moment and moment.get("source") == "signal"
    assert voice.drain() == []
