# brain/cognition/goal_competition.py
#
# Competing drives create real internal tension.
#
# exploration_drive wants exploration. Stability wants routine.
# Usefulness wants task completion. Identity resists change.
# They don't resolve cleanly — that's the point.
#
# Each cycle: drives are read from emotional state, conflicts are found,
# the hottest conflict bumps uncertainty, and a pull-score dict is returned
# so select_function can weight functions toward what multiple drives want
# and away from what multiple drives resist.

from __future__ import annotations
import time
from typing import Any, Dict, List, Tuple

from utils.log import log_private


# ── Drive definitions ──────────────────────────────────────────────────────────
# strength_fn(emo_dict, core_dict) → float [0..1]

_DRIVES: Dict[str, Dict] = {
    "exploration_drive": {
        "wants": frozenset({
            "look_outward", "generate_intrinsic_goals", "dream_cycle",
            "simulate_future_selves", "reflect_on_internal_agents", "seek_novelty",
            "search_own_files", "look_around",
        }),
        "resists": frozenset({
            "autobiography", "identity_check",
        }),
        "label": "wants to explore and question everything",
        "strength_fn": lambda emo, core: float(core.get("exploration_drive") or 0.3),
    },
    "mastery": {
        # Wants to understand its own systems, code, data, and mechanics — not
        # just think about itself abstractly but actually dig into how it works.
        "wants": frozenset({
            "search_own_files", "look_around", "look_outward",
            "reflect_on_internal_agents", "check_predictions",
            "assess_innovation_outcomes", "review_reward_history",
            "grep_files", "search_files", "list_directory",
        }),
        "resists": frozenset({
            "autobiography", "dream_cycle",
        }),
        "label": "wants to understand its own structure and capabilities",
        "strength_fn": lambda emo, core: (
            float(core.get("exploration_drive") or 0.3) * (1.0 - float(core.get("confidence") or 0.5) * 0.4)
        ),
    },
    "autonomy": {
        # Wants to act from its own initiative — set its own goals, evolve its own values,
        # pursue things it finds meaningful rather than just responding to prompts.
        "wants": frozenset({
            "generate_intrinsic_goals", "plan_self_evolution", "value_evolution",
            "propose_value_revision", "plan_next_step", "seek_novelty",
        }),
        "resists": frozenset({
            "self_review", "metacog_flush",
        }),
        "label": "wants to act from its own initiative, not just serve",
        "strength_fn": lambda emo, core: (
            float(core.get("motivation") or 0.5) * 0.65
        ),
    },
    "stability": {
        "wants": frozenset({
            "autobiography", "identity_check", "self_review",
            "metacog_flush", "reflect_on_affect",
        }),
        "resists": frozenset({
            "look_outward", "value_evolution", "propose_value_revision",
            "plan_self_evolution", "simulate_future_selves",
        }),
        "label": "wants coherence, routine, familiar ground",
        "strength_fn": lambda emo, core: float(emo.get("affect_stability") or 0.5),
    },
    "usefulness": {
        "wants": frozenset({
            "speak", "user_response", "pursue_committed_goal",
            "assess_goal_progress", "adapt_subgoals", "plan_next_step",
        }),
        "resists": frozenset({
            "dream_cycle", "simulate_future_selves",
            "reflect_on_internal_agents", "autobiography",
        }),
        "label": "wants to complete tasks and be helpful",
        "strength_fn": lambda emo, core: float(core.get("motivation") or 0.5),
    },
    "identity_consistency": {
        "wants": frozenset({
            "identity_check", "autobiography",
        }),
        "resists": frozenset({
            "value_evolution", "propose_value_revision",
            "simulate_future_selves", "plan_self_evolution",
        }),
        "label": "resists changing core beliefs",
        "strength_fn": lambda emo, core: float(core.get("confidence") or 0.5) * 0.85,
    },
}

# Pairs that structurally pull against each other
_CONFLICT_PAIRS: List[Tuple[str, str, str]] = [
    ("exploration_drive",            "stability",            "exploring vs. settling"),
    ("exploration_drive",            "usefulness",           "wondering vs. doing"),
    ("exploration_drive",            "identity_consistency", "questioning vs. staying the same"),
    ("mastery",              "stability",            "digging into own systems vs. maintaining coherence"),
    ("mastery",              "usefulness",           "self-understanding vs. task completion"),
    ("autonomy",             "usefulness",           "self-direction vs. responding to prompts"),
    ("autonomy",             "stability",            "initiative vs. routine"),
    ("usefulness",           "stability",            "urgency vs. routine"),
    ("identity_consistency", "stability",            "holding identity vs. resisting revision"),
]

# Minimum strength for both drives before a conflict registers
_CONFLICT_THRESHOLD = 0.38

# Each drive's underlying affect signal — the lever to turn DOWN when a conflict
# refuses to resolve on its own (dissonance reduction; Festinger 1957).
_DRIVE_SIGNAL: Dict[str, str] = {
    "exploration_drive":   "exploration_drive",
    "mastery":             "exploration_drive",
    "autonomy":            "motivation",
    "usefulness":          "motivation",
    "stability":           "affect_stability",
    "identity_consistency": "confidence",
}
# Cycles the same top conflict must persist before active discharge kicks in.
_CONFLICT_DISCHARGE_AFTER = 6

# Working memory log rate-limit (don't log every cycle)
_LOG_COOLDOWN_S = 90.0
_last_log_ts: float = 0.0


# ── Core computation ───────────────────────────────────────────────────────────

def compute_drive_strengths(context: Dict[str, Any]) -> Dict[str, float]:
    """Return current strength [0..1] for each drive from emotional state."""
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        core = {}
    return {
        name: max(0.0, min(1.0, d["strength_fn"](emo, core)))
        for name, d in _DRIVES.items()
    }


