# think/think_utils/selection/tag_sets.py
#
# Membership sets for select_function() (CODEBASE_CLEANUP_PLAN Phase 4.5A).
#
# These name *which* functions each scoring block applies to. They were lifted
# verbatim out of select_function.py's module header so both the coordinator and
# the extracted scoring steps (selection/boosts.py) can share them without a
# circular import. select_function.py re-imports them all (noqa F401) so the
# golden tag test's `sf._NEURO_NE_FOCUS` / `sf._OUTWARD_MED` access paths and the
# in-body references are unchanged.
#
# The tag-derived sets (_tagged_or) read the capability manifest
# (capability_descriptions.json) as the source of truth for membership and keep
# their literal default as a fallback, so a missing/corrupt manifest degrades to
# the pre-Phase-4 behavior. tests/brain/test_capability_tags.py asserts each
# derived set equals its literal default — Phase 4 changed the *mechanism*, not
# the picks.
from __future__ import annotations

from brain.think.think_utils.selection.catalog import _tagged_or

# Functions that directly serve the user or produce external value. Literal
# FALLBACK only — the live set is tag-derived below (tags "outward" +
# "goal-progress"), so a newly tagged function participates without touching this
# list. (E6 cleanup: the dead pursue_committed_goal entry was dropped — it runs
# in the Executive lane and is never in the pool.)
_USER_HELPFUL_DEFAULT: frozenset[str] = frozenset({
    "plan_next_step",
    "assess_goal_progress",
    "adapt_subgoals",
    "look_outward",
    "search_own_files",
    "grep_files",
    "search_files",
    "thread_continue",
    "seek_novelty",
    "look_around",
    "leave_note",
    "save_note",
    "research_topic",
    "fetch_and_read",
    "wikipedia_search",
})

# Pure introspection — valuable, but should yield to helpfulness when user is present.
# Phase 4 fallback for the "introspective" tag.
_INTROSPECTION_DEFAULT: frozenset[str] = frozenset({
    "idle_consolidation_cycle",
    "narrative_update",
    "reflection",
    "reflect_on_directive",
    "propose_value_revision",
    "metacog_flush",
    "self_review",
})

# Goal-DELIBERATION functions: they reason *about* a goal without advancing it.
# When avoidance is entrenched (behavioral_adaptation sets _suppress_goal_deliberation
# at high action_debt) these are locked out for a cycle so "assess / adapt / re-weight
# the goal" can no longer be chosen in place of actually doing it.
_GOAL_DELIBERATION_FNS: frozenset[str] = frozenset({
    "assess_goal_progress",
    "adapt_subgoals",
    "adjust_goal_weights",
})

# Meta-rut detection (think-vs-act). The anti-repeat guard only catches a single
# function repeating; it is blind to a *varied* run of thinking functions that
# never executes (assess → adjust → abduce → adapt → assess …). These two sets let
# the selector measure the think/act ratio over the recent window and force an
# execution function when deliberation has crowded out doing.
_DELIBERATION_FNS: frozenset[str] = frozenset({
    "assess_goal_progress", "adapt_subgoals", "adjust_goal_weights",
    "abduce", "reflection", "self_review", "narrative_update",
    "reflect_on_directive", "reflect_on_affect", "metacog_flush",
    "detect_memory_contradictions", "propose_value_revision",
    "introspective_planning", "associative_recall", "plan_next_step",
})
_EXECUTION_FNS: frozenset[str] = frozenset({
    # Phase 4 / E6 cleanup: pursue_committed_goal dropped — it never appears in
    # `recent` (not selectable), so it could never satisfy the think/act check.
    "research_topic", "wikipedia_search",
    "fetch_and_read", "search_own_files", "search_files", "grep_files",
    "look_outward", "look_around", "seek_novelty", "thread_continue",
    "leave_note", "save_note", "write_desktop_note", "read_a_book",
    "write_cognitive_function", "write_tool",
    "decide_to_write_code", "synthesize_from_gap",
    # generate_intrinsic_goals removed: producing more goals is deliberation,
    # not acting on one. Counting it as execution let a think-only rut satisfy
    # the meta-rut breaker's "acted" check (2026-06-12: 1186 picks, 5900-cycle
    # goal-avoidance streak, breaker never fired once).
})
# Pure-curiosity reads: the "blind exploration" subset the dominant-emotion semantic
# prior pins selection onto when exploration_drive is high. Damped by goal-shielding
# (cognitive control) when a committed goal is active AND the function is not
# goal-relevant (no goal_recruit overlap). They stay fully selectable — the bias is
# graded, never a lockout. research_topic / wikipedia_search / fetch_and_read are
# deliberately EXCLUDED: those are how a research goal is actually pursued, so
# goal-relevant outward work is never shielded against.
_BLIND_EXPLORE_FNS: frozenset[str] = frozenset({
    "search_own_files", "search_files", "grep_files",
    "look_outward", "look_around", "seek_novelty",
    "read_a_book", "read_book",
})

