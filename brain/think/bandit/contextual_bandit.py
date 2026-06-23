# brain/think/bandit/contextual_bandit.py
#
# Tabular contextual bandit. The continuous context is binned into a small set
# of discrete AFFECT buckets, and each bucket keeps its own UCB1 statistics per
# action. No linear features / LinUCB — selection is plain UCB1 within the bucket
# that matches the current affect context.
#
#   Auer, Cesa-Bianchi & Fischer (2002) — "Finite-time analysis of the
#   multi-armed bandit problem" (UCB1). The contextual part is a hard
#   partition of the state space rather than a learned linear model.
#
# Buckets (from the dominant affect signal; names match the affect vocabulary):
#   exploration_drive (curious)   impasse_signal (frustrated)
#   social_deficit    (lonely)    stable         (calm / everything else)
#
# State schema (bandit_state.json):
#   { "buckets": { bucket: { action: {"n": int, "q": float} } },
#     "counts":  { action: int },          # total selections (stagnation detector)
#     "suppressed": { action: cycles } }
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
import math
import threading
from typing import Dict, List, Optional, Tuple
from pathlib import Path
_log = get_logger(__name__)

_LOCK = threading.Lock()

# Prefer paths.py definitions; fall back to data/bandit_state.json
try:
    from brain.paths import BANDIT_STATE_FILE as _BANDIT_PATH  # preferred
except Exception:
    try:
        from brain.paths import BANDIT_STATE_JSON as _BANDIT_PATH
    except Exception:
        try:
            from brain.paths import DATA_DIR as _DATA_DIR
            _BANDIT_PATH = _DATA_DIR / "bandit_state.json"
        except Exception:
            _BANDIT_PATH = Path("data") / "bandit_state.json"

BANDIT_STATE_PATH: Path = Path(_BANDIT_PATH)

from brain.utils.json_utils import load_json, save_json  # uses your locking/logging
from brain.utils.failure_counter import record_failure

# ---------- affect buckets ----------
BUCKETS: Tuple[str, ...] = ("exploration_drive", "impasse_signal", "social_deficit", "stable")
_DEFAULT_BUCKET = "stable"
_AFFECT_BUCKETS = ("exploration_drive", "impasse_signal", "social_deficit")


def _context_bucket(features: Optional[Dict[str, float]]) -> str:
    """
    Map a context/feature dict to exactly one discrete affect bucket.

    Primary signal is the dominant-emotion one-hot that select_function emits
    (``emo_<name>``); a caller may instead pass raw affect magnitudes keyed by
    the signal name. Anything that isn't clearly one of the three affect states
    lands in the calm 'stable' bucket.
    """
    f = features or {}
    # 1) dominant-emotion one-hot from extract_features()
    for b in _AFFECT_BUCKETS:
        try:
            if float(f.get(f"emo_{b}", 0.0) or 0.0) > 0.0:
                return b
        except (TypeError, ValueError):  # intentional: non-numeric feature → skip bucket
            pass
    # 2) raw affect magnitudes passed directly
    try:
        cand = {b: float(f.get(b, 0.0) or 0.0) for b in _AFFECT_BUCKETS}
        top = max(cand, key=cand.get)
        if cand[top] >= 0.5:
            return top
    except (TypeError, ValueError):  # intentional: non-numeric magnitudes → default bucket
        pass
    return _DEFAULT_BUCKET


def _safe_float(x) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except (TypeError, ValueError):  # intentional: non-numeric → 0.0
        return 0.0


# ---------- state ----------
def _validate_state(st: Dict) -> None:
    """Coerce malformed state in-place to the bucketed schema (never raises)."""
    buckets = st.get("buckets")
    if not isinstance(buckets, dict):
        st["buckets"] = {}
        buckets = st["buckets"]
    for b in BUCKETS:
        bd = buckets.get(b)
        if not isinstance(bd, dict):
            buckets[b] = {}
            bd = buckets[b]
        for action, stat in list(bd.items()):
            if not isinstance(stat, dict):
                bd[action] = {"n": 0, "q": 0.0}
                continue
            try:
                stat["n"] = max(0, int(stat.get("n", 0) or 0))
            except Exception:
                stat["n"] = 0
            stat["q"] = _safe_float(stat.get("q", 0.0))

    counts = st.get("counts")
    if not isinstance(counts, dict):
        st["counts"] = {}
    else:
        for a, v in list(counts.items()):
            try:
                counts[a] = int(v)
            except Exception:
                counts[a] = 0

    if not isinstance(st.get("suppressed"), dict):
        st["suppressed"] = {}


