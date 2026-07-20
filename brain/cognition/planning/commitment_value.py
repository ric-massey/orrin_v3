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

import os
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

# F4 (RUN7_FIX_PLAN_2026-07-11): re-commit cooldown. Run 6's avoid→release→
# re-commit orbit existed because avoidance was only a score penalty that decayed
# ×0.9/pull once the slot was lost — a pumped incumbent re-won as soon as the
# streak decayed. Losing the slot while the streak is still high (displaced BY
# avoidance, not ordinary rotation) now stamps a temporal block: the goal is
# ineligible for the driver slot, unconditionally — credit does NOT clear it and
# the incumbent bonus does not apply — until the block decrements to zero.
_RECOMMIT_AVOID_TRIGGER = 15    # ¾ of _AVOID_FULL
_RECOMMIT_BLOCK_PULLS = 300     # pulls of driver-slot ineligibility

# F1 (RUN8_FIX_PLAN_2026-07-14): absolute staleness refractory — the missing
# ABSOLUTE release. Every other lever in commit_score is relative and caps at
# −30; with no rival in range it did nothing while Run 7's holder rode
# stale_cycles 120 → 10,291. A driver that holds the slot this many cycles with
# ZERO credited effect (credit zeroes stale_cycles, so this can only trip on
# genuine non-production) arms its OWN F4 block and yields — no rival required.
# C2 (Run 11 §6.1) DEMOTES this to a dead-man backstop: neglect pressure below
# is the healthy displacement mechanism; the refractory only exists for the
# life where that economy somehow fails (it never fired in Runs 8–10).
_STALE_REFRACTORY_CYCLES = 250   # ~130 cycles past the −15 stale saturation:
                                 # the relative machinery gets first refusal,
                                 # then the absolute lever forces the yield.
_STALE_REFRACTORY_ENABLED = os.environ.get("ORRIN_STALE_REFRACTORY", "1") != "0"

# C2 (Run 11 §6.1) — ASPIRATION NEGLECT PRESSURE, the antagonist the timer
# clamps stood in for. Every candidate offered but NOT chosen accrues neglect;
# being served (holding the slot, or a credited effect) drains it. Neglect adds
# POSITIVE pull to commit_score, so an unserved direction grows until it
# displaces the incumbent — monopoly becomes economically impossible instead of
# administratively forbidden. Sized to beat the maximum value gap (±5 each side
# = 10) plus incumbency (+2) at saturation, so displacement is GUARANTEED by
# ~_NEGLECT_FULL_PULLS even against a perfect incumbent — but a well-earning
# incumbent holds proportionally longer (economics, not a timer).
_NEGLECT_PRESSURE_ENABLED = os.environ.get("ORRIN_NEGLECT_PRESSURE", "1") != "0"
_W_NEGLECT = 13.0
_NEGLECT_FULL_PULLS = 200.0    # pulls-not-chosen at which neglect saturates
_NEGLECT_SERVE_DECAY = 0.25    # being chosen drains fast (×0.25/pull held)

