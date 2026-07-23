# R10-8: reward must see impossibility. An action the LLM tool-gate refuses is
# structurally blocked; it must (1) be attributed the block via the currently-
# dispatched function, (2) pay zero reward, (3) leave the selectable set until a
# periodic re-probe, and (4) return once the capability is back.

import time

from brain.control_signals.reward_signals import impossibility as imp


def _reset():
    # Clear any persisted state between assertions.
    for a in list(imp._load().keys()):
        imp.note_possible(a)
    imp.clear_current_action()


def test_gate_denial_attributes_block_to_current_action():
    _reset()
    imp.set_current_action("decide_to_write_code")
    imp.mark_from_gate("tool unavailable: llm (tool-only)")
    imp.clear_current_action()
    assert imp.is_impossible("decide_to_write_code")
    # A gate denial with no action in flight marks nothing.
    imp.mark_from_gate("tool unavailable: llm")
    assert imp.impossible_actions() == {"decide_to_write_code"}


def test_note_possible_clears_the_block():
    _reset()
    imp.mark_impossible("write_tool", "tool unavailable: llm")
    assert imp.is_impossible("write_tool")
    imp.note_possible("write_tool")
    assert not imp.is_impossible("write_tool")


def test_reprobe_window_lets_action_back_in():
    _reset()
    imp.mark_impossible("compose_section", "tool unavailable: llm")
    assert imp.is_impossible("compose_section")
    # Past the re-probe horizon it re-enters the selectable set for one attempt.
    assert not imp.is_impossible("compose_section", now=time.time() + imp._REPROBE_S + 1)


def test_impossible_action_leaves_the_candidate_pool():
    _reset()
    from brain.think.think_utils.selection import candidates as cand
    imp.mark_impossible("decide_to_write_code", "tool unavailable: llm")
    assert "decide_to_write_code" in cand._impossible_now()
    names = cand._load_actions()
    assert "decide_to_write_code" not in names
    _reset()
    # Once cleared, nothing is spuriously excluded by this mechanism.
    assert cand._impossible_now() == frozenset()


# ── 1D.1 (Run 12) — the SYMBOLIC-MODE block path ─────────────────────────────
# Run 11: decide_to_write_code was blocked 1,967/1,967 times yet held EMA 0.576
# and 22 causal edges. Two leaks: (a) ask_llm's llm_available() early return
# never reaches generate_response, so the R10-8 gate marking never fired in
# symbolic mode; (b) the blocked function swallows the denial and returns
# cleanly, so the loop's "genuine success" clearing erased any mark the same
# dispatch it was made. These are the forced-fire harnesses for both seams.

def test_symbolic_mode_ask_llm_block_marks_dispatched_action(monkeypatch):
    _reset()
    from brain.cognition.tools import ask_llm as ask_mod
    monkeypatch.setattr(ask_mod, "llm_available", lambda: False)
    imp.set_current_action("decide_to_write_code")
    out = ask_mod.ask_llm({}, query="write a function body", purpose="question")
    imp.clear_current_action()
    assert "unavailable" in out.lower()
    assert imp.is_impossible("decide_to_write_code")
    _reset()


def test_hollow_success_does_not_clear_the_block():
    _reset()
    # Simulate the dispatch order the loop uses: mark during dispatch, then the
    # "ran without raising" success path must NOT clear the fresh mark.
    imp.set_current_action("decide_to_write_code")
    imp.mark_from_gate("tool unavailable: llm (disabled in config)")
    imp.clear_current_action()
    assert imp.blocked_this_dispatch()
    if not imp.blocked_this_dispatch():
        imp.note_possible("decide_to_write_code")
    assert imp.is_impossible("decide_to_write_code")
    # A later dispatch that is NOT blocked resets the flag and may clear.
    imp.set_current_action("decide_to_write_code")
    imp.clear_current_action()
    assert not imp.blocked_this_dispatch()
    imp.note_possible("decide_to_write_code")
    assert not imp.is_impossible("decide_to_write_code")
    _reset()


def test_forced_fire_dispatch_marks_zeroes_and_excludes(monkeypatch):
    """End-to-end harness (R9-F7 / F-LN8 pattern): dispatch a function through
    the real loop path while the LLM tool is absent; it must end the dispatch
    marked impossible, pay zero-with-prejudice, and leave the selectable set."""
    _reset()
    from brain.cognition.tools import ask_llm as ask_mod
    monkeypatch.setattr(ask_mod, "llm_available", lambda: False)

    def _fake_decide_to_write_code(context=None, **_):
        # Mirrors brain/agency/code_writer.decide_to_write_code's shape: calls
        # ask_llm, gets the unavailable message, swallows it, returns None.
        ask_mod.ask_llm(context or {}, query="write code", purpose="question")
        return None

    from brain.think.loop_helpers import execute_action_via_registries

    class _Reg(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    reg = _Reg({"decide_to_write_code": _fake_decide_to_write_code})
    res = execute_action_via_registries("decide_to_write_code", {}, reg)
    assert isinstance(res, dict) and res.get("success")   # hollow success
    # …but the block was attributed, survived the success path,
    assert imp.is_impossible("decide_to_write_code")
    # …zeroes the realized reward,
    assert imp.realized_reward_with_prejudice("decide_to_write_code", 0.8) == 0.0
    # …and removes the action from the selectable set.
    from brain.think.think_utils.selection import candidates as cand
    assert "decide_to_write_code" in cand._impossible_now()
    _reset()