def _load() -> Dict:
    st = load_json(BANDIT_STATE_PATH, default_type=dict)
    if not isinstance(st, dict):
        st = {}
    # Migrate from the old linear/LinUCB schema: keep counts + suppression,
    # drop the obsolete linear-model state so the file adopts the bucketed schema.
    for _obsolete in ("weights", "alpha", "beta", "traces"):
        st.pop(_obsolete, None)
    st.setdefault("buckets", {})
    st.setdefault("counts", {})
    st.setdefault("suppressed", {})
    _validate_state(st)
    return st


def _save(state: Dict) -> None:
    BANDIT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_json(BANDIT_STATE_PATH, state)


def _bucket_dict(st: Dict, bucket: str) -> Dict:
    return st["buckets"].setdefault(bucket, {})


def _stat(bd: Dict, action: str) -> Dict:
    s = bd.get(action)
    if not isinstance(s, dict):
        s = {"n": 0, "q": 0.0}
        bd[action] = s
    return s


# ---------- exploration helpers (bucket-agnostic) ----------
def _stagnation_epsilon_boost(st: Dict, actions: List[str], base_epsilon: float) -> float:
    """
    Increase epsilon when the same small set of arms has dominated recent choices.
    Detects when top-3 arms account for >80% of all selections → forces exploration.
    """
    counts = st.get("counts", {})
    total = sum(int(counts.get(a, 0)) for a in actions)
    if total < 20:
        return base_epsilon

    sorted_counts = sorted(
        [(a, int(counts.get(a, 0))) for a in actions],
        key=lambda x: x[1], reverse=True,
    )
    top3 = sum(c for _, c in sorted_counts[:3])
    concentration = top3 / max(total, 1)

    if concentration > 0.80:
        return min(0.5, base_epsilon + 0.25 * (concentration - 0.80) / 0.20)
    elif concentration > 0.65:
        return min(0.35, base_epsilon + 0.10 * (concentration - 0.65) / 0.15)
    return base_epsilon


def _filter_suppressed(st: Dict, actions: List[str]) -> List[str]:
    """Drop suppressed actions from the candidate list."""
    sup = st.get("suppressed") or {}
    if not isinstance(sup, dict) or not sup:
        return list(actions)
    return [a for a in actions if int(sup.get(a, 0) or 0) <= 0]


# ---------- selection: per-bucket UCB1 ----------
def choose(
    actions: List[str],
    features: Optional[Dict[str, float]] = None,
    epsilon: float = 0.1,
    ucb_c: float = 0.5,
    return_scores: bool = False,
):
    """
    Pick an action via UCB1 within the affect bucket implied by `features`.

    - Bucketing: `features` → one of {exploration_drive, impasse_signal,
      social_deficit, stable} (see _context_bucket).
    - Cold arms in the bucket are tried first (UCB1 optimism).
    - Epsilon-greedy floor + stagnation boost still apply.
    - Metacog-suppressed actions are filtered out.

    Returns the chosen action (str). If `return_scores=True`, returns
    ``(action, {"scores": {...}, "bucket": str, "epsilon": float})``.
    """
    if not actions:
        raise ValueError("choose() requires a non-empty actions list")
    st = _load()
    bucket = _context_bucket(features)

    _filtered = _filter_suppressed(st, actions)
    if _filtered:
        actions = _filtered

    epsilon = min(1.0, max(0.0, float(epsilon)))
    epsilon = _stagnation_epsilon_boost(st, actions, epsilon)
    bd = _bucket_dict(st, bucket)

    if random.random() < epsilon:
        picked = random.choice(actions)
    else:
        # UCB1: explore each unseen arm (in this bucket) at least once
        unexplored = [a for a in actions if int(_stat(bd, a)["n"]) == 0]
        if unexplored:
            picked = random.choice(unexplored)
        else:
            total_n = sum(int(_stat(bd, a)["n"]) for a in actions)
            best, best_score = None, -float("inf")
            for a in actions:
                s = _stat(bd, a)
                n = max(1, int(s["n"]))
                bonus = float(ucb_c) * math.sqrt(math.log(max(total_n + 1, 2)) / n)
                score = _safe_float(s["q"]) + bonus
                if score > best_score:
                    best_score, best = score, a
            picked = best if best is not None else random.choice(actions)

    if return_scores:
        return picked, {
            "scores": get_scores(actions, features, ucb_c),
            "bucket": bucket,
            "epsilon": round(epsilon, 3),
        }
    return picked


