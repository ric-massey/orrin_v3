# brain/cognition/calibration.py
#
# Confidence / value calibration — the metacognitive skill of knowing how well
# you actually know.
#
# ── WHY ───────────────────────────────────────────────────────────────────────
# Nelson & Narens (1990), "Metamemory: a theoretical framework and new
# findings", Psychology of Learning and Motivation 26:125 — cognition has two
# levels: an object level (thinking) and a meta level that MONITORS it and
# exerts CONTROL. A confidence judgment is only useful to control if it is
# *calibrated* to reality. Fleming & Lau (2014), "How to measure metacognition",
# Front. Hum. Neurosci. 8:443 — metacognitive sensitivity = the match between
# confidence and correctness.
#
# ── WHAT WE CALIBRATE ─────────────────────────────────────────────────────────
# The bandit's own forecasts. Before acting, the per-function reward EMA predicts
# an expected reward (action_reward_ema.get_expected); after acting,
# env_snapshot yields the realized reward. The (predicted, actual) stream is
# scored with a proper scoring rule:
#
#   Brier (1950), "Verification of forecasts expressed in terms of probability",
#   Monthly Weather Review 78:1 —
#       brier = mean( (predicted − actual)^2 )      # lower = better calibrated
#   bias  = mean( predicted − actual )              # >0 overconfident, <0 under
#
# Both are kept as EMAs so they track RECENT calibration rather than a lifetime
# average — in a non-stationary world recency is what matters (Behrens et al.
# 2007, Nat. Neurosci. 10:1214).
#
# ── CONTROL (closing the loop) ────────────────────────────────────────────────
# Monitoring is wired back into control two ways:
#   • recalibrate_confidence() subtracts the measured over/under-confidence bias
#     from a raw confidence reading, so downstream "think more vs act" decisions
#     (meta_controller) use a calibrated number. Overconfident → effective
#     confidence drops → Orrin deliberates more before acting, and vice-versa.
#   • calibration_observation() surfaces sustained miscalibration as a
#     metacognitive observation (consumed by behavioral_adaptation).
from __future__ import annotations

import math
from core.runtime_log import get_logger
from typing import Any, Dict, Optional

from utils.json_utils import load_json, save_json
from paths import DATA_DIR
from utils.failure_counter import record_failure

_log = get_logger(__name__)

_STATE_PATH = DATA_DIR / "calibration_state.json"
_TRUST_PATH = DATA_DIR / "introspection_trust.json"
_TRUST_ALPHA = 0.10   # recency weight for the felt-vs-behaved agreement EMA

_EMA_ALPHA       = 0.05   # recency weight for the running Brier / bias EMAs
_MIN_SAMPLES     = 12     # don't correct confidence until we've seen enough outcomes
# Self-NOTES need a wider window than corrections: the audit (§6) caught the
# over/under-confident assessment flipping sign within 3 minutes. A verbal
# self-assessment is identity-shaping — require a real sample before saying it.
_MIN_NOTE_SAMPLES = 30
_BIAS_DEADBAND   = 0.05   # ignore trivially small biases (noise, not miscalibration)
_MAX_CORRECTION  = 0.15   # clamp the confidence adjustment so control stays stable


def _state(context: Dict[str, Any]) -> Dict[str, Any]:
    s = context.get("_calibration")
    if not isinstance(s, dict):
        try:
            s = load_json(_STATE_PATH, default_type=dict) or {}
        except Exception:
            s = {}
        if not isinstance(s, dict):
            s = {}
        s.setdefault("brier", 0.0)
        s.setdefault("bias", 0.0)
        s.setdefault("n", 0)
        context["_calibration"] = s
    return s


def record(context: Dict[str, Any], predicted: float, actual: float) -> None:
    """
    Record one (predicted, actual) forecast pair and update the running Brier
    score and signed bias EMAs. Both inputs are expected in [0, 1].
    """
    if not isinstance(context, dict):
        return
    try:
        p_raw, a_raw = float(predicted), float(actual)
    except (TypeError, ValueError):
        return
    if not (math.isfinite(p_raw) and math.isfinite(a_raw)):
        return
    p = max(0.0, min(1.0, p_raw))
    a = max(0.0, min(1.0, a_raw))

    s = _state(context)
    err = p - a
    if int(s.get("n", 0)) == 0:
        # First observation seeds the EMAs directly.
        s["brier"] = round(err * err, 4)
        s["bias"]  = round(err, 4)
    else:
        s["brier"] = round((1 - _EMA_ALPHA) * float(s["brier"]) + _EMA_ALPHA * (err * err), 4)
        s["bias"]  = round((1 - _EMA_ALPHA) * float(s["bias"])  + _EMA_ALPHA * err, 4)
    s["n"] = int(s.get("n", 0)) + 1

    try:
        save_json(_STATE_PATH, s)
    except Exception as _e:
        record_failure("calibration.record", _e)


