# affect/reward_signals/action_reward_ema.py
#
# Per-action expected reward (the prediction baseline for reward prediction
# error) PLUS a surprise-driven, adaptive learning rate.
#
# ── EXPECTED VALUE: temporal-difference learning ──────────────────────────────
# Schultz, Dayan & Montague (1997), "A neural substrate of prediction and
# reward", Science 275:1593 — midbrain dopamine encodes a reward prediction
# error (RPE): actual − expected. The expected value is learned by a TD update
# (Sutton 1988, "Learning to predict by the methods of temporal differences",
# Machine Learning 3:9):
#       expected[t+1] = expected[t] + α · (actual[t] − expected[t])
# When an action reliably yields reward R, expected → R and RPE → 0, so the
# 50th routine `speak` produces RPE≈0 while a rare high-quality one still fires.
#
# ── LEARNING RATE: surprise-driven associability (the upgrade) ────────────────
# A FIXED α is wrong for an agent in a non-stationary world: it learns too
# slowly when things change and too jumpily when they're stable. The empirical
# fix is to make the learning rate track recent surprise / volatility:
#
#   Pearce & Hall (1980), "A model for Pavlovian learning: variations in the
#   effectiveness of conditioned but not of unconditioned stimuli",
#   Psychological Review 87:532 — a cue's *associability* (its effective learning
#   rate) rises with the recent magnitude of UNSIGNED prediction error. Poor
#   recent predictors command more learning; reliable ones command less:
#       associability[t+1] = γ·|actual[t] − expected[t]| + (1−γ)·associability[t]
#
#   Behrens, Woolrich, Walton & Rushworth (2007), "Learning the value of
#   information in an uncertain world", Nature Neuroscience 10:1214 — humans
#   are near-Bayes-optimal: they raise their learning rate in volatile periods
#   and lower it in stable ones. Adaptive associability is the mechanistic
#   approximation of that volatility tracking.
#   (cf. Sutton 1992 IDBD meta-learning of step sizes; Mackintosh 1975.)
#
# So the effective per-action learning rate is interpolated by associability:
#       α_eff = α_min + (α_max − α_min) · associability        (associability∈[0,1])
# A surprising, volatile action learns fast (α_eff→α_max); a predictable one
# settles (α_eff→α_min, never 0 — the world can always change again).
#
# associability is ALSO a first-class uncertainty signal other systems can read
# (directed exploration; Gershman 2018, "Deconstructing the human algorithms
# for exploration", Cognition 173:34): high associability == "I don't have a
# stable model of this action's payoff yet."
#
# ── STORAGE ───────────────────────────────────────────────────────────────────
# Expected values stay in action_reward_ema.json as {action_type: float} —
# unchanged on-disk format, so every existing reader keeps working.
# Associability lives in a sibling file action_associability.json.
from __future__ import annotations

from brain.core.runtime_log import get_logger
from pathlib import Path
from brain.utils.json_utils import load_json, save_json
from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Canonical location: the brain's data dir, alongside all other cognition state.
_EMA_PATH   = DATA_DIR / "action_reward_ema.json"
_ASSOC_PATH = DATA_DIR / "action_associability.json"

# Legacy location: repo-root data/ (these files used parents[3]/data, which
# resolves OUTSIDE brain/ — a path-split bug that isolated reward learning from
# the rest of cognition). Migrate any existing legacy file once, then remove it.
_LEGACY_DIR = Path(__file__).resolve().parents[3] / "data"


def _migrate_legacy(new_path: Path, name: str) -> None:
    legacy = _LEGACY_DIR / name
    try:
        if legacy.exists() and legacy.resolve() != new_path.resolve():
            old = load_json(legacy, default_type=dict) or {}
            if old and not (load_json(new_path, default_type=dict) or {}):
                save_json(new_path, old)
            legacy.unlink()
            legacy.with_suffix(legacy.suffix + ".lock").unlink(missing_ok=True)
    except Exception as _e:
        record_failure("action_reward_ema._migrate_legacy", _e)

# Legacy fixed TD rate — superseded by the adaptive α below; kept so any external
# import of _ALPHA does not break, and as the historical reference point.
_ALPHA = 0.08

_ALPHA_MIN = 0.04   # floor: a settled action still drifts a little (world can change)
_ALPHA_MAX = 0.30   # ceiling: a surprising action learns fast but not jumpily
_PH_GAMMA  = 0.5    # Pearce-Hall associability blend (classic value)

_DEFAULT       = 0.45  # expected-value prior — slightly below typical actual so first wins feel rewarding
_ASSOC_DEFAULT = 0.5   # associability prior — moderate → mid learning rate before evidence