def get_scores(
    actions: List[str],
    features: Optional[Dict[str, float]] = None,
    ucb_c: float = 0.5,
) -> Dict[str, float]:
    """
    Return the UCB1 score for every action in the current bucket without
    selecting. Cold arms get a large optimistic score so select_function's
    hint-blending still favours exploring them.
    """
    if not actions:
        return {}
    st = _load()
    bucket = _context_bucket(features)
    _filtered = _filter_suppressed(st, actions)
    if _filtered:
        actions = _filtered
    bd = _bucket_dict(st, bucket)
    total_n = sum(int(_stat(bd, a)["n"]) for a in actions)
    scores: Dict[str, float] = {}
    for a in actions:
        s = _stat(bd, a)
        n = int(s["n"])
        if n == 0:
            scores[a] = 1.0  # optimistic: never tried in this bucket
            continue
        bonus = float(ucb_c) * math.sqrt(math.log(max(total_n + 1, 2)) / n)
        scores[a] = _safe_float(s["q"]) + bonus
    return scores


# ---------- updates ----------
def _record(st: Dict, bucket: str, action: str, reward: float,
            lr: Optional[float] = None) -> float:
    """Update the value estimate for (bucket, action); return the pre-update q.

    Two regimes, selected by whether the caller supplies a learning rate:
      - ``lr is None`` → UCB1 **sample-mean** (effective step ``1/n``): the
        stationary default used by callers that don't pass a rate (the historical
        behaviour of every path).
      - ``lr`` given → **constant-step** ``q += lr*(reward - q)``: recency-weighted
        / non-stationary tracking. This is the regime the ACh-modulated selector
        (``loop_helpers.bandit_learn`` → ``update_with_pe(lr=_ach_lr)``), dream
        replay (``_REPLAY_LR``), and value-alignment nudges (``update(lr=…)``)
        always intended — the rate was previously accepted and silently ignored.

    ``n`` (the visit count driving the UCB exploration bonus) increments in both
    regimes; reward is pre-clamped to [-1, 1] by callers, so the convex
    constant-step update keeps ``q`` in range without an extra clamp.
    """
    bd = _bucket_dict(st, bucket)
    s = _stat(bd, action)
    q_before = _safe_float(s["q"])
    n = int(s["n"]) + 1
    if lr is None:
        s["q"] = q_before + (reward - q_before) / n          # UCB1 running mean
    else:
        step = min(1.0, max(0.0, float(lr)))
        s["q"] = q_before + step * (reward - q_before)       # constant-step (tracking)
    s["n"] = n
    st["counts"][action] = int(st["counts"].get(action, 0)) + 1
    return q_before


def update(
    action: str,
    features: Optional[Dict[str, float]] = None,
    reward: float = 0.0,
    lr: Optional[float] = None,   # None → UCB1 sample-mean; a value → constant-step tracking
    l2: float = 0.001,            # accepted for API compatibility; no weight decay here
) -> None:
    """Record `reward` for `action` in the bucket implied by `features`.

    Pass ``lr`` to use a constant-step (recency-weighted) update; omit it for the
    default UCB1 sample-mean. See ``_record`` for the two regimes.
    """
    if not action:
        return
    with _LOCK:
        st = _load()
        bucket = _context_bucket(features)
        reward = max(-1.0, min(1.0, _safe_float(reward)))
        _record(st, bucket, action, reward, lr=lr)
        _save(st)


def update_with_pe(
    action: str,
    features: Optional[Dict[str, float]] = None,
    reward: float = 0.0,
    lr: Optional[float] = None,   # ACh-modulated rate from the selector; None → sample-mean
    l2: float = 0.001,            # accepted for API compatibility; no weight decay here
) -> float:
    """
    Record reward AND return the prediction error (reward − prior value estimate
    for this bucket+action). Single load+save. Used by the per-cycle PE pipeline.

    ``lr`` is the acetylcholine-modulated learning rate the selector computes
    (``loop_helpers.bandit_learn``); it drives a constant-step update so uncertain
    contexts learn faster (Yu & Dayan 2005). The returned PE is ``reward − q_before``
    — computed before the update — so it is independent of the chosen ``lr``.
    """
    if not action:
        return 0.0
    with _LOCK:
        st = _load()
        bucket = _context_bucket(features)
        reward = max(-1.0, min(1.0, _safe_float(reward)))
        q_before = _record(st, bucket, action, reward, lr=lr)
        pe = max(-2.0, min(2.0, reward - q_before))
        _save(st)
    return pe


