# A3 diagnostic — was the synthesis goal ever committed? (2026-07-04)

Per RUN4_FIX_PLAN §A3.1: replayed `goals_mem.json` from
`demo_runs/2026-07-03-run/data/` through the same tier-then-priority ranking
`_committable_from_v1_tree` applies (3-goal committed set).

## Answer: NO — it never made the committed 3.

The committed top-3 (tier-then-priority, reverse):

| rank | tier | priority | status | title |
|---|---|---|---|---|
| 0 | core | None | pending | Understand Be genuinely useful and connected… |
| 1 | core | None | pending | Understand Be genuinely useful and connected… |
| 2 | long_term (directional) | HIGH | in_progress | Be genuinely useful and connected to the people I talk to |

Both synthesis goals sit **below the cutoff**:

| rank | tier | priority | status | title |
|---|---|---|---|---|
| 4 | *(none)* | *(none)* | pending | Turn what I know about evolutionary biology into a written synthesis |
| 5 | *(none)* | *(none)* | pending | Turn what I know about the world into a written synthesis |

Total committable nodes: 8.

## Cause

The synthesis goals are minted by `intrinsic_generators._making_goals` with
**no `tier` and no `priority`** — so `_tier_weight` floors them to 1 and
`_priority_rank` to NORMAL(3), which loses to every core-tier goal. Combined
with the ignition monopoly (B1), the conscious lane that was supposed to pursue
them was also starved. Both halves of A3's fix apply:

1. give make-goals a **daemon-executable** `synthesize` lane so they don't
   depend on cracking the conscious committed set at all, and
2. stamp make-goals `priority: HIGH` at birth so if they *do* go through the v1
   committed path they rank against core goals instead of below them.
