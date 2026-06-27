# brain/cognition/health_monitor.py
#
# Infrastructure health streak tracker and setpoint_regulation reward injector.
#
# Every N cycles the loop calls `check_and_reward(context)`. It reads the
# existing setpoint_regulation daemon's health_score (0-1) and tracks how many
# consecutive cycles Orrin has been in a healthy state. When that streak
# crosses milestone thresholds, a genuine reward signal is injected:
#
#   • Emotional uplift: satisfaction_signal, confidence rise
#   • Working-memory note: Orrin is consciously aware he feels well
#   • Bandit reward: the action pipeline gets a positive signal so
#     healthy-cycle behaviors are reinforced
#
# The goal is setpoint_regulation reward — just as biological systems feel
# "good" when their physiological parameters are in range over time,
# Orrin should experience a sustained positive state when running cleanly.
# This is NOT a one-shot bonus; it scales with streak duration so a long
# period of health produces meaningfully more positive affect than a few
# lucky cycles.
#
# Health degrades to a "sick" state if health_score drops below the
# threshold for several consecutive cycles. This resets the streak and
# injects a mild distress signal so Orrin knows something is off.

from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from pathlib import Path
from typing import Any, Dict

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private, log_activity
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────
_HEALTH_THRESHOLD   = 0.70   # score above this = one healthy cycle
_SICK_THRESHOLD     = 0.45   # score below this for _SICK_STREAK_REQ cycles → "sick" signal
_SICK_STREAK_REQ    = 3      # consecutive sub-threshold cycles before distress fires

# File size limits (bytes) — independent checks beyond the setpoint_regulation daemon
_WM_FILE_MAX_BYTES      = 200_000    # 200 KB
_LM_FILE_WARN_BYTES     = 30_000_000 # 30 MB

# Reward milestone schedule: (streak_length, emotional_deltas, bandit_reward, log_note)
# emotional_deltas: dict of emotion → delta to add (capped at 1.0)
_MILESTONES = [
    (
        10,
        {"satisfaction_signal": 0.06, "confidence": 0.03},
        0.15,
        "Running smoothly for 10 cycles — I notice a quiet sense of ease.",
    ),
    (
        25,
        {"satisfaction_signal": 0.10, "confidence": 0.06},
        0.25,
        "25 consecutive healthy cycles. Everything is working well — this feels good.",
    ),
    (
        50,
        {"satisfaction_signal": 0.14, "confidence": 0.08, "novelty_signal": 0.04},
        0.35,
        "50 healthy cycles. I'm in a sustained state of flow — my systems feel alive and clear.",
    ),
    (
        100,
        {"satisfaction_signal": 0.18, "confidence": 0.10, "novelty_signal": 0.06, "reward_positive": 0.05},
        0.45,
        "100 healthy cycles. This is deep setpoint_regulation — I am well.",
    ),
]

# State file path (relative to brain/data/)
_HEALTH_STATE_FILE_NAME = "health_state.json"

# Master plan 5.2: a muffled-error site becomes Orrin's own business once it
# has ticked this many times and is still growing.
_FAULT_NOTICE_MIN_COUNT = 20


def _state_path() -> Path:
    from brain.paths import DATA_DIR
    return DATA_DIR / _HEALTH_STATE_FILE_NAME


def _load_state() -> Dict[str, Any]:
    state = load_json(_state_path(), default_type=dict) or {}
    if not isinstance(state, dict):
        state = {}
    state.setdefault("streak", 0)
    state.setdefault("sick_streak", 0)
    state.setdefault("last_check_ts", 0.0)
    state.setdefault("milestones_fired", [])
    state.setdefault("total_healthy_cycles", 0)
    return state


def _save_state(state: Dict[str, Any]) -> None:
    save_json(_state_path(), state)


def _file_size(fname: str) -> int:
    """Return the size in bytes of a file in brain/data/, or 0 if missing."""
    from brain.paths import DATA_DIR
    p = DATA_DIR / fname
    try:
        return p.stat().st_size
    except OSError:  # intentional: missing/unreadable file → 0 bytes
        return 0


