# brain/affect/arbiter.py
#
# AffectArbiter — the single convergence point for affect changes.
#
# THE PROBLEM IT SOLVES
# Previously, many subsystems wrote to context["affect_state"] directly, in
# whatever order they happened to run that cycle. Instinctual systems (threat,
# drives, reward impulses) and analytical systems (goal stall, drive competition,
# body sense) raced on the same dict; the last writer in the cycle won and earlier
# updates were silently clobbered. This is the affect half of the "split brain".
#
# THE V2 MODEL: propose -> integrate -> commit once
#   1. During the cycle, every subsystem calls submit_affect(...) instead of
#      mutating affect_state. Nothing is applied yet, so there is no ordering
#      race and nobody reads half-applied state.
#   2. At cycle end, commit_affect(...) integrates ALL proposals at once:
#        - contradictory pushes on the same signal net out (weighted sum),
#        - a homeostatic stability budget caps the total change a single cycle
#          can make, so one chaotic cycle can't fragment the whole state,
#        - deltas that push a signal AWAY from its setpoint cost double against
#          the budget, so the system resists being driven far from equilibrium.
#   3. The integrated deltas are queued into the existing affect_buffer, so they
#      drain gradually over the next few cycles through update_affect_state's
#      normal velocity / clamp / ceiling / baseline-decay machinery.
#
# This generalises affect_buffer.py (previously used only by reward signals) to
# ALL affect writers, and adds the homeostatic budgeting that makes the model a
# stability model rather than an override model.
#
# Cannon (1932) homeostasis; Russell & Barrett (1999) core affect.

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from affect.affect_buffer import queue_affect_change
from affect.setpoints import setpoint
from config.tuning import AFFECT_AWAY_COST_MULTIPLIER, AFFECT_STABILITY_BUDGET
from utils.log import log_activity

# Per-cycle ceiling on the total (homeostasis-weighted) magnitude of affect change.
# If the integrated proposals exceed this, every delta is scaled down
# proportionally. Tuned so a normal cycle (a handful of small nudges) passes
# untouched, but a cycle where many subsystems fire at once cannot lurch the
# whole affect vector. (Finding 9: value lives in config.tuning.)
STABILITY_BUDGET = AFFECT_STABILITY_BUDGET

# Proposals away from setpoint are this much more "expensive" against the budget.
_AWAY_COST_MULTIPLIER = AFFECT_AWAY_COST_MULTIPLIER

_PROP_KEY = "_affect_proposals"

# Top-level scalar fields that are NOT core_signals but may still be proposed
# against (e.g. resource_deficit). These are applied directly to the affect_state
# dict at commit time rather than drained gradually through the core buffer.
# affect_stability is here because regulation strategies carry stability
# side-effects; without it those proposals drained into the core buffer where
# the signal doesn't live and were dropped as "unknown emotion" every cycle
# (RUN_ISSUES_2026-06-10 §2 — regulation of stability was silently broken).
_SCALAR_TARGETS = frozenset({"resource_deficit", "affect_stability"})

# ── I16: per-lane affect sub-budgets ────────────────────────────────────────
# The three dual-process roles emit affect every cycle. Without sub-caps the
# always-on Monitor + Executive could collectively peg the velocity budget and
# wash out the focal (Deliberate) resolution. Each BACKGROUND lane gets a ceiling
# (a fraction of STABILITY_BUDGET); the Deliberate lane — the conscious focal mind —
# is bounded only by the global budget. Still integrated once by commit_affect.
_LANE_SUBCAP = {"monitor": 0.20, "executive": 0.20}   # × STABILITY_BUDGET; deliberate uncapped


def _lane_of(source: str) -> str:
    s = (source or "").lower()
    if s.startswith("monitor"):
        return "monitor"
    if "exec" in s or s.startswith("dream") or "daemon" in s:
        return "executive"
    return "deliberate"


