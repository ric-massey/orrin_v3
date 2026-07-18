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