# F3a: real work on the goal is counter-evidence to avoidance only when the
# work actually relates to the goal; unrelated output is not.
_AVOID_RELIEF_MIN_ALIGNMENT = 0.3
# F5: recent credited content hashes kept per goal for diversity weighting.
_CREDIT_HASH_WINDOW = 20


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
    every other candidate's penalties DECAY — the release/recovery path. Also
    runs the F4 re-commit cooldown: active blocks pay one pull, and a driver
    displaced while its avoid streak was still high gets a fresh block."""
    chosen = str(chosen_id or "")
    if not chosen:
        return
    try:  # C8: commitment occupancy is a load-bearing distribution — observe it
        from brain.cognition.entropy_monitor import observe as _entropy_observe
        _entropy_observe("commitment_driver", chosen)
    except Exception as _eo:
        record_failure("commitment_value.entropy_observe", _eo)
    try:
        with modify_json(_SIGNALS_FILE, dict) as d:
            goals = d.setdefault("goals", {})
            prev = str(d.get("driver") or "")
            d["driver"] = chosen
            now = time.time()
            # F4: decrement every active block one pull (before any fresh stamp).
            for r in goals.values():
                if isinstance(r, dict):
                    b = float(r.get("recommit_block_pulls", 0.0) or 0.0)
                    if b > 0.0:
                        r["recommit_block_pulls"] = max(0.0, b - 1.0)
            # F4: displaced by avoidance (streak still ≥ trigger when the slot
            # was lost, checked before this pull's decay) → temporal block.
            if prev and prev != chosen:
                pr = goals.get(prev)
                if (isinstance(pr, dict)
                        and float(pr.get("avoid_streak", 0.0)) >= _RECOMMIT_AVOID_TRIGGER):
                    pr["recommit_block_pulls"] = float(_RECOMMIT_BLOCK_PULLS)
            row = _row(goals, chosen)
            row["stale_cycles"] = float(row.get("stale_cycles", 0.0)) + 1.0
            row["last_ts"] = now
            # F1 (Run 8): absolute refractory release. The holder has occupied the
            # driver slot for _STALE_REFRACTORY_CYCLES with no credited effect
            # (credit zeroes stale_cycles); the −30 relative penalty saturated
            # long ago and no rival displaced it. Arm its own block so
            # order_committable makes it ineligible next pull — the slot yields
            # even if nothing outscores it. Logged for the Run 8 gate.
            if (_STALE_REFRACTORY_ENABLED
                    and float(row.get("stale_cycles", 0.0)) >= _STALE_REFRACTORY_CYCLES
                    and float(row.get("recommit_block_pulls", 0.0) or 0.0) <= 0.0):
                row["recommit_block_pulls"] = float(_RECOMMIT_BLOCK_PULLS)
                ev = d.get("refractory_events")
                if not isinstance(ev, list):
                    ev = []
                d["refractory_events"] = (ev + [{
                    "goal": chosen,
                    "ts": now,
                    "stale_cycles": float(row.get("stale_cycles", 0.0)),
                    "avoid_streak": float(row.get("avoid_streak", 0.0)),
                }])[-200:]
            # C2: the holder is being SERVED — its neglect drains fast.
            if _NEGLECT_PRESSURE_ENABLED:
                row["neglect_pulls"] = round(
                    float(row.get("neglect_pulls", 0.0) or 0.0) * _NEGLECT_SERVE_DECAY, 3)
            for cid in candidate_ids:
                cid = str(cid or "")
                if not cid or cid == chosen:
                    continue
                # C2: an offered-but-unchosen candidate accrues neglect even on
                # its first appearance (create the row); the pull grows until
                # displacement, then serving drains it — the restoring force in
                # BOTH directions (§6.0's homeostat, not a one-way slide).
                if _NEGLECT_PRESSURE_ENABLED:
                    r = _row(goals, cid)
                    r["neglect_pulls"] = min(
                        _NEGLECT_FULL_PULLS,
                        float(r.get("neglect_pulls", 0.0) or 0.0) + 1.0)
                elif cid not in goals:
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


def note_goal_credit(goal_id: str, significance: float, *,
                     alignment: Optional[float] = None,
                     content_hash: Optional[str] = None) -> None:
    """A credited (novel, significant) effect landed for this goal — the "real
    action" signal. Folds into the value EMA — weighted by how much the content
    actually relates to the goal (F3a) and by content diversity (F5), so a
    barely-related or single-family stream of output can't pump value — and
    clears staleness (the goal DID act). The avoidance streak halves only when
    alignment ≥ 0.3: unrelated output is not counter-evidence to avoidance.
    Never touches an active recommit block (F4)."""
    gid = str(goal_id or "")
    if not gid:
        return
    try:
        sig = max(0.0, min(1.0, float(significance or 0.0)))
    except (TypeError, ValueError):
        sig = 0.0
    try:
        align = 1.0 if alignment is None else max(0.0, min(1.0, float(alignment)))
    except (TypeError, ValueError):
        align = 1.0
    try:
        with modify_json(_SIGNALS_FILE, dict) as d:
            goals = d.setdefault("goals", {})
            row = _row(goals, gid)
            # F5: distinct-hash share over the last credited effects. With the
            # ledger's exact-dup gate live this rarely binds — it exists so the
            # NEXT undiscovered volatile-token trick still can't buy a monopoly
            # from a single content family.
            hashes = [h for h in (row.get("recent_hashes") or []) if isinstance(h, str)]
            if content_hash:
                hashes = (hashes + [str(content_hash)])[-_CREDIT_HASH_WINDOW:]
                row["recent_hashes"] = hashes
            diversity = (len(set(hashes)) / len(hashes)) if hashes else 1.0
            sample = max(0.0, min(1.0, 0.5 + sig * align * diversity))
            old = float(row.get("value_ema", 0.5))
            row["value_ema"] = round((1.0 - _VALUE_ALPHA) * old + _VALUE_ALPHA * sample, 4)
            row["stale_cycles"] = 0.0
            # C2: a credited effect IS service — the neglect pull is satisfied.
            if _NEGLECT_PRESSURE_ENABLED:
                row["neglect_pulls"] = 0.0
            if alignment is None or align >= _AVOID_RELIEF_MIN_ALIGNMENT:
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
        # C2: unserved pull. At saturation (+13) it beats the widest possible
        # value gap (10) plus incumbency (2) — displacement by economics.
        if _NEGLECT_PRESSURE_ENABLED:
            neglect = float((row or {}).get("neglect_pulls", 0.0) or 0.0)
            adjust += _W_NEGLECT * min(1.0, neglect / _NEGLECT_FULL_PULLS)
        # F4: no incumbency for a blocked goal — the block is temporal and
        # unconditional, hysteresis be damned.
        if gid == str(d.get("driver") or "") and float(
                (row or {}).get("recommit_block_pulls", 0.0) or 0.0) <= 0.0:
            adjust += _W_INCUMBENT
        # L3: a small pull toward the believed destination (≤ +0.1 additive,
        # proposal §4) — it biases the ordering, never dictates it; C2's
        # neglect pressure (+13 at saturation) always out-muscles it.
        try:
            from brain.cognition.self_state.life_ambition import ambition_bias
            adjust += ambition_bias(goal)
        except Exception as _abe:
            record_failure("commitment_value.ambition_bias", _abe)
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
    # F4: a directional under an active re-commit block is ineligible for the
    # driver slot — it stays a signpost and the next-best directional drives.
    try:
        _tbl = _load_signals().get("goals", {})
        blocked = {g for g, r in _tbl.items() if isinstance(r, dict)
                   and float(r.get("recommit_block_pulls", 0.0) or 0.0) > 0.0}
    except Exception as exc:
        record_failure("commitment_value.order_committable.blocked", exc)
        blocked = set()
    result: List[Dict[str, Any]] = []
    seen_directional = False
    driver_id = ""
    for g in found:
        tier = str(g.get("tier") or g.get("kind") or "").lower()
        # F2 (Run 8): treat any long-term aspiration as a direction. Only
        # self_understanding ever acquired the directional/never_complete flags
        # (causal-frontier promotion), so the directional cap governed a
        # single-member pool and F1's release had nowhere to hand the slot. The
        # _aspiration flag is set on exactly the four enduring directions.
        is_directional = tier == "long_term" and bool(
            g.get("directional") or g.get("never_complete") or g.get("_aspiration"))
        if is_directional:
            if seen_directional or _gid(g) in blocked:
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


def refractory_events() -> List[Dict[str, Any]]:
    """Run-analysis: every absolute-staleness refractory release this life
    (F1). Empty list = the release never fired — read alongside the max
    stale_cycles at death to decide whether Run 8's fix did anything."""
    ev = _load_signals().get("refractory_events", [])
    return ev if isinstance(ev, list) else []
