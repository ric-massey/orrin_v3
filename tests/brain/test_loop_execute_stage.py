# Phase 4A: the action/cognition execution stages extracted from
# run_cognitive_loop live in brain/loop/execute.py. The cognitive-loop boot net
# (a newborn single cycle) typically takes Path B (a cognition function), so
# Path A — execute_behavior_action — gets its own direct stage test here. The
# unknown-action branch is the cheapest to exercise end to end (no take_action),
# and pins the (context, reward) contract.
import brain.loop.execute as ex


def test_unknown_behavior_action_returns_penalty_reward():
    context = {"speaker": None, "committed_goal": None, "affect_state": {}}
    result = {"action": {"type": "definitely_not_a_real_action", "content": ""}}
    out_ctx, reward, acted = ex.execute_behavior_action(
        context, result, _decision_id="test-decision", _evaluator=None, BEH_NAMES=set()
    )
    # Unknown action → fixed penalty reward, context returned (same object), and
    # acted_this_cycle stays False (no action was taken).
    assert out_ctx is context
    assert reward == -0.3
    assert acted is False
