# User input is consumed exactly once (BEHAVIOR_FIX_PLAN 0.2 / audit §3).
#
# get_user_input() returns the last non-empty chat line WITHOUT clearing the
# file, so the same line is visible every cycle until the user speaks again.
# The contract under test: only the FIRST sighting of a line counts as input —
# afterwards the cycle behaves exactly as if the user were silent (no
# user_input signal, no reward release, no reply evaluation, no
# latest_user_input for the speaker to answer).
import types

import pytest

import brain.think.think_utils.user_input as ui_mod
from brain.think.think_utils.user_input import handle_user_input, log_user_input_once


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Route all side effects into counters/tmp files; same line every cycle."""
    calls = types.SimpleNamespace(reward=0, eval_reply=0, summarize=0)

    monkeypatch.setattr(ui_mod, "LAST_SEEN_USER_INPUT", tmp_path / "last_seen.txt")
    monkeypatch.setattr(ui_mod, "get_user_input", lambda: "what has your attention?")

    def _reward(*a, **k):
        calls.reward += 1
    monkeypatch.setattr(ui_mod, "release_reward_signal", _reward)

    def _summarize(*a, **k):
        calls.summarize += 1
    monkeypatch.setattr(ui_mod, "summarize_chat_to_long_memory", _summarize)

    import brain.think.speech_evaluator as se_mod

    def _eval(*a, **k):
        calls.eval_reply += 1
    monkeypatch.setattr(se_mod, "evaluate_last_reply", _eval)

    # Keep the rest of the pipeline inert / off live data files.
    monkeypatch.setattr(ui_mod, "check_violates_boundaries", lambda _c: False)
    monkeypatch.setattr(ui_mod, "update_last_active", lambda: None)
    monkeypatch.setattr(ui_mod, "read_recent_errors_txt", lambda *a, **k: [])
    monkeypatch.setattr(ui_mod, "read_recent_errors_jsonl", lambda *a, **k: [])

    import brain.cognition.novelty as wonder_mod
    monkeypatch.setattr(wonder_mod, "detect_novelty_trigger", lambda *a, **k: None)
    import brain.cognition.comprehension as comp_mod
    monkeypatch.setattr(comp_mod, "comprehend", lambda *a, **k: None)
    import brain.cognition.self_state.values_check as vc_mod
    monkeypatch.setattr(vc_mod, "evaluate_input_against_self",
                        lambda *a, **k: (False, ""))
    import brain.utils.self_model as sm_mod
    monkeypatch.setattr(sm_mod, "get_self_model", lambda *a, **k: {})

    return calls


def _run_cycles(n, context=None):
    context = context if context is not None else {"self_model": {}, "affect_state": {}}
    results = []
    for i in range(n):
        signals, context = handle_user_input(
            context, {"count": i}, None, None, relationships={},
        )
        results.append(signals)
    return results, context


def test_same_line_five_cycles_processes_once(patched):
    results, context = _run_cycles(5)

    user_signals = [
        s for cycle in results for s in cycle if s.get("source") == "user_input"
    ]
    assert len(user_signals) == 1, "exactly one user_input signal for one line"
    assert patched.reward == 1, "exactly one reward release for one line"
    assert patched.eval_reply == 1, "previous reply evaluated exactly once"

    # After the first sighting, the speaker must see silence, not the stale line.
    assert context["latest_user_input"] == ""

    # Duplicate cycles degrade to the internal stagnation prompt, like silence.
    for cycle in results[1:]:
        assert all(s.get("source") != "user_input" for s in cycle)


def test_new_line_after_duplicates_is_processed(patched, monkeypatch):
    _run_cycles(3)
    monkeypatch.setattr(ui_mod, "get_user_input", lambda: "and now something else")
    results, context = _run_cycles(1)

    user_signals = [s for s in results[0] if s.get("source") == "user_input"]
    assert len(user_signals) == 1
    assert context["latest_user_input"] == "and now something else"


def test_log_user_input_once_is_the_gate(patched):
    ctx = {}
    assert log_user_input_once("hello there", ctx) is True
    assert log_user_input_once("hello there", ctx) is False
    # Crash-safe: a fresh context (restart) still dedups via the disk marker.
    assert log_user_input_once("hello there", {}) is False
    assert log_user_input_once("different line", {}) is True


def test_noise_and_empty_are_never_new(patched):
    assert log_user_input_once("", {}) is False
    assert log_user_input_once("   ", {}) is False
    assert log_user_input_once("—", {}) is False


def test_persist_last_seen_single_line(patched, tmp_path):
    ui_mod._persist_last_seen("line one\nline two\n")
    content = (tmp_path / "last_seen.txt").read_text(encoding="utf-8")
    assert "\n" not in content