# Functions ε-exploration (§3.2) is allowed to FORCE-sample. Reversible /
# internally-scoped only: procedural reads & observations, notes, and reflections
# / recalls / detections that merely compute and record. Curated against the live
# Phase-1 pool. Anything NOT here can still WIN on merit via the normal score; it
# just may never be force-sampled (E4: "rarely-used" != "safe-to-try").
#
# Deliberately EXCLUDED — the Dig#2 "situational, leave rare" irreversible tail
# (stays selectable on merit, never forced): abandon_goal, mutate_directive,
# evolve_core_value, invent_new_value, emergency_self_modification,
# propose_value_revision, reconcile_identity, submit_finetune_job,
# run_active_experiment, run_sandbox_experiments, run_experiment_cycle,
# run_pipeline, redirect_goal_plan, adapt_subgoals, adjust_goal_weights,
# select_focus_goals, maybe_complete_goals, generate_intrinsic_goals,
# generate_absurd_goal, plan_self_evolution, self_supervised_repair, and the
# record_*/commit_*/propose_extension goal-state mutations.
_SAFE_TO_EXPLORE_DEFAULT: frozenset[str] = frozenset({
    # procedural reads / observations (mirror of step_execution._PROCEDURAL_FNS,
    # extended with the reversible read-only tools in the live pool)
    "research_topic", "fetch_and_read", "wikipedia_search", "fetch_wikipedia",
    "read_rss", "read_a_book", "read_book", "pick_book", "list_books",
    "read_text", "learn_from_reading", "search_own_files", "look_outward",
    "look_around", "survey_environment", "seek_novelty", "leave_note",
    "mark_private", "read_vitals", "current_awareness",
    # reversible internal cognition: reflect / recall / detect / consolidate /
    # dream / imagine — these compute and note, they do not commit external or
    # identity/value/goal state.
    "reflect_on_self_beliefs", "reflect_on_outcomes", "reflect_on_effectiveness",
    "reflect_on_desire", "reflect_on_opinions", "reflect_on_growth_history",
    "reflect_on_internal_agents", "reflect_on_internal_voices", "reflect_on_think",
    "reflect_on_missed_goals", "reflect_on_conversation_patterns",
    "reflect_on_cognition_patterns", "reflect_on_emotion_sensitivity",
    "reflect_as_agents", "narrative_update", "periodic_self_review",
    "associative_recall", "maybe_surface_association", "maybe_surface_regret",
    "process_regret", "detect_memory_contradictions", "detect_tensions",
    "consolidate_from_long_memory", "consolidate_language", "idle_consolidation_cycle",
    "compose_consolidation", "introspective_planning", "evaluate_recent_cognition",
    "summarize_relationships", "audit_reflective_claims",
    "generate_concepts_from_memories", "extract_semantic_facts",
    "imagine_opposite_self", "simulate_future_selves",
    "simulate_conflicting_beliefs",
    # Code-writing orchestrators: reversible in practice — output goes through
    # syntax + AST-safety + sandbox verification before registration, and
    # delete_own_code can undo any registration. Without a first forced pull
    # these arms stay cold forever (no emotion prior, no bandit history), which
    # starved the 2026-06-12 "write a cognitive function" goal for 5900 cycles.
    # propose_extension / commit_extension stay excluded: they mutate the
    # gestation pipeline's persistent proposal state.
    "decide_to_write_code", "synthesize_from_gap",
})

