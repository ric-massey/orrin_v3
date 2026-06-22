# Characterization net for select_function() (CODEBASE_CLEANUP_PLAN Phase 4.5A).
#
# Phase 4.5A decomposes the ~1,120-line select_function() body into ordered,
# individually-testable scoring steps. That is a *pure structural move* — the
# decision it returns must not change. The existing invariant test only checks
# the chosen name is dispatchable; it would not catch a boost block that silently
# stopped contributing (the selector would still return *a* valid name, just the
# wrong one). This test pins the EXACT decision for a battery of seeded contexts
# that each exercise a distinct scoring path, so any behavior drift during the
# extraction fails loudly.
#
# The golden values were captured from the pre-4.5A implementation with
# random.seed(_SEED) before each call. They depend on the committed data tree
# (capability_descriptions.json tags, learned stats, function_chains.json); if a
# *deliberate* selector/data change moves a decision, regenerate the golden map
# with tools and review the diff — do not loosen the assertion.
import copy
import random

import pytest

import brain.think.think_utils.select_function as sf

_SEED = 12345

_GOAL_RESEARCH = {
    "title": "understand quantum entanglement",
    "name": "research",
    "status": "active",
    "description": "research and read about quantum physics",
    "tags": ["acquire_knowledge"],
}

# name -> (context, expected chosen function). Each context targets a different
# boost/routing path inside select_function().
_CASES = {
    "empty": ({}, "leave_note"),
    "alert_user": (
        {"attention_mode": "alert", "latest_user_input": "hello can you help me"},
        "search_own_files",
    ),
    "engaged": ({"attention_mode": "engaged"}, "leave_note"),
    "wandering": ({"attention_mode": "wandering"}, "seek_novelty"),
    "drowsy": ({"attention_mode": "drowsy"}, "leave_note"),
    "goal_research": (
        {"committed_goal": _GOAL_RESEARCH, "attention_mode": "engaged"},
        "research_topic",
    ),
    "goal_impasse": (
        {
            "committed_goal": _GOAL_RESEARCH,
            "affect_state": {
                "core_signals": {
                    "impasse_signal": 0.8,
                    "motivation": 0.8,
                    "confidence": 0.6,
                }
            },
        },
        "research_topic",
    ),
    "neuro_focus": (
        {
            "committed_goal": _GOAL_RESEARCH,
            "affect_state": {"_ne_proxy": 0.8, "_stability_signal_proxy": 0.4},
        },
        "research_topic",
    ),
    "monitor_replan": (
        {
            "global_workspace": {
                "source": "monitor:metacog",
                "wants": "re-plan",
                "kind": "stuck",
                "salience": 0.9,
            }
        },
        "redirect_goal_plan",
    ),
    "workspace_percept": (
        {"global_workspace": {"source": "percept", "salience": 0.8}},
        "leave_note",
    ),
    "unconscious": (
        {"_conscious_cycle": False, "attention_mode": "wandering"},
        "seek_novelty",
    ),
    "tensions": ({"active_tensions": [{"id": 1}]}, "propose_value_revision"),
    "deadline": (
        {
            "_temporal_pressure": {"deadline_alerts": [{"phase": "imminent"}]},
            "committed_goal": _GOAL_RESEARCH,
        },
        "research_topic",
    ),
    "distress": (
        {"affect_state": {"core_signals": {"negative_valence": 0.9, "threat_level": 0.7}}},
        "reflect_on_internal_agents",
    ),
    "force_action": ({"_force_action_next": True}, "seek_novelty"),
    "suppress_delib": (
        {"_suppress_goal_deliberation": True, "committed_goal": _GOAL_RESEARCH},
        "research_topic",
    ),
    "novelty_pressure": ({"_novelty_pressure": 0.5}, "leave_note"),
    "exploration_drive": (
        {"affect_state": {"core_signals": {"exploration_drive": 0.9}}},
        "look_outward",
    ),
    "no_explore": (
        {"_exploration_epsilon": 0.0, "attention_mode": "wandering"},
        "seek_novelty",
    ),
}


@pytest.fixture(scope="module", autouse=True)
def _warm_selector():
    # The first select_function() call in a process loads the embedding model
    # lazily, so _capability_overlap returns cold-start values for that one call.
    # The pinned decisions below are the steady-state (warm) behavior the runtime
    # actually sees and the refactor must preserve — warm once up front.
    random.seed(0)
    sf.select_function({"committed_goal": copy.deepcopy(_GOAL_RESEARCH)})


@pytest.mark.parametrize("name", sorted(_CASES))
def test_select_function_decision_is_pinned(name):
    ctx, expected = _CASES[name]
    random.seed(_SEED)
    chosen = sf.select_function(copy.deepcopy(ctx))
    assert chosen == expected, (
        f"case {name!r}: select_function returned {chosen!r}, expected {expected!r} "
        f"— Phase 4.5A extraction must preserve the decision exactly"
    )
