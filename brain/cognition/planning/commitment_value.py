# brain/cognition/planning/commitment_value.py
#
# Run 6 Fixes 2–4 (RUN6_FIX_PLAN_2026-07-08 §3) — the commitment half of
# "learning must steer behavior."
#
# Run 5 committed one directional goal for 99.9 % of the life because
# goal_io._committable_from_v1_tree sorted on (tier, priority) — a static
# stable-sort where every directional aspiration ties (long_term + HIGH), so the
# same one won every cycle forever. Being actively AVOIDED 240 times never
# lowered its rank; nothing about pursuit (or non-pursuit) fed back into
# commitment. This module is that missing feedback path:
#
#   commit_score = tier·w_t + priority·w_p
#                + learned_goal_value·w_v      (credited effects + aspiration credit, Fix 4)
#                − staleness_penalty·w_s       (driver cycles without a credited effect)
#                − avoidance_penalty·w_a       (goal_avoidance streak, Fix 3)
#
# A committed-but-unacted goal loses rank and yields the driver slot; released,
# its penalties decay so it can recover when it's actionable again. The tier
# floor Part I established (survival > core > …) is preserved: the adjustment
# is bounded well under one tier step (w_t = 100), though it can legitimately
# cross priority ranks (a stale HIGH driver should yield to a fresh NORMAL one).
#
# Writers: goal_io (driver selection, per pull), behavioral_adaptation +
# goal_closure (avoidance, Fix 3), effect_ledger (credited effects). All entry
# points are fail-safe — commitment feedback must never break the loop.
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, modify_json

_SIGNALS_FILE = DATA_DIR / "commitment_signals.json"

# Score weights. Tier/priority mirror goal_io's ordering; the learned terms are
# sized so value swings ±5, and staleness+avoidance together max at −30 —
# enough to displace a same-tier rival, never enough to cross a tier boundary.
W_TIER = 100.0
W_PRIORITY = 10.0
_W_VALUE = 10.0
_W_STALE = 15.0
_W_AVOID = 15.0

_W_INCUMBENT = 2.0         # hysteresis bonus for the current slot-holder: without
                           # it the first-listed goal wins every exact tie, so a
                           # newly rotated-in driver would be a one-pull blip

_VALUE_ALPHA = 0.25        # EMA rate for the credited-effect value signal
_STALE_FULL_CYCLES = 120   # driver cycles without credit at which staleness saturates
_STALE_GRACE_CYCLES = 30   # free holding period before staleness pressure begins —
                           # without it two tied directionals would flip the driver
                           # slot every pull (will.py exists to stop impulse switching)
_AVOID_FULL = 20           # avoidance streak at which the penalty saturates
                           # (Run 5 streaks reached 68 consecutive cycles)
_AVOID_GRACE = 2           # a lone detection doesn't move commitment; a streak does
_RELEASE_DECAY = 0.90      # per-pull recovery decay while NOT holding the driver slot
_GOALS_CAP = 200           # bound the per-goal signal table


def _gid(goal: Any) -> str:
    if not isinstance(goal, dict):
        return ""
    return str(goal.get("id") or goal.get("title") or goal.get("name") or "")


def _load_signals() -> Dict[str, Any]:
    try:
        d = load_json(_SIGNALS_FILE, default_type=dict) or {}
        if not isinstance(d, dict):
            d = {}
    except Exception as exc:
        record_failure("commitment_value._load_signals", exc)
        d = {}
    d.setdefault("goals", {})
    return d


def _row(goals: Dict[str, Any], gid: str) -> Dict[str, Any]:
    row = goals.get(gid)
    if not isinstance(row, dict):
        row = {"value_ema": 0.5, "stale_cycles": 0.0, "avoid_streak": 0.0}
        goals[gid] = row
    return row


def _prune(goals: Dict[str, Any]) -> None:
    if len(goals) <= _GOALS_CAP:
        return
    for k in sorted(goals, key=lambda k: float(goals[k].get("last_ts", 0.0)))[
            : len(goals) - _GOALS_CAP]:
        goals.pop(k, None)


def note_driver_selected(chosen_id: str, candidate_ids: Iterable[str]) -> None:
    """Called by goal_io once per committed-goal pull with the goal holding the
    driver slot. The holder accrues staleness (reset only by a credited effect);
    every other candidate's penalties DECAY — the release/recovery path."""
    chosen = str(chosen_id or "")
    if not chosen:
        return
    try:
        with modify_json(_SIGNALS_FILE, dict) as d:
            goals = d.setdefault("goals", {})
            d["driver"] = chosen
            now = time.time()
            row = _row(goals, chosen)
            row["stale_cycles"] = float(row.get("stale_cycles", 0.0)) + 1.0
            row["last_ts"] = now
            for cid in candidate_ids:
                cid = str(cid or "")
                if not cid or cid == chosen or cid not in goals:
                    continue
                r = goals[cid]
                r["stale_cycles"] = round(float(r.get("stale_cycles", 0.0)) * _RELEASE_DECAY, 3)
                r["avoid_streak"] = round(float(r.get("avoid_streak", 0.0)) * _RELEASE_DECAY, 3)
            _prune(goals)
    except Exception as exc:
        record_failure("commitment_value.note_driver_selected", exc)