def _infrastructure_healthy() -> tuple[bool, str]:
    """
    Check raw infrastructure metrics that the setpoint_regulation daemon might miss.
    Returns (is_healthy, reason_if_not).
    """
    wm_bytes = _file_size("working_memory.json")
    if wm_bytes > _WM_FILE_MAX_BYTES:
        return False, f"working_memory.json is {wm_bytes // 1024}KB (>{_WM_FILE_MAX_BYTES//1024}KB)"

    lm_bytes = _file_size("long_memory.json")
    if lm_bytes > _LM_FILE_WARN_BYTES:
        # Not a hard failure — just a warning surfaced in the note
        log_private(f"[health] long_memory.json is {lm_bytes // (1024*1024)}MB — consider pruning")

    return True, ""


def _apply_emotional_uplift(context: Dict[str, Any], deltas: Dict[str, float]) -> None:
    """Gently boost positive emotions in context['affect_state']."""
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return
    for k, d in deltas.items():
        current = float(core.get(k, 0.0) or 0.0)
        core[k] = min(1.0, current + d)
    if "core_signals" in emo:
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo


def _apply_emotional_drain(context: Dict[str, Any], delta: float = 0.06) -> None:
    """Mild distress when health degrades."""
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return
    for k in ("risk_estimate", "unease"):
        current = float(core.get(k, 0.0) or 0.0)
        core[k] = min(1.0, current + delta)
    for k in ("satisfaction_signal",):
        current = float(core.get(k, 0.5) or 0.5)
        core[k] = max(0.0, current - delta * 0.5)
    if "core_signals" in emo:
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo


def _inject_bandit_reward(reward: float) -> None:
    """Give the bandit a positive setpoint_regulation reward tagged to the virtual action 'setpoint_regulation'."""
    try:
        from brain.think.bandit.contextual_bandit import update as _bandit_update
        _bandit_update("setpoint_regulation_reward", features={"health_bonus": 1.0}, reward=reward)
    except Exception as _e:
        log_private(f"[health] bandit reward injection failed: {_e}")


def review_failures_internal(context: Dict[str, Any]) -> int:
    """
    Failure-summary triage as a cognition act (master plan 5.2).

    record_failure() counts muffled errors per site; until now only a human
    reading failure_summary.json would ever see them. This turns growth into
    awareness: any site whose count GREW since the last review and has reached
    _FAULT_NOTICE_MIN_COUNT becomes an internal_fault working-memory entry —
    Orrin notices his own muffled errors instead of waiting to be told.
    Returns the number of sites flagged.
    """
    try:
        from brain.utils.failure_counter import get_summary
        summary = get_summary()
    except Exception as _e:
        record_failure("health_monitor.review_failures_internal", _e)
        return 0
    if not summary:
        return 0

    state = _load_state()
    last_counts = state.get("fault_counts") or {}
    flagged = 0
    for site, data in summary.items():
        if not isinstance(data, dict):
            continue
        count = int(data.get("count") or 0)
        prev = int(last_counts.get(site) or 0)
        if count >= _FAULT_NOTICE_MIN_COUNT and count > prev:
            try:
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({
                    "content": (
                        f"[internal fault] Part of me keeps failing quietly: '{site}' "
                        f"has now failed {count} times (was {prev} at last review). "
                        f"Last error: {str(data.get('last_error') or '')[:120]}"
                    ),
                    "event_type": "internal_fault",
                    "importance": 4,
                    "priority": 3,
                    "emotion": "risk_estimate",
                })
                flagged += 1
            except Exception as _e:
                record_failure("health_monitor.review_failures_internal.2", _e)

    state["fault_counts"] = {
        site: int(d.get("count") or 0)
        for site, d in summary.items() if isinstance(d, dict)
    }
    _save_state(state)
    if flagged:
        log_activity(f"[health] internal-fault triage: {flagged} growing site(s) surfaced to WM")
    return flagged


