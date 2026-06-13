"""
peers/peer_registry.py

Single entry point for waking peer entities.

Call wake_peers(context) once per cycle before process_inputs().
Returns a list of signal dicts that will be stored in
context["_peer_signals"] and picked up by gather_signals() so they
flow through the full signal_router pipeline.

Each peer is instantiated once (module-level) and consulted every
cycle.  The peers themselves decide whether to wake based on context
and cycle number.
"""
from __future__ import annotations

from typing import Any, Dict, List

from utils.log import log_activity, log_error
from utils.get_cycle_count import get_cycle_count

from peers.observer import Observer
from peers.reward_auditor import RewardAuditor
from peers.goal_auditor import GoalAuditor
from peers.emotion_historian import EmotionHistorian
from peers.architect import Architect


# Module-level instances — one each, stateless between wakes.
_PEERS = [
    Observer(),
    RewardAuditor(),
    GoalAuditor(),
    EmotionHistorian(),
    Architect(),
]


def wake_peers(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Consult all peers.  Any that decide to wake run their observe()
    and return signals.  Signals are returned as a flat list.

    After individual peers report, a synthesis pass checks for thematic
    corroboration across different peers — when two observers independently
    flag the same concern, that convergence is itself a signal.

    Never raises — peer failures are logged and ignored so a broken
    peer never crashes Orrin's cycle.
    """
    cycle = get_cycle_count()
    all_signals: List[Dict[str, Any]] = []

    for peer in _PEERS:
        try:
            if not peer.should_wake(context, cycle):
                continue
            signals = peer.wake(context, cycle=cycle)  # pass cycle for rate-limiting
            if signals:
                all_signals.extend(signals)
                log_activity(
                    f"[peer:{peer.name}] woke — {len(signals)} signal(s): "
                    + "; ".join(s.get("content", "")[:60] for s in signals[:2])
                )
        except Exception as e:
            log_error(f"[peer_registry] {peer.name} failed: {e}")

    # Synthesis pass: look for the same theme flagged by 2+ different peers
    syntheses = _synthesize_peer_signals(all_signals)
    if syntheses:
        all_signals.extend(syntheses)
        for s in syntheses:
            log_activity(f"[peer_synthesis] {s.get('content', '')[:80]}")

    return all_signals


_SYNTHESIS_SKIP_TAGS = frozenset({"peer", "internal", "peer_synthesis"})


def _synthesize_peer_signals(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    When 2+ different peers independently flag the same thematic tag,
    emit a single corroboration signal at elevated strength.
    """
    if len(signals) < 2:
        return []

    # Map theme_tag → {peer_name → [signals]}
    # Use source field as authoritative peer identity (always "peer_<name>", strip prefix)
    theme_peers: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for sig in signals:
        tags = sig.get("tags") or []
        source = sig.get("source", "unknown")
        peer_name = source.removeprefix("peer_") if source.startswith("peer_") else source
        for tag in tags:
            if tag in _SYNTHESIS_SKIP_TAGS:
                continue
            # Skip the peer-name tag itself — it's identity, not theme
            if tag == peer_name:
                continue
            theme_peers.setdefault(tag, {}).setdefault(peer_name, []).append(sig)

    syntheses: List[Dict[str, Any]] = []
    seen_pairs: set = set()

    for tag, peer_map in theme_peers.items():
        if len(peer_map) < 2:
            continue
        peer_names = tuple(sorted(peer_map.keys()))
        pair_key = (tag, peer_names)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        flat = [s for sigs in peer_map.values() for s in sigs]
        max_strength = max(float(s.get("signal_strength", 0.5)) for s in flat)
        snippets = [s.get("content", "")[:70] for s in flat[:2]]

        syntheses.append({
            "source":         "peer_synthesis",
            "content":        (
                f"[Peer synthesis] {len(peer_map)} observers independently flagging '{tag}': "
                + " | ".join(snippets)
            ),
            "signal_strength": round(min(0.90, max_strength * 1.15), 3),
            "tags":           ["peer", "peer_synthesis", tag, "internal"],
        })

    return syntheses
