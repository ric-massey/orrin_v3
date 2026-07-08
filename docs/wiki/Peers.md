# Peers (Outside Observers)

Peers are entities that watch Orrin's state **from the outside** and, when their wake conditions
fire, push *signals* into the next cycle. They are advisory by construction: a peer can make the
workspace competition care about something, but it cannot issue a command or mutate state directly.

## The five peers

| Peer | Watches for |
|------|-------------|
| **Architect** | Self-modifications — reviews proposed code before it lands |
| **Signal Historian** | Chronic control-signal patterns (stuck pressure) |
| **Goal Auditor** | Low-quality or unmeasurable goals |
| **Observer** | Unproductive loops and repetitive behavior |
| **Reward Auditor** | A bandit reward signal that has collapsed to noise |

## How they integrate

Peers register themselves in the world model / relationships on first wake (so Orrin's self-model
knows they exist) and flow through the same `signal_router` as every other signal. They nudge
attention without ever commanding action — the same "propose, don't race" discipline as the rest of
the architecture.

For the implementation and how to write your own, see the
[Peers Subsystem](Peers_Subsystem) deep dive and [Adding a Custom Peer](Adding_Custom_Peer).

## Code pointers

- `brain/peers/` — the peers and registry
- `brain/think/signal_router.py` — where peer signals join everything else
