# Invariant test (Finding 11): select_function must always return a name that
# is genuinely dispatchable — i.e. present in COGNITIVE_FUNCTIONS with a
# callable "function" entry, not just "_is_dispatchable() didn't object".
#
# ORRIN_loop dispatches the chosen name via:
#     meta_or_fn = COGNITIVE_FUNCTIONS.get(fn_name)
#     fn = meta_or_fn.get("function") if isinstance(meta_or_fn, dict) else meta_or_fn
#     if callable(fn): ... else: "Unknown function requested" (bandit penalty,
#     try_auto_repair UnknownFunction).
# A selector return value that fails this check is a silent dispatch failure.
import random

import think.think_utils.select_function as sf
from registry.cognition_registry import COGNITIVE_FUNCTIONS


def _assert_dispatchable(name):
    assert isinstance(name, str) and name, f"selector returned {name!r}"
    meta_or_fn = COGNITIVE_FUNCTIONS.get(name)
    fn = meta_or_fn.get("function") if isinstance(meta_or_fn, dict) else meta_or_fn
    assert callable(fn), f"{name!r} is not in COGNITIVE_FUNCTIONS / not callable"
    assert sf._is_dispatchable(name)


def test_fallback_actions_are_dispatchable():
    for name in sf.FALLBACK_ACTIONS:
        _assert_dispatchable(name)


def test_ensure_min_candidates_from_empty_is_dispatchable():
    seeded = sf._ensure_min_candidates([])
    assert len(seeded) >= 2
    for name in seeded:
        _assert_dispatchable(name)


def test_select_function_empty_context():
    random.seed(0)
    assert isinstance(sf.select_function({}), str)
    _assert_dispatchable(sf.select_function({}))


def test_select_function_attention_modes():
    random.seed(0)
    for mode in ("alert", "engaged", "wandering", "drowsy", "neutral"):
        ctx = {"attention_mode": mode, "affect_state": {"core_signals": {"threat_level": 0.9}}}
        _assert_dispatchable(sf.select_function(ctx))


def test_select_function_when_everything_undispatchable():
    # Every real candidate has been refused this session -> selector must fall
    # back to FALLBACK_ACTIONS, which must themselves be dispatchable.
    ctx = {"_undispatchable_fns": list(COGNITIVE_FUNCTIONS.keys())}
    _assert_dispatchable(sf.select_function(ctx))


def test_select_function_with_extreme_affect_state():
    extreme_core = {k: 1.0 for k in (
        "threat_level", "impasse_signal", "conflict_signal", "negative_valence",
        "uncertainty", "stagnation_signal", "social_deficit",
    )}
    ctx = {"affect_state": {"core_signals": extreme_core}}
    _assert_dispatchable(sf.select_function(ctx))