def note_avoidance(goal_id: str, weight: float = 1.0) -> None:
    """Fix 3 — a goal-avoidance detection on this committed goal. Raises the
    avoidance penalty so avoidance can RELEASE the commitment, not only prod
    action on it (`_force_action_next` fought the symptom 240× in Run 5 and
    never touched commitment)."""
    gid = str(goal_id or "")
    if not gid:
        return
    try:
        with modify_json(_SIGNALS_FILE, dict) as d:
            goals = d.setdefault("goals", {})
            row = _row(goals, gid)
            row["avoid_streak"] = round(float(row.get("avoid_streak", 0.0)) + float(weight), 3)
            row["last_ts"] = time.time()
            _prune(goals)
    except Exception as exc:
        record_failure("commitment_value.note_avoidance", exc)


def note_goal_credit(goal_id: str, significance: float) -> None:
    """A credited (novel, significant) effect landed for this goal — the "real
    action" signal. Folds into the value EMA, clears staleness, and halves the
    avoidance streak (real work on the goal is the strongest counter-evidence)."""
    gid = str(goal_id or "")
    if not gid:
        return
    try:
        sample = max(0.0, min(1.0, 0.5 + float(significance or 0.0)))
    except (TypeError, ValueError):
        sample = 0.5
    try:
        with modify_json(_SIGNALS_FILE, dict) as d:
            goals = d.setdefault("goals", {})
            row = _row(goals, gid)
            old = float(row.get("value_ema", 0.5))
            row["value_ema"] = round((1.0 - _VALUE_ALPHA) * old + _VALUE_ALPHA * sample, 4)
            row["stale_cycles"] = 0.0
            row["avoid_streak"] = round(float(row.get("avoid_streak", 0.0)) * 0.5, 3)
            row["last_ts"] = time.time()
            _prune(goals)
    except Exception as exc:
        record_failure("commitment_value.note_goal_credit", exc)


def _learned_goal_value(goal: Dict[str, Any], row: Optional[Dict[str, Any]]) -> float:
    """[0,1] learned value: the goal's own credited-effect EMA blended with the
    credited-contribution signal of the aspiration its drive serves (Fix 4 —
    the loop that makes the pursued aspiration and the rewarded one converge)."""
    own = float((row or {}).get("value_ema", 0.5))
    asp: Optional[float] = None
    spec = goal.get("spec") if isinstance(goal.get("spec"), dict) else {}
    driven = str(goal.get("driven_by") or spec.get("driven_by") or "")
    if driven:
        try:
            from brain.cognition.intrinsic_objectives import aspiration_credit_value
            asp = aspiration_credit_value(driven)
        except Exception as exc:
            record_failure("commitment_value.aspiration_credit", exc)
    if asp is None:
        return own
    return 0.5 * own + 0.5 * float(asp)


def commit_score(goal: Dict[str, Any], *, tier_weight: int, priority_rank: int) -> float:
    """The full commitment score goal_io sorts on (Fix 2). Fail-safe: on any
    signal-store trouble this degrades to the legacy tier/priority ordering."""
    base = W_TIER * float(tier_weight) + W_PRIORITY * float(priority_rank)
    gid = _gid(goal)
    if not gid:
        return base
    try:
        d = _load_signals()
        goals = d.get("goals", {})
        row = goals.get(gid) if isinstance(goals.get(gid), dict) else None
        value = _learned_goal_value(goal, row)
        stale = float((row or {}).get("stale_cycles", 0.0))
        avoid = float((row or {}).get("avoid_streak", 0.0))
        stale_norm = min(1.0, max(0.0, stale - _STALE_GRACE_CYCLES)
                         / max(1.0, _STALE_FULL_CYCLES - _STALE_GRACE_CYCLES))
        avoid_norm = min(1.0, max(0.0, avoid - _AVOID_GRACE)
                         / max(1.0, _AVOID_FULL - _AVOID_GRACE))
        adjust = (_W_VALUE * (value - 0.5)
                  - _W_STALE * stale_norm
                  - _W_AVOID * avoid_norm)
        if gid == str(d.get("driver") or ""):
            adjust += _W_INCUMBENT
        return base + adjust
    except Exception as exc:
        record_failure("commitment_value.commit_score", exc)
        return base


def order_committable(
    found: List[Dict[str, Any]],
    *,
    tier_weight_fn: Callable[[Any], int],
    priority_rank_fn: Callable[[Any], int],
    limit: int,
) -> List[Dict[str, Any]]:
    """Order goal_io's committable candidates by commit_score and apply the P4
    directional cap — exactly ONE directional long_term goal drives at a time,
    now the highest-SCORED one, so which directional drives rotates on learned
    value/staleness/avoidance rather than a stable tie-break. Extra directionals
    stay signposts; the remaining committed slots go to ordinary goals so the
    never-ending driver can never starve the pool. Also feeds the rotation loop
    (the slot-holder accrues staleness; released candidates decay/recover).
    Returns shallow copies so per-cycle edits don't corrupt the tree."""
    found = sorted(
        found,
        key=lambda g: commit_score(
            g,
            tier_weight=tier_weight_fn(g.get("tier") or g.get("kind")),
            priority_rank=priority_rank_fn(g.get("priority")),
        ),
        reverse=True,
    )
    result: List[Dict[str, Any]] = []
    seen_directional = False
    driver_id = ""
    for g in found:
        tier = str(g.get("tier") or g.get("kind") or "").lower()
        is_directional = tier == "long_term" and bool(
            g.get("directional") or g.get("never_complete"))
        if is_directional:
            if seen_directional:
                continue
            seen_directional = True
            driver_id = _gid(g)
        result.append(g)
        if len(result) >= limit:
            break
    if result:
        note_driver_selected(driver_id or _gid(result[0]), [_gid(g) for g in found])
    return [dict(g) for g in result]


def signals_snapshot() -> Dict[str, Any]:
    """Read-only copy of the signal table (telemetry / run analysis)."""
    return _load_signals().get("goals", {})
