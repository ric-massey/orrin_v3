# brain/config/tuning.py
#
# Central registry of the hand-tuned numeric constants behind Orrin's
# decision core (Finding 9 — "magic-number sprawl"). Each name here is the
# single source of truth for that value: the modules that previously
# hardcoded it now import it from here instead. This gives:
#
#   - one place to see the whole tuned parameter space at a glance,
#   - a target for the benchmark registry (brain/benchmarks/) to sweep or
#     A/B individual constants instead of hunting through call sites,
#   - protection against related constants (e.g. an attention-mode
#     multiplier and the base weight it scales) drifting apart silently.
#
# This module only MOVES values — it changes WHERE a constant is defined,
# not what it is or how it's used. No behavior change. Per-site rationale
# comments remain at the call sites; the grouping comments here describe
# the family a constant belongs to.
from __future__ import annotations


# ── Selector base weights ───────────────────────────────────────────────────
# brain/think/think_utils/select_function.py — function_selection_fix_v2 §3.3.
# Combined multiplicatively with the attention-mode modulation below, then
# summed into the final per-action score.
SELECTOR_W_DIR: float = 0.22          # directive-text alignment
SELECTOR_W_GOAL: float = 0.22         # focus-goal alignment
SELECTOR_W_EMO: float = 0.26          # emotion-priority prior
SELECTOR_BASE_W_NOVEL: float = 0.10   # novelty, before stagnation amplification
SELECTOR_W_BAND: float = 0.25         # bandit/learned hint
SELECTOR_W_DRIVE: float = 0.15        # net drive-pull bias

# ── Prior outcome-devaluation (LEARNING_DIAGNOSIS_2026-06-16 §5.2) ────────────
# A static emotion prior must not keep boosting an arm the agent has proven is
# low-yield. Once a function has enough learned evidence, its prior is decayed
# in proportion to how far its avg_reward sits below the candidate-pool median.
# This restores outcome-devaluation sensitivity (model-based override of habit).
SELECTOR_DEVAL_MIN_PULLS: int = 30    # need a stable estimate before devaluing
SELECTOR_DEVAL_K: float = 1.2         # devaluation strength per unit reward gap
SELECTOR_DEVAL_FLOOR: float = 0.25    # prior shrinks to at most 25%, never to 0

# ── Stagnation rut breaker in the real pick (§5.3) ───────────────────────────
# Mirror of contextual_bandit._stagnation_epsilon_boost, applied to the actual
# weighted-sum pick. When recent selections concentrate in a few arms, raise the
# exploration epsilon so the value learner gets control back.
SELECTOR_RUT_MIN_TOTAL: int = 20      # min selections before checking concentration
SELECTOR_RUT_TRIP: float = 0.80       # top-3 share that counts as a rut
SELECTOR_RUT_EPS_GAIN: float = 0.25   # epsilon added at full concentration
SELECTOR_RUT_EPS_CAP: float = 0.50    # ceiling on the boosted epsilon

# ── Selector attention-mode modulation ──────────────────────────────────────
# signal_router computes `attention_mode`; these multipliers/boosts are what
# make that mode actually change which function gets picked. Grouped by mode.

# alert: a user is present — strongly bias toward helpful, goal-directed fns.
ATTN_ALERT_GOAL_MULT: float = 2.10
ATTN_ALERT_NOVEL_MULT: float = 0.30
ATTN_ALERT_EMO_MULT: float = 0.55
ATTN_ALERT_GOAL_CAP: float = 0.45
ATTN_ALERT_NOVEL_FLOOR: float = 0.03
ATTN_ALERT_EMO_FLOOR: float = 0.08
ATTN_ALERT_FN_BOOST: float = 0.42        # flat boost for _MODE_ALERT_FNS
ATTN_ALERT_INTROSPECTION_PENALTY: float = -0.22

# engaged: high-priority signal, no direct user input — moderate goal+emotion lift.
ATTN_ENGAGED_GOAL_MULT: float = 1.35
ATTN_ENGAGED_EMO_MULT: float = 1.20
ATTN_ENGAGED_GOAL_CAP: float = 0.30
ATTN_ENGAGED_EMO_CAP: float = 0.32
ATTN_ENGAGED_FN_BOOST: float = 0.15      # flat boost for _MODE_ENGAGED_FNS

# wandering: internal signals dominate — proactive/outward before introspection.
ATTN_WANDERING_NOVEL_MULT: float = 1.40
ATTN_WANDERING_DIR_MULT: float = 0.65
ATTN_WANDERING_GOAL_MULT: float = 0.60
ATTN_WANDERING_NOVEL_CAP: float = 0.45
ATTN_WANDERING_DIR_FLOOR: float = 0.10
ATTN_WANDERING_GOAL_FLOOR: float = 0.08
ATTN_WANDERING_OUTWARD_BOOST: float = 0.25   # tier 1: _MODE_WANDERING_FNS
ATTN_WANDERING_REFLECT_BOOST: float = 0.08   # tier 2: _MODE_WANDERING_REFLECT_FNS

# drowsy: no signals at all — consolidation/rest over active cognition.
ATTN_DROWSY_NOVEL_MULT: float = 0.40
ATTN_DROWSY_EMO_MULT: float = 0.45
ATTN_DROWSY_DIR_MULT: float = 1.90
ATTN_DROWSY_NOVEL_FLOOR: float = 0.05
ATTN_DROWSY_EMO_FLOOR: float = 0.05
ATTN_DROWSY_DIR_CAP: float = 0.45
ATTN_DROWSY_FN_BOOST: float = 0.20       # flat boost for _MODE_DROWSY_FNS

# ── Goal-relevance / capability matching ────────────────────────────────────
# brain/cognition/planning/step_execution.py — function_selection_fix_v2 §4.1.
# Floor for the semantic step→function match (embedding similarity, falling
# back to stopword-filtered keyword overlap when embeddings are unavailable).
SEMANTIC_MATCH_FLOOR: float = 0.22

# ── Affect arbiter ───────────────────────────────────────────────────────────
# brain/affect/arbiter.py. Per-cycle ceiling on the total homeostasis-weighted
# magnitude of affect change, and the extra "cost" multiplier for deltas that
# push a signal away from its setpoint. See arbiter.py's module docstring for
# the full propose -> integrate -> commit model.
AFFECT_STABILITY_BUDGET: float = 0.60
AFFECT_AWAY_COST_MULTIPLIER: float = 2.0

# ── ORRIN_loop: transient-signal decay & crisis detection ──────────────────
# Per-cycle exponential decay applied to transient negative-affect signals
# (impasse, penalty, conflict, threat, stagnation, uncertainty) so a single
# spike fades rather than lingering indefinitely.
AFFECT_TRANSIENT_DECAY: float = 0.92

# Sustained-crisis detection for the emergency_self_modification gate. Two
# paths: an acute spike (one core-negative >= CRISIS_ACUTE_PEAK and at least
# CRISIS_ABOVE_HALF_COUNT others >= CRISIS_ABOVE_HALF_THRESHOLD), or a broad
# collapse (mean of all core negatives >= CRISIS_CHRONIC_MEAN).
CRISIS_ACUTE_PEAK: float = 0.85
CRISIS_ABOVE_HALF_THRESHOLD: float = 0.50
CRISIS_ABOVE_HALF_COUNT: int = 2
CRISIS_CHRONIC_MEAN: float = 0.70
