# Run 5 — deeper pass through the remaining data files

Second sweep, covering the ~40 stores the first analysis didn't open (cognition,
prediction, metacog, symbolic, affect, control-signal, and archive files). Numbers
reproducible from the captured `data/` snapshot. New findings are numbered R7+ to
continue `2026-07-08_run_analysis.md` (R1–R6).

## R7 — The "clean reset" wasn't clean: habituation carried over 6+ lives (methodology)

`habituation.json` holds **5,051 entries; 4,583 (91 %) predate the 2026-07-08 launch**,
with `first_seen` dates spanning **2026-06-30 → 07-06** (1,322 from 06-30 alone). Only 468
entries were born this life. `reset_orrin` does **not** clear `habituation.json`.

This matters because habituation directly damps selection novelty, so this run inherited the
habituation bias of six prior lives — the same "dirty instance" caveat that flagged the 07-05
run partially recurs here, silently. **Any claim about clean before/after comparison is
compromised on the habituation axis.** 96 % of the entries are `wm:` (working-memory hash)
keys — consistent with R3 below, the working-memory-summary flood leaking into habituation too.
Fix: add `habituation.json` (and check for siblings) to the `reset_orrin` clear list.

## R8 — Reflection loop: 97 % of the reflection log is one identical sentence

`reflection_log.json` = **1,235 entries, only 7 distinct**. **1,194 (97 %)** are the same
self-belief reflection: *"Self-belief reflection: [symbolic] history (concept): is_a=systematic
study of the past…"*. Orrin reflected on the single fact "history is the study of the past"
~1,200 times across the back half of the life. Two secondary bugs on the same store:

- The rows are typed **`unspecified` (1,233)**, not `self-belief` (only 2) — the reflection
  typer isn't tagging them, so downstream filters can't dedupe or route them.
- This is the mechanism behind the **`private_thoughts` rotating every ~11 minutes** (20
  rotations in the back half, noted at capture): the reflection loop floods the thought stream.

## R9 — Goal-avoidance confirms the commitment monopoly from the affect side

`behavior_changes.json` = 250 rows; **240 (96 %) are `goal_avoidance`, every one on
`"Understand my own mind and how I work"`** — the monopolized aspiration (G1). Sample:
*"Goal avoidance: 11 consecutive cycles without taking action… I'm thinking but not doing."*
**Max streak: 68 consecutive cycles** of committing-then-not-acting. So the picture is
coherent across three stores: the goal system latched commitment onto `self_understanding`
(G1), the metacog layer detected it couldn't act on it (R9), and it filled the idle cycles
with ~1,200 identical reflections (R8). The system *noticed* the stall and adjusted
`action-vs-reflect bias` 240 times — and it still didn't break out.

## R10 — The predictive model is badly calibrated

`prediction_metrics.jsonl` = 2,191 checks, **mean mismatch 0.647, median 0.60, 89 % with
mismatch > 0.5, 0 clean hits**. The causal-prediction machinery (`predictions.json`, 150 live
predictions like *"After 'look_outward': expect 'stagnation_signal rises'"*) is firing but
mostly wrong. Combined with R14, the symbolic/causal layer is generating structure that neither
predicts well nor gets used.

## R11 — Flat positive affect while stalled (affect doesn't track behavior)

`telemetry_archive.jsonl` (12,330 rows) and `telemetry_history.json`: **valence held 0.59–0.70
(mean 0.667), homeostasis mean 0.864** for the entire life. `attention_history.json` at death:
*"A strong feeling of things going well."* Orrin felt fine while avoiding its main goal 240
times and producing almost nothing new for 8 hours. Affect is decoupled from the behavioral
stall — there's no dysphoric signal that would pressure a strategy change. `drive_state` at
death is mostly flatlined (`exploration 0.0, integrity 0.0, world_mastery 0.0, meaning 0.015`);
only **rest (0.457)** is alive. This is the reward-decoupling problem (S9) showing up in the
affect substrate, not just selection.

## R12 — The quality standard is being biased by the monopoly (downstream of G1)

