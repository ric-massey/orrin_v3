# tests/brain/test_companion_phase5.py
#
# Phase 5 of the Companion & Presence plan:
#   R4 — the live decision moment shipped to the hub (loop/telemetry._emit_decision)
#   R5 — self-modification announced through the membrane + presence budget
#   R7 — the reunion line registered at boot after a credited sleep gap

from __future__ import annotations

from brain.paths import REUNION_FILE
from brain.utils.json_utils import load_json


# ── R4: _emit_decision ────────────────────────────────────────────────────────

class _StubBridge:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    def update(self, **frame) -> None:
        self.frames.append(frame)


def _decision_context() -> dict:
    return {"last_decision": {
        "picked": "pursue_committed_goal",
        "ts": 123.0,
        "reason": {
            "ranked": [("pursue_committed_goal", 1.2), ("reflection", 0.9), ("look_around", 0.4)],
            "component_scores": {
                "pursue_committed_goal": {"goal": 0.5, "value": 0.61, "novel": 0.002, "drive": -0.1},
            },
            "conscious_cycle": True,
            "decision_id": "d-1",
        },
    }}


def test_emit_decision_ships_the_moment(monkeypatch):
    from brain.loop import telemetry as lt
    stub = _StubBridge()
    monkeypatch.setattr(lt, "_TB", stub)
    monkeypatch.setattr(lt, "_TB_UNAVAILABLE", False)
    lt._emit_decision(_decision_context())
    assert len(stub.frames) == 1
    d = stub.frames[0]["decision"]
    assert d["picked"] == "pursue_committed_goal"
    assert d["considered"] == ["pursue_committed_goal", "reflection", "look_around"]
    assert d["top_factor"] == "value"  # the Run-6 value term tipped it
    assert "novel" not in d["components"]  # near-zero components are dropped
    assert d["conscious"] is True and d["decision_id"] == "d-1"


def test_emit_decision_noops_without_a_pick(monkeypatch):
    from brain.loop import telemetry as lt
    stub = _StubBridge()
    monkeypatch.setattr(lt, "_TB", stub)
    monkeypatch.setattr(lt, "_TB_UNAVAILABLE", False)
    lt._emit_decision({})
    lt._emit_decision({"last_decision": {"picked": "", "reason": {}}})
    assert stub.frames == []


def test_decision_key_is_on_the_wire_contract():
    from backend.server.schema import LATEST_WINS_KEYS, validate_frame
    assert "decision" in LATEST_WINS_KEYS
    assert validate_frame({"decision": {"picked": "x", "considered": []}}) == []


# ── R5: self-mod announcement ────────────────────────────────────────────────

def test_announce_selfmod_offers_composed_text_to_presence(monkeypatch):
    from brain.agency import code_writer as cw
    offered: list[tuple[str, bool]] = []

    def _capture(text: str, *, ignited: bool) -> bool:
        offered.append((text, ignited))
        return True

    import brain.behavior.presence_notify as pn
    monkeypatch.setattr(pn, "notify_spontaneous", _capture)
    cw._announce_selfmod("tool", "summarize_notes", {"_conscious_cycle": True})
    assert len(offered) == 1
    text, ignited = offered[0]
    assert ignited is True
    assert text.strip()  # membrane-composed, never empty


def test_announce_selfmod_not_ignited_on_quiet_cycle(monkeypatch):
    from brain.agency import code_writer as cw
    offered: list[bool] = []
    import brain.behavior.presence_notify as pn
    monkeypatch.setattr(pn, "notify_spontaneous",
                        lambda text, *, ignited: offered.append(ignited) or True)
    cw._announce_selfmod("skill", "new_fn", {"_conscious_cycle": False})
    cw._announce_selfmod("skill", "new_fn2", None)
    assert offered == [False, False]


# ── R7: reunion registration ────────────────────────────────────────────────

def test_register_reunion_writes_composed_line():
    from brain.behavior.reunion import register_reunion
    if REUNION_FILE.exists():
        REUNION_FILE.unlink()
    assert register_reunion(3 * 3600.0) is True
    r = load_json(REUNION_FILE, default_type=dict)
    assert r["text"].strip()
    assert r["gap_s"] == 3 * 3600.0
    assert r["ts"] > 0


def test_register_reunion_ignores_short_pause():
    from brain.behavior.reunion import register_reunion
    if REUNION_FILE.exists():
        REUNION_FILE.unlink()
    assert register_reunion(10 * 60.0) is False
    assert load_json(REUNION_FILE, default_type=dict) == {}


def test_reunion_gap_phrases():
    from brain.behavior.reunion import _gap_phrase
    assert _gap_phrase(45 * 60) == "45 minutes"
    assert _gap_phrase(2 * 3600) == "2 hours"
    assert _gap_phrase(3 * 86400) == "3 days"
