# Peers Subsystem

`brain/peers/` implements the outside observers described in [Peers](Peers): entities that read
Orrin's state from the outside and, when their wake conditions fire, push **signals** into the next
cycle rather than mutating state directly. They flow through the same `signal_router`
(`brain/think/signal_router.py`) as every other signal, so they nudge attention without ever
issuing commands.

## The five peers

| Peer | File | Watches for |
|------|------|-------------|
| Architect | `architect.py` | Self-modifications — reviews proposed code before it lands |
| Signal Historian | `signal_historian.py` | Chronic control-signal patterns (stuck pressure) |
| Goal Auditor | `goal_auditor.py` | Low-quality or unmeasurable goals |
| Observer | `observer.py` | Unproductive loops and repetitive behavior |
| Reward Auditor | `reward_auditor.py` | A bandit reward signal that has collapsed to noise |

## Mechanics

- `peer_base.py` — the base class: a wake condition (cheap, evaluated against current state) plus a
  proposal generator that emits signals when awake.
- `peer_registry.py` — registration and scheduling; peers register themselves in the world model /
  relationships on first wake, so Orrin's self-model knows they exist.
- Peers are deliberately **advisory**: their output is salience, not control. A peer can make the
  workspace competition care about something; it cannot force an action.

## Writing a custom peer

Inherit from the base class in `peer_base.py`, implement the wake condition and proposal
generation, and register it in `peer_registry.py`. Keep wake conditions cheap (they run often) and
emit signals, not state mutations. Walkthrough: [Adding a Custom Peer](Adding_Custom_Peer).

## Code pointers

- `brain/peers/` — all of the above
- `brain/think/signal_router.py` — where peer signals join everything else