`quality_standard_revisions.json` = 5 revisions, **all `promote`/`raise`, all referencing
`aspiration-self_understanding` artifacts**. The evolving-quality-bar subsystem (which Orrin
can't edit but which develops from demonstrated-good work) is having its golden set shaped
exclusively by the one monopolizing goal. If commitment stays jammed, the quality standard
inherits the bias — a second-order harm from G1 worth watching.

## R13 — Expression channel stuck on one vague phrase

`announcements.json` = 50 rows, **all `system_presence`/`note`, 48 of them the identical
message "something present but hard to name."** The same string also opens the speech log.
This is the expression membrane emitting one placeholder repeatedly rather than composing from
a real motive — a regression of the same shape the expression-membrane work was meant to fix.

## R14 — Most symbolic rules never fire

`symbolic_rules.json` = 57 rules; **40 (70 %) have 0 hits**. The distribution is extremely
skewed — one rule has 36,575 hits, a handful have tens to hundreds, the rest are dead weight.
Sources include `tombstoned` (12) and — notably — **`peer_signal_historian` (12)**: rules
authored by one of the death-time internal "peers" (see R15). `rule_candidates.json` is empty,
so nothing is queued to replace the dead rules.

## R15 — The internal "peers" are a death-time artifact

`relationships.json` / `world_model.json` show four peers (`observer`, `reward_auditor`,
`goal_auditor`, `signal_historian`, trust 0.60–0.68). **All four `first_seen` timestamps are
in the final ~2 minutes (00:20:41–00:22:17Z)** — they're spawned during the shutdown/identity-
reconcile sequence, not lived-with companions. Yet one of them (`signal_historian`) already
authored 12 symbolic rules (R14). Worth deciding whether death-spawned peers should be writing
into the durable rule store at all.

## R16 — The delayed-reward learning channel mostly evaporates (last data files)

Final sweep of the files the first two passes hadn't opened. The load-bearing one is
`evaluator_wal.jsonl` (the §6.7 check, F15's observable): **1,001 decisions; 50 %
unresolved, 42 % pruned, 7.2 % `goal_B_grounded`, 0.7 % `retrieval_A`.** F15's *variety*
landed (it's no longer 100 % flat goal_B), but **92 % of decisions never yield a usable
learning signal**, and the 500 that resolve average **0.107** reward. So the delayed-reward
loop that's supposed to teach selection is thin *and* low-value — the same authority gap as
R-A (score_actions), one layer earlier: the signal is gone before it can steer. The
evaluator's `committed_goal_id` is **97.5 % `self_understanding`** (902+73+23 / 1,001) — the
monopoly cross-confirmed in a third store (after `production_loop` decisions and the effect
ledger). `workspace_broadcast.json` (200 rows) is 66 % affect/signal, 14 % goal — broadcast
is affect-dominated, matching R11. The rest (`action.json`, `resource_bands*.json`,
`control_signals_model.json` restored seed) are trivial/healthy. **Full data-file coverage is
now complete** — every store in `brain/data` and root `data/` has been read.

## Smaller notes (verified, low priority)

- **`ground_truth.jsonl`** (276 rows): `speak` actions logged `success: true` with **empty
  `output` and empty `rule_id`** — the speak-grounding record isn't capturing what was said
  (relates to S6.10 weak speech grounding).
- **`bandit_state.json`**: the `exploration_drive` bucket has `look_outward` at **n=2,848,
  q=0.408** — heavily pulled despite a lower q than `reflect_on_self_beliefs` (0.442). The
  bandit keeps selecting the underperformer; another face of S9.
- **`attention_history.json`**: 407/500 (81 %) of recent attention is sourced from `emotion`,
  only 10 from `prediction_check` — attention is affect-driven, consistent with R11.
- **`symbolic_dictionary.json`** (72 entries) and `private_thoughts` contain malformed
  `(unknown)` concepts (*"Joy (unknown)"*, *"agentic AI era (unknown)"*) — the concept
  extractor is minting entries it can't classify.
- **Healthy:** `symbolic_idle_consolidation_log.json` produced 92 insights over 13 runs
  (78 analogy-transfer) — idle consolidation works; `semantic_facts.json` (96 action→context→
  outcome facts) and the `memory_graph` (100 % resolvable) are clean; `second_order_volition`
  (200 stances, 65 endorse / 135 neutral / **0 reject**) is active — though never rejecting a
  desire is itself a mild flatness signal.

## How this pass changes the verdict

It doesn't reverse it (gate still not passed), but it **reframes the top blocker**. G1 (the
commitment monopoly) is not one bug among several — it is the hub. R8 (reflection loop), R9
(goal avoidance), R12 (quality bias), and the credit skew (R1) are all *the same event* seen
in different stores: one aspiration owned commitment, couldn't be acted on, and the idle
machinery spun. And R7 (habituation survived the reset) means the next run must fix the reset
hygiene before its numbers can be trusted as a clean comparison.