def _apply_lane_subcaps(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scale down a background lane's proposals if its raw assertion magnitude
    (Σ|delta×weight|) exceeds that lane's sub-budget — so no single background role
    floods the velocity budget (I16). Pure pre-integration shaping; the global
    STABILITY_BUDGET still applies afterward. Returns a (possibly new) proposal list."""
    raw: Dict[str, float] = {}
    for p in proposals:
        if not isinstance(p, dict):
            continue
        lane = _lane_of(p.get("source", ""))
        raw[lane] = raw.get(lane, 0.0) + abs(float(p.get("delta") or 0.0) * float(p.get("weight") or 0.0))
    lane_scale: Dict[str, float] = {}
    for lane, frac in _LANE_SUBCAP.items():
        cap = frac * STABILITY_BUDGET
        if cap > 0 and raw.get(lane, 0.0) > cap:
            lane_scale[lane] = cap / raw[lane]
    if not lane_scale:
        return proposals
    out: List[Dict[str, Any]] = []
    for p in proposals:
        if isinstance(p, dict):
            sc = lane_scale.get(_lane_of(p.get("source", "")))
            if sc is not None:
                p = {**p, "weight": float(p.get("weight") or 0.0) * sc}
        out.append(p)
    try:
        log_activity("[affect_arbiter] lane sub-cap: " +
                     ", ".join(f"{l}×{s:.2f}" for l, s in lane_scale.items()))
    except Exception:
        pass
    return out

# ── Thread-safe daemon inbox ──────────────────────────────────────────────────
# Daemons (dream, tool_runner, tamper_guard) run on separate threads and must NOT
# touch affect_state on disk or mutate the shared context dict's proposal list
# without coordination. Instead they submit proposals here, into a lock-guarded
# module-level inbox, which the main loop drains during commit_affect(). This is
# the single mechanism that replaces every daemon's load->mutate->save_json race.
_inbox_lock = threading.Lock()
_inbox: List[Dict[str, Any]] = []


def _make_proposal(target: str, delta: float, weight: float, source: str, ttl_cycles: int) -> Dict[str, Any]:
    return {
        "target": str(target),
        "delta": delta,
        "weight": weight,
        "source": str(source)[:48],
        "ttl": max(2, int(ttl_cycles)),
    }


def submit_affect(
    context: Optional[Dict[str, Any]],
    target: str,
    delta: float,
    *,
    weight: float = 1.0,
    source: str = "",
    ttl_cycles: int = 3,
) -> None:
    """
    Propose a change to an affect signal. Accumulated, not applied — commit_affect()
    integrates all proposals at cycle end.

    target:     core-signal name, e.g. "impasse_signal", "motivation"; or a
                top-level scalar in _SCALAR_TARGETS (e.g. "resource_deficit").
    delta:      signed change requested by this source.
    weight:     how strongly this source asserts the change (0..1+). Reflex-grade
                sources may use weight > 1 to assert priority; the weighted sum
                means a strong source dominates without erasing weaker ones.
    ttl_cycles: how many cycles the change drains over (gradual, human-like).

    Threading: pass a live `context` dict from the main cognitive loop. Daemons on
    other threads MUST pass context=None — the proposal is then queued onto the
    thread-safe module inbox and drained by the main loop's commit_affect(). This
    is what keeps daemons off the affect file entirely.
    """
    try:
        delta = float(delta)
        weight = float(weight)
    except (TypeError, ValueError):
        return
    if abs(delta) < 1e-6 or weight <= 0.0:
        return

    prop = _make_proposal(target, delta, weight, source, ttl_cycles)

    if isinstance(context, dict):
        context.setdefault(_PROP_KEY, []).append(prop)
        return

    # Daemon / context-less path → thread-safe inbox.
    with _inbox_lock:
        # Cap the inbox so a stuck daemon can't grow it without bound.
        if len(_inbox) < 512:
            _inbox.append(prop)


def _drain_inbox() -> List[Dict[str, Any]]:
    """Atomically take and clear the daemon inbox. Main-loop only."""
    with _inbox_lock:
        if not _inbox:
            return []
        drained = list(_inbox)
        _inbox.clear()
        return drained


def _integrate(proposals: List[Dict[str, Any]]):
    """Weighted-sum proposals per target. Returns (net_deltas, ttls)."""
    nets: Dict[str, float] = {}
    ttls: Dict[str, int] = {}
    for p in proposals:
        if not isinstance(p, dict):
            continue
        t = p.get("target")
        if not t:
            continue
        nets[t] = nets.get(t, 0.0) + float(p.get("delta") or 0.0) * float(p.get("weight") or 0.0)
        ttls[t] = max(ttls.get(t, 2), int(p.get("ttl") or 3))
    return nets, ttls


def commit_affect(context: Dict[str, Any]) -> Dict[str, float]:
    """
    Integrate all submitted affect proposals into a single bounded delta vector and
    queue it into the affect_buffer for gradual application. Returns the applied
    per-target deltas (also stored on context["_affect_committed"] for telemetry).

    Safe to call every cycle; a no-op when there are no proposals.
    """
    # Combine this cycle's in-context proposals with anything daemons queued onto
    # the thread-safe inbox since the last commit.
    proposals = list(context.get(_PROP_KEY) or [])
    proposals.extend(_drain_inbox())
    if not proposals:
        return {}

    state = context.get("affect_state")
    if not isinstance(state, dict):
        # Nothing to attach the buffer to — drop proposals rather than crash.
        context[_PROP_KEY] = []
        return {}

    core = state.get("core_signals")
    if not isinstance(core, dict):
        core = state  # flat layout

    # I16 — bound each background lane before integration (Monitor/Executive can't
    # collectively wash out the focal Deliberate resolution).
    proposals = _apply_lane_subcaps(proposals)
    nets, ttls = _integrate(proposals)

    def _current(target: str) -> float:
        """Current value of a target — core signal, top-level scalar, or setpoint."""
        if target in core:
            src = core
        elif target in state:
            src = state
        else:
            return setpoint(target)
        try:
            return float(src.get(target))
        except (TypeError, ValueError):
            return setpoint(target)

    # Homeostasis-weighted cost: pushing a signal away from its setpoint costs more.
    weighted_cost: Dict[str, float] = {}
    away_targets: set = set()
    for t, net in nets.items():
        cur = _current(t)
        sp = setpoint(t)
        moving_away = (net > 0 and cur >= sp) or (net < 0 and cur <= sp)
        if moving_away:
            away_targets.add(t)
        weighted_cost[t] = abs(net) * (_AWAY_COST_MULTIPLIER if moving_away else 1.0)

    # Two-tier budgeting. The old single proportional scale throttled
    # toward-setpoint (regulatory) deltas by the same factor as the excitation
    # that blew the budget — so in chronically over-budget runs, decay back to
    # baseline could never outpace re-assertion and signals like impasse_signal
    # stayed pinned near max for days. Now: toward-setpoint deltas are funded
    # first; away-from-setpoint deltas split whatever budget remains.
    total_cost  = sum(weighted_cost.values())
    toward_cost = sum(c for t, c in weighted_cost.items() if t not in away_targets)
    away_cost   = total_cost - toward_cost
    scale_toward = scale_away = 1.0
    if total_cost > STABILITY_BUDGET:
        if toward_cost <= STABILITY_BUDGET:
            scale_away = (STABILITY_BUDGET - toward_cost) / away_cost if away_cost > 0 else 1.0
        else:
            # Even pure regulation exceeds the budget — scale everything.
            scale_toward = scale_away = STABILITY_BUDGET / total_cost
        log_activity(
            f"[affect_arbiter] stability budget exceeded "
            f"(cost={total_cost:.2f} > {STABILITY_BUDGET}); toward×{scale_toward:.2f}, "
            f"away×{scale_away:.2f} across {len(nets)} signal(s)"
        )

    applied: Dict[str, float] = {}
    for t, net in nets.items():
        d = net * (scale_away if t in away_targets else scale_toward)
        if abs(d) < 1e-4:
            continue
        if t in _SCALAR_TARGETS:
            # Top-level scalar (e.g. resource_deficit): apply directly, clamped.
            # Not drained through the core buffer — these are not core_signals.
            new_val = max(0.0, min(1.0, _current(t) + d))
            state[t] = round(new_val, 4)
        else:
            queue_affect_change(state, t, d, ttl_cycles=ttls.get(t, 3), source="arbiter")
        applied[t] = round(d, 4)

    context[_PROP_KEY] = []
    context["_affect_committed"] = applied
    return applied
