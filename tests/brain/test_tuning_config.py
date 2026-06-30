# Finding 9 (config centralization): brain/config/tuning.py is now the single
# source of truth for the selector/arbiter/loop "magic numbers" the finding
# named (selector base weights, attention-mode multipliers, arbiter stability
# budget + away-cost multiplier, signal decay, crisis thresholds, the semantic
# match floor). These tests pin the documented values and confirm the
# consuming modules actually read from this module rather than a stale
# parallel copy of the same constant.
from pathlib import Path

import brain.control_signals.arbiter as arbiter
import brain.config.tuning as tuning
from brain.cognition.planning import step_execution
from brain.think.think_utils.selection import score_setup

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_arbiter_constants_sourced_from_tuning():
    assert arbiter.STABILITY_BUDGET == tuning.AFFECT_STABILITY_BUDGET == 0.60
    assert arbiter._AWAY_COST_MULTIPLIER == tuning.AFFECT_AWAY_COST_MULTIPLIER == 2.0


def test_step_execution_semantic_floor_sourced_from_tuning():
    assert step_execution._SEMANTIC_FLOOR == tuning.SEMANTIC_MATCH_FLOOR == 0.22


def test_selector_base_weights_sourced_from_tuning():
    # The selector's weight wiring moved to selection/score_setup.py (Phase 4.5A).
    assert score_setup._tuning is tuning
    assert tuning.SELECTOR_W_DIR == 0.22
    assert tuning.SELECTOR_W_GOAL == 0.22
    assert tuning.SELECTOR_W_EMO == 0.26
    assert tuning.SELECTOR_BASE_W_NOVEL == 0.10
    assert tuning.SELECTOR_W_BAND == 0.25
    assert tuning.SELECTOR_W_DRIVE == 0.15


def test_selector_attention_mode_constants_match_documented_multipliers():
    # Spot-check the exact multipliers Finding 9 calls out by name.
    assert tuning.ATTN_ALERT_GOAL_MULT == 2.10
    assert tuning.ATTN_ALERT_NOVEL_MULT == 0.30
    assert tuning.ATTN_ALERT_EMO_MULT == 0.55
    assert tuning.ATTN_ALERT_FN_BOOST == 0.42
    assert tuning.ATTN_WANDERING_OUTWARD_BOOST == 0.25
    assert tuning.ATTN_ENGAGED_FN_BOOST == 0.15
    assert tuning.ATTN_WANDERING_REFLECT_BOOST == 0.08


def test_selector_source_has_no_leftover_hardcoded_weights():
    """Guard against the base weights drifting back into two places: the
    literal float assignments the selector used to have for w_dir/
    w_goal/w_emo/w_band/w_drive must now be config.tuning lookups. The weight
    wiring lives in selection/score_setup.py (Phase 4.5A)."""
    src = (_REPO_ROOT / "brain" / "think" / "think_utils" / "selection" / "score_setup.py").read_text()
    assert "w_dir = _tuning.SELECTOR_W_DIR" in src
    assert "w_goal = _tuning.SELECTOR_W_GOAL" in src
    assert "w_emo = _tuning.SELECTOR_W_EMO" in src
    assert "w_band = _tuning.SELECTOR_W_BAND" in src
    assert "w_drive = _tuning.SELECTOR_W_DRIVE" in src


def test_orrin_loop_reads_crisis_constants_from_tuning():
    """The sustained-crisis stage (_apply_transient_signal_decay) was extracted to
    brain/loop/signal_decay.py in Phase 4.5B; its crisis detection must reference
    config.tuning's names, not bare literals (Finding 9). NOTE: the transient
    SIGNAL DECAY this stage used to run was removed in the Grounded Cognition plan
    (Phase 1B / invariant #1) — homeostasis is the single decay authority — so
    AFFECT_TRANSIENT_DECAY is no longer referenced here."""
    src = (_REPO_ROOT / "brain" / "loop" / "signal_decay.py").read_text()
    assert "from brain.config.tuning import (" in src
    for name in (
        "CRISIS_ACUTE_PEAK",
        "CRISIS_ABOVE_HALF_THRESHOLD",
        "CRISIS_ABOVE_HALF_COUNT",
        "CRISIS_CHRONIC_MEAN",
    ):
        assert name in src

    # The second decay authority is gone — no decay multiply remains in the stage.
    assert "AFFECT_TRANSIENT_DECAY" not in src
    assert "* 0.92" not in src
    assert "_peak >= CRISIS_ACUTE_PEAK and _above_half >= CRISIS_ABOVE_HALF_COUNT" in src
    assert "_peak >= 0.85" not in src
    assert "_mean  >= 0.70" not in src and "_mean >= 0.70" not in src