# Pseudo-action EMA keys that are submitted on purpose and are not cognitive
# functions: "cycle" (finalize.py's pre-choice fallback) and the calibrated
# reward channels (reward_calibrator._release submits action_type=channel so
# each channel learns its own expectation). Whitelisted so they don't trip the
# "possible typo'd action name" warning on first use.
_KNOWN_PSEUDO_ACTIONS = frozenset({
    "cycle",
    "goal_closure",
    "user_validation",
    "prediction_hit",
    "contradiction_resolved",
    "retrieval_auxiliary",
})


def _flag_unknown_action(action_type: str) -> None:
    """Surface first-seen action names that no registry knows. The table accepts
    any string, so a typo'd caller quietly learns its own EMA forever — a stray
    action_type="cycle" sat in action_associability.json until the 2026-06-11
    data audit found it (§7). Logged, not blocked: legitimately novel actions
    (new tools, behavioral functions) must still be able to learn."""
    # "cycle" is finalize.py's deliberate fallback EMA key for the cycle-level
    # reward before any function has been chosen (first cycle after a reset) —
    # a known pseudo-action, not a typo. The calibrated reward channels
    # (reward_calibrator._release) likewise pass their channel name as
    # action_type on purpose, so each channel learns its own expectation —
    # also known pseudo-actions, not typos.
    if action_type in _KNOWN_PSEUDO_ACTIONS:
        return
    try:
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
        if COGNITIVE_FUNCTIONS and action_type not in COGNITIVE_FUNCTIONS:
            _log.warning(
                "action_reward_ema: first reward for action %r, which is not a "
                "registered cognitive function — possible typo'd action name",
                action_type,
            )
    except Exception:
        pass


def _cache(context: dict) -> dict:
    c = context.get("_action_ema")
    if not isinstance(c, dict):
        _migrate_legacy(_EMA_PATH, "action_reward_ema.json")
        try:
            c = load_json(_EMA_PATH, default_type=dict) or {}
        except Exception:
            c = {}
        context["_action_ema"] = c
    return c


def _assoc_cache(context: dict) -> dict:
    c = context.get("_action_assoc")
    if not isinstance(c, dict):
        _migrate_legacy(_ASSOC_PATH, "action_associability.json")
        try:
            c = load_json(_ASSOC_PATH, default_type=dict) or {}
        except Exception:
            c = {}
        context["_action_assoc"] = c
    return c


def get_expected(context: dict, action_type: str) -> float:
    """Return the learned expected reward (RPE baseline) for this action type."""
    return float(_cache(context).get(action_type, _DEFAULT))


def get_associability(context: dict, action_type: str) -> float:
    """
    Return the Pearce-Hall associability for this action type in [0, 1] — a
    proxy for how volatile / poorly-modelled its payoff currently is. High means
    recent outcomes have been surprising (good target for directed exploration).
    """
    return float(_assoc_cache(context).get(action_type, _ASSOC_DEFAULT))


def get_learning_rate(context: dict, action_type: str) -> float:
    """Return the current effective TD learning rate α_eff for this action type."""
    assoc = get_associability(context, action_type)
    return _ALPHA_MIN + (_ALPHA_MAX - _ALPHA_MIN) * assoc


def update_expected(context: dict, action_type: str, actual: float) -> None:
    """
    Observe an actual reward for `action_type`: update its expected value by a
    TD step whose size is gated by Pearce-Hall associability, then update the
    associability from the unsigned prediction error. Persists both.
    """
    try:
        actual = float(actual)
    except (TypeError, ValueError):
        return

    v_cache = _cache(context)
    a_cache = _assoc_cache(context)

    # First experience seeds the prediction; surprise is only defined relative to
    # an existing expectation, so associability is left at its prior here.
    if action_type not in v_cache:
        _flag_unknown_action(action_type)
        v_cache[action_type] = round(actual, 4)
        a_cache.setdefault(action_type, _ASSOC_DEFAULT)
        _persist(v_cache, a_cache)
        return

    prev  = float(v_cache[action_type])
    assoc = float(a_cache.get(action_type, _ASSOC_DEFAULT))
    error = actual - prev

    # TD update with surprise-gated step size (α_eff = α_min + span·associability).
    alpha_eff = _ALPHA_MIN + (_ALPHA_MAX - _ALPHA_MIN) * assoc
    v_cache[action_type] = round(prev + alpha_eff * error, 4)

    # Pearce-Hall: associability follows recent UNSIGNED prediction error.
    new_assoc = _PH_GAMMA * abs(error) + (1.0 - _PH_GAMMA) * assoc
    a_cache[action_type] = round(min(1.0, max(0.0, new_assoc)), 4)

    _persist(v_cache, a_cache)


def _persist(v_cache: dict, a_cache: dict) -> None:
    try:
        save_json(_EMA_PATH, v_cache)
    except Exception as _e:
        record_failure("action_reward_ema._persist", _e)
    try:
        save_json(_ASSOC_PATH, a_cache)
    except Exception as _e:
        record_failure("action_reward_ema._persist.2", _e)
