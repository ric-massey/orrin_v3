# Behavioral queue unification (V3 D4): one urgency/veto-ranked resolution path,
# replacing pending_actions.insert(0) position-hacking.
from think.think_utils.action_gate import propose_action, resolve_pending_actions


def test_higher_urgency_resolves_to_front():
    ctx = {}
    propose_action(ctx, {"type": "speak", "urgency": 0.3})
    propose_action(ctx, {"type": "user_response", "urgency": 0.92})
    propose_action(ctx, {"type": "log", "urgency": 0.1})
    resolve_pending_actions(ctx)
    assert ctx["pending_actions"][0]["type"] == "user_response"


def test_veto_outranks_high_urgency():
    ctx = {}
    propose_action(ctx, {"type": "ask_user", "urgency": 0.99})
    propose_action(ctx, {"type": "refuse", "urgency": 0.5})  # veto by type
    resolve_pending_actions(ctx)
    assert ctx["pending_actions"][0]["type"] == "refuse"


def test_explicit_veto_flag_outranks():
    ctx = {}
    propose_action(ctx, {"type": "ask_user", "urgency": 0.99})
    propose_action(ctx, {"type": "user_response", "urgency": 0.4}, veto=True)
    resolve_pending_actions(ctx)
    assert ctx["pending_actions"][0].get("veto") is True


def test_stable_within_tier():
    # Equal urgency keeps insertion order (FIFO within a priority tier).
    ctx = {}
    propose_action(ctx, {"type": "a", "urgency": 0.5})
    propose_action(ctx, {"type": "b", "urgency": 0.5})
    resolve_pending_actions(ctx)
    assert [a["type"] for a in ctx["pending_actions"]] == ["a", "b"]


def test_propose_sets_urgency_override():
    ctx = {}
    propose_action(ctx, {"type": "x"}, urgency=0.9)
    assert ctx["pending_actions"][0]["urgency"] == 0.9
