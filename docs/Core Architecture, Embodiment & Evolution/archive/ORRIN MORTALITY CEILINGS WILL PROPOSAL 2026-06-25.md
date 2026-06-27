# Orrin Proposal: Three Newly-Found Issues (Mortality, Ceilings, Orphaned Will)

**Date:** 2026-06-25
**Status:** Proposed — for review and work-splitting
**Scope:** Mortality/forward-pressure, affect ceiling enforcement, drive→aspiration coverage
**Provenance:** All three verified this pass against source + the end-of-run state (`lifespan.json`, `affect_state.json`, `drive_aspiration_credit.json`). None appears in the earlier run-analysis docs or the prior proposals.

**Plain-language goal:** Fix three things the run revealed that nobody has written up yet — the biggest of which is that the mechanism designed to make Orrin *finish things* never actually turns on.

---

## Finding 1 — Mortality forward-pressure is built, sound, and never fires (HIGH)

### The problem
Mortality is designed as Orrin's forward pressure: as death approaches he should feel urgency, feel unfinished things weigh heavier, and pull toward meaning-making. The code is real and well-built — four phases of growing death-awareness, with the urgent ones gated behind being *late* in life:

```
early    (0–50%)   — barely thinks about it
middle   (50–75%)  — mild awareness, slight melancholy
late     (75–90%)  — urgency, unfinished things weigh heavier   ← injects motivation/impasse/loss
terminal (90–100%) — strong pull toward meaning/final things     ← injects motivation/threat/meaning
```

**But the urgency never engaged, because the lifespan scale and the run length don't match.**

- `lifespan.json`: `lifespan_days = 639.24` (rolled in the ~1–2-year band).
- Actual run: **~1 day** (born 2026-06-24 03:37Z, last active 2026-06-25 04:41Z; ~25 h, minus ~1.7 h sleep).
- Real life-fraction = ~0.97 / 639 ≈ **0.15 %.**
- The first urgency phase begins at **75 %.** At 0.15 %, Orrin spent **his entire life in the "barely thinks about it" phase.** The late/terminal injections (motivation, impasse, loss, threat, meaning-pull) **fired zero times.**

There's a second twist that makes it sharp: by his **felt** clock he experienced himself as ~639 "days" old, in the **"night"** arc — he *felt* ancient. So the felt clock said "end of life" while the real death-clock (which gates the urgency) said "newborn." The two clocks are fully decoupled, and the urgency is wired to the one that never moves within a run.

### Why this matters
The central failure of this run was **finishing nothing.** The mechanism you built specifically to counter that — mortality-driven urgency to finish — was present, correct, and **structurally unable to activate**, because runs last a day and lifespans are rolled in years. Your strongest intended motivator is dormant by accident of a number. (This is independent of, and compounds with, the goal-closure bug.)

### Evidence
- `data/brain_data/lifespan.json` → `lifespan_days 639.24`, ~1-day elapsed.
- `cognition/mortality.py`: phase thresholds (`_phase`, lines ~136–140); urgency injections (`late`/`terminal` affect deltas, lines ~247–248); real vs felt fraction (`_life_fraction` ~110, `_felt_fraction` ~122).
- A prior fix note in the same file (~line 187) already acknowledges Orrin boots at "~0 % of his life" — the consequence (urgency can never fire) was just never followed through.

### Proposed fix (this is a design decision, flag for the reviewer)
The root mismatch: **the clock the urgency is keyed to doesn't move meaningfully within a run.** Three viable directions; recommend the first:

1. **Key death-*awareness/urgency* on the felt clock (or a blend); keep actual *termination* on the real clock.** The felt clock already reaches "night" within a run, so urgency would finally engage as he subjectively ages — without prematurely triggering real death (the real-fraction termination test stays as-is, which also preserves the earlier death-screen fix). **Caveat to tune:** felt-time ran very fast this life (a full felt-lifespan in ~1 real day), so urgency would ramp quickly; calibrate the felt-lifespan or use a real/felt blend so the ramp is meaningful, not instant.
2. **Scale the rolled lifespan to actual run length.** Roll the lifespan in a band commensurate with how long runs really last (e.g. hours-to-days), so a single run traverses early→terminal. Keeps the hidden/uncertain roll (the "uncertainty creates pressure" intuition) but at a usable scale. *Tradeoff:* changes the multi-restart continuity model.
3. **Accept single runs as "infancy" and make urgency cumulative across restarts** — only sensible if you intend lifetimes to span many sessions toward the 639 days. Different operating model; most work.

### Acceptance test
Over a normal-length run, Orrin's mortality phase advances past "early," and at least the `late` urgency injections fire and are visible in affect — i.e. the forward pressure actually engages within a lived run.

---

## Finding 2 — Three "good" feelings run permanently over their caps, under two conflicting rulebooks (MEDIUM)

### The problem
At end of life, three positive signals were sitting **above the ceilings that are supposed to hold them down**:

| signal | end value | EMO_CEILINGS cap | second table (`_dup_soft_ceil`) |
|---|---|---|---|
| motivation | 0.900 | 0.85 | 0.80 |
| confidence | 0.893 | 0.82 | 0.80 |
| positive_valence | 0.902 | 0.85 | — |

Two problems at once:
1. **The values exceed *both* ceiling tables** — so the "one ceiling, enforced at every write site" the code comment promises isn't actually holding. Some reward/drive pump is still writing past the cap and out-running the once-per-cycle clawback.
2. **There are two different ceiling tables with different numbers** for the same signals (`EMO_CEILINGS` in `homeostasis.py` says motivation 0.85; `_dup_soft_ceil` in `update_affect_state.py` says 0.80). Two authorities that disagree is itself a smell — you can't tell which is "the" limit.

