# Expression membrane — regression tests (EXPRESSION_MEMBRANE_FIX_PLAN 2026-06-14).
#
# Guards the invariant: every person-facing artifact is COMPOSED through the one
# door (behavior.express_to_user) from a Motive + felt state, never POPULATED by
# scraping working memory / symbolic / telemetry representation.
#
# Covers E1-E7:
#   - speakability invariant (one list, no leaked tags/paths)        [E7]
#   - the door composes from a Motive and never ships backend tags   [E1/E2/E3]
#   - a seed carrying [symbolic]...[rule] is reworded, never copied
#   - emitters no longer read working_memory (scrape path is gone)   [E1/E2/E3]
#   - notes are delivered, not only written to a dead outbox         [E4]
#   - each artifact carries a motive with non-empty intent + why
#   - the goal's motive is threaded across the execution boundary    [E6]
import ast
from pathlib import Path

import pytest

import brain.behavior.express_to_user as door
from brain.behavior.express_to_user import Motive, build_motive, compose_from_motive, express_to_user
from brain.behavior.speakability import (
    is_speakable, assert_speakable, strip_internal, SpeakabilityError,
    INTERNAL_MARKERS,
)


_AFFECT = {"affect_state": {"core_signals": {"wonder": 0.7, "positive_valence": 0.4}}}


# ── Speakability invariant (E7) ──────────────────────────────────────────────

def test_is_speakable_accepts_plain_language():
    assert is_speakable("I feel uncertain about the path ahead.")


@pytest.mark.parametrize("bad", [
    "[symbolic] reaper [rule] x",
    "[chunk: 12] thinking",
    "[regulation] NORMAL",
    "see /Users/ric/brain/foo.py for details",
    "wrote to data/announcements.json",
    "✅ done",
    "",
    "   ",
])
def test_is_speakable_rejects_backend_leakage(bad):
    assert not is_speakable(bad)


def test_assert_speakable_raises_on_leak():
    with pytest.raises(SpeakabilityError):
        assert_speakable("[causal] this leaked")
    # passes through clean text unchanged
    assert assert_speakable("just a thought") == "just a thought"


def test_strip_internal_removes_tags_but_keeps_meaning():
    assert strip_internal("[symbolic] a real thought [rule] here") == "a real thought here"
    assert strip_internal("[NORMAL] feeling steady") == "feeling steady"


# ── The door composes from a Motive, never copies backend representation ──────

def test_compose_strips_tags_from_seed_never_passes_through():
    m = Motive(intent="share a finding", why="understand language",
               seed="[symbolic] the origin of writing [rule] x")
    text = compose_from_motive(m, _AFFECT)
    assert is_speakable(text)
    assert "[symbolic]" not in text and "[rule]" not in text


def test_express_to_user_returns_speakable_text_and_stamps_motive(monkeypatch):
    captured = {}

    def fake_route(text, artifact, ctx):
        captured["text"] = text
        captured["artifact"] = artifact
        return True

    monkeypatch.setitem(door._ROUTES, "note", fake_route)
    m = Motive(intent="report a blocker", why="finish the task", recipient="Ric")
    out = express_to_user(m, "note", _AFFECT)

    assert out["success"] is True
    assert is_speakable(out["text"])
    assert captured["artifact"]["motive"]["intent"] == "report a blocker"
    assert captured["artifact"]["motive"]["why"] == "finish the task"
    assert captured["artifact"]["text"] == out["text"]


def test_unknown_channel_is_refused():
    out = express_to_user(Motive(intent="x"), "telepathy", _AFFECT)
    assert out["success"] is False


# ── leave_note composes via the door, carries a motive, never scrapes WM ──────

def test_leave_note_composes_and_does_not_leak_working_memory(monkeypatch):
    captured = {}

    def fake_route(text, artifact, ctx):
        captured["text"] = text
        captured["artifact"] = artifact
        return True

    monkeypatch.setitem(door._ROUTES, "note", fake_route)
    import brain.cognition.leave_note as ln

    ctx = {
        "affect_state": {"core_signals": {"impasse_signal": 0.8, "negative_valence": 0.5}},
        "committed_goal": {"id": "g1", "title": "name the obstacle for Ric",
                           "spec": {"description": "tell Ric what is blocking progress"}},
        # backend junk that the OLD scrape path would have emitted verbatim:
        "working_memory": [{"content": "[chunk: 99] internal junk that must not leak"}],
    }
    ret = ln.leave_note(ctx)
    assert ret.startswith("Left a note")
    assert is_speakable(captured["text"])
    assert "junk" not in captured["text"]
    mot = captured["artifact"]["motive"]
    assert mot["intent"] == "leave_note"
    assert mot["why"]  # non-empty, references the goal


# ── E6: the goal's motive is threaded across the execution boundary ──────────

def test_execute_step_action_threads_and_clears_motive():
    import brain.cognition.planning.step_execution as se
    from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS

    seen = {}

    def fake_leave_note(context=None):
        seen["motive"] = build_motive(context or {}, intent="leave_note").to_dict()
        return "Left a note: composed text long enough to count as a real effect."

    COGNITIVE_FUNCTIONS["leave_note"] = {"function": fake_leave_note, "is_cognition": True}

    ctx = {"affect_state": {"core_signals": {"impasse_signal": 0.8}}}
    goal = {"id": "g7", "title": "name the obstacle for Ric",
            "spec": {"description": "tell Ric what blocks progress"}}
    executed, _ = se.execute_step_action(
        "leave_note", ctx, step_text="Note the obstacle for Ric", goal=goal)

    assert executed is True
    assert seen["motive"]["why"] == "tell Ric what blocks progress"
    assert seen["motive"]["goal_id"] == "g7"
    assert "obstacle" in seen["motive"]["intent"].lower()
    # motive is cleared after the act — it never leaks to a later, unrelated act
    assert "_expression_motive" not in ctx


# ── Static guard: expressive emitters never READ working memory (scrape gone) ─

def _emitter_func_sources():
    """Return {name: source} for the three converted emitters."""
    import brain.ORRIN_loop as ORRIN_loop
    srcs = {}

    ln_src = Path(Path(__import__("brain.cognition.leave_note", fromlist=["x"]).__file__)).read_text("utf-8")
    srcs["leave_note"] = ln_src

    loop_src = Path(ORRIN_loop.__file__).read_text("utf-8")
    tree = ast.parse(loop_src)
    loop_lines = loop_src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_write_desktop_note", "_announce"):
            srcs[node.name] = "\n".join(loop_lines[node.lineno - 1: node.end_lineno])
    return srcs


@pytest.mark.parametrize("name", ["leave_note", "_write_desktop_note", "_announce"])
def test_emitter_does_not_read_working_memory(name):
    srcs = _emitter_func_sources()
    assert name in srcs, f"could not locate source for {name}"
    src = srcs[name]
    # The reafference WRITE (update_working_memory(...)) is allowed — only READS
    # of the raw WM list are the scrape we removed.
    assert 'get("working_memory")' not in src
    assert '["working_memory"]' not in src
    assert 'working_memory", []' not in src


# ── Sanity: the shared internal-marker list is the single source of truth ─────

def test_speech_pipeline_uses_shared_marker_list():
    src = Path(__import__("brain.behavior.speech_pipeline", fromlist=["x"]).__file__).read_text("utf-8")
    assert "from brain.behavior.speakability import INTERNAL_MARKERS" in src
    # and it is non-trivial
    assert len(INTERNAL_MARKERS) > 5