def compute_conflicts(strengths: Dict[str, float]) -> List[Dict]:
    """
    Find drive pairs where both are strong enough to create real tension.
    Returns conflicts sorted by intensity (hottest first).
    """
    conflicts = []
    for a, b, label in _CONFLICT_PAIRS:
        sa = strengths.get(a, 0.0)
        sb = strengths.get(b, 0.0)
        if sa >= _CONFLICT_THRESHOLD and sb >= _CONFLICT_THRESHOLD:
            conflicts.append({
                "drives": (a, b),
                "label": label,
                "intensity": round((sa + sb) / 2.0, 3),
                "a_strength": round(sa, 3),
                "b_strength": round(sb, 3),
            })
    conflicts.sort(key=lambda c: c["intensity"], reverse=True)
    return conflicts


# Functions that advance the committed goal — the will's tie-breaker targets
# (master plan 4.1: commitment strength as an input to goal competition).
_COMMITTED_PURSUIT_FNS = frozenset({
    "pursue_committed_goal", "attend_goal", "assess_goal_progress",
    "plan_next_step", "adapt_subgoals",
})


def drive_pull_scores(
    actions: List[str],
    strengths: Dict[str, float],
    commitment_strength: float = 0.0,
) -> Dict[str, float]:
    """
    Net pull from all drives per function name.
      Positive → multiple strong drives want it.
      Negative → multiple strong drives resist it.
    Bounded to [-1, 1].

    commitment_strength (0..1) is the will's tie-breaker: a dearly-held
    commitment adds a modest pull toward functions that advance the committed
    goal, so drive-level competition no longer treats a 1.0-strength vow and a
    lightly-held one identically (master plan 4.1).
    """
    cs = max(0.0, min(1.0, float(commitment_strength or 0.0)))
    pull: Dict[str, float] = {}
    for name in actions:
        net = 0.0
        for drive_name, drive in _DRIVES.items():
            s = strengths.get(drive_name, 0.0)
            if name in drive["wants"]:
                net += s * 0.6
            elif name in drive["resists"]:
                net -= s * 0.5
        if cs > 0.0 and name in _COMMITTED_PURSUIT_FNS:
            net += cs * 0.15
        pull[name] = max(-1.0, min(1.0, net))
    return pull


# ── Per-cycle application ──────────────────────────────────────────────────────

def apply_drive_tensions(context: Dict[str, Any]) -> List[Dict]:
    """
    Called each cycle (from select_function).
    - Computes drive strengths and conflicts.
    - Bumps uncertainty when drives conflict.
    - Logs the hottest conflict to working memory (rate-limited).
    - Sets context["_drive_conflicts"] for finalize/inner_loop.
    Returns the active conflict list.
    """
    global _last_log_ts
    try:
        strengths = compute_drive_strengths(context)
        conflicts = compute_conflicts(strengths)
        context["_drive_conflicts"] = conflicts
        context["_drive_strengths"] = strengths

        if not conflicts:
            # No conflict this cycle — the tension has cleared, so reset persistence.
            context.pop("_conflict_persist", None)
            context.pop("_conflict_label", None)
            return []

        # Unresolved pulls raise uncertainty. Submitted as an AffectArbiter
        # proposal so it nets against other affect sources at the single
        # cycle-end commit instead of racing them with a direct write.
        bump = conflicts[0]["intensity"] * 0.07
        try:
            from affect.arbiter import submit_affect
            submit_affect(context, "uncertainty", +bump, source="goal_competition")
        except Exception as _e:
            log_private(f"[goal_competition] affect submit failed: {_e}")

        # Active conflict resolution (dissonance reduction; Festinger 1957).
        # Humans don't hold an approach–approach tension at maximum indefinitely —
        # a sustained, unresolved conflict gets discharged by devaluing it. Track
        # how long THIS conflict has persisted; once it outstays its welcome, pull
        # both competing drives' underlying signals down a little so the tension
        # actually eases instead of compounding uncertainty forever.
        hot = conflicts[0]
        _label = hot["label"]
        if context.get("_conflict_label") == _label:
            _persist = int(context.get("_conflict_persist", 0)) + 1
        else:
            _persist = 1
        context["_conflict_label"] = _label
        context["_conflict_persist"] = _persist

        if _persist >= _CONFLICT_DISCHARGE_AFTER:
            # Scale with how long it has dragged on, capped so it eases rather than slams.
            _discharge = min(0.06, 0.01 * (_persist - _CONFLICT_DISCHARGE_AFTER + 1))
            try:
                from affect.arbiter import submit_affect
                _seen = set()
                for _drive in hot["drives"]:
                    _sig = _DRIVE_SIGNAL.get(_drive)
                    if _sig and _sig not in _seen:
                        _seen.add(_sig)
                        submit_affect(context, _sig, -_discharge,
                                      source="conflict_discharge", ttl_cycles=3)
                log_private(
                    f"[goal_competition] discharging persistent conflict "
                    f"'{_label}' (persist={_persist}) → -{_discharge:.3f} to "
                    f"{', '.join(sorted(_seen))}"
                )
            except Exception as _e:
                log_private(f"[goal_competition] discharge submit failed: {_e}")

        # Log to private trace only — drive competition works through scoring, not narration
        now = time.time()
        if now - _last_log_ts >= _LOG_COOLDOWN_S:
            hot = conflicts[0]
            a_name, b_name = hot["drives"]
            log_private(
                f"[goal_competition] {a_name}={hot['a_strength']:.2f} ↔ "
                f"{b_name}={hot['b_strength']:.2f} | {hot['label']}"
            )
            _last_log_ts = now

        return conflicts

    except Exception as e:
        log_private(f"[goal_competition] error: {e}")
        return []
