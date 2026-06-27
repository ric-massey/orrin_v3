"""Shared leaf constants for selection (Phase 4D, from select_function.py).

Pure data imported by both the core selector and the extracted scoring layer,
so they live here to keep those modules acyclic.
"""
from __future__ import annotations

FALLBACK_ACTIONS = ["reflect_on_self_beliefs", "assess_goal_progress", "consolidate_from_long_memory"]


_ALWAYS_EXCLUDE = frozenset({
    "apply_cognitive_costs", "apply_drive_tensions",
    "apply_inhibition_costs",
    "speak", "respond", "respond_to_user",
    # Require injected args — cannot be dispatched bare by the selector
    "add_goal", "add_entity", "add_relation",
    "advance_goal_plan", "adjust_priority",
    "apply_attention_filter", "apply_emotional_contagion",
    "apply_signal_routing", "append_death_continuity",
    "set_goal_plan", "mark_goal_completed", "mark_goal_failed",
    "mark_goal_status_by_name", "merge_updated_goal_into_tree",
    "get_next_pending_step", "get_goal_plan",
    # Dual-process Phase 2: goal-step EXECUTION is owned by the Executive
    # (cognition/planning/executive.py), which runs pursue_committed_goal in the
    # background before think(). Excluding it from DELIBERATE selection frees the
    # conscious slot and prevents double execution (I3). The thin `attend_goal`
    # act remains selectable for "consciously deciding to focus" without executing.
    "pursue_committed_goal",
    "decompose_goal", "create_micro_goal_for_action",
    # Dynamic subgoal-adaptation primitives — operate on a passed goal dict and
    # are orchestrated by adapt_subgoals(); never dispatch them bare.
    "insert_plan_step", "skip_pending_steps", "reprioritize_pending_steps",
    "prune_satisfied_steps", "met_milestone_tokens", "unmet_milestone_texts",
    # Per-cycle UPKEEP that already runs automatically every cycle and was ALSO
    # competing as a deliberate "choice" (~22% of all selections), double-applying
    # when picked: update_affect_state runs at ~9 sites; the apply_* pressures run
    # in finalize.py each cycle. Excluding them from SELECTION loses no behaviour —
    # they still run automatically — and frees those cycles for real cognition.
    "update_affect_state",
    "apply_lifetime_pressure", "apply_temporal_pressure",
    "apply_habituation", "apply_fragmentation_cost",
    # Closure/maintenance UPKEEP now runs deterministically on a slow cadence in
    # ORRIN_loop's maintenance block (retirement/fade/satiety), NOT as a deliberate
    # emotion-cued choice. fade_goals is dispatchable and was in the bandit pool but
    # never won (no prior, cold-start starvation). Excluding it follows the same
    # precedent as update_affect_state/apply_* — it still runs automatically every
    # cadence window, and selection stays honest (only deliberate cognition competes).
    "fade_goals",
    # Need injected args the dispatcher can't supply bare (name/description/body),
    # yet slipped the signature filter — they were selected then skipped, filling
    # error_log.txt. They're invoked with explicit args by their own orchestrators.
    "write_tool", "write_cognitive_function",
})
