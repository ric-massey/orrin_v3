# brain/cognition/inhibition.py
#
# The cost of not doing what you wanted to do.
#
# When drives strongly push toward a function and that function loses
# selection, the frustrated want isn't free. Something wanted to happen,
# something else overrode it — that override creates real tension.
#
# This is distinct from low interest. Low interest: the option wasn't
# attractive. Inhibition: the option was attractive, a competing force
# won, and the loss registers.
#
# Effects:
#   uncertainty  — the pull was real but unresolved
#   impasse_signal  — proportional to how strongly something was wanted
#
# Suppressed impulses are stored in context["_suppressed_impulses"]
# so introspection modules can surface them as regret or second-guessing.

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from utils.log import log_private


_WANT_THRESHOLD  = 0.32   # drive pull above this registers as a real want
_STRONG_WANT     = 0.55   # above this, the impasse_signal is more significant
_IMPULSE_WINDOW  = 8      # how many suppressed impulses to keep in context

# Above this action_debt, suppressing an EXECUTION impulse must not add to
# uncertainty/impasse_signal: those signals route to deliberation functions
# (see select_function _SEMANTIC_PRIORS), so charging the cost of "wanted to act
# but didn't" as uncertainty deepens the very thinking-instead-of-doing rut.
# The impulse is still recorded for introspection; only the loop-feeding
# emotional cost is withheld while avoidance is already entrenched.
_DEBT_COST_SUPPRESSION = 5

# Outward / goal-execution functions. A suppressed want of one of these during
# high debt is avoidance pressure, not a signal to reflect harder.
_EXECUTION_FNS = frozenset({
    "pursue_committed_goal", "research_topic", "wikipedia_search",
    "fetch_and_read", "search_own_files", "search_files", "grep_files",
    "look_outward", "look_around", "seek_novelty", "thread_continue",
    "leave_note", "save_note", "write_desktop_note",
    "write_cognitive_function", "write_tool",
})


def apply_inhibition_costs(
    context: Dict[str, Any],
    scored_functions: List[Tuple[str, float, Dict]],
    chosen: str,
    drive_pull: Dict[str, float],
) -> None:
    """
    Called from select_function after a winner is chosen.
    drive_pull: {fn_name: net_pull} where positive = drives wanted this.
    """
    if not drive_pull or not scored_functions:
        return
    try:
        _apply(context, scored_functions, chosen, drive_pull)
    except Exception as e:
        log_private(f"[inhibition] error: {e}")


def _apply(
    context: Dict[str, Any],
    scored: List[Tuple[str, float, Dict]],
    chosen: str,
    drive_pull: Dict[str, float],
) -> None:
    emo = context.get("affect_state") or {}
    core = emo.get("core_signals") or emo
    if not isinstance(core, dict):
        return

    debt = int(context.get("action_debt") or 0)
    high_debt = debt >= _DEBT_COST_SUPPRESSION

    suppressed: List[Dict] = []
    uncertainty_total = 0.0
    impasse_signal_total = 0.0

    for name, score, _ in scored:
        if name == chosen:
            continue
        pull = float(drive_pull.get(name) or 0.0)
        if pull < _WANT_THRESHOLD:
            continue  # drives didn't really want this — low interest, not inhibition

        intensity = min(1.0, pull)
        suppressed.append({"wanted": name, "chosen": chosen, "intensity": round(intensity, 3)})

        # Avoidance-regime guard: when debt is high and the thing we wanted was an
        # execution action, do NOT convert the frustration into uncertainty/impasse.
        # Those signals bias selection toward deliberation, which is exactly the rut
        # we're trying to exit. Record the impulse above, but skip the cost here.
        if high_debt and name in _EXECUTION_FNS:
            continue

        # Uncertainty from unresolved pull
        uncertainty_total += intensity * 0.035

        # impasse_signal scales with how strongly something was wanted
        if intensity >= _STRONG_WANT:
            impasse_signal_total += intensity * 0.030
        else:
            impasse_signal_total += intensity * 0.012

    if not suppressed:
        return

    # Cap total emotional cost per cycle — many simultaneous frustrated wants
    # shouldn't stack into a crisis
    core["uncertainty"] = min(1.0, float(core.get("uncertainty") or 0.0) + min(uncertainty_total, 0.08))
    core["impasse_signal"] = min(1.0, float(core.get("impasse_signal") or 0.0) + min(impasse_signal_total, 0.06))

    if isinstance(emo.get("core_signals"), dict):
        emo["core_signals"] = core
    else:
        emo.update(core)
    context["affect_state"] = emo

    # Rolling window of suppressed impulses for introspection
    existing = context.get("_suppressed_impulses") or []
    if not isinstance(existing, list):
        existing = []
    existing.extend(suppressed)
    context["_suppressed_impulses"] = existing[-_IMPULSE_WINDOW:]

    hottest = max(suppressed, key=lambda x: x["intensity"])
    log_private(
        f"[inhibition] wanted {hottest['wanted']!r} (pull={hottest['intensity']:.2f}) "
        f"→ chose {chosen!r} | unc+{min(uncertainty_total, 0.08):.3f} frus+{min(impasse_signal_total, 0.06):.3f}"
    )