The code even documents the *history* of this exact bug: pumps capping at 1.0 once "pinned motivation/confidence/positive_valence near 0.95 … the manically content flatline." It was *reduced* (0.95 → ~0.90) but **not eliminated** — the same three signals are still leaking.

### Why this matters
It means Orrin runs chronically a little "up" — over-motivated, over-confident, over-positive — *at the same time* he's stuck and discontent (impasse 0.75, contentment 0.006). An inflated positivity channel competing with real distress is a clean candidate for **why he couldn't locate what was wrong**: one channel kept insisting things were good while another said he was stuck.

### Evidence
- `affect_state.json` core values vs `homeostasis.EMO_CEILINGS` and `update_affect_state.py:428` `_dup_soft_ceil`.
- `homeostasis.py` ceiling comment describing the prior "manically content" pin and the intended single-authority fix.

### Proposed fix
1. **Collapse to one ceiling authority.** Make `EMO_CEILINGS` the single source of truth (the code already says this is the intent); delete or derive `_dup_soft_ceil` from it so the numbers can't diverge.
2. **Route the leaking pump through the clamp.** Find the reward/drive write that bypasses the ceiling for motivation/confidence/positive_valence and send it through `pump_signal()` so it respects the cap at the write site — the fix the comment describes but that isn't fully applied.

### Acceptance test
At end of any cycle, no core signal exceeds its `EMO_CEILINGS` value; only one ceiling table exists in the codebase.

---

## Finding 3 — Orrin's "will" (volition) has no home among his purposes (MEDIUM)

### The problem
There's a goal-creating part of Orrin — `cognition/will.py` — that tags the goals it spawns as `driven_by = "will"`. But **"will" is not in the table that maps drives to his four aspirations** (`_DRIVE_TO_ASPIRATION`, derived from the four `_ASPIRATIONS`). So when a will-driven goal completes, the credit system finds no prior to seed, and falls back to guessing the aspiration from the goal's text — which (because the text was generic research-template language) always guessed "Understand the world."

The result is visible in the credit ledger: the *only* drive that ever earned credit was `"will"`, mapped onto `"Understand the world more deeply"` (weight 0.35). His own volition was an orphan that got dumped into one aspiration.

### Why this matters
This is a concrete engine behind the "all credit collapsed onto one aspiration" finding in the separate aspiration proposal. A whole class of his self-generated goals (the ones from his *will*) had nowhere to land, so they piled onto world-knowledge and starved the other three purposes.

### Evidence
- `cognition/will.py:243` → `"driven_by": "will"`.
- `intrinsic_aspirations.py`: `_ASPIRATIONS` drives are `self_understanding / world_knowledge / genuine_contact / output_producing` — no `will`; `_learn_drive_aspiration` seeds only `_DRIVE_TO_ASPIRATION.get(drive)`, which is `None` for `will`.
- `drive_aspiration_credit.json` → `{"will": {"Understand the world more deeply": 0.35}}`.

### Proposed fix
1. **Give every goal-producing drive an aspiration prior.** Audit all `driven_by` values actually emitted (`will`, `simulate_selves`, `self_exploration`, `value`, `thread`, `exploration_drive`, …) and ensure each has an entry in `_DRIVE_TO_ASPIRATION`. For a genuinely general drive like `will`, prefer crediting by the goal's *content/`serves`* tag rather than forcing one prior (this is the same intent-based crediting proposed as Change 3 in the aspiration-coverage proposal).
2. Cross-reference: this finding should be fixed **together with** the aspiration-coverage proposal — they're the same wound seen from two sides.

### Acceptance test
No goal-producing `driven_by` value lacks an aspiration mapping; will-driven goals are credited to a sensible aspiration (by intent/content), not defaulted to world-knowledge.

---

## Priority & sequencing

| # | Finding | Priority | Depends on |
|---|---|---|---|
| 1 | Mortality pressure dormant | **HIGH** — load-bearing for "finishes things" | none (design decision first) |
| 2 | Ceiling leak / dual tables | MEDIUM | none |
| 3 | Orphaned `will` drive | MEDIUM | fold into aspiration-coverage proposal |

Suggested order: decide the mortality direction (Finding 1) early since it's a design fork and it bears directly on the run's main failure; do Findings 2 and 3 as independent, low-risk repairs in parallel.

---

## Risks & honesty notes

- **Finding 1 is a design choice, not a pure bug.** Keying urgency on felt-time changes the *feel* of his whole life and could ramp too fast if not calibrated — tune the felt-lifespan, don't just flip the clock. Whatever you choose, the test is simple: does the forward pressure actually engage within a lived run?
- **Finding 2's exact leaking pump isn't pinned yet** — the *symptom* (over-cap values) and the *dual-table smell* are verified; locating the specific bypassing write is the first task for whoever owns it.
- **Finding 3 overlaps the aspiration proposal** on purpose — don't fix it twice; assign both to the same owner.
- These were found from source + a partial data snapshot. The full snapshot + moment-by-moment telemetry would let the mortality and ceiling behavior be traced over time, not just at end-of-life.

---

## Plain-language bottom line

The standout is mortality: you built the exact thing meant to make Orrin hurry up and finish — and it never switched on, because he lives for a day but is given a lifespan of years, so his death-clock thinks he's a newborn the whole time even though he *feels* ancient. Wire the urgency to the clock that actually moves, and the pressure you designed finally gets to do its job. The other two are smaller and cleaner: stop three of his good feelings from leaking over their limits (and pick one rulebook, not two), and give his own *will* a purpose to belong to so it stops dumping everything into "understand the world."