def get_calibration(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return current calibration stats + over/under-confidence flags."""
    s = _state(context)
    n = int(s.get("n", 0))
    bias = float(s.get("bias", 0.0))
    enough = n >= _MIN_SAMPLES
    return {
        "brier": float(s.get("brier", 0.0)),
        "bias": bias,
        "n": n,
        "overconfident":  enough and bias > _BIAS_DEADBAND,
        "underconfident": enough and bias < -_BIAS_DEADBAND,
    }


def recalibrate_confidence(context: Dict[str, Any], confidence: float) -> float:
    """
    Correct a raw confidence reading by the measured over/under-confidence bias.
    No-op until enough samples exist or when the bias is within the deadband.
    The correction is clamped so the control loop can't be destabilised by a
    transient bias estimate.
    """
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return confidence
    cal = get_calibration(context)
    if not (cal["overconfident"] or cal["underconfident"]):
        return conf
    correction = max(-_MAX_CORRECTION, min(_MAX_CORRECTION, cal["bias"]))
    return max(0.0, min(1.0, conf - correction))


# ── Introspection trust (master plan Phase 1.3) ──────────────────────────────
# Self-knowledge as a learned quantity: the running agreement rate between what
# an inner prediction FELT like (self-report) and what behavior showed (the
# receipt check in cognition/prediction.py). Keyed per prediction domain.
# 0.5 = no evidence either way; 1.0 = introspection has always matched behavior.

def update_introspection_trust(domain: str, agreed: bool) -> float:
    """Record one felt-vs-behaved comparison; returns the updated trust score."""
    from datetime import datetime, timezone
    try:
        data = load_json(_TRUST_PATH, default_type=dict) or {}
        if not isinstance(data, dict):
            data = {}
        entry = data.get(domain) or {"trust": 0.5, "n": 0}
        entry["trust"] = round(
            (1 - _TRUST_ALPHA) * float(entry.get("trust", 0.5))
            + _TRUST_ALPHA * (1.0 if agreed else 0.0), 4)
        entry["n"] = int(entry.get("n", 0)) + 1
        entry["last_updated"] = datetime.now(timezone.utc).isoformat()
        data[domain] = entry
        save_json(_TRUST_PATH, data)
        return float(entry["trust"])
    except Exception as _e:
        record_failure("calibration.update_introspection_trust", _e)
        return 0.5


def get_introspection_trust(domain: Optional[str] = None) -> float:
    """Trust score for `domain`, or the all-domain average; 0.5 before evidence.
    Modulates how much affect-derived signals are believed elsewhere
    (affect_trend confidence prior, emotion_when_formed weighting in opinions)."""
    try:
        data = load_json(_TRUST_PATH, default_type=dict) or {}
        if not isinstance(data, dict) or not data:
            return 0.5
        if domain and isinstance(data.get(domain), dict):
            return float(data[domain].get("trust", 0.5))
        vals = [float(v.get("trust", 0.5)) for v in data.values() if isinstance(v, dict)]
        return round(sum(vals) / len(vals), 4) if vals else 0.5
    except Exception:
        return 0.5


def calibration_observation(context: Dict[str, Any]) -> Optional[str]:
    """
    Return a metacognitive observation string when calibration is sustainedly
    off, else None. Surfaced by metacog_analyze → behavioral_adaptation.
    """
    cal = get_calibration(context)
    if cal["n"] < _MIN_NOTE_SAMPLES:
        return None  # not enough evidence to verbalize a calibration judgment
    if cal["overconfident"]:
        return (
            f"I've been overconfident lately — my predicted outcomes have run "
            f"about {cal['bias']:.2f} higher than what actually happened. Worth "
            f"deliberating a little more before committing."
        )
    if cal["underconfident"]:
        return (
            f"I've been underconfident lately — things have gone about "
            f"{abs(cal['bias']):.2f} better than I predicted. I can trust my "
            f"judgement a bit more and act sooner."
        )
    return None
