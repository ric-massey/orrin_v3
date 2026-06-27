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
    # Post-pick tail: these exercise the scoring loop's repeat/penalty paths and
    # the post-pick refinements (ε-exploration, threat arbiter, anti-repeat,
    # meta-rut breaker) — paths the empty-recent cases above never reach.
    "repeat_run": (
        {"recent_picks": ["leave_note", "leave_note", "leave_note"], "attention_mode": "engaged"},
        "generate_intrinsic_goals",
    ),
    "meta_rut": (
        {
            "recent_picks": ["assess_goal_progress", "reflection", "self_review",
                             "narrative_update", "abduce"],
            "committed_goal": _GOAL_RESEARCH,
        },
        "research_topic",
    ),
    "threat_spike": (
        {"threat_detector_response": {"shortcut_function": "dream", "spike_intensity": 0.9}},
        "idle_consolidation_cycle",
    ),
    "suppress_intrinsic": (
        {"_suppress_intrinsic_goals": True, "attention_mode": "wandering"},
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
    ctx = copy.deepcopy(ctx)
    # Disable the stochastic ε-exploration branch: it can override the argmax with
    # a random dormant safe fn whose pick depends on module-level cache state other
    # tests perturb, so its output is not a stable golden. These cases pin the
    # DETERMINISTIC scoring decision — the behavior the extraction must preserve.
    ctx["_exploration_epsilon"] = 0.0
    random.seed(_SEED)
    chosen = sf.select_function(ctx)
    assert chosen == expected, (
        f"case {name!r}: select_function returned {chosen!r}, expected {expected!r} "
        f"— Phase 4.5A extraction must preserve the decision exactly"
    )


# Distress routes to internally-scoped reflection/regulation, but the exact winner
# is a tie among the reflect_on_* family broken by learned-stats global state that
# other tests perturb — so pin the FAMILY (the stable invariant), not the name.
_DISTRESS_OK_PREFIXES = ("reflect_on_", "attempt_regulation", "investigate_",
                         "self_soothing", "narrative_update", "dream", "reflection")


def test_distress_routes_to_reflection_family():
    ctx = {
        "affect_state": {"core_signals": {"reward_negative": 0.9, "threat_level": 0.7}},
        "_exploration_epsilon": 0.0,
    }
    random.seed(_SEED)
    chosen = sf.select_function(ctx)
    assert chosen.startswith(_DISTRESS_OK_PREFIXES), (
        f"distress should route to the reflection/regulation family, got {chosen!r}"
    )