# ── Phase 4 (function_selection_fix_v2 §5): tag-derived boost sets ────────────
# The capability manifest (capability_descriptions.json, {fn: {desc, tags}}) is
# now the source of truth for WHICH functions each boost block applies to — a
# new function participates in the right boosts by being tagged, not by editing
# ~15 hardcoded name-lists. Every set keeps its literal default as fallback
# (_tagged_or), so a missing/corrupt manifest degrades to the pre-Phase-4
# behavior instead of collapsing selection.
_USER_HELPFUL_FUNCTIONS: frozenset[str] = _tagged_or(("outward", "goal-progress"), _USER_HELPFUL_DEFAULT)
_INTROSPECTION_FUNCTIONS: frozenset[str] = _tagged_or(("introspective",), _INTROSPECTION_DEFAULT)
_SAFE_TO_EXPLORE: frozenset[str] = _tagged_or(("safe_to_explore",), _SAFE_TO_EXPLORE_DEFAULT)

# Attention-mode per-fn affinity sets (the literal tuples that lived inline in
# the attention_mode blocks).
_MODE_ALERT_FNS = _tagged_or(("mode_alert",), frozenset({
    "assess_goal_progress", "plan_next_step", "look_outward", "search_own_files"}))
_MODE_ENGAGED_FNS = _tagged_or(("mode_engaged",), frozenset({
    "generate_intrinsic_goals", "assess_goal_progress"}))
_MODE_WANDERING_FNS = _tagged_or(("mode_wandering",), frozenset({
    "look_outward", "seek_novelty", "look_around", "generate_intrinsic_goals",
    "search_own_files", "search_files", "grep_files"}))
_MODE_WANDERING_REFLECT_FNS = _tagged_or(("mode_wandering_reflect",), frozenset({
    "idle_consolidation_cycle", "reflection", "narrative_update"}))
_MODE_DROWSY_FNS = _tagged_or(("mode_drowsy",), frozenset({
    "idle_consolidation_cycle", "self_review", "narrative_update", "consolidate_memory",
    "reflect_on_directive"}))

# Neuromodulator boost target sets (per-list shared multipliers stay in code —
# they are dynamics, not membership).
_NEURO_NE_FOCUS = _tagged_or(("neuro_ne_focus",), frozenset({
    "assess_goal_progress", "plan_next_step"}))
_NEURO_NE_SUPPRESS = _tagged_or(("neuro_ne_suppress",), frozenset({
    "idle_consolidation_cycle", "seek_novelty", "look_around", "narrative_update"}))
_NEURO_CALM_SUPPRESS = _tagged_or(("neuro_calm_suppress",), frozenset({
    "attempt_regulation", "reflect_on_affect", "investigate_unexplained_emotions"}))
_NEURO_STRESS_SUPPRESS = _tagged_or(("neuro_stress_suppress",), frozenset({
    "plan_self_evolution", "detect_memory_contradictions", "propose_value_revision",
    "narrative_update", "idle_consolidation_cycle", "generate_intrinsic_goals"}))
_NEURO_STRESS_RESTORE = _tagged_or(("neuro_stress_restore",), frozenset({
    "attempt_regulation", "self_soothing", "reflection"}))

# Standing outward-presence tiers (graded boost weights stay in code).
_OUTWARD_HIGH = _tagged_or(("outward_artifact",), frozenset({
    "leave_note", "write_desktop_note", "write_cognitive_function",
    "write_tool", "save_note", "notify_user", "announce_to_dashboard"}))
_OUTWARD_MED = _tagged_or(("outward_explore",), frozenset({
    "look_outward", "look_around", "seek_novelty", "wikipedia_search",
    "read_rss", "research_topic", "fetch_and_read", "read_a_book",
    "search_own_files", "grep_files", "search_files"}))
_OUTWARD_LOW = _tagged_or(("outward_sense",), frozenset({
    "survey_environment", "read_clipboard", "check_user_presence",
    "run_embodied_observation"}))
