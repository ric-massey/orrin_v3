# Hard-Number Register — Run 11 (N1, backlog §6.2)

Every surviving constant in the selection / drive / satiety / credit layers,
with an owner line: what it does, why the value, and its de-clamp
classification per the unopposed-force test (Law 9) —
**wall** (stays by design, §6.3), **antagonist parameter** (a drive weight the
predictive core should eventually learn), or **instrument tuning** (telemetry
cadence, no behavioral force). A constant not in this register that exerts
selection/credit force is a defect: add it or convert it.

Copy this file into the Run 11 run folder at capture.

## Selection layer (`brain/think/think_utils/selection/`)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_W_EXPLORE` (score_actions) | 0.12 | antagonist | Gershman (2018) directed-exploration weight; uncertainty bonus |
| `_W_EXPLOIT` (score_actions) | 0.25 | antagonist | learned-value exploitation weight opposite `_W_EXPLORE` |
| `_W_SATIETY` (score_actions) | 0.30 | antagonist | per-action satiety devaluation (C-satiety); opposes incumbency |
| `_W_BOREDOM` (score_actions, C5) | 0.45 | antagonist | felt stagnation × pick-share devalues repetition; replaces the forced rut switch |
| `_W_BOREDOM_CAT` (score_actions, C5) | 0.50 | antagonist | graded think-vs-act pressure when deliberation crowds the window (>0.6 share) |
| `_W_VALUE` (score_actions) | 0.6 | antagonist | Fix-1 first-class additive learned-value term |
| `_MATURITY_OBS` (score_actions) | 8 | wall | observations before an action's EMA counts as mature (statistics, not policy) |
| `_EXPL_CAP_MIN` (score_actions) | 0.12 | wall | exploration term can never be starved to zero (liveness floor) |
| `_META_RUT_WINDOW` (pick) | 5 | legacy | old forced-switch trigger; only active with `ORRIN_BOREDOM_DRIVE=0` |
| `_META_RUT_BACKSTOP_WINDOW` (pick, C5) | 12 | wall | dead-man backstop: a freeze surviving boredom economics is broken by force |

## Energy economics (`brain/motivation/energy_orientation.py`, C6)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_MAX_EFFORT_PRICE` | 0.50 | antagonist | price of a full-effort fn at zero activation; engages below a=0.5 (neutral pays nothing) |
| `_W_VIGOR` | 0.60 | antagonist | surplus activation above 0.6 presses toward action |
| effort tiers | 1.0 / 0.40 / 0.15 | antagonist | action / other / reflect effort classes; ordering is the mechanism, values are the tune |

## Drive substrate (`brain/motivation/substrate.py`, D3)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_DRIVE_DEFAULTS` table | per-drive | antagonist | baselines + rise/fall rates; D4 (deferred) derives these from demand-relief learning |
| novelty rise (D3) | 0.0005 /s | antagonist | was 0.00018 (36× drain/recover asymmetry → extinction); now ~13×, oscillation-capable |
| `_NOVELTY_FLOOR` (D3) | 0.12 | wall | proportional relief approaches, never crosses — one action cannot zero the drive |
| activation budget | 0.6 × n_drives | wall | soft normalization keeping the arbiter's gradient differentiable (audit §10) |

## Topic satiety (`brain/cognition/intrinsic_helpers.py`, C3)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_APPETITE_TAU_S` | 48 h | antagonist | appetite recovery time-constant, scales with completion count |
| `_APPETITE_SPAWN_FLOOR` | 0.30 | antagonist | below this the want is too quenched to spawn a respawn |
| `TITLE_COMPLETION_CAP` | 5 | legacy | old lifetime ban; only active with `ORRIN_TOPIC_SATIETY=0` |

## Credit layer (`brain/agency/effect_ledger.py`, C4 + §6.3 walls)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `MIN_ARTIFACT_CHARS` | 120 | wall | boilerplate floor between affect strings (~40) and a real finding (§6.3: stays) |
| `NEAR_DUP_SIM` / `NEAR_DUP_RESIDUAL` | 0.9 / 0.15 | wall | novelty pricing core — the anti-pump wall (§6.3: stays) |
| `NOVELTY_CREDIT_FLOOR` / `_NOVELTY_RAMP_CEIL` | 0.05 / 0.30 | wall | recorded-but-uncredited floor; proportional ramp to full credit |
| `_PATH_CREDIT_DECAY` | 1.0/0.5/0.25 | wall | per-path rewrite decay (F2c anti-pump) |
| marginal price shape (C4) | 1/(1+(k/2)²) | antagonist | k-th symbolic credit in the window; half-life k=2 — a storm extinguishes economically |
| `_SYMBOLIC_CAP_WINDOW_S` | 600 s | instrument | the pricing window length |
| `_SYMBOLIC_CAP` | 6 | legacy | old cliff; only active with `ORRIN_NOVELTY_PRICING=0` |
| `_NOVELTY_WINDOW` | 64 | instrument | near-dup comparison depth |

## Growth ladder (`brain/cognition/growth_ladder.py`, G1/G3)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_STREAK_TO_CLIMB` | 3 | antagonist | verified successes per rung; low on purpose for the first laddered life |
| `_MAX_RUNG` | 5 | wall | criteria hardening has 2 tiers today; headroom is bounded until more exist |
| mastery bonus | +0.15/term, cap ×1.5 | antagonist | G3 adjacency pull toward the zone next to competence; cap keeps frontiers reachable |

## Answer citation (`brain/cognition/answer_citation.py`, G2)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_MIN_TERM_OVERLAP` | 2 | wall | question-subject terms required in the deciding context; 1 = noise citations |
| `_MAX_ROWS` | 100 | instrument | rolling answered-question index depth |

## Distant connections (`brain/symbolic/analogy_engine.py`, D2)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_DISTANT_SURFACE_CEIL` | 0.15 | antagonist | above this a pair is a neighbor, not a leap (below the memory graph's 0.18 link line — never co-associated) |
| `_CROSS_INTENT_BONUS` | 0.15 | antagonist | cross-domain jump bonus |
| score weights | 0.55 relation / 0.45 distance | antagonist | the bridge matters slightly more than the leap |

## Entropy organs (`entropy_monitor.py` / `entropy_budget.py`, C8/C9)

| Constant | Value | Class | Owner line |
|---|---|---|---|
| `_WINDOW` / `_MIN_SAMPLES` | 200 / 30 | instrument | per-channel window; no verdict on a cold distribution |
| `_COLLAPSE_FLOOR` | 0.35 | antagonist | normalized entropy below this routes felt pressure — the general anti-monopoly organ |
| `_PRESSURE_COOLDOWN_S` | 600 s | wall | pressure is a push, not a siren |
| `_SNAPSHOT_EVERY` / `_HISTORY_KEEP` | 25 / 400 | instrument | persistence cadence for the §10 gate |
| `_QUARTER_CYCLES` (budget) | 5000 | instrument | life-quarter bucketing for a 20k life |
| `_FLUSH_EVERY_N` / `_FLUSH_EVERY_S` (budget) | 20 / 60 s | instrument | write batching, no behavioral force |

*Filed 2026-07-20 as part of the Run 11 Slice 2 build (N1). The `antagonist`
rows are the predictive core's future learning targets (§11); the `wall` rows
are §6.3's explicit keeps; `legacy` rows exist only behind their OFF flags for
bisection.*
