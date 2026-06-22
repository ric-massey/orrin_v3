# think/think_utils/select_function.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
from typing import Dict, List, Tuple, Union, Any
import uuid
import random as _rand
import math as _math
import statistics as _statistics

from brain.paths import (
    COGNITIVE_FUNCTIONS_LIST_FILE,
    BEHAVIORAL_FUNCTIONS_LIST_FILE,
    FOCUS_GOAL,
    AFFECT_STATE_FILE,
    SELF_MODEL_FILE,
    EMOTION_FUNCTION_MAP_FILE
)
from brain.utils.json_utils import load_json
from brain.utils.goals import extract_current_focus_goal
from brain.think.bandit import contextual_bandit as bandit
from brain.affect.reward_signals.action_reward_ema import get_associability, _ASSOC_DEFAULT
from brain.config import tuning as _tuning
_log = get_logger(__name__)

# Emergency-fallback candidates used when the cognitive-functions list is
# empty/missing or filtering empties the pool. Must be names present in
# COGNITIVE_FUNCTIONS (registry/cognition_registry.py) — ORRIN_loop dispatches
# `chosen` via COGNITIVE_FUNCTIONS.get(name); a name not in the registry is
# treated as "Unknown function requested" (bandit penalty + auto-repair),
# defeating the point of a *safe* fallback (Finding 11 — selector must always
# return a dispatchable function). The previous names (reflect_on_directive,
# plan_next_step, summarize_memory) were never registered under those names.
FALLBACK_ACTIONS = ["reflect_on_self_beliefs", "assess_goal_progress", "consolidate_from_long_memory"]


def _workspace_routes_for(moment: Dict[str, Any]) -> Dict[str, float]:
    """Map a conscious atomic or bound situation to additive action priors."""
    source = str(moment.get("source", ""))
    atomic = {
        "goal":    {"attend_goal": 1.0, "plan_next_step": 0.8, "assess_goal_progress": 0.6},
        "affect":  {"reflection": 0.8, "reflect_on_self_beliefs": 0.7, "narrative_update": 0.5},
        "thought": {"reflection": 0.8, "narrative_update": 0.6},
        "signal":  {"look_outward": 0.9, "search_own_files": 0.6},
        "user":    {"attend_goal": 0.7, "narrative_update": 0.6},
    }
    if source != "binding":
        return atomic.get(source, {})

    facets = moment.get("facets") or {}
    if not isinstance(facets, dict):
        return {}
    routes: Dict[str, float] = {}

    def merge(values: Dict[str, float]) -> None:
        for name, weight in values.items():
            routes[name] = max(routes.get(name, 0.0), weight)

    if facets.get("goal"):
        merge(atomic["goal"])
    if facets.get("affect"):
        merge(atomic["affect"])
    if facets.get("memory"):
        merge(atomic["thought"])
    if facets.get("event") or facets.get("motion") or facets.get("object"):
        merge(atomic["signal"])
    if facets.get("interlocutor"):
        merge(atomic["user"])
    return routes

# Directed (uncertainty-seeking) exploration weight. Gershman (2018), "Deconstructing
# the human algorithms for exploration", Cognition 173:34 — humans add an
# uncertainty bonus to actions whose value is poorly known, on top of random
# exploration. We use Pearce-Hall associability (action_reward_ema) as that
# uncertainty signal, measured RELATIVE to its neutral prior so a well-modelled
# action gets no bonus and only genuinely volatile/under-explored ones are lifted.
_W_EXPLORE = 0.12

