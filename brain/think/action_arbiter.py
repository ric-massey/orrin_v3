# brain/think/action_arbiter.py
#
# ActionArbiter — the convergence point for "what should run this cycle?".
#
# THE PROBLEM IT SOLVES
# The instinctual lane (threat_detector's fight/flight/freeze shortcut) used to
# *overwrite* the analytical lane's choice with a hard `if spike > 0.65: chosen =
# reflex`. That is a step function: at spike 0.64 the planned goal wins outright,
# at 0.66 the reflex wins outright, and as the threat scalar hovers near the
# threshold the winner flip-flops cycle to cycle. That oscillation is the
# behavioural half of the "split brain".
#
# THE V2 MODEL: weighted vote + commitment, not override
#   - Every lane submits an ActionProposal (a vote, a weight, an urgency), instead
#     of writing the decision directly.
#   - resolve() sums weighted votes per candidate and returns one winner. A strong
#     planned goal and a moderate threat now *combine* and degrade gracefully in
#     the ambiguous middle band, instead of one erasing the other.
#   - Hysteresis: the incumbent (last cycle's choice) is only displaced if a
#     challenger beats it by `margin`. This is the commitment that kills the
#     flip-flop — the agent stops changing its mind every 20 seconds.
#   - veto: the single hard-override path, reserved for genuine safety/boundary
#     stops. Replaces "the reflex always wins" with "the reflex votes very
#     strongly; only safety can veto".
#
# An acute threat still dominates (high spike -> high weight*vote), so reflexive
# behaviour is preserved exactly where it matters.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# How much an incumbent challenger must win by to displace the incumbent.
DEFAULT_MARGIN = 0.10

# Urgency contributes to a candidate's score at this rate.
_URGENCY_WEIGHT = 0.5


@dataclass
class ActionProposal:
    """One lane's bid for what should run this cycle."""
    name: str                 # cognitive-function name or action type
    vote: float               # desirability, nominally 0..1
    weight: float = 1.0       # lane authority (reflex lanes use weight > 1)
    urgency: float = 0.0      # time-criticality, nominally 0..1
    veto: bool = False        # hard safety stop (boundary/safety lane only)
    source: str = ""          # lane identifier, for telemetry


def resolve(
    proposals: List[ActionProposal],
    *,
    incumbent: Optional[str] = None,
    margin: float = DEFAULT_MARGIN,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Integrate proposals into a single winner + an info dict for telemetry.

    Returns (winner_name_or_None, info).
    """
    proposals = [p for p in proposals if p is not None and getattr(p, "name", None)]
    if not proposals:
        return None, {"reason": "no_proposals"}

    # ── veto lane: a hard safety stop wins outright (highest-weight veto) ──────
    vetoes = [p for p in proposals if p.veto]
    if vetoes:
        win = max(vetoes, key=lambda p: p.weight)
        return win.name, {"reason": "veto", "winner": win.name, "source": win.source}

    # ── weighted vote ─────────────────────────────────────────────────────────
    agg: Dict[str, float] = {}
    sources: Dict[str, List[str]] = {}
    for p in proposals:
        score = max(0.0, float(p.vote)) * max(0.0, float(p.weight)) \
            + max(0.0, float(p.urgency)) * _URGENCY_WEIGHT
        agg[p.name] = agg.get(p.name, 0.0) + score
        sources.setdefault(p.name, []).append(p.source)

    ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    winner, top = ranked[0]

    # ── commitment / hysteresis: keep the incumbent unless beaten by `margin` ──
    hysteresis = False
    if incumbent and incumbent in agg and winner != incumbent:
        if (top - agg[incumbent]) < margin:
            winner = incumbent
            hysteresis = True

    return winner, {
        "reason": "vote",
        "winner": winner,
        "ranked": [(n, round(s, 4)) for n, s in ranked[:6]],
        "hysteresis": hysteresis,
        "incumbent": incumbent,
        "margin": margin,
        "sources": {n: sources.get(n, []) for n, _ in ranked[:6]},
    }