def update_delayed(
    action: str,
    features: Optional[Dict[str, float]] = None,
    reward: float = 0.0,
    decision_id: Optional[str] = None,
    lr: Optional[float] = None,   # None → UCB1 sample-mean (the delayed-reward default)
    l2: float = 0.001,
) -> None:
    """Apply a delayed reward to a previously chosen action (same math as update)."""
    from brain.think.loop_helpers import emit_trace
    update(action, features, reward, lr=lr, l2=l2)
    try:
        emit_trace(
            type="BANDIT_UPDATE_DELAYED",
            action=action,
            reward=reward,
            decision_id=decision_id,
        )
    except Exception as _e:
        record_failure("contextual_bandit.update_delayed", _e)


def update_from_prediction_error(
    action: str,
    prediction_error: float,
    features: Optional[Dict[str, float]] = None,
    lr: float = 0.07,
) -> float:
    """
    Gentle value nudge along the PE direction for (bucket, action), bounded so a
    single surprise can't dominate. Tabular analogue of the old TD weight nudge.
    """
    if not action:
        return 0.0
    pe = max(-2.0, min(2.0, _safe_float(prediction_error)))
    lr = min(0.25, max(0.0, float(lr)))
    if abs(pe) < 1e-6 or lr <= 0.0:
        return pe
    with _LOCK:
        st = _load()
        bucket = _context_bucket(features)
        s = _stat(_bucket_dict(st, bucket), action)
        delta = min(0.20, max(-0.20, lr * pe))
        s["q"] = max(-1.0, min(1.0, _safe_float(s["q"]) + delta))
        _save(st)
    return pe


def step_traces(action: str, features: Optional[Dict[str, float]] = None, **_kw) -> None:
    """No-op retained for API compatibility — the tabular bandit keeps no
    eligibility traces. Safe to call after choose()."""
    return None


def expected_reward(action: str, features: Optional[Dict[str, float]] = None) -> float:
    """Current value estimate q for (bucket, action), in [-1, 1]."""
    if not action:
        return 0.0
    st = _load()
    bucket = _context_bucket(features)
    s = st["buckets"].get(bucket, {}).get(action)
    if not isinstance(s, dict):
        return 0.0
    return max(-1.0, min(1.0, _safe_float(s.get("q", 0.0))))


def penalise(action: str, magnitude: float = 0.08) -> None:
    """Soft penalty without a feature vector (lands in the 'stable' bucket)."""
    reward = max(-1.0, 0.5 - float(magnitude))
    update(action, features=None, reward=reward)


# ---------- introspection / lifecycle ----------
def get_state() -> Dict:
    """Return the current bandit state."""
    return _load()


def reset_state() -> None:
    """Delete the persisted bandit state file."""
    try:
        if BANDIT_STATE_PATH.exists():
            BANDIT_STATE_PATH.unlink()
    except Exception as _e:
        record_failure("contextual_bandit.reset_state", _e)


# ---------- metacog suppression ----------
def suppress_action(action: str, n_cycles: int = 15) -> None:
    """Mask `action` from selection for the next `n_cycles` tick_suppression() calls."""
    if not action:
        return
    n_cycles = max(0, int(n_cycles))
    with _LOCK:
        st = _load()
        sup = st.setdefault("suppressed", {})
        if not isinstance(sup, dict):
            sup = {}
            st["suppressed"] = sup
        if n_cycles <= 0:
            sup.pop(action, None)
        else:
            sup[action] = n_cycles
        _save(st)


def tick_suppression() -> Dict[str, int]:
    """Decrement all suppression counters; drop entries that hit 0. Call once per cycle."""
    with _LOCK:
        st = _load()
        sup = st.get("suppressed") or {}
        if not isinstance(sup, dict):
            sup = {}
        new_sup: Dict[str, int] = {}
        for action, n in list(sup.items()):
            try:
                remaining = int(n) - 1
            except Exception:
                remaining = 0
            if remaining > 0:
                new_sup[action] = remaining
        st["suppressed"] = new_sup
        _save(st)
        return dict(new_sup)


def get_suppressed() -> Dict[str, int]:
    """Return a copy of the current suppression map (action -> cycles_remaining)."""
    st = _load()
    sup = st.get("suppressed") or {}
    if not isinstance(sup, dict):
        return {}
    return {a: int(n) for a, n in sup.items()}


def clear_suppression(action: Optional[str] = None) -> None:
    """Clear suppression for one action, or all if `action` is None."""
    with _LOCK:
        st = _load()
        if action is None:
            st["suppressed"] = {}
        else:
            sup = st.get("suppressed") or {}
            if isinstance(sup, dict):
                sup.pop(action, None)
                st["suppressed"] = sup
        _save(st)