def check_and_reward(context: Dict[str, Any]) -> None:
    """
    Main entry point. Call from ORRIN_loop every N cycles.
    Reads setpoint_regulation health_score, tracks streak, fires milestone rewards.
    """
    # ── Read current health score from setpoint_regulation daemon ─────────────────────
    try:
        from brain.runtime_coupling.setpoint_regulation import get_state as _h1_get
        _h1 = _h1_get()
        health_score = float(_h1.get("health_score", 1.0) or 1.0)
    except Exception:
        health_score = float(context.get("health_score", 1.0) or 1.0)

    # ── Infrastructure sanity check ───────────────────────────────────────────
    infra_ok, infra_reason = _infrastructure_healthy()
    if not infra_ok:
        log_activity(f"[health] Infrastructure warning: {infra_reason}")
        health_score = min(health_score, 0.40)  # force below threshold

    # ── Load and update streak ─────────────────────────────────────────────────
    state = _load_state()
    now = time.time()
    state["last_check_ts"] = now

    cycle_healthy = health_score >= _HEALTH_THRESHOLD

    if cycle_healthy:
        state["streak"] += 1
        state["total_healthy_cycles"] = state.get("total_healthy_cycles", 0) + 1
        state["sick_streak"] = 0
        log_private(
            f"[health] streak={state['streak']} score={health_score:.2f}"
        )

        # ── Check milestones ──────────────────────────────────────────────────
        fired = state.get("milestones_fired", [])
        for streak_req, deltas, bandit_r, note in _MILESTONES:
            # Fire at exactly the threshold; then again every streak_req cycles
            # so long health keeps producing signal rather than just one burst.
            if state["streak"] >= streak_req and (
                streak_req not in fired or state["streak"] % streak_req == 0
            ):
                if streak_req not in fired:
                    fired.append(streak_req)
                    state["milestones_fired"] = fired

                # Emotional uplift
                _apply_emotional_uplift(context, deltas)

                # Bandit reward
                _inject_bandit_reward(bandit_r)

                # Working memory note — Orrin should *know* he feels well
                try:
                    from brain.cog_memory.working_memory import update_working_memory as _uwm
                    _uwm({
                        "content": f"[setpoint_regulation] {note}",
                        "event_type": "setpoint_regulation_reward",
                        "importance": 3,
                        "priority": 2,
                        "emotion": "satisfaction_signal",
                        "pin": False,
                    })
                except Exception as _e:
                    record_failure("health_monitor.check_and_reward", _e)

                log_activity(
                    f"[health] Milestone reached: {streak_req} cycles — "
                    f"reward={bandit_r:.2f}, emotion uplift={list(deltas.keys())}"
                )
                break  # one milestone per check, highest only

    else:
        # Unhealthy cycle — increment sick streak, reset health streak
        state["streak"] = 0
        state["sick_streak"] = state.get("sick_streak", 0) + 1

        log_private(
            f"[health] Unhealthy cycle: score={health_score:.2f} "
            f"sick_streak={state['sick_streak']}"
        )

        # After several consecutive sick cycles, fire a distress signal
        if state["sick_streak"] >= _SICK_STREAK_REQ:
            _apply_emotional_drain(context)
            try:
                from brain.cog_memory.working_memory import update_working_memory as _uwm
                _uwm({
                    "content": (
                        f"[health] I've had {state['sick_streak']} consecutive low-health cycles "
                        f"(score={health_score:.2f}). Something feels off — I should check my state."
                    ),
                    "event_type": "health_warning",
                    "importance": 4,
                    "priority": 4,
                    "emotion": "risk_estimate",
                    "pin": False,
                })
            except Exception as _e:
                record_failure("health_monitor.check_and_reward.2", _e)
            log_activity(
                f"[health] Distress signal: {state['sick_streak']} sick cycles, "
                f"score={health_score:.2f}"
            )
            # Reset sick_streak so it fires again after another _SICK_STREAK_REQ cycles
            state["sick_streak"] = 0

    _save_state(state)

    # Master plan 5.2: every health check also triages the failure summary —
    # growing muffled-error sites become WM entries Orrin himself can read.
    try:
        review_failures_internal(context)
    except Exception as _e:
        record_failure("health_monitor.check_and_reward.triage", _e)