# Functions that should NEVER enter the cognitive selector — they are
# behavioral (outward-facing) or bookkeeping utilities that don't
# belong in the same bandit pool as real cognition choices.
# BEH_NAMES is the authoritative source; this is a belt-and-suspenders
# fallback for any that leak through before the file is read.
_ALWAYS_EXCLUDE = frozenset({
    "apply_cognitive_costs", "apply_drive_tensions",
    "apply_inhibition_costs",
    "speak", "respond", "respond_to_user",
    # Require injected args — cannot be dispatched bare by the selector
    "add_goal", "add_entity", "add_relation",
    "advance_goal_plan", "adjust_priority",
    "apply_attention_filter", "apply_emotional_contagion",
    "apply_emotion_routing", "append_death_continuity",
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
    "apply_mortality_pressure", "apply_temporal_pressure",
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

# ---------------------------------------------------------------------------
# Shape-based selectability filter (function_selection_fix_v2.md Phase 1).
#
# The candidate pool was polluted by ~160 non-behaviors: 76 corrupted
# auto-generated explore_* stubs (49 of them runaway "..._more_deeply" chains)
# plus per-cycle upkeep/accessor plumbing that already runs automatically each
# cycle. They diluted every novelty/bandit/curiosity signal and could win the
# argmax. _ALWAYS_EXCLUDE names such functions one-by-one; this filters them BY
# SHAPE so newly generated junk is dropped as a class without growing that list
# by hand (self-maintaining).
#
#   - explore_* : corrupted auto-generated goal-exploration stubs. The root
#                 cause is cured at source (behavior_generation suffix collapse +
#                 the persist_names explore_* filter); this is the in-selector
#                 containment / defense-in-depth.
#   - upkeep / accessor prefixes that already run automatically each cycle and,
#                 when *selected*, only double-applied (see _ALWAYS_EXCLUDE).
#
# is_*/maybe_* are deliberately NOT denied as a class — maybe_form_opinion and
# some is_* may be real cognition. Confirmed-plumbing accessors go in
# _NON_SELECTABLE_EXACT individually instead.
_NON_SELECTABLE_PREFIXES: Tuple[str, ...] = (
    "explore_",
    "apply_", "update_", "compute_", "recompute_", "decay_", "ensure_",
    "build_", "init_", "load_", "save_", "persist_", "register_", "refresh_",
    "reset_", "migrate_", "coerce_", "normalize_", "sync_", "flush_", "gc_",
    "get_", "set_", "has_", "should_",
)

# Functions that start with a denied prefix but ARE real behaviors — keep them.
_SELECTABLE_PREFIX_EXCEPTIONS: frozenset = frozenset({
    "update_world_model",   # genuine cognition entry point (router-wrapped)
})

_NON_SELECTABLE_EXACT: frozenset = frozenset({
    # trivial-name leaks from over-broad public-function discovery
    "available", "exists", "get", "start", "stop", "status", "report",
    "flush", "generate", "simulate", "commit", "size_chars", "vocab_size",
    "lm_ready", "poll_fs_changes",
    # internal reward/calibration calc that surfaced as "choices"
    "calibrated_reward", "calibration_observation", "check_and_reward",
    "check_and_reward_contradiction_resolution", "check_and_reward_goal_closure",
    "check_and_reward_prediction_accuracy", "train_tokenizer_on_library",
    "reflect_on_prompts", "build_system_prompt", "ensure_tokenizer",
})


def _is_selectable_name(name: str) -> bool:
    """False for plumbing/junk that must never enter the selector pool (Phase 1).

    Exact denials and curated prefix-exceptions are checked before the prefix
    sweep, so a real behavior that happens to start with a denied prefix
    (e.g. update_world_model) is kept while the plumbing it resembles is dropped.
    """
    if name in _NON_SELECTABLE_EXACT:
        return False
    if name in _SELECTABLE_PREFIX_EXCEPTIONS:
        return True
    return not name.startswith(_NON_SELECTABLE_PREFIXES)


# Functions that directly serve the user or produce external value.
# When user is present, these get a strong additive boost that overrides
# the intrinsic exploration_drive/reflection pull of the semantic emotion priors.
# Phase 4: literal FALLBACK only — the live set is tag-derived below
# (tags "outward" + "goal-progress" in capability_descriptions.json), so a newly
# tagged function participates without touching this list. (E6 cleanup: the
# dead pursue_committed_goal entry was dropped — it runs in the Executive lane
# and is never in the pool.)
_USER_HELPFUL_DEFAULT: frozenset = frozenset({
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
_INTROSPECTION_DEFAULT: frozenset = frozenset({
    "dream_cycle",
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
_GOAL_DELIBERATION_FNS: frozenset = frozenset({
    "assess_goal_progress",
    "adapt_subgoals",
    "adjust_goal_weights",
})

# Cached learned per-function stats (avg_reward + usage count). Used to make
# selection reward-aware (Fix #2) and to nudge curiosity toward dormant functions
# (Fix #3). Refreshed at most every ~15s so we never hit disk in the hot path.
from brain.utils.failure_counter import record_failure
# Catalog/manifest + learned-stats loaders, extracted to selection/catalog.py
# (Phase 4D). Cache dicts are shared singletons; re-export (noqa F401) for the
# direct-cache readers below + external importers of _capability_descriptions.
from brain.think.think_utils.selection.catalog import (  # noqa: E402,F401
    _STATS_PATH, _STATS_CACHE, _CAPS_PATH, _CAPS_CACHE,
    _load_manifest, _capability_descriptions, _fns_tagged, _tag_weights,
    _tagged_or, _learned_stats,
)

# Meta-rut detection (think-vs-act). The anti-repeat guard only catches a single
# function repeating; it is blind to a *varied* run of thinking functions that
# never executes (assess → adjust → abduce → adapt → assess …). These two sets let
# the selector measure the think/act ratio over the recent window and force an
# execution function when deliberation has crowded out doing.
_DELIBERATION_FNS: frozenset = frozenset({
    "assess_goal_progress", "adapt_subgoals", "adjust_goal_weights",
    "abduce", "reflection", "self_review", "narrative_update",
    "reflect_on_directive", "reflect_on_affect", "metacog_flush",
    "detect_memory_contradictions", "propose_value_revision",
    "introspective_planning", "associative_recall", "plan_next_step",
})
_EXECUTION_FNS: frozenset = frozenset({
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
_BLIND_EXPLORE_FNS: frozenset = frozenset({
    "search_own_files", "search_files", "grep_files",
    "look_outward", "look_around", "seek_novelty",
    "read_a_book", "read_book",
})
# How many of the last N picks being deliberation (with zero execution) trips the
# meta-rut breaker.
_META_RUT_WINDOW = 5

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
_SAFE_TO_EXPLORE_DEFAULT: frozenset = frozenset({
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
    "consolidate_from_long_memory", "consolidate_language", "dream_cycle",
    "compose_dream", "introspective_planning", "evaluate_recent_cognition",
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

# Hard-coded semantic priors: which functions make sense for each dominant emotion.
# The learned emotion_function_map starts empty; these priors fire immediately and
# decline in relative weight as the learned map accumulates evidence.
#
# Regulation functions (attempt_regulation, reflect_on_affect, etc.) are explicitly
# mapped to distress-state emotions. Without these priors the distress signal injected
# by ORRIN_loop has no path to the regulation functions — the signal would raise a tag
# that goes unread, since select_function routes on emotion priors, not signal tags.
# Gross (1998) process model: regulation strategy selection is situationally cued;
# the prior implements that cueing at the function-selection level.
_SEMANTIC_PRIORS: Dict[str, Dict[str, float]] = {
    "stagnation_signal":     {"seek_novelty": 0.9, "search_own_files": 0.82, "look_outward": 0.75,
                    "read_a_book": 0.78, "look_around": 0.70, "grep_files": 0.65,
                    "wikipedia_search": 0.62, "research_topic": 0.60,
                    "search_files": 0.60, "dream_cycle": 0.60, "generate_intrinsic_goals": 0.55},
    # Prior realignment (LEARNING_DIAGNOSIS_2026-06-16 §5.1): the curiosity urge was
    # wired to the cheap diversive scanners (look_outward/look_around, learned q≈0.11–0.14)
    # over the epistemic explorers (seek_novelty/research_topic/wikipedia_search, q≈0.34–0.59).
    # The static prior's lift was the entire margin keeping the low-reward arms on top, so
    # learning could never dig out. Point the prior at what he is actually rewarded for and
    # demote the scanners below them — turns diversive curiosity into epistemic.
    "exploration_drive":   {"seek_novelty": 0.85, "research_topic": 0.80,
                    "wikipedia_search": 0.78, "read_a_book": 0.70,
                    "grep_files": 0.62, "reflect_on_internal_agents": 0.55,
                    "generate_intrinsic_goals": 0.55, "search_own_files": 0.50,
                    "search_files": 0.50, "look_outward": 0.45, "look_around": 0.40},
    "impasse_signal": {"attempt_regulation": 0.88, "reflect_on_affect": 0.82,
                    "investigate_unexplained_emotions": 0.76, "reflection": 0.72,
                    "reflect_on_emotion_model": 0.68, "propose_value_revision": 0.65,
                    "self_review": 0.62, "detect_memory_contradictions": 0.60, "plan_self_evolution": 0.52},
    "risk_estimate":     {"attempt_regulation": 0.90, "reflect_on_affect": 0.84,
                    "investigate_unexplained_emotions": 0.78, "check_affect_drift": 0.72,
                    "reflect_on_emotion_model": 0.66, "self_review": 0.62,
                    "reflection": 0.58, "narrative_update": 0.52},
    "threat_level":        {"attempt_regulation": 0.85, "reflect_on_affect": 0.80,
                    "investigate_unexplained_emotions": 0.74, "reflection": 0.70,
                    "reflect_on_emotion_model": 0.64, "propose_value_revision": 0.60,
                    "self_review": 0.56},
    "negative_valence":     {"reflect_on_affect": 0.85, "attempt_regulation": 0.78,
                    "narrative_update": 0.75, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.64, "apply_affective_feedback": 0.60},
    "conflict_signal":       {"attempt_regulation": 0.88, "reflect_on_affect": 0.80,
                    "detect_memory_contradictions": 0.72, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.64, "investigate_unexplained_emotions": 0.62},
    # Phase 4 / E6 cleanup: dead pursue_committed_goal entries removed from the
    # priors below (never scored — the name is excluded from the pool).
    "confidence":  {"plan_self_evolution": 0.7, "generate_intrinsic_goals": 0.6},
    "motivation":  {"assess_goal_progress": 0.8, "adapt_subgoals": 0.6, "plan_self_evolution": 0.6},
    "positive_valence":         {"narrative_update": 0.65, "leave_note": 0.62, "generate_intrinsic_goals": 0.6,
                    "look_outward": 0.55, "search_own_files": 0.50},
    "uncertainty": {"search_own_files": 0.78, "self_review": 0.75, "reflection": 0.72,
                    "attempt_regulation": 0.65, "look_around": 0.60, "adapt_subgoals": 0.55,
                    "propose_value_revision": 0.50},
    "social_penalty":       {"attempt_regulation": 0.88, "reflect_on_affect": 0.82,
                    "investigate_unexplained_emotions": 0.72, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.62, "narrative_update": 0.55},
    "overwhelm":   {"attempt_regulation": 0.90, "reflect_on_affect": 0.82,
                    "self_review": 0.72, "reflection": 0.65,
                    "investigate_unexplained_emotions": 0.60},
    "expected_gain":        {"plan_self_evolution": 0.7, "generate_intrinsic_goals": 0.6},
    # §5.1: same realignment as exploration_drive — lead with epistemic explorers,
    # demote look_outward/look_around so the prior stops over-privileging the scanners.
    "wonder":      {"seek_novelty": 0.82, "research_topic": 0.78, "wikipedia_search": 0.74,
                    "search_own_files": 0.62, "reflect_on_internal_agents": 0.60,
                    "leave_note": 0.58, "look_outward": 0.50, "look_around": 0.48},
}

# ── Phase 4 (function_selection_fix_v2 §5): tag-derived boost sets ────────────
# The capability manifest (capability_descriptions.json, {fn: {desc, tags}}) is
# now the source of truth for WHICH functions each boost block applies to — a
# new function participates in the right boosts by being tagged, not by editing
# ~15 hardcoded name-lists. Every set keeps its literal default as fallback
# (_tagged_or), so a missing/corrupt manifest degrades to the pre-Phase-4
# behavior instead of collapsing selection. The golden test
# (tests/brain/test_capability_tags.py) asserts each derived set equals its
# literal default — i.e. Phase 4 changed the *mechanism*, not the picks.
_USER_HELPFUL_FUNCTIONS: frozenset = _tagged_or(("outward", "goal-progress"), _USER_HELPFUL_DEFAULT)
_INTROSPECTION_FUNCTIONS: frozenset = _tagged_or(("introspective",), _INTROSPECTION_DEFAULT)
_SAFE_TO_EXPLORE: frozenset = _tagged_or(("safe_to_explore",), _SAFE_TO_EXPLORE_DEFAULT)

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
    "dream_cycle", "reflection", "narrative_update"}))
_MODE_DROWSY_FNS = _tagged_or(("mode_drowsy",), frozenset({
    "dream_cycle", "self_review", "narrative_update", "consolidate_memory",
    "reflect_on_directive"}))

# Neuromodulator boost target sets (per-list shared multipliers stay in code —
# they are dynamics, not membership).
_NEURO_NE_FOCUS = _tagged_or(("neuro_ne_focus",), frozenset({
    "assess_goal_progress", "plan_next_step"}))
_NEURO_NE_SUPPRESS = _tagged_or(("neuro_ne_suppress",), frozenset({
    "dream_cycle", "seek_novelty", "look_around", "narrative_update"}))
_NEURO_CALM_SUPPRESS = _tagged_or(("neuro_calm_suppress",), frozenset({
    "attempt_regulation", "reflect_on_affect", "investigate_unexplained_emotions"}))
_NEURO_STRESS_SUPPRESS = _tagged_or(("neuro_stress_suppress",), frozenset({
    "plan_self_evolution", "detect_memory_contradictions", "propose_value_revision",
    "narrative_update", "dream_cycle", "generate_intrinsic_goals"}))
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


def _emo_mode_function_map() -> Dict[str, Dict[str, float]]:
    """Emotional-mode → per-fn boost map. Weighted "emo_<mode>:<w>" tags in the
    manifest are the source of truth; each mode falls back to its literal map.
    (E6: the dead pursue_committed_goal 0.20 entry under "focused" was removed.)"""
    defaults: Dict[str, Dict[str, float]] = {
        "focused":       {"assess_goal_progress": 0.15, "plan_next_step": 0.10},
        "creative":      {"generate_intrinsic_goals": 0.18, "look_outward": 0.15, "narrative_update": 0.12},
        "exploratory":   {"seek_novelty": 0.20, "search_own_files": 0.15, "look_around": 0.12},
        "philosophical": {"reflection": 0.20, "narrative_update": 0.15, "dream_cycle": 0.10},
        "critical":      {"detect_memory_contradictions": 0.18, "self_review": 0.15, "attempt_regulation": 0.10},
        "cautious":      {"attempt_regulation": 0.20, "reflection": 0.15, "self_review": 0.10},
        "analytical":    {"search_own_files": 0.18, "grep_files": 0.15, "self_review": 0.10},
    }
    return {mode: (_tag_weights(f"emo_{mode}") or dflt) for mode, dflt in defaults.items()}


# -------------------- basic loaders (unchanged API) --------------------

def _load_behavioral_names() -> frozenset:
    """Return the set of behavioral function names from the persisted list."""
    try:
        items = load_json(BEHAVIORAL_FUNCTIONS_LIST_FILE, default_type=list) or []
        names = set()
        for it in items:
            if isinstance(it, dict) and "name" in it:
                names.add(str(it["name"]))
            elif isinstance(it, str):
                names.add(it)
        return frozenset(names)
    except Exception as exc:
        record_failure("select_function.behavioral_names", exc)
        return frozenset()


# Mirrors ORRIN_loop._build_kwargs_for's mapping keys — the arg names the
# dispatcher can actually supply. A cognition function requiring any param OUTSIDE
# this set (e.g. save_goals(goals), train_on(text), apply_fix(capability, key),
# ask_llm(query)) can never be dispatched bare by the selector — it just gets
# picked, skips, wastes the cycle, and feeds a false impasse signal. We drop such
# helpers from the candidate pool so only genuinely selectable cognition competes.
# Self-maintaining: new non-dispatchable helpers are filtered automatically,
# without having to keep growing _ALWAYS_EXCLUDE by hand.
#
# NOTE: "goal"/"focus_goal" are deliberately NOT here. The dispatcher only supplies
# them WHEN a goal exists (committed_goal/focus_goal non-None); listing them as
# always-supplyable made functions like pursue_goal/try_to_accomplish pass the
# filter, then get skipped at dispatch whenever there was no goal — the bulk of
# error_log.txt and a false-impasse drip. Goal pursuit itself runs via
# pursue_committed_goal (needs only `context`), which is unaffected.
_SUPPLYABLE_ARGS: frozenset = frozenset({
    "context", "ctx", "self_model", "affect_state", "emotions", "relationships",
    "long_memory", "working_memory", "recent", "recent_memories",
    "retrieved_memories", "speaker",
})
_dispatchable_cache: Dict[str, bool] = {}


def _is_dispatchable(name: str) -> bool:
    """True unless the registered callable needs a required arg the dispatcher
    can't supply. Cached; fails open (keeps the candidate) if anything's unclear."""
    if name in _dispatchable_cache:
        return _dispatchable_cache[name]
    ok = True
    try:
        import inspect
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS  # lazy: avoid import cycle
        meta = COGNITIVE_FUNCTIONS.get(name)
        fn = meta.get("function") if isinstance(meta, dict) else meta
        if callable(fn):
            for p in inspect.signature(fn).parameters.values():
                if (p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                        and p.default is p.empty
                        and p.name not in ("self", "cls")
                        and p.name not in _SUPPLYABLE_ARGS):
                    ok = False
                    break
    except Exception:
        ok = True  # unsure → keep it; never drop a candidate by accident
    _dispatchable_cache[name] = ok
    return ok


def _load_actions() -> List[str]:
    """Load cognitive function names, excluding behavioral and bookkeeping functions."""
    items = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list)
    if not isinstance(items, list) or not items:
        return FALLBACK_ACTIONS
    beh_names = _load_behavioral_names()
    excluded = beh_names | _ALWAYS_EXCLUDE
    names: List[str] = []
    for it in items:
        name = str(it["name"]) if isinstance(it, dict) and "name" in it else (it if isinstance(it, str) else "")
        if name and name not in excluded and _is_selectable_name(name) and _is_dispatchable(name):
            names.append(name)
    return names or FALLBACK_ACTIONS


def _dominant_emotion() -> str:
    emo = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    core = emo.get("core_signals", {})
    if isinstance(core, dict) and core:
        try:
            return max(core.items(), key=lambda kv: kv[1])[0]
        except Exception as _e:
            record_failure("select_function._dominant_emotion", _e)
    return str(emo.get("dominant", "neutral"))


def _focus_goal_name() -> str:
    fg = load_json(FOCUS_GOAL, default_type=dict) or {}
    try:
        s = extract_current_focus_goal(fg)
        if s:
            return str(s)
    except Exception as _e:
        record_failure("select_function._focus_goal_name", _e)
    return str(fg.get("name", ""))


# -------------------- small helpers (additive) --------------------
# Text/keyword-overlap utilities, extracted to selection/text.py (Phase 4D).
# Re-exported (noqa F401) so external importers + tests keep their existing
# `from …select_function import _tokenize/_capability_overlap/…` paths.
from brain.think.think_utils.selection.text import (  # noqa: E402,F401
    _tokenize, _kw_overlap_score, _CAP_STOPWORDS, _capability_overlap,
)


def _load_action_defs() -> Tuple[List[str], Dict[str, str]]:
    """
    Returns (names, defs) for COGNITIVE functions only.

    Behavioral functions (outward-facing: speak, respond_to_user, etc.)
    and bookkeeping utilities (apply_cognitive_costs, apply_drive_tensions)
    are excluded so they never compete in the same bandit pool as genuine
    cognition choices.  They enter separately via Path A in ORRIN_loop.py.

    Supports:
      - ['name', ...]
      - [{'name': 'fn', 'definition': '...'}, ...]
    Falls back to using the name as the definition.
    """
    items = load_json(COGNITIVE_FUNCTIONS_LIST_FILE, default_type=list)
    if not isinstance(items, list) or not items:
        return (list(FALLBACK_ACTIONS), {n: n for n in FALLBACK_ACTIONS})

    beh_names = _load_behavioral_names()
    excluded  = beh_names | _ALWAYS_EXCLUDE

    names: List[str] = []
    defs: Dict[str, str] = {}
    for it in items:
        if isinstance(it, dict) and "name" in it:
            nm = str(it["name"])
            if nm in excluded or not _is_selectable_name(nm) or not _is_dispatchable(nm):
                continue
            names.append(nm)
            defs[nm] = str(it.get("definition") or nm)
        elif isinstance(it, str):
            if it in excluded or not _is_selectable_name(it) or not _is_dispatchable(it):
                continue
            names.append(it)
            defs[it] = it

    if len(names) < 2:
        for fb in FALLBACK_ACTIONS:
            if fb not in names and fb not in excluded:
                names.append(fb)
                defs[fb] = fb
    return names, defs


def _get_directive_text() -> str:
    sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    cd = sm.get("core_directive")
    if isinstance(cd, dict):
        return str(cd.get("statement", "")) or ""
    if isinstance(cd, str):
        return cd
    return ""


def _planned_action_recruitment(context: Dict[str, Any], actions: List[str]) -> Dict[str, float]:
    """Bounded deliberate boost for an explicit Executive handoff."""
    goal = context.get("committed_goal") or {}
    need_fn = goal.get("_needs_deliberate_action") if isinstance(goal, dict) else None
    if not need_fn or need_fn not in actions:
        return {}
    impasse = float(
        ((context.get("affect_state") or {}).get("core_signals") or {}).get(
            "impasse_signal", 0.0
        ) or 0.0
    )
    return {str(need_fn): min(0.6, 0.22 + 0.5 * impasse)}


def _get_focus_goal_text() -> str:
    fg = load_json(FOCUS_GOAL, default_type=dict) or {}
    try:
        s = extract_current_focus_goal(fg)
        if s:
            return str(s)
    except Exception as _e:
        record_failure("select_function._get_focus_goal_text", _e)
    name = str(fg.get("name", "") or "")
    desc = str(fg.get("description", "") or "")
    return (name + " " + desc).strip()


def _dominant_emotion_and_stagnation_signal(context: Dict[str, Any] | None = None) -> Tuple[str, float]:
    # Prefer in-memory context so function selection uses the current cycle's
    # emotional state, not the stale disk file from the previous cycle.
    if context is not None:
        emo = context.get("affect_state") or {}
    else:
        emo = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    core = emo.get("core_signals", {}) or {}
    stagnation_signal = float(core.get("stagnation_signal", emo.get("stagnation_signal", 0.0)) or 0.0)
    dom = None
    try:
        if isinstance(core, dict) and core:
            dom = max(core.items(), key=lambda kv: kv[1])[0]
    except Exception:
        dom = None
    return (dom or str(emo.get("dominant", "neutral"))), max(0.0, min(1.0, stagnation_signal))


def _recent_picks_from_ctx(ctx: Dict[str, Any]) -> List[str]:
    rp = ctx.get("recent_picks", [])
    return rp if isinstance(rp, list) else []


def _emotion_pref_scores_for_dominant(actions: List[str]) -> Dict[str, float]:
    """
    Use *only existing state* to bias functions by emotion:
    - First look inside AFFECT_STATE_FILE:
        - emotion_function_map[dominant] / function_preferences[dominant] / emotion_function_weights[dominant]
    - Then (fallback) look inside EMOTION_FUNCTION_MAP_FILE if present.
    Normalizes to [0..1] with a floor, and handles singletons.
    """
    emo_state = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    dom = _dominant_emotion()
    candidates = (
        (emo_state.get("emotion_function_map") or {}),
        (emo_state.get("function_preferences") or {}),
        (emo_state.get("emotion_function_weights") or {}),
    )
    pref: Dict[str, float] = {}
    for block in candidates:
        if isinstance(block, dict) and isinstance(block.get(dom), dict):
            for fn, wt in block[dom].items():  # type: ignore[index]
                if fn in actions and isinstance(wt, (int, float)):
                    pref[fn] = float(wt)
            break

    # 🔁 fallback: dedicated map file produced by update_affect_function_map(...)
    if not pref and EMOTION_FUNCTION_MAP_FILE:
        try:
            external_map = load_json(EMOTION_FUNCTION_MAP_FILE, default_type=dict) or {}
            block = external_map.get(dom)
            if isinstance(block, dict):
                for fn, wt in block.items():
                    if fn in actions and isinstance(wt, (int, float)):
                        pref[fn] = float(wt)
        except Exception as _e:
            record_failure("select_function._emotion_pref_scores_for_dominant", _e)

    if not pref:
        return {}

    vals = list(pref.values())
    if len(vals) == 1:               # singleton → full weight
        k = next(iter(pref))
        return {k: 1.0}

    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return {k: 0.15 + 0.85 * ((v - lo) / span) for k, v in pref.items()}  # small floor so emo signal shows up




def _semantic_emotion_prior(actions: List[str], dominant: str) -> Dict[str, float]:
    """
    Return semantic prior scores [0..1] for actions based on dominant emotion.
    Uses the hard-coded _SEMANTIC_PRIORS table so emotion drives selection from
    cycle 1, before the learned map has accumulated evidence.
    """
    priors = _SEMANTIC_PRIORS.get(dominant.lower(), {})
    return {name: priors[name] for name in actions if name in priors}


def _devalue_prior(
    prior: float,
    name: str,
    stats: Dict[str, Dict[str, float]],
    pool_median: float | None,
) -> float:
    """
    Decay a static emotion prior by how far this fn's learned avg_reward sits
    below the candidate-pool median (LEARNING_DIAGNOSIS_2026-06-16 §5.2).

    Only applies once the fn has >= SELECTOR_DEVAL_MIN_PULLS of evidence, and is
    floored at SELECTOR_DEVAL_FLOOR so a prior can never be killed outright (cold
    re-sampling must stay possible). Restores outcome-devaluation sensitivity:
    a prior cannot keep boosting an arm the agent has proven is worse than peers.
    """
    if prior <= 0.0 or pool_median is None:
        return prior
    st = stats.get(name) or {}
    if int(st.get("count", 0) or 0) < int(_tuning.SELECTOR_DEVAL_MIN_PULLS):
        return prior
    gap = pool_median - float(st.get("avg_reward", 0.5) or 0.5)
    count = int(st.get("count", 0) or 0)
    avg = float(st.get("avg_reward", 0.5) or 0.5)
    # A heavily sampled neutral outcome is itself evidence: the action is
    # predictably boring even when the pool median is also flat.
    # P4 — give self-knowledge MORE authority over a heavily-sampled, proven-neutral
    # action. Calibration was near-perfect (Brier 0.010) yet had ~zero authority
    # over action: generate_intrinsic_goals learned `neutral` and was STILL picked
    # #1. The neutral-penalty ceiling now rises with evidence (0.20 → 0.40 once an
    # arm is deeply sampled), and for such an arm the demotion floor drops, so "I
    # know this is empty" can finally become "so I'll pick it less" — while the
    # SELECTOR_DEVAL_MIN_PULLS count gate above still protects cold re-sampling of
    # lightly-sampled arms.
    neutral_cap = 0.40 if count >= 50 else 0.20
    neutral_penalty = min(neutral_cap, 0.03 * (count ** 0.5)) if abs(avg - 0.5) <= 0.05 else 0.0
    if gap <= 0.0 and neutral_penalty <= 0.0:
        return prior
    floor = float(_tuning.SELECTOR_DEVAL_FLOOR)
    if count >= 50 and neutral_penalty >= 0.30:
        floor = floor * 0.5   # proven-empty AND heavily sampled → demotable further
    return prior * max(
        floor,
        1.0 - float(_tuning.SELECTOR_DEVAL_K) * max(0.0, gap) - neutral_penalty,
    )


def _novelty_score(name: str, recent: List[str]) -> float:
    """
    High if not used recently or rarely used.
    Combines recency distance and inverse frequency within a window.
    """
    if not recent:
        return 1.0
    try:
        idx = len(recent) - 1 - recent[::-1].index(name)
        distance = len(recent) - 1 - idx
    except ValueError:
        distance = len(recent)  # never seen → maximum novelty

    window = recent[-32:]
    freq = window.count(name)
    # recency: farther back → higher
    r = min(1.0, distance / max(4.0, len(window) / 4.0))
    # frequency: fewer occurrences → higher
    f = 1.0 - min(1.0, (freq - 0.0) / max(1.0, len(window) / 3.0))
    return max(0.0, min(1.0, 0.6 * r + 0.4 * f))


def _bandit_pick_with_info(actions: List[str], feats: Dict[str, float]) -> Tuple[str, Dict[str, Any]]:
    """
    Try to get (picked, info) from the bandit; degrade gracefully to just a choice.
    `info` may contain 'scores', 'epsilon', etc., if supported by the bandit.
    """
    if hasattr(bandit, "choose"):
        # Prefer newer signature that can return scores
        try:
            picked, info = bandit.choose(actions, feats, return_scores=True)  # type: ignore
            if not isinstance(info, dict):
                info = {"_info": info}
            return picked, info
        except TypeError:
            res = bandit.choose(actions, feats)  # type: ignore
            if isinstance(res, tuple) and len(res) >= 2:
                return res[0], {"scores": res[1]}
            return res, {}
    if hasattr(bandit, "pick"):
        return bandit.pick(actions, feats), {}
    return (actions[0] if actions else ""), {}


def _bandit_hint_scores(actions: List[str], feats: Dict[str, float]) -> Dict[str, float]:
    """
    Return bandit UCB scores for all actions, clamped to [0..1].
    Uses get_scores() directly so learned weights actually influence selection —
    the old approach called choose(..., return_scores=True) which threw TypeError
    and always returned an empty dict.

    Fixed-scale clamp instead of min-max normalization (function_selection_fix_v2
    §3.3): the bandit returns an optimistic 1.0 for any cold arm in the current
    bucket (contextual_bandit.get_scores). Min-max DESTROYED that optimism —
    when every candidate is cold they all score 1.0, the span collapses to 0, and
    they all normalize to 0.0, so the bandit's exploration never reached the pick.
    Clamping preserves the cold-arm 1.0 as a real positive hint.
    """
    try:
        from brain.think.bandit.contextual_bandit import get_scores
        raw = get_scores(actions, feats)
        if not raw:
            return {}
        return {k: max(0.0, min(1.0, float(v))) for k, v in raw.items()}
    except Exception as exc:
        record_failure("select_function.bandit_scores", exc)
        return {}


def _ensure_min_candidates(actions: List[str]) -> List[str]:
    """Guarantee at least 2 options to avoid collapsing into auto-select."""
    if len(actions) >= 2:
        return list(dict.fromkeys(actions))  # de-dupe preserve order
    seeded = list(dict.fromkeys([*actions, *FALLBACK_ACTIONS]))
    return seeded[:2] if len(seeded) >= 2 else seeded


# -------------------- public features (your original, unchanged) --------------------
def extract_features(context: Dict) -> Dict[str, float]:
    ctx = context or {}
    es = ctx.get("affect_state", {}) or {}
    features: Dict[str, float] = {
        "bias_action": float(ctx.get("bias_action", 0.0) or 0.0),
        "pending_tools": float(len(ctx.get("pending_tools", []) or [])),
        "resource_deficit": float(es.get("resource_deficit", 0.0) or 0.0),
        "has_focus_goal": 1.0 if _focus_goal_name() else 0.0,
    }
    emo = _dominant_emotion()
    features[f"emo_{emo}"] = 1.0
    # Explicit intercept so the bandit can learn a baseline
    features["__bias__"] = 1.0

    # Neuromodulator state features — bandit learns context→reward associations over time.
    # These also feed directly into the neuromodulator boost block in select_function().
    _ne = float(es.get("_ne_proxy") or es.get("activation_level") or 0.0)
    if _ne > 0.3:
        features["ne_high"] = round(min(1.0, _ne), 3)
    _sero = float(es.get("_stability_signal_proxy") or 0.0)
    if _sero > 0.1:
        features["stability_signal"] = round(min(1.0, _sero), 3)
    _bs_f = ctx.get("body_sense") or {}
    _cort = min(1.0, max(0, int(_bs_f.get("_stress_streak") or 0) - 20) / 200.0)
    if _cort > 0.05:
        features["stress_load_load"] = round(_cort, 3)

    # User-presence signal: critical for learning that helpfulness is rewarded.
    # finalize.py gives agentic_action 1.0 reward and cognition_only 0.2 — but
    # only if the bandit can see user_present as a feature can it learn that pattern.
    if (ctx.get("latest_user_input") or "").strip():
        features["user_present"] = 1.0

    # Local-search intent signal (Nelson & Narens, 1990 monitoring / FOK).
    # Graded 0..1 — the bandit learns to associate this feature with
    # search_own_files getting rewarded (Auer et al., 2002 contextual UCB).
    local_search_strength = float(ctx.get("_local_search_signal", 0.0) or 0.0)
    if local_search_strength > 0.0:
        features["signal_local_search"] = local_search_strength

    # Action-debt feature: bandit can learn that high debt predicts action functions
    # over cognition functions (temporal difference credit assignment).
    debt = int(ctx.get("action_debt", 0) or 0)
    if ctx.get("_goal_pressure_amplified"):
        debt = int(debt * 1.5)  # amplify so select_function scores goal fns higher
    if debt > 0:
        features["action_debt"] = min(1.0, debt / 5.0)

    # Tension active: 1.0 when formative tensions exist.
    # Bandit learns that reflection/values functions are rewarded during tension.
    try:
        if ctx.get("active_tensions"):
            features["tension_active"] = 1.0
    except Exception as _e:
        record_failure("select_function.extract_features", _e)

    # Goal stalled: 1.0 when the committed goal has hit the stall threshold.
    # Bandit learns that plan_self_evolution/reflection get rewarded when stalled.
    try:
        _cg = ctx.get("committed_goal") or {}
        if isinstance(_cg, dict) and _cg.get("_stalled"):
            features["goal_stalled"] = 1.0
    except Exception as _e:
        record_failure("select_function.extract_features.2", _e)

    # Deadline pressure: graded signal so bandit can learn goal-pursuit functions
    # get rewarded when time is running out.
    try:
        _tp = ctx.get("_temporal_pressure") or {}
        _alerts = _tp.get("deadline_alerts") or []
        if _alerts:
            _phases = {a.get("phase", "") for a in _alerts if isinstance(a, dict)}
            if "overdue" in _phases or "imminent" in _phases:
                features["deadline_pressure"] = 1.0
            elif "approaching" in _phases:
                features["deadline_pressure"] = 0.6
            elif "near" in _phases:
                features["deadline_pressure"] = 0.3
    except Exception as _e:
        record_failure("select_function.extract_features.3", _e)

    # Identity investment: keyword overlap between the active goal and identity_story
    # + core_values. Higher overlap → bandit learns goal-pursuit functions get rewarded.
    try:
        _cg = ctx.get("committed_goal") or {}
        if isinstance(_cg, dict):
            _goal_text = ((_cg.get("title") or "") + " " + (_cg.get("description") or "")).strip()
            if _goal_text:
                _sm = load_json(SELF_MODEL_FILE, default_type=dict) or {}
                _id_story = str(_sm.get("identity_story", "") or "")
                _cv = _sm.get("core_values") or []
                _cv_text = " ".join(
                    (v["value"] if isinstance(v, dict) else str(v)) for v in _cv
                )
                _id_combined = (_id_story + " " + _cv_text)
                features["identity_investment"] = min(1.0, _kw_overlap_score(_goal_text, _id_combined) * 3.0)
    except Exception as _e:
        record_failure("select_function.extract_features.4", _e)

    # Distress-present feature: graded signal so the bandit can learn that
    # regulation functions produce higher reward when distress is elevated.
    # Aldao et al. (2010): strategy selection effectiveness is context-dependent —
    # the bandit must observe the context (distress level) to learn the association.
    # Without this feature the reward gradient exists but the bandit cannot see
    # the input that predicts it, so the pattern never generalises.
    try:
        from brain.affect.observers import negative_load
        _distress = negative_load(ctx.get("affect_state") or {})
        if _distress > 0.35:
            features["distress_present"] = min(1.0, _distress / 2.5)
    except Exception as _e:
        record_failure("select_function.extract_features.5", _e)

    return features


# -------------------- main selection (multi-factor) --------------------
def select_function(context: Dict, *args: Any, **kwargs: Any) -> Union[str, Tuple[str, Dict, bool]]:
    """
    Back-compat selector with multi-factor scoring (no new files):
      - Directive alignment (keyword overlap)
      - Focus-goal alignment (keyword overlap)
      - Emotion bias (if AFFECT_STATE_FILE holds per-emotion fn weights)
      - Novelty/recency (rare & not recently used → higher)
      - stagnation_signal boosts novelty weight
      - Bandit scores used as a hint (small weight), not the decider

    - New style: select_function(context) -> "fn_name"
    - Legacy: select_function(context, ...) -> (fn_name, reason, is_action)
    """
    # Candidates + definitions (if present in JSON)
    actions, defs = _load_action_defs()
    actions = _ensure_min_candidates(actions)

    # LLM-as-tool gating: functions tagged requires_llm are skipped cleanly when
    # the LLM tool is down — not candidates, no error, no template fallback.
    # When the tool comes back they rejoin the pool automatically.
    try:
        from brain.utils.llm_gate import filter_llm_dependent
        filtered = filter_llm_dependent(actions)
        # If filtering empties the pool, fall back to safe defaults — never
        # restore the LLM-dependent candidates (the old `or actions` fallback
        # is exactly how requires_llm functions kept getting selected and
        # failing while the tool was down).
        actions = filtered if filtered else _ensure_min_candidates([])
    except Exception as _e:
        record_failure("select_function.select_function", _e)

    # Drop functions the dispatcher has already refused this session
    # (unsatisfiable required args). Selecting them again just burns the cycle.
    try:
        _undisp = set(context.get("_undispatchable_fns") or [])
        if _undisp:
            remaining = [a for a in actions if a not in _undisp]
            actions = remaining if remaining else _ensure_min_candidates([])
    except Exception as _e:
        record_failure("select_function.select_function.2", _e)

    feats = extract_features(context)

    # Legacy signals from kwargs (if present)
    if "threat_detector_response" in kwargs:
        try:
            _amy = kwargs["threat_detector_response"]
            # threat_detector_response may be a dict (from process_affective_signals) or a float
            if isinstance(_amy, dict):
                feats["threat_detector_response"] = float(_amy.get("spike_intensity") or 0.0)
            else:
                feats["threat_detector_response"] = float(_amy)
        except Exception:
            feats["threat_detector_response"] = 0.0

    is_legacy = bool(args) or bool(kwargs)
    decision_id = str(uuid.uuid4())

    # Multi-factor data
    directive = _get_directive_text()
    focus_goal_text = _get_focus_goal_text()
    recent = _recent_picks_from_ctx(context)
    dominant, stagnation_signal = _dominant_emotion_and_stagnation_signal(context)
    emo_pref = _emotion_pref_scores_for_dominant(actions)
    band_hint = _bandit_hint_scores(actions, feats)

    # Semantic emotion priors: fire immediately from cycle 1.
    # As the learned map fills in, learned scores gain weight (0.5 each when both present).
    sem_prior = _semantic_emotion_prior(actions, dominant)

    # Weights: emotion raised to 0.25 now that it carries real signal.
    # Novelty weight reduced (was 0.20) — was driving look_outward to 33% of cycles.
    # stagnation_signal can still amplify novelty but from a lower base.
    # Values live in config.tuning (Finding 9 — single place to view/tune the
    # selector's parameter space).
    w_dir = _tuning.SELECTOR_W_DIR
    w_goal = _tuning.SELECTOR_W_GOAL
    w_emo = _tuning.SELECTOR_W_EMO
    base_w_novel = _tuning.SELECTOR_BASE_W_NOVEL   # reduced from 0.20 to prevent novelty-seeking domination
    w_novel = min(0.25, base_w_novel * (1.0 + 2.0 * stagnation_signal))  # stagnation_signal still helps, capped lower
    w_band = _tuning.SELECTOR_W_BAND  # bandit hint (raised 0.15→0.25, fn_selection_fix_v2 §3.3: now
                   # that the pool is clean (Phase 1) and the cold-arm optimism
                   # survives normalization, the learned/exploratory hint can
                   # compete with the additive boosts — still a hint, not decider.
    w_drive = _tuning.SELECTOR_W_DRIVE  # net drive-pull bias

    # === Attention-mode modulation (signal_router → selection) ===
    # The signal_router computes attention_mode from signal priority; here we
    # let that mode actually change what gets picked by adjusting weights
    # and adding per-function affinities.  Without this the mode is cosmetic.
    attention_mode = str(context.get("attention_mode") or "neutral")
    _attn_fn_boost: Dict[str, float] = {}

    # Attention-mode multipliers/caps/boosts live in config.tuning (Finding 9).
    if attention_mode == "alert":
        # User is present: strongly bias toward helpful, goal-directed functions.
        # The emotion prior for reflection (e.g. impasse_signal→reflection at 0.85)
        # otherwise wins — the boosts here must overpower that pull.
        w_goal  = min(_tuning.ATTN_ALERT_GOAL_CAP, w_goal  * _tuning.ATTN_ALERT_GOAL_MULT)
        w_novel = max(_tuning.ATTN_ALERT_NOVEL_FLOOR, w_novel * _tuning.ATTN_ALERT_NOVEL_MULT)
        w_emo   = max(_tuning.ATTN_ALERT_EMO_FLOOR, w_emo   * _tuning.ATTN_ALERT_EMO_MULT)  # reduce emotion's pull on function choice
        # E6: pursue_committed_goal removed — it is in _ALWAYS_EXCLUDE, never in
        # `actions`, so boosting it here was dead. Goal-specific routing now comes
        # from the §4.2 goal-recruit block below. Phase 4: membership is the
        # "mode_alert" tag in the capability manifest.
        for fn in _MODE_ALERT_FNS:
            _attn_fn_boost[fn] = _tuning.ATTN_ALERT_FN_BOOST
        # Suppress pure introspection — user is here, it can wait
        for fn in _INTROSPECTION_FUNCTIONS:
            _attn_fn_boost[fn] = _attn_fn_boost.get(fn, 0.0) + _tuning.ATTN_ALERT_INTROSPECTION_PENALTY

    elif attention_mode == "engaged":
        # High-priority signal but no direct user input: moderate goal + emotion lift.
        w_goal = min(_tuning.ATTN_ENGAGED_GOAL_CAP, w_goal * _tuning.ATTN_ENGAGED_GOAL_MULT)
        w_emo  = min(_tuning.ATTN_ENGAGED_EMO_CAP, w_emo  * _tuning.ATTN_ENGAGED_EMO_MULT)
        for fn in _MODE_ENGAGED_FNS:  # Phase 4: "mode_engaged" tag (E6: pursue dropped)
            _attn_fn_boost[fn] = _tuning.ATTN_ENGAGED_FN_BOOST

    elif attention_mode == "wandering":
        # Internal signals dominate — but proactive/outward before pure introspection.
        # Reflection is valuable but should not be the default when nothing is urgent.
        w_novel = min(_tuning.ATTN_WANDERING_NOVEL_CAP, w_novel * _tuning.ATTN_WANDERING_NOVEL_MULT)
        w_dir   = max(_tuning.ATTN_WANDERING_DIR_FLOOR, w_dir   * _tuning.ATTN_WANDERING_DIR_MULT)
        w_goal  = max(_tuning.ATTN_WANDERING_GOAL_FLOOR, w_goal  * _tuning.ATTN_WANDERING_GOAL_MULT)
        # Tier 1: proactive outward engagement (Phase 4: "mode_wandering" tag)
        for fn in _MODE_WANDERING_FNS:
            _attn_fn_boost[fn] = _tuning.ATTN_WANDERING_OUTWARD_BOOST
        # Tier 2: introspection (useful but not the default; "mode_wandering_reflect")
        for fn in _MODE_WANDERING_REFLECT_FNS:
            _attn_fn_boost[fn] = _tuning.ATTN_WANDERING_REFLECT_BOOST

    elif attention_mode == "drowsy":
        # No signals at all: consolidation / rest over active cognition.
        w_novel = max(_tuning.ATTN_DROWSY_NOVEL_FLOOR, w_novel * _tuning.ATTN_DROWSY_NOVEL_MULT)
        w_emo   = max(_tuning.ATTN_DROWSY_EMO_FLOOR, w_emo   * _tuning.ATTN_DROWSY_EMO_MULT)
        w_dir   = min(_tuning.ATTN_DROWSY_DIR_CAP, w_dir   * _tuning.ATTN_DROWSY_DIR_MULT)
        for fn in _MODE_DROWSY_FNS:  # Phase 4: "mode_drowsy" tag
            _attn_fn_boost[fn] = _tuning.ATTN_DROWSY_FN_BOOST

    # Phase 3 (dual_process_loop.md §6.2 → §11): react to a Metacog Monitor
    # breakthrough that WON consciousness. The Global Workspace broadcast carries
    # the requested route ("wants"); bias the deliberate pick toward acting on it —
    # diagnose / re-plan / decide / savor / pick-new-goal. This BIASES, never forces
    # (I7): it's an additive boost competing with everything else.
    _gw_now = context.get("global_workspace") or {}
    context.pop("_bt_pending", None)   # only set when a monitor breakthrough is live this cycle
    if str(_gw_now.get("source", "")).startswith("monitor:"):
        _route = {
            "re-plan":       {"redirect_goal_plan": 0.34, "adapt_subgoals": 0.30,
                              "assess_goal_progress": 0.22},
            "diagnose":      {"search_own_files": 0.30, "assess_goal_progress": 0.24,
                              "reflect_on_self_beliefs": 0.20},
            "decide":        {"attend_goal": 0.34},
            "savor":         {"narrative_update": 0.18},
            "comprehend":    {"narrative_update": 0.28, "reflect_on_self_beliefs": 0.18},
            "release":       {"abandon_goal": 0.40},   # guarded: only abandons a stuck goal
            "pick-new-goal": {"generate_intrinsic_goals": 0.34},
        }.get(_gw_now.get("wants"), {})
        for _rfn, _rb in _route.items():
            _attn_fn_boost[_rfn] = _attn_fn_boost.get(_rfn, 0.0) + _rb
        # §20.1 dismissal-recalibration: remember which functions would HONOR this
        # breakthrough's route, so the final pick can be judged honored vs dismissed
        # (the Monitor reads the verdict next cycle to quiet crying-wolf kinds).
        if _route:
            context["_bt_pending"] = {"kind": _gw_now.get("kind"), "route_fns": list(_route.keys())}

    # ── Workspace → action coupling (Fix 2; Redgrave, Prescott & Gurney 1999) ──
    # The Global Workspace already chose ONE conscious content this cycle. In the
    # brain, the basal-ganglia selector is driven by the currently salient cortical
    # representation — the "spotlight" and the motor selector are the SAME
    # bottleneck. Here they had drifted apart: the workspace winner only biased
    # selection when it was a Monitor breakthrough (above); for ordinary conscious
    # content (a feeling, the goal, a percept, a thought) it touched nothing, so
    # awareness and action were decoupled. This makes the conscious content a real
    # prior on the action pick, scaled by its salience — a strong additive bias,
    # NOT a hard override (I7: bias, never preempt). Monitor breakthroughs are
    # already routed above, so they're skipped here to avoid double-counting.
    # Disable with ORRIN_WORKSPACE_PRIOR=0.
    _workspace_prior: Dict[str, float] = {}
    try:
        import os as _os_wp
        if _os_wp.environ.get("ORRIN_WORKSPACE_PRIOR", "1") != "0":
            _gw_ws  = context.get("global_workspace") or {}
            _ws_src = str(_gw_ws.get("source", ""))
            _ws_sal = float(_gw_ws.get("salience", 0.0) or 0.0)
            if _ws_src and not _ws_src.startswith("monitor:") and _ws_sal > 0.0:
                # source → the functions that ACT ON that kind of conscious content.
                _ws_routes = _workspace_routes_for(_gw_ws)
                # Headroom 0.35: strong enough to be a genuine prior (cf. tension 0.15,
                # ACC recruit ≤0.6), bounded so it never dominates the arg-max alone.
                _ws_gain = 0.35 * max(0.0, min(1.0, _ws_sal))
                for _wfn, _wwt in _ws_routes.items():
                    if _wfn in actions:
                        _workspace_prior[_wfn] = _ws_gain * _wwt
    except Exception as _wpe:
        record_failure("select_function.workspace_prior", _wpe)

    # ── Unconscious damp (Fix 1 teeth; Dehaene 2014 ignition is all-or-none) ────
    # On a non-ignited cycle the loop stayed in low-power default mode: deliberate
    # System-2 functions should not win the slot. Damp the expensive/generative
    # deliberate functions so a quiet cycle drifts toward cheap default-mode work
    # (light reflection, rest) instead of spinning up planning/codegen/research.
    # Graded penalty, never a lockout — the floor still forces ignition eventually.
    # Disable with ORRIN_IGNITION_GATE=0 (the gate itself sets _conscious_cycle).
    _unconscious_damp: Dict[str, float] = {}
    try:
        if context.get("_conscious_cycle") is False:
            _EFFORTFUL_FNS = frozenset({
                "plan_next_step", "plan_self_evolution", "redirect_goal_plan",
                "adapt_subgoals", "generate_intrinsic_goals", "decide_to_write_code",
                "write_cognitive_function", "skill_synthesis", "self_review",
                "web_research", "look_outward", "search_own_files",
            })
            for _efn in _EFFORTFUL_FNS:
                if _efn in actions:
                    _unconscious_damp[_efn] = -0.30
    except Exception as _ude:
        record_failure("select_function.unconscious_damp", _ude)

    # Tension boost: when active tensions exist, nudge resolution-oriented functions
    _tension_boost: Dict[str, float] = {}
    try:
        active_tensions = context.get("active_tensions") or []
        if active_tensions:
            for fn in ("reflection", "propose_value_revision", "plan_self_evolution", "self_review", "narrative_update"):
                _tension_boost[fn] = 0.15
    except Exception as _e:
        record_failure("select_function.select_function.3", _e)

    # ── ACC→dlPFC control recruitment ───────────────────────────────────────
    # When the committed goal is blocked on a deliberate/generative action the
    # background Executive can't run (pursue marked goal["_needs_deliberate_action"],
    # e.g. decide_to_write_code), let the impasse that the block PRODUCES recruit the
    # conscious selector toward actually doing it — instead of toward affect-
    # regulation/introspection, which is where the impasse_signal prior otherwise
    # routes (soothing the feeling, not resolving the cause). Scaled by impasse so the
    # alarm clears by the goal getting done. Additive bias, never a forced pick (I7).
    _recruit_boost: Dict[str, float] = {}
    try:
        # An explicit planned handoff is already evidence of relevance. It
        # should not need to manufacture distress before becoming viable;
        # impasse amplifies the bounded recruitment instead.
        _recruit_boost = _planned_action_recruitment(context, actions)
    except Exception as _e:
        record_failure("select_function.select_function.recruit", _e)

    # Deadline urgency: imminent/overdue deadlines strongly bias toward goal pursuit
    try:
        _tp_alerts = (context.get("_temporal_pressure") or {}).get("deadline_alerts") or []
        if _tp_alerts:
            _phases = {a.get("phase", "") for a in _tp_alerts if isinstance(a, dict)}
            # E6: pursue_committed_goal lines dropped (dead — not in `actions`).
            # The deadline urgency now lands on the real selectable goal fns.
            if "overdue" in _phases or "imminent" in _phases:
                _tension_boost["assess_goal_progress"]  = max(_tension_boost.get("assess_goal_progress", 0), 0.25)
                _tension_boost["plan_next_step"]        = max(_tension_boost.get("plan_next_step", 0), 0.20)
            elif "approaching" in _phases:
                _tension_boost["assess_goal_progress"]  = max(_tension_boost.get("assess_goal_progress", 0), 0.15)
    except Exception as _e:
        record_failure("select_function.select_function.4", _e)

    # Drive competition: compute per-function pull from competing motivations.
    # apply_drive_tensions() also bumps uncertainty and logs the hottest conflict.
    _drive_pull: Dict[str, float] = {}
    try:
        from brain.cognition.goal_competition import apply_drive_tensions, compute_drive_strengths, drive_pull_scores
        _conflicts = apply_drive_tensions(context)
        _strengths = context.get("_drive_strengths") or compute_drive_strengths(context)
        # Master plan 4.1: commitment strength is a tie-breaker input to goal
        # competition — a dearly-held vow pulls toward pursuit functions.
        _c = context.get("_commitment")
        _cs = float(_c.get("strength", 0.0)) if isinstance(_c, dict) else 0.0
        _drive_pull = drive_pull_scores(actions, _strengths, commitment_strength=_cs)
    except Exception as _e:
        record_failure("select_function.select_function.5", _e)

    # Function chaining bonus: if the previous function has a known high-reward
    # successor in function_chains.json, add its stored bonus to that successor.
    # This implements basal-ganglia-style procedural chunking learned during dream.
    _chain_boost: Dict[str, float] = {}
    try:
        import json as _json
        from brain.paths import DATA_DIR as _DATA_DIR
        _chains_path = _DATA_DIR / "function_chains.json"
        if _chains_path.exists():
            _chains = _json.loads(_chains_path.read_text(encoding="utf-8"))
            _last_fn = (recent[-1] if recent else None)
            if _last_fn and _last_fn in _chains:
                for _succ, _entry in (_chains[_last_fn] or {}).items():
                    if _succ in actions:
                        _chain_boost[_succ] = float(
                            _entry.get("bonus", 0.0) if isinstance(_entry, dict) else 0.0
                        )
    except Exception as _e:
        record_failure("select_function.select_function.6", _e)

    # Energy orientation boost: high energy → action functions up; low/rest → reflection up.
    _energy_boost: Dict[str, float] = {}
    try:
        from brain.motivation.energy_orientation import energy_boost_scores as _ebs
        _energy_state = str(context.get("energy_state") or "medium")
        _action_bias  = float(context.get("action_vs_reflect_bias") or 0.5)
        _rest_mode    = bool(context.get("_rest_mode"))
        _energy_boost = _ebs(actions, _energy_state, _action_bias, _rest_mode)
    except Exception as _e:
        record_failure("select_function.select_function.7", _e)

    # === Emotional mode → function selection translation ===
    # recommend_mode_from_affect_state() returns "focused"/"creative"/"exploratory" etc.
    # select_function reads attention_mode ("alert"/"wandering"/"drowsy") from signal_router.
    # These are two different vocabularies that never talked to each other — this block
    # bridges them by translating the emotional mode into direct function score boosts.
    _emo_mode_boost: Dict[str, float] = {}
    try:
        from brain.affect.modes_and_affect import get_current_mode as _gcm
        _emo_mode = _gcm()
        # Phase 4: weighted "emo_<mode>:<w>" tags in the capability manifest are
        # the source of truth (literal fallbacks inside _emo_mode_function_map).
        _emo_mode_boost = _emo_mode_function_map().get(_emo_mode, {})
    except Exception as _e:
        record_failure("select_function.select_function.8", _e)

    # Compute goal status before neuromodulator block — used at line 749.
    # Was previously defined at line 815, causing NameError inside the try block
    # that silently killed all NE, stability_signal, and stress_load boosts.
    _goal_obj_pre = context.get("committed_goal") if context else None
    _has_committed_goal = (
        isinstance(_goal_obj_pre, dict)
        and bool(_goal_obj_pre.get("title") or _goal_obj_pre.get("name"))
        and _goal_obj_pre.get("status") not in ("completed", "abandoned", "failed")
    )

    # === Neuromodulator-driven function selection boosts ===
    # These translate chemical state directly into behavioral choice — the mechanism
    # by which NE, stability_signal, and stress_load actually change what Orrin does next.
    # Without this block these signals stay in affect_state and do nothing.
    _neuro_boost: Dict[str, float] = {}
    try:
        _emo_full      = context.get("affect_state") or {}
        _ne_level      = float(_emo_full.get("_ne_proxy") or _emo_full.get("activation_level") or 0.0)
        _sero_level    = float(_emo_full.get("_stability_signal_proxy") or 0.0)
        _bs_nb         = context.get("body_sense") or {}
        _stress_streak = int(_bs_nb.get("_stress_streak", 0) or 0)
        _stress_load_load = min(1.0, max(0, _stress_streak - 20) / 200.0)

        # gain_signal (Sara 2009): high activation_level narrows attention to the goal at hand.
        # Suppresses exploration and mind-wandering; pushes pursuit and assessment up.
        # Phase 4: membership via "neuro_*" tags. E6: pursue_committed_goal
        # dropped from the focus list (dead — never in `actions`).
        if _ne_level > 0.45:
            _ne_scale = (_ne_level - 0.45) / 0.55  # 0→1 above threshold
            for fn in _NEURO_NE_FOCUS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) + _ne_scale * 0.22
            for fn in _NEURO_NE_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _ne_scale * 0.15

        # stability_signal (Dayan & Huys 2009): promotes patience and persistence.
        # High stability_signal → stay on the current goal, don't reflexively switch to regulation.
        # E6: the persistence boost used to land on pursue_committed_goal, which is
        # never in the pool — moved to attend_goal, the thin selectable "consciously
        # stay with the goal" proxy (same relocation as the commitment bias).
        if _sero_level > 0.12 and _has_committed_goal:
            _sero_scale = min(1.0, (_sero_level - 0.12) / 0.38)
            _neuro_boost["attend_goal"] = (
                _neuro_boost.get("attend_goal", 0.0) + _sero_scale * 0.18
            )
            for fn in _NEURO_CALM_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _sero_scale * 0.10

        # stress_load allostatic load (McEwen 2007): sustained stress impairs executive function.
        # Suppress high-cost planning; push toward simple, restorative actions.
        if _stress_load_load > 0.10:
            for fn in _NEURO_STRESS_SUPPRESS:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) - _stress_load_load * 0.28
            for fn in _NEURO_STRESS_RESTORE:
                _neuro_boost[fn] = _neuro_boost.get(fn, 0.0) + _stress_load_load * 0.12
    except Exception as _e:
        record_failure("select_function.select_function.9", _e)

    # User attention debt: grows when user is present but no reply was generated.
    # Feeds into helpfulness bias so unresponded-to presence creates escalating pressure to engage.
    _user_spoke = bool((context.get("latest_user_input") or "").strip())
    _last_responded = (context.get("_last_responded_input") or "").strip()
    _latest_input   = (context.get("latest_user_input") or "").strip()
    if _user_spoke and _latest_input != _last_responded:
        # User spoke but hasn't been answered yet — increment debt
        _debt = int(context.get("_user_attention_debt", 0) or 0)
        context["_user_attention_debt"] = min(_debt + 1, 10)
    elif not _user_spoke:
        # User is quiet — slowly forgive the debt
        _debt = int(context.get("_user_attention_debt", 0) or 0)
        if _debt > 0:
            context["_user_attention_debt"] = max(0, _debt - 1)
    _attention_debt = int(context.get("_user_attention_debt", 0) or 0)

    # Usefulness/helpfulness boost: when the user has spoken this cycle, helpful
    # functions get a strong additive boost that overrides intrinsic exploration_drive and
    # reflection pull. Pure introspection functions are dampened — they can wait.
    # Attention debt makes the social pull escalate until Orrin actually replies.
    _helpfulness_boost: Dict[str, float] = {}
    _debt_bonus = min(0.50, 0.10 * _attention_debt)  # up to +0.50 after 5 ignored cycles
    if _user_spoke or _attention_debt > 0:
        for fn in actions:
            if fn in _USER_HELPFUL_FUNCTIONS:
                _helpfulness_boost[fn] = 0.45 + _debt_bonus  # persistent social pull
            elif fn in _INTROSPECTION_FUNCTIONS:
                _helpfulness_boost[fn] = -0.25  # introspection must wait when user is present

    # Emotion routing — deep cognitive policy signal (not just prompt influence).
    # risk_estimate → verification; stagnation_signal → novelty; Confidence → prune; etc.
    _emo_route_boost: Dict[str, float] = {}
    try:
        from brain.cognition.emotion_routing import emotion_bias as _eb
        _emo_state_full = context.get("affect_state") or {}
        for _fn in actions:
            _bias = _eb(_fn, _emo_state_full)
            if _bias != 0.0:
                _emo_route_boost[_fn] = _bias
    except Exception as _e:
        record_failure("select_function.select_function.10", _e)

    # Standing outward-presence boost: Orrin should engage with his environment
    # regularly, not just compute internally. These functions couple cognition to the
    # world and should be structurally preferred regardless of emotional state.
    # Clark (1997) embodied cognition: acting on the environment is constitutive of
    # cognition. Lave (1988) situated action: knowledge is constituted in use.
    # Boost is graded: highest for acts that produce external artifacts (notes, code),
    # then exploration (search, look_outward), then sensing (read_clipboard, survey).
    # Phase 4: tiers come from the "outward_artifact"/"outward_explore"/
    # "outward_sense" tags (module-level _OUTWARD_HIGH/MED/LOW). E6: the dead
    # pursue_committed_goal entry in the old inline MED tier was dropped.
    _outward_boost: Dict[str, float] = {}
    for _fn in actions:
        if _fn in _OUTWARD_HIGH:
            _outward_boost[_fn] = 0.20
        elif _fn in _OUTWARD_MED:
            _outward_boost[_fn] = 0.13
        elif _fn in _OUTWARD_LOW:
            _outward_boost[_fn] = 0.07

    # Reward-aware damping (Fix #2): the standing outward boost must not keep
    # floating reads that consistently return little. Scale each boost by how well
    # the function has actually paid off — full boost at avg_reward ≥ 0.5, fading to
    # 0.3× by avg_reward ≤ 0.1. So low-yield reads (look_outward ~0.09, search_own_files
    # ~0.07) get only a small nudge and their REAL reward governs how often he reaches
    # for them; high-yield outward acts keep their full boost. Self-correcting: if a
    # read starts paying off again, its boost recovers automatically.
    _stats = _learned_stats()
    for _fn in list(_outward_boost.keys()):
        _ar = float((_stats.get(_fn) or {}).get("avg_reward", 0.5))
        _rf = max(0.3, min(1.0, (_ar - 0.1) / 0.4))
        _outward_boost[_fn] *= _rf

    # Amplify outward boost when outward-debt is high (too many internal-only cycles).
    _od = int(context.get("_outward_debt", 0) or 0)
    if _od >= 8:
        _od_scale = min(2.0, 1.0 + (_od - 8) * 0.07)
        _outward_boost = {k: v * _od_scale for k, v in _outward_boost.items()}

    # Goal shielding (Shah, Friedman & Kruglanski 2002): while a committed goal is
    # active, curiosity/exploration reads should not crowd out the goal work
    # itself. Scale DOWN the standing outward boost for pure-exploration reads when
    # pursue_committed_goal is on the table — leaving pursue_committed_goal's own
    # outward boost intact (it *is* the goal work). This is what stops look_outward
    # from monopolising cycles despite goal pursuit being the higher-reward action.
    # E6: gate on _has_committed_goal alone. The old `"pursue_committed_goal" in
    # actions` test was always False (pursue_committed_goal is in _ALWAYS_EXCLUDE),
    # so this goal-shielding never actually fired — exploration reads were never
    # damped during goal pursuit. Gating on the goal's presence restores the
    # intended Shah/Friedman/Kruglanski (2002) shielding behavior.
    if _has_committed_goal:
        _EXPLORE_READS = frozenset({
            "look_outward", "seek_novelty", "look_around",
            "search_own_files", "grep_files", "search_files",
        })
        for _fn in list(_outward_boost.keys()):
            if _fn in _EXPLORE_READS:
                _outward_boost[_fn] *= 0.4

    # No-goal suppression: pursue_committed_goal and assess_goal_progress are
    # useless (and waste a full LLM cycle) when there is no committed goal.
    # Apply a strong penalty so even a high motivation prior can't overcome it.
    # _has_committed_goal already computed above (before neuromodulator block).
    # E6: pursue_committed_goal dropped (not in pool); the no-goal suppression
    # still applies to the real deliberate goal-pursuit fns.
    _GOAL_PURSUIT_FNS = frozenset({"assess_goal_progress", "adapt_subgoals"})

    # Goal-specific recruitment (function_selection_fix_v2.md §4.2): derive which
    # functions THIS goal needs from its OWN title/description/tags via the curated
    # capability descriptions, instead of a static hardcoded name-list. This is
    # what makes different goal TYPES recruit visibly different function sets (a
    # research goal pulls research_topic/fetch_and_read/wikipedia_search; a
    # self-model goal pulls reflect_on_self_beliefs/propose_value_revision/...),
    # rather than every goal collapsing onto assess_goal_progress. Capped at +0.40
    # so it is comparable to s_attn and never dominates the score on its own.
    _goal_recruit: Dict[str, float] = {}
    try:
        _grg = context.get("committed_goal") or {}
        if isinstance(_grg, dict):
            _grg_text = " ".join(
                str(_grg.get(k, "") or "") for k in ("title", "name", "description")
            ).strip()
            # Goals created by generate_intrinsic_goals carry their description
            # nested at spec.description (often naming the exact functions to
            # use, e.g. "Use write_cognitive_function or write_tool ...") —
            # without it the recruiter only ever sees the title.
            _grg_spec = _grg.get("spec") or {}
            if isinstance(_grg_spec, dict):
                _spec_desc = str(_grg_spec.get("description") or "").strip()
                if _spec_desc:
                    _grg_text = (_grg_text + " " + _spec_desc).strip()
            _grg_tags = _grg.get("tags") or []
            if isinstance(_grg_tags, list) and _grg_tags:
                _grg_text = (_grg_text + " " + " ".join(str(t) for t in _grg_tags)).strip()
            if _grg_text:
                _caps = _capability_descriptions()
                for _nm in actions:
                    _ref = _caps.get(_nm) or defs.get(_nm, _nm)
                    _sim = _capability_overlap(_ref, _grg_text)
                    if _sim > 0.0:
                        _goal_recruit[_nm] = min(0.40, 0.6 * _sim)
    except Exception as _e:
        record_failure("select_function.select_function.11", _e)

    # Score each action
    scored: List[Tuple[str, float, Dict[str, float]]] = []
    # Curiosity nudge (Fix #3): when his exploration drive is up, make functions he
    # has rarely/never tried a little more appealing — an intrinsic pull toward
    # unfamiliar capability, NOT a forced override. Gated on exploration_drive, fades
    # as a function accumulates use, and skips the corrupted self-generated duplicates
    # so it surfaces real dormant tools rather than junk. This is how he comes to
    # *want* to exercise more of his repertoire instead of looping on a familiar few.
    _expl_drive = float(((context.get("affect_state") or {}).get("core_signals") or {}).get("exploration_drive", 0.0))
    # Cognitive-control strength for goal-shielding (Fix #1): how firmly a committed
    # goal is held (motivation + confidence), amplified below by impasse — the
    # curiosity trap forms precisely when stuck-but-committed. Used to damp blind
    # exploration so the single arg-max affect (exploration_drive) can't monopolise
    # selection against the goal. Miller & Cohen (2001) guided activation; Shah,
    # Friedman & Kruglanski (2002) goal shielding.
    _cs_now  = ((context.get("affect_state") or {}).get("core_signals") or {})
    _impasse = float(_cs_now.get("impasse_signal", 0.0) or 0.0)
    _goal_commit = max(0.0, min(1.0, 0.5 * (float(_cs_now.get("motivation", 0.0) or 0.0)
                                            + float(_cs_now.get("confidence", 0.0) or 0.0))))

    # Goal-type action gating (means-ends): an action that EXCLUSIVELY serves a
    # different kind of goal than the committed one must not win the slot — a
    # code-writing action on a research goal, or research on a code goal, is working
    # on the wrong end-state. Classify once here; penalise mismatches in the loop.
    # Only exclusive "doing" actions are gated; shared/reflective functions stay free.
    _goal_type = "general"
    _mismatch_fn = None
    _type_family: frozenset = frozenset()   # the committed goal type's instrumental actions
    if _has_committed_goal:
        try:
            from brain.cognition.planning.goal_types import (
                goal_type_of, is_mismatched_doing_action as _mismatch_fn, EXCLUSIVE_DOING,
            )
            _goal_type = goal_type_of(context.get("committed_goal") or {})
            # Type-based recruitment (EXPLORE_EXPLOIT_VALUE_PLAN §6.4 Fix A; Miller & Cohen
            # 2001 guided activation): a strongly-typed goal categorically recruits its OWN
            # means — e.g. an acquire_knowledge goal pulls research_topic/wikipedia_search —
            # which fuzzy capability-text overlap fails to distinguish from look_outward.
            _type_family = EXCLUSIVE_DOING.get(_goal_type, frozenset())
        except Exception as _gte:
            record_failure("select_function.goal_type", _gte)
            _mismatch_fn = None

    # Explore/exploit value governs the outward-exploration reads (replaces the
    # look_outward wall-clock cooldown + the standing MED outward boost for these fns,
    # so they are not double-counted). cognition.exploration_value.
    try:
        from brain.cognition.exploration_value import reach_value as _reach_value_fn, _OUTWARD_FNS as _REACH_FNS
    except Exception:
        _reach_value_fn = None
        _REACH_FNS = frozenset()

    # Prior outcome-devaluation baseline (LEARNING_DIAGNOSIS_2026-06-16 §5.2): the
    # median learned avg_reward over candidates that have enough evidence. A prior on
    # an arm whose reward sits below this median is decayed in the loop below, so a
    # static prior can no longer keep boosting an arm the agent has proven is low-yield.
    _deval_min = int(_tuning.SELECTOR_DEVAL_MIN_PULLS)
    _evidenced = [
        float((_stats.get(a) or {}).get("avg_reward", 0.5) or 0.5)
        for a in actions
        if int((_stats.get(a) or {}).get("count", 0) or 0) >= _deval_min
    ]
    _pool_median_reward = _statistics.median(_evidenced) if _evidenced else None
    context["_escape_available"] = any(
        name != "generate_intrinsic_goals"
        and name not in _GOAL_DELIBERATION_FNS
        for name in actions
    )

    for name in actions:
        definition = defs.get(name, name)
        s_dir  = _kw_overlap_score(definition, directive)
        s_goal = _kw_overlap_score(definition, focus_goal_text)
        s_nov  = _novelty_score(name, recent)
        s_band = float(band_hint.get(name, 0.0))
        s_drv  = float(_drive_pull.get(name, 0.0))  # [-1..1]: net drive pull

        # Blend learned map with semantic prior: equal weight when both present,
        # full prior when map is empty, full learned when prior has no opinion.
        learned = float(emo_pref.get(name, 0.0))
        prior   = float(sem_prior.get(name, 0.0))
        # Outcome-devaluation (§5.2): decay the static prior if this fn has proven
        # low-yield relative to its peers (see _devalue_prior).
        prior = _devalue_prior(prior, name, _stats, _pool_median_reward)
        if learned > 0 and prior > 0:
            s_emo = 0.5 * learned + 0.5 * prior
        elif learned > 0:
            s_emo = learned
        else:
            s_emo = prior * 0.85   # slight discount: pure prior, not yet validated

        s_emo = min(1.0, s_emo + _tension_boost.get(name, 0.0))
        s_attn   = float(_attn_fn_boost.get(name, 0.0))
        s_energy = float(_energy_boost.get(name, 0.0))
        s_help   = float(_helpfulness_boost.get(name, 0.0))
        # EVC cost gating (proactive_resource_plan.md Phase 3 / C2): a payoff-
        # discounted, depletion-scaled COST penalty (≤ 0) — proactively paces effort
        # by down-weighting expensive-but-low-payoff functions BEFORE spending on
        # them. Reward/depletion-mode are handled elsewhere (no double-count). Shenhav
        # et al. (2013). Fail-safe; 0 when disabled.
        s_evc = 0.0
        try:
            from brain.cognition.interoception import evc_selection_adjust as _evc_adj
            s_evc = _evc_adj(name, float((_stats.get(name) or {}).get("avg_reward", 0.5) or 0.5), context)
        except Exception:
            s_evc = 0.0
        s_emo_route = float(_emo_route_boost.get(name, 0.0))
        s_chain     = float(_chain_boost.get(name, 0.0))
        s_neuro     = float(_neuro_boost.get(name, 0.0))
        s_emo_mode  = float(_emo_mode_boost.get(name, 0.0))
        s_outward   = float(_outward_boost.get(name, 0.0))
        # Explore/exploit value for outward reads (habituation + curiosity-gap +
        # opportunity-cost + boredom). For these fns it REPLACES the standing MED
        # outward boost (zero s_outward to avoid double-counting).
        s_reach = 0.0
        if _reach_value_fn is not None and name in _REACH_FNS:
            s_reach = _reach_value_fn(name, context)
            s_outward = 0.0
        # Type-based recruitment (Fix A): the committed goal type's own means get a
        # decisive boost, comparable to the emotion prior.
        s_type_recruit = 0.20 if name in _type_family else 0.0
        s_goal_recruit = float(_goal_recruit.get(name, 0.0))  # §4.2 goal-derived
        s_recruit      = float(_recruit_boost.get(name, 0.0))  # ACC→action recruitment
        s_workspace    = float(_workspace_prior.get(name, 0.0))   # Fix 2: awareness→action
        s_uncon_damp   = float(_unconscious_damp.get(name, 0.0))  # Fix 1: quiet-cycle damp
        # Directed exploration: lift actions whose payoff is currently uncertain
        # (associability above its neutral prior). Clamped at 0 so confidently
        # modelled actions are neither bonused nor penalised (Gershman 2018).
        s_explore   = _W_EXPLORE * max(0.0, get_associability(context, name) - _ASSOC_DEFAULT)

        # Curiosity nudge toward dormant capability (Fix #3).
        s_curio = 0.0
        if _expl_drive > 0.5 and "more_deeply_more" not in name:
            _nuse = int((_stats.get(name) or {}).get("count", 0))
            if _nuse < 8:
                s_curio = 0.18 * (_expl_drive - 0.5) * (1.0 - _nuse / 8.0)

        s_goal_lens = 0.0
        try:
            from brain.cognition.goal_lens import action_prior as _goal_lens_prior
            s_goal_lens = _goal_lens_prior(context.get("goal_lens"), name, definition)
        except Exception as exc:
            record_failure("select_function.goal_lens_prior", exc)
        total = (w_dir * s_dir) + (w_goal * s_goal) + (w_emo * s_emo) + (w_novel * s_nov) + (w_band * s_band) + (w_drive * s_drv) + s_attn + s_energy + s_help + s_emo_route + s_chain + s_neuro + s_emo_mode + s_outward + s_reach + s_type_recruit + s_goal_recruit + s_goal_lens + s_recruit + s_explore + s_curio + s_evc + s_workspace + s_uncon_damp

        # (Dual-process Phase 2) The pursue-on-cooldown yield band-aid was removed
        # here: pursue_committed_goal is no longer a deliberate candidate (it runs in
        # the Executive lane), so it can never be picked or "spin" the slot.

        # Suppress goal-pursuit functions when there is no active goal to pursue.
        # -0.65 overcomes the strongest emotional prior (motivation→pursue: 0.9 × 0.25w = 0.225)
        # plus attention boost (0.15), so the penalty is always decisive.
        if not _has_committed_goal and name in _GOAL_PURSUIT_FNS:
            total -= 0.65

        # Goal-shielding / cognitive control (Fix #1): when a committed goal is
        # active, damp BLIND exploration (curiosity reads with no relevance to this
        # goal) so a pinned exploration_drive can't win the arg-max routing against
        # goal work. Goal-RELEVANT exploration is exempt — s_goal_recruit > 0 means
        # the goal's own text recruits this function (e.g. outward research for a
        # research goal). Graded and capped (never a lockout): the read stays
        # rankable, just no longer dominant. This is the layer the old 0.4× outward-
        # boost damp was too weak to provide — it only touched s_outward, leaving the
        # far larger s_emo exploration prior (≈0.19 of total) untouched.
        # Fix B (EXPLORE_EXPLOIT_VALUE_PLAN §6.4): exempt from shielding only on
        # MEANINGFUL goal-relevance, not any positive fuzzy overlap. A blind-explore
        # read with a spurious ~0.1 capability overlap on a research goal (look_outward
        # measured at 0.106) used to clear `s_goal_recruit > 0` and compete unshielded —
        # the goal-neglect leak (Duncan et al. 1996). Require a real overlap floor OR
        # membership in the goal type's own instrumental family.
        _meaningfully_relevant = (s_goal_recruit >= 0.15) or (name in _type_family)
        if _has_committed_goal and name in _BLIND_EXPLORE_FNS and not _meaningfully_relevant:
            total -= min(0.40, 0.15 + 0.20 * _goal_commit + 0.10 * _impasse)

        # Goal-type gate: decisively suppress an action that exclusively serves a
        # DIFFERENT goal type (e.g. decide_to_write_code on an "understand X" goal).
        # -0.6 overcomes even the impasse→action recruitment boost so cross-type
        # actions can't win — the action that produces THIS goal's end-state does.
        if _mismatch_fn is not None and _mismatch_fn(_goal_type, name):
            total -= 0.6

        # Behavioral adaptation signals (Carver & Scheier, 1982 control systems):
        # Set by behavioral_adaptation.py when metacog detects recurring patterns.
        # _force_action_next: reflection imbalance detected — boost action fns.
        if context.get("_force_action_next"):
            _ADAPT_ACTION_FNS = frozenset({
                "pursue_goal", "look_outward",  # E6: dropped pursue_committed_goal (dead)
                "search_own_files", "seek_novelty", "generate_intrinsic_goals",
                "plan_self_evolution", "plan_next_step",
            })
            _ADAPT_REFLECT_FNS = frozenset({
                "reflection", "self_review", "narrative_update",
                "assess_goal_progress", "introspective_planning",
            })
            if name in _ADAPT_ACTION_FNS:
                total += 0.30
            elif name in _ADAPT_REFLECT_FNS:
                total -= 0.20

        # Goal-deliberation lockout: behavioral_adaptation sets this once
        # action_debt is high enough that soft pressure has demonstrably failed.
        # A large penalty (not removal) keeps the candidate rankable as a last
        # resort but ensures any genuine execution option outscores it.
        if context.get("_suppress_goal_deliberation") and name in _GOAL_DELIBERATION_FNS:
            total -= 0.80
        if context.get("_suppress_intrinsic_goals") and name == "generate_intrinsic_goals":
            total -= 1.0

        # Will/commitment follow-through bias (cognition/will.py): a small,
        # decaying boost to actually pursuing the committed goal, so fresh resolve
        # is shielded from impulse switching. Capped + decaying so it never
        # becomes a rut (the meta-rut breaker still applies on top).
        # E6: pursue_committed_goal is in _ALWAYS_EXCLUDE (it runs in the Executive
        # lane), so the will/commitment follow-through bias is applied to
        # attend_goal — the thin, selectable "consciously decide to focus on the
        # goal" proxy that remains in the deliberate pool — rather than to an
        # unreachable name where it had no effect.
        if name == "attend_goal":
            total += float(context.get("_commitment_bias", 0.0) or 0.0)

        # Contestation routing (FIX): genuine value-contestation signals — active
        # tensions / recurring drive collisions — must actually REACH
        # propose_value_revision, or its contestation logic never runs and
        # value_revisions stays empty. The normal _tension_boost (0.15) is folded
        # into s_emo then ×w_emo (0.26) and capped, contributing only ~0.04 to
        # total — far too weak to win among 300+ candidates. Add a decisive boost
        # straight to total when contestation is present and it wasn't just run
        # (so it fires on contestation without becoming a rut). It defers harmlessly
        # if, on inspection, no genuine contestation is found.
        if name == "propose_value_revision" and context.get("active_tensions") and name not in recent:
            total += 0.60

        # _novelty_pressure: rut/oscillation detected — amplify exploration.
        # Tolman (1932): blocked habitual path → amplify exploration signal.
        _np = float(context.get("_novelty_pressure") or 0.0)
        if _np > 0.0 and name not in recent:
            total += _np * s_nov  # scale by how novel this fn already is

        # Repetition penalty (BEHAVIOR_FIX_PLAN 2.1): deterministic, always on —
        # not dependent on metacog noticing. Score decays ×0.6 per consecutive
        # pick of the same function beyond 2, floored at ×0.1, so no function
        # (assess_goal_progress most of all) can hold the slot for hours.
        _consec = 0
        for _p in reversed(recent):
            if _p == name:
                _consec += 1
            else:
                break
        if _consec >= 2 and total > 0:
            total *= max(0.1, 0.6 ** (_consec - 1))

        # Metacog rut suppression: when metacognition flags a rut it writes a
        # temporary per-function cooldown (context["_fn_suppression"]) — honor it.
        _supp = context.get("_fn_suppression")
        if isinstance(_supp, dict) and name in _supp and total > 0:
            try:
                _cc_now = int((context.get("cycle_count") or {}).get("count", 0) or 0)
                if _cc_now < int(_supp[name]):
                    total *= 0.15
                else:
                    _supp.pop(name, None)  # cooldown expired
            except Exception as exc:
                record_failure("select_function.fn_suppression", exc)

        scored.append((name, total, {"dir": s_dir, "goal": s_goal, "emo": s_emo, "novel": s_nov, "band": s_band, "drive": s_drv, "attn": s_attn, "energy": s_energy, "help": s_help, "emo_route": s_emo_route, "chain": s_chain, "neuro": s_neuro, "emo_mode": s_emo_mode, "outward": s_outward, "goal_recruit": s_goal_recruit, "goal_lens": s_goal_lens, "explore": s_explore}))

    scored.sort(key=lambda t: t[1], reverse=True)
    if context.get("goal_lens"):
        try:
            _lens_ranked = [
                {"function": nm, "score": round(sc, 3), "lens_prior": round(float(parts.get("goal_lens", 0.0)), 3)}
                for nm, sc, parts in scored[:8]
            ]
            context.setdefault("_goal_lens_telemetry", {})["selection_top"] = _lens_ranked
        except Exception as exc:
            record_failure("select_function.goal_lens_telemetry", exc)

    # Consume the one-cycle goal-deliberation lockout now that scoring is done,
    # so it affects exactly this selection and not subsequent ones.
    context.pop("_suppress_goal_deliberation", None)

    if scored:
        chosen = scored[0][0]

        # --- Phase 2: gated exploration (function_selection_fix_v2.md §3.2) ----
        # With probability ε, try a SAFE, rarely-used function instead of the
        # deterministic argmax — so dormant-but-reversible capability actually
        # gets sampled, the bandit accrues evidence for it, and the self-
        # reinforcing dead zone (never tried → never learned → never tried) is
        # broken. Gated on _SAFE_TO_EXPLORE (E4: rarely-used != safe-to-try) and
        # on low usage count; softmax over the candidates' OWN scores so we
        # explore plausible options rather than thrash into clearly-bad ones. ε
        # may be raised by exploration_drive but is capped at 0.30. This sits
        # BEFORE the threat-arbiter block, so a real reflex spike still overrides
        # whatever exploration picked. Setting context["_exploration_epsilon"]=0
        # disables the branch entirely (documented rollback).
        _expl_eps_base = float(context.get("_exploration_epsilon", 0.10) or 0.0)
        if _expl_eps_base > 0.0:
            _expl_eps = min(0.30, _expl_eps_base + 0.20 * max(0.0, _expl_drive - 0.5))
            # Metacognitive rut breaker (LEARNING_DIAGNOSIS_2026-06-16 §5.3): the
            # stagnation detector in contextual_bandit only runs inside bandit.choose(),
            # which the real (weighted-sum) pick never calls — so the breaker built for
            # exactly this rut had 0 effect. Replicate its concentration check here and
            # raise ε when recent picks are dominated by a few arms, handing control back
            # to the value learner. Mirrors contextual_bandit._stagnation_epsilon_boost.
            try:
                _counts = (bandit.get_state() or {}).get("counts", {}) or {}
                _cand_total = sum(int(_counts.get(a, 0) or 0) for a in actions)
                if _cand_total >= int(_tuning.SELECTOR_RUT_MIN_TOTAL):
                    _top3 = sum(sorted(
                        (int(_counts.get(a, 0) or 0) for a in actions), reverse=True)[:3])
                    _conc = _top3 / max(_cand_total, 1)
                    _trip = float(_tuning.SELECTOR_RUT_TRIP)
                    if _conc > _trip:
                        _expl_eps = min(
                            float(_tuning.SELECTOR_RUT_EPS_CAP),
                            _expl_eps + float(_tuning.SELECTOR_RUT_EPS_GAIN)
                            * (_conc - _trip) / max(1.0 - _trip, 1e-6),
                        )
            except Exception as exc:
                record_failure("select_function.rut_exploration", exc)
            if _rand.random() < _expl_eps:
                _stats_now = _learned_stats()
                _tail = [
                    (nm, sc) for (nm, sc, _f) in scored
                    if nm in _SAFE_TO_EXPLORE
                    and int((_stats_now.get(nm) or {}).get("count", 0)) < 8
                    and nm not in recent
                ]
                if _tail:
                    _T = 0.5  # softmax temperature
                    _mx = max(sc for _, sc in _tail)
                    _ws = [_math.exp((sc - _mx) / _T) for _, sc in _tail]
                    _tot = sum(_ws) or 1.0
                    _r, _acc = _rand.random() * _tot, 0.0
                    for (_nm, _sc), _w in zip(_tail, _ws):
                        _acc += _w
                        if _r <= _acc:
                            chosen = _nm
                            from brain.utils.log import log_activity as _la
                            _la(f"[explore] ε-sampled dormant safe fn → {chosen} "
                                f"(ε={_expl_eps:.2f})")
                            break
        # ----------------------------------------------------------------------

        # threat_detector → weighted vote (V2: convergence, not override).
        # The threat_detector computes fight/flight/freeze → a recommended function.
        # Instead of a hard `if spike > 0.65: chosen = reflex` step-function override
        # (which made the choice flip-flop as the threat scalar crossed the
        # threshold), the reflex now joins the analytical (bandit) picks as a
        # high-weight proposal in the ActionArbiter. An acute spike still dominates;
        # a moderate spike blends with a strong planned pick; hysteresis against last
        # cycle's choice prevents the flip-flop. See think/action_arbiter.py.
        _AMY_SHORTCUT_MAP = {"speak": "speak", "dream": "dream_cycle",
                              "introspective_planning": "introspective_planning"}
        try:
            _amy_resp    = context.get("threat_detector_response") or {}
            _amy_sc      = str(_amy_resp.get("shortcut_function") or "none")
            _amy_spike   = float(_amy_resp.get("spike_intensity") or 0.0)
            _mapped      = _AMY_SHORTCUT_MAP.get(_amy_sc, _amy_sc)
            # Only convene the arbiter when there is a real reflex bid to weigh in;
            # otherwise the analytical winner stands unchanged (zero behaviour drift).
            if _amy_sc != "none" and _amy_spike > 0.45 and _mapped in actions:
                from brain.think.action_arbiter import ActionProposal, resolve as _resolve
                # Normalise the top analytical scores to [0,1] (robust to negatives).
                _tops = [t for _, t, _ in scored[:5]]
                _lo, _hi = (min(_tops), max(_tops)) if _tops else (0.0, 1.0)
                _rng = (_hi - _lo) or 1.0
                _props = [
                    ActionProposal(name=_nm, vote=max(0.0, min(1.0, (_t - _lo) / _rng)),
                                   weight=1.0, source="bandit")
                    for _nm, _t, _ in scored[:5]
                ]
                # Reflex lane: weight 1.2 + urgency=spike. At spike≈0.65 this is a
                # near-tie with the top analytical pick; above it the reflex wins,
                # below it the plan wins.
                _props.append(ActionProposal(
                    name=_mapped, vote=min(1.0, _amy_spike), weight=1.2,
                    urgency=min(1.0, _amy_spike), source="threat_detector",
                ))
                _incumbent = recent[-1] if recent else None
                _winner, _info = _resolve(_props, incumbent=_incumbent, margin=0.10)
                if _winner and _winner in actions:
                    chosen = _winner
                    from brain.utils.log import log_activity as _la
                    _la(f"[action_arbiter] threat-vote → {chosen} "
                        f"(spike={_amy_spike:.2f}, hysteresis={_info.get('hysteresis')})")
        except Exception as _e:
            record_failure("select_function.select_function.12", _e)

        # Inhibition: record the emotional cost of not doing what drives wanted
        try:
            from brain.cognition.inhibition import apply_inhibition_costs
            apply_inhibition_costs(context, scored, chosen, _drive_pull)
        except Exception as _e:
            record_failure("select_function.select_function.13", _e)

    elif actions:
        # Validate the fallback exists in the registry before returning it;
        # an unknown name causes the bandit to penalise a selection it generated.
        try:
            from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS as _cf_reg
            _valid = [a for a in actions if a in _cf_reg]
            chosen = _valid[0] if _valid else ""
        except Exception:
            chosen = actions[0]
    else:
        chosen = ""

    # Anti-repeat guard: prevent any function from monopolising cycles.
    # Fires on immediate repeat (regardless of stagnation_signal) OR consecutive run ≥2
    # OR domination of ≥35% of the last 10 picks.  Override picks the highest-
    # scoring alternative that hasn't appeared in the last 3 cycles.
    #
    # Distress exemption: regulation functions are exempt during high distress.
    # Gross (1998) process model: sustained regulation effort under high negative
    # affect is therapeutic repetition, not rut-formation — interrupting it with
    # novelty-seeking defeats the function of the regulation strategy entirely.
    # Nolen-Hoeksema et al. (2008): failed regulation attempts that are interrupted
    # before resolution produce worse outcomes than repeated sustained engagement.
    _REGULATION_GUARD_EXEMPT = frozenset({
        "attempt_regulation", "reflect_on_affect",
        "investigate_unexplained_emotions", "reflect_on_emotion_model",
        "apply_affective_feedback",
    })
    _guard_distress_high = False
    try:
        from brain.affect.observers import negative_load
        _guard_distress_high = negative_load(context.get("affect_state") or {}) > 0.55
    except Exception as _e:
        record_failure("select_function.select_function.14", _e)

    override_applied = False
    immediate_repeat = False
    _repeat_attempt = False
    _ema_delta = 0.0
    _reward_improving = False
    _consecutive = 0
    _dominated = False
    # Hard cap on refinement repeats: even while reward keeps improving, a single
    # function may not monopolise more than this many consecutive cycles.
    _MAX_REFINE_REPEATS = 4
    try:
        immediate_repeat = bool(recent and chosen == recent[-1])
        _window10 = recent[-10:]
        _dominated = (
            len(_window10) >= 6
            and _window10.count(chosen) >= max(3, int(len(_window10) * 0.35))
        )
        _consecutive = 0
        for _x in reversed(recent[-10:]):
            if _x == chosen:
                _consecutive += 1
            else:
                break
        # Ground-truth "trying to repeat" signal, measured BEFORE the override
        # rewrites `chosen` — this is what drives the stagnation signal (Fix #2)
        # regardless of whether the refinement exemption lets the repeat through.
        _repeat_attempt = bool(immediate_repeat or _dominated or _consecutive >= 2)

        # Controlled-refinement exemption (Fix #4): allow a repeat when this
        # function's reward EMA is still climbing (iterative refinement is paying
        # off) and we're under the hard consecutive cap. _fn_ema_delta is written
        # by finalize.py after each cycle's reward is observed.
        _ema_delta = float((context.get("_fn_ema_delta") or {}).get(chosen, 0.0))
        _reward_improving = _ema_delta > 0.0 and _consecutive < _MAX_REFINE_REPEATS

        # NO hard anti-repeat cap. Humans don't have a "you may not pick this twice"
        # rule — they keep doing something while it works or while they're learning
        # from it, and naturally tire of it when it stops paying off. So we do NOT
        # force a different choice here; his real top-scoring preference stands. The
        # pressure against MINDLESS repetition is natural instead:
        #   • stagnation_signal (below) rises on repeat attempts → boredom builds,
        #   • dopaminergic habituation in the reward path (ORRIN_loop) makes pure,
        #     non-learning repetition progressively unrewarding so the bandit drifts
        #     off it on its own,
        #   • repetition that keeps IMPROVING reward (trying it differently to learn)
        #     stays rewarding and continues freely.
        # This surfaces what he actually WANTS to do, not a forced shuffle.
        _ = (_reward_improving, _dominated, immediate_repeat)  # kept for tracker/telemetry
    except Exception as _e:
        record_failure("select_function.select_function.15", _e)

    # Stagnation signal (Fix #2): drive it from the actual repeat *attempt*
    # detected above, routed through submit_affect so it lands in core_signals
    # (where _dominant_emotion_and_stagnation_signal reads it first) and persists
    # across cycles via commit_affect — the old top-level writer in think_module
    # never reached core_signals and stayed pinned at 0.000.
    try:
        from brain.affect.arbiter import submit_affect
        if _repeat_attempt:
            submit_affect(context, "stagnation_signal", +0.06,
                          source="select_repeat", ttl_cycles=4)
        else:
            submit_affect(context, "stagnation_signal", -0.02,
                          source="select_fresh", ttl_cycles=4)
    except Exception as _e:
        record_failure("select_function.select_function.16", _e)

    # Similarity / repeat tracker (Fix #4): expose the repeat state so the metacog
    # layer can read it (and a future "experiment with variation" pattern extend it).
    context["_repeat_tracker"] = {
        "chosen": chosen,
        "immediate_repeat": immediate_repeat,
        "consecutive": _consecutive,
        "dominated": _dominated,
        "ema_delta": _ema_delta,
        "refine_allowed": _reward_improving,
        "override_applied": override_applied,
    }

    # Meta-rut breaker (think-vs-act). The anti-repeat guard above only catches a
    # single function name repeating; a *varied* run of deliberation functions that
    # never executes slips straight past it (assess → adjust → abduce → adapt …).
    # This measures the category-level think/act ratio over the recent window and,
    # when deliberation has fully crowded out doing, forces the highest-scoring
    # execution function. Independent of (and faster than) the metacog avoidance
    # detector, so a forming rut is broken before it entrenches.
    try:
        if chosen in _DELIBERATION_FNS:
            _rut_window = recent[-_META_RUT_WINDOW:]
            if len(_rut_window) >= _META_RUT_WINDOW:
                _acted = any(p in _EXECUTION_FNS for p in _rut_window)
                _all_think = all(p in _DELIBERATION_FNS for p in _rut_window)
                if _all_think and not _acted:
                    _exec_alts = sorted(
                        ((n, s) for (n, s, _) in scored if n in _EXECUTION_FNS),
                        key=lambda t: t[1], reverse=True,
                    )
                    if _exec_alts and _exec_alts[0][0] != chosen:
                        chosen = _exec_alts[0][0]
                        override_applied = True
                        from brain.utils.log import log_private as _lp
                        _lp(
                            f"[meta_rut] {_META_RUT_WINDOW} deliberation picks with no "
                            f"action → forcing execution: {chosen!r}"
                        )
    except Exception as _e:
        record_failure("select_function.select_function.17", _e)

    # Reason payload
    features_on = {k: v for k, v in feats.items() if isinstance(v, (int, float)) and abs(v) > 0}
    ranked = [(n, round(s, 4)) for n, s, _ in scored[:6]]
    comp = {n: cs for (n, _, cs) in scored[:6]}

    reason = {
        "via": "multi-factor",
        "weights": {"dir": w_dir, "goal": w_goal, "emo": w_emo, "novel": w_novel, "band": w_band, "drive": w_drive},
        "features_on": features_on,
        "dominant_affect": dominant,
        "stagnation_signal": stagnation_signal,
        "attention_mode": attention_mode,
        "energy_state": str(context.get("energy_state") or "medium"),
        "energy_boosts": {k: round(v, 3) for k, v in _energy_boost.items() if abs(v) > 0.01},
        "neuro_boosts":  {k: round(v, 3) for k, v in _neuro_boost.items()  if abs(v) > 0.01},
        "workspace_prior": {k: round(v, 3) for k, v in _workspace_prior.items() if abs(v) > 0.01},
        "conscious_cycle": context.get("_conscious_cycle", True),
        "user_spoke": _user_spoke,
        "helpfulness_boosts": {k: round(v, 3) for k, v in _helpfulness_boost.items() if abs(v) > 0.01},
        "candidates": list(actions),
        "ranked": ranked,
        "component_scores": comp,
        "decision_id": decision_id,
        "anti_repeat": {
            "applied": override_applied,
            "stagnation_signal": stagnation_signal,
            "immediate_repeat": immediate_repeat,
        },
        "drive_conflicts": [
            {"drives": list(c["drives"]), "label": c["label"], "intensity": c["intensity"]}
            for c in (context.get("_drive_conflicts") or [])[:3]
        ],
    }

    # TD(λ): stamp eligibility trace for the chosen function at decision time.
    # bandit.update() in bandit_learn() will apply reward backward through these traces.
    if chosen:
        try:
            bandit.step_traces(chosen, feats)
        except Exception as _e:
            record_failure("select_function.select_function.18", _e)

    # §20.1 dismissal-recalibration: was the breakthrough that won consciousness
    # HONORED (the deliberate pick took its route) or DISMISSED (picked something
    # else despite it)? The Monitor consumes this next cycle to adapt the kind's
    # threshold — the watched governing the watcher.
    _btp = context.get("_bt_pending")
    if isinstance(_btp, dict) and _btp.get("route_fns"):
        context["_breakthrough_outcome"] = {
            "kind": _btp.get("kind"),
            "honored": chosen in set(_btp["route_fns"]),
        }
        context.pop("_bt_pending", None)

    if is_legacy:
        return chosen, reason, False
    return chosen
