# Code connection audit - 2026-07-05 run

This is a fourth pass over the 2026-07-05 staging run, written after reading
the current code paths behind the run symptoms. Important caveat: the working
tree now includes Run 5 fixes, so current code is not a byte-for-byte copy of
what executed on 2026-07-05. I use current code as a causal map because the
new guards and comments name the old failure surfaces directly. The raw run
stores still provide the evidence.

The earlier deeper pass is still right at the architectural level: semantic
knowledge lacked control authority. This pass adds the awkward wiring: the
places where counters, goals, memories, effects, and speech all touch each
other through surprising side doors.

## Headline corrections

There are two production instruments, and the earlier docs blur them.

`brain/data/production_funnel.json` is candidate-only in this run:

- 1,282 events.
- all 1,282 are `candidate`.
- no `committed`, `handoff`, `producer_ran`, `artifact`, or `credited` events.

That is not because production had no later stages. It is because the deeper
stage callsites were not actually writing to this file. Current code still only
shows the `candidate` call in `_mk_goal`; handoff/attempt/success live in a
different file, `production_loop.jsonl`.

`brain/data/production_loop.jsonl` did track later production-like events, but
its cumulative counters reset on relaunch while the JSONL file kept appending:

| Segment | Rows / cycles | Handoffs | Attempts | Successes |
|---|---:|---:|---:|---:|
| segment 1 | cycles 1-11009 | 236 | 228 | 140 |
| segment 2 | cycles 11011-15554 | 292 | 124 | 28 |
| row-level total | full JSONL | 528 | 352 | 168 |

The tail numbers previously quoted as `292 / 124 / 28` are only the second
process segment. The file reset at JSONL row 11010, cycle 11011, immediately
after the relaunch line in `run_log.txt`.

This does not make the production story better in a simple way. It means
production telemetry was more alive than the docs said, but also less clean:
`production_loop.jsonl` counts any ledger row drained from any lane as an
attempt, and any positive-significance row as success. It is not the same as
"the staged producer wrote a good artifact."

Future S7 reads should use three numbers, not one:

1. `production_funnel.json` stage counts, to see whether the explicit staged
   funnel is wired.
2. `production_loop.jsonl` row booleans, summed across process resets.
3. content audit of the artifacts, because counters cannot tell synthesis from
   structurally novel template copies.

## The strongest missed connection

The run did not merely lack a good composer. It lacked a usable material
economy, and the only sidecar material it preserved was the bad artifact.

Evidence from `effect_ledger.jsonl` and `effect_artifacts/`:

| Kind | Rows | Credited rows | Missing body sidecars |
|---|---:|---:|---:|
| `tracked_work` | 166 | 10 | 0 |
| `note_novel` | 23 | 23 | 23 |
| `tool_run_effect` | 6 | 6 | 6 |
| `symbolic_artifact` | 157 | 129 | 129 |
| `file_write` | 9 | 0 | 0 |

The 10 available sidecar files are the first credited tracked-work sections,
not the 23 satiety learned notes. Current `section_material.py` makes the
dependency explicit: a composer can only use recent credited ledger prose when
`effect_artifacts.load(hash)` returns the body. In the run, the ledger knew the
learned notes were novel, but the future synthesizer could not read them.

So F1 and F3 are one bug, not two. The composer had no material because the
memory/ledger boundary preserved hashes better than bodies. The best prose
became accounting metadata; the counterfeit manuscript became durable text.

A future run can fail honestly here. With the fixed composer, if there are fewer
than two usable sources, `compose_section` should return `nothing_to_synthesize`
instead of writing. That may reduce artifact count, but it is healthier than
manufacturing text from nowhere.

## Long memory was mostly instrumentation

The earlier docs correctly call out external junk entering memory, but the
deeper pressure was internal instrumentation.

At death, `long_memory.json` retained 2,001 entries:

- 1,431 `goal_progress` entries.
- 163 `chunk` entries.
- 143 `metacog_pattern` entries.
- 56 `world_perception` entries.
- 23 credited learned-note ledger rows had no retained sidecar bodies.

Every retained `goal_progress` entry had `importance = 4`. The code path
explains why:

- `goal_io.record_goal_progress` writes a note every 5 cycles for the active
  goal with base `importance=2`.
- `long_memory.update_long_memory` adds up to +2 importance from emotional
  context.
- `prune_long_memory` scores recent, high-importance, high-affect memories as
  valuable.

So routine progress telemetry was promoted into high-value episodic memory.
The pruner then ran 384 times in the final eight minutes, each time pruning two
memories and writing "summarized and merged" to private thoughts.

This changes the F3 interpretation. The estate was not simply polluted by web
markup. It was dominated by self-instrumentation. The memory system was mostly
remembering that it had been pursuing goals, not preserving what those pursuits
learned or made.

Run 5 should therefore check an instrumentation ratio:

`goal_progress + metacog_pattern + housekeeping-like entries` as a percentage
of long memory at death. If that ratio is high, memory is still an audit log
wearing the mask of autobiography.

## Goal identity is still a major seam in this run

The v2/v1 bridge passed S8 because desync repairs stayed at zero. That proves a
specific lifecycle bug was fixed. It does not mean goal identity was canonical.

Run-store facts:

- `goals_mem.json`: 35 flattened live nodes.
- 31 of 35 live nodes have no `id`.
- 90 of 130 `goal_failure` rows have blank `goal_id`.
- the live synthesis goal has `id = None`.
- the synthesis ledger rows use a fallback title/slug goal id.
- `_step_attempts` on the synthesis goal is `{}` after 146 retries of one step.

Current `goal_io.py` shows why this is dangerous. The code has elaborate
id-stamping for proposed executable goals and v2 reconciliation, but cognitive
or legacy v1 nodes can still live id-less. When that happens, separate systems
fall back differently:

- effect ledger keys by supplied `goal_id`, title, or slug;
- deadline failure may see empty id;
- v2 close mirrors only if an id exists;
- attempts need a stable `(goal, step)` key;
- completed-goal credit dedupes by id or title;
- active-tree reconciliation can only title-match.

The run had store integrity without identity integrity. That is a subtler S8
lesson: "no resurrection repairs" does not guarantee that effects, failures,
attempts, and completions are all talking about the same object.

Run 5 should report:

- percent of live goals with ids;
- percent of failure rows with ids;
- percent of effect rows whose `goal_id` matches a live or completed goal id;
- any active artifact-gated goal without an id.

## The generator monopoly is completion-coupled

F5 frames the monopoly as `generate_intrinsic_goals` owning the conscious
action slot. That is true, but incomplete.

`mark_goal_completed` has a goal-continuity hook:

- clear `context["committed_goal"]`;
- set `intrinsic_goals._LAST_INTRINSIC_TS = 0.0`;
- call `generate_intrinsic_goals(context)` immediately.

That means completions themselves bypass the generator cooldown. The 41 cheap
frontier completions were not just an output of the candidate economy; they
also fed the next candidate burst. A completion can open a generation slot even
when the generator would otherwise be rate-limited.

This matters because Run 4 had fast frontier children:

- retained completions: 51;
- three "Understand X more deeply" titles account for 41 completions;
- median duration was 85.5 s in outcome metrics;
- generation was 1,508 -> 224 -> 51 by scoreboard stages.

So the loop was:

`cheap completion -> cooldown bypass -> generate more candidates -> select a
frontier child -> cheap completion`.

Pool-depth backoff helps, but Run 5 should specifically ask whether completions
still trigger immediate generation when the generated:attempted pool is already
deep. Otherwise the monopoly can move from conscious selection into the
completion hook.

## The aspiration scoreboard is not a causal funnel

`aspiration_scoreboard.json` looks like a funnel, but the run data proves it is
not a pure one:

| Aspiration | Generated | Attempted | Completed |
|---|---:|---:|---:|
| Understand the world | 1,270 | 155 | 1 |
| Understand self | 226 | 58 | 19 |
| Make things | 12 | 11 | 17 |
| Genuine contact | 0 | 0 | 14 |

Contact cannot have 14 completions after 0 generated and 0 attempted if this is
a single causal pipeline. Making cannot complete 17 from 12 generated for the
same reason.

The code explains the mismatch:

- `generated` is recorded when `_mk_goal` creates a candidate.
- `attempted` is recorded when `_build_committed_goal` commits a candidate.
- `completed` is recorded later by `credit_objectives`, using a completed goal's
  `serves` field or learned driven-by mapping.
- `progressed` only comes from `mark_objective_contribution`, which requires a
  specific effect-backed contribution path.

Those stages can be attributed through different fields at different times. A
frontier child born under one drive can complete under a parent `serves` label.
An old or id-less goal can be credited without having been generated through
the scoreboard path.

So the scoreboard is useful as pressure telemetry, not as a causal funnel. It
should not be read as "contact had no pipeline but somehow succeeded." It means
contact credit arrived from outside the recorded birth/attempt path.

Run 5 should either rename this as an aspiration pressure ledger or add stable
per-goal ids to each event so a true funnel can be reconstructed.

## The executive's multi-goal story has a hidden global cooldown

Current `executive.py` says the Executive can advance every queued goal each
tick. Current `goal_execution.py` still has one module-global pursuit cooldown:

`_last_pursuit_ts` with `_COOLDOWN_S = 30.0`.

The connection is awkward. The Executive can allocate steps to multiple queued
goals, but `pursue_committed_goal` stamps a single global clock. After the
first target advances, a second target in the same tick can hit the global
cooldown and return `{"skipped": True, "reason": "cooldown"}`.

The Executive computes `fn = recognise_step_action(step)` before calling
`pursue_committed_goal`. If a function was recognized, it still routes a
learning/history event after the result, with `_outcome_reward(... skipped ...)
= 0.2`, then breaks for that target.

This means multi-goal telemetry can contain recognized executive actions that
were no-op cooldown skips. That matters for reading production and EMA: a
recognized `compose_section` step is not automatically a producer run.

If multi-goal pursuit is meant to be real parallel progress, the cooldown needs
to be per goal or the Executive summary needs to separate "recognized" from
"ran." Otherwise the code says "all K goals advance," while the runner enforces
"one pursuit per 30 seconds globally."

## Production classification is not one definition

There are several overlapping "making" classifiers:

- `goal_criteria._is_artifact_gated`: broad; true for `requires_artifact`,
  `output_producing`, or title words like write/build/create/produce.
- `goal_criteria.goal_is_make_shaped`: narrower; true for coding,
  output-producing, or synthesize/make specs.
- `step_execution._MAKE_SHAPED_FNS`: includes `compose_section`,
  `produce_and_check`, `leave_note`, `write_desktop_note`, `save_note`,
  `write_tool`, and `write_cognitive_function`.
- `step_execution._goal_is_make_shaped`: uses the narrow make-shaped check OR
  the broad artifact-gated check.
- `intrinsic_objectives._evidenced_aspiration`: strips making credit if the goal
  is not make-shaped under the narrower shared function.

This is how production counts and aspiration credit can disagree. A note or
check under a broad artifact-gated goal can become a production handoff in
`production_loop.jsonl`, while later objective credit may refuse to call the
same goal "making" if it does not satisfy the narrower make-shaped definition.

That is probably the right direction for preventing research memos from wearing
the making hat, but it makes counters easy to misread. "Production handoff"
does not mean "making aspiration credit," and "making credit" does not mean
"the producer path ran."

Run 5 should report these separately:

- artifact-gated goals;
- make-shaped goals;
- make-shaped function dispatches;
- ledger-credited artifacts;
- making-aspiration completions.

## The ledger paid the first template copies

The ledger successfully deduped 156 of 166 tracked-work rows. But the first 10
tracked-work rows were credited.

That happened because `tracked_work` structural significance is based on
durable path, section name, and completed section count:

- section 1 significance 0.55;
- section 2 significance 0.60;
- section 3 significance 0.65;
- ...
- section 8 and later cap at 0.90.

The first 10 template sections earned a total of 7.6 significance before exact
and near-duplicate gates caught up. So "garbage doesn't get paid" is slightly
too strong. The correct statement is: structurally novel garbage got a small
startup payment, then the dedupe gate starved the treadmill.

This matters for Run 5 because a new bad template can always get a few credited
rows before novelty collapses. The gate should inspect first artifacts for
grounding, not only total significance over the whole run.

## Reuse was blocked by both population and callsite

F4 says reuse was unreachable because there were no research memos. That is
right, but the code reveals the exact shape:

- `web_research._write_research_memo` now records a `file_write` with
  `metadata.path`, then writes the memo only if the ledger credits it.
- `effect_ledger` indexes `metadata.path -> content_hash`.
- `goal_io._credit_spec_artifact_refs` only pays reuse when a new goal spec
  references paths under `goals/artifacts`.
- `fetch_and_read` calls `mark_reused_path`, but web URLs do not resolve to a
  local path hash.
- `compose_section` now calls `mark_reused(hash)` for source ledger artifacts it
  actually used.

So reuse is not "I read something later." It is "I read or cite a local
artifact whose path/hash the ledger can resolve." Run 4 had 0 reuse because it
had no memo population and no grounded composer. A future run can have many web
reads and still have 0 reuse if the reads do not become local, path-indexed
artifacts or cited sidecar hashes.

Run 5 should check:

- number of memo files under `data/goals/artifacts`;
- `file_write` rows with non-empty `metadata.path`;
- `mark_reused` rows by source hash;
- whether a later artifact names or transforms the reused source.

## Satiety notes depended on the memory they were meant to rescue

`satiety_note.write_learned_note` builds a learned note by searching recent
working memory and long memory for text overlapping the goal topic. If it finds
fewer than two snippets, it writes nothing. If the only available snippets are
goal-progress telemetry, the note can become a summary of process rather than
learning.

This connects three symptoms:

1. satiety closures stayed at 0;
2. 23 `note_novel` rows were credited but their bodies vanished;
3. long memory was dominated by `goal_progress` entries.

The note writer was trying to convert "I explored this" into a durable effect,
but it was drawing from a memory store already saturated with "I am pursuing
this." That makes the learned-note path vulnerable to circular self-evidence.

Run 5 should inspect the bodies of satiety notes, not just their existence:

- Do they contain external facts, source references, code observations, or
  causal claims?
- Or do they mostly contain goal-progress and affect phrasing?

## Speech was not just repeated. It was weakly bound.

The earlier docs describe 388 variants of one sentence. The data is more
specific:

- 388 speech-log rows.
- 330 source `composed`.
- top exact reply appears 54 times.
- many replies are variants of "something present but hard to name."
- some replies glue internal fragments into that affect phrase, for example
  `GoalPlanned: Trace...` followed by the same vague check-in.

Current `talk_policy.py` adds self-speech habituation, which addresses the
repeat rate. But the deeper issue is content binding. The mouth needs a typed
content kernel: answer the user, report a finding, ask a grounded question,
share an artifact, or state a blocker. In the run, the dominant kernel was
vague affect pressure.

That is why inbound and outbound failures are connected. Ric's "What do you
think?" became open-question goals because the system treated addressed speech
as available cognitive content. Orrin's replies became generic affect because
the expression path did not reliably bind to a specific conversational act.

Run 5 should measure:

- distinct-utterance ratio;
- percent of replies with a concrete referent from user input, active goal, or
  produced artifact;
- percent of intrinsic goal candidates whose title is copied from user input.

## The current fixes create a new honest-failure mode

Several Run 5 fixes deliberately make the system fail closed:

- `compose_section` refuses to draft with fewer than two sources.
- deduped drafts do not append to the manuscript.
- step attempts persist outside the goal dict and escalate.
- aspirations are skipped by executive and deadline walkers.
- note bodies are captured as artifacts, not trusted to memory.
- web research writes memo artifacts only if the ledger credits the body.

This is good, but it changes how the next run should be read. A clean Run 5 may
produce less visible output at first. That is not automatically regression. The
key distinction is:

- healthy failure: no material -> no section -> attempt count rises -> goal
  gathers material or fails clearly;
- unhealthy failure: no material -> template section -> dedupe -> retry forever.

The next analysis should treat a `nothing_to_synthesize` failure as evidence of
truthfulness, not as failure to make, unless the system then never learns to
gather material.

## Revised organism-level picture

The run's deepest shape is a set of partial loops that touched each other
without sharing contracts:

`goal generation` made too many candidates, and completions bypassed its
cooldown.

`goal execution` recognized production-shaped steps, but a global cooldown and
daemon/conscious lane split made "recognized" different from "ran."

`effect ledger` knew novelty and significance, but early structural credit paid
some template sections, and body sidecars existed only for the wrong artifacts.

`long memory` should have supplied synthesis material, but mostly retained
instrumentation.

`aspiration credit` counted completions through `serves`, while generated and
attempted stages were recorded elsewhere.

`speech` routed felt pressure outward, while inbound user speech leaked inward
as self-originated goals.

So the issue is not just missing authority. It is also missing join keys and
missing material contracts. The system has many ledgers, but not enough stable
ways to say "this candidate became this goal, ran this act, produced this body,
credited this aspiration, reused that source, and changed this future choice."

## What I would add to the next run analysis

For Run 5, keep the existing gate, but add these code-connection checks:

1. **Production reset-safe totals:** sum `production_loop.jsonl` booleans across
   counter resets; do not trust the tail cumulative fields alone.
2. **Funnel wiring:** verify `production_funnel.json` has stages beyond
   `candidate`, or say it is candidate-only.
3. **Goal identity coverage:** live, failed, completed, and effect rows with
   stable ids.
4. **Material availability:** credited prose rows whose sidecar body resolves.
5. **Material transformation:** later artifacts using prior hashes or memo paths.
6. **Memory composition:** percentage of long memory that is instrumentation.
7. **Attempt durability:** max attempts for any `(goal_id, step)` key.
8. **Cooldown truth:** count recognized executive actions separately from actions
   that actually ran.
9. **Classifier agreement:** artifact-gated vs make-shaped vs production handoff
   vs making-aspiration credit.
10. **Speech grounding:** replies with concrete referents, not just non-duplicate
    wording.

## Bottom line

The earlier pass said Orrin could notice more truth than he could act on. This
code pass makes that sharper: Orrin also could not reliably join his truths
together.

The 2026-07-05 run had ledgers for effects, goals, production, aspirations,
memory, speech, and outcomes. The failures live between those ledgers:
counter resets, id-less goals, sidecar-less notes, candidate-only funnels,
completion-triggered generation, and production classifiers that overlap but do
not mean the same thing.

Run 5 should prove not only that each organ is patched, but that a piece of
work can travel through the whole organism with one stable identity and one
recoverable body.

*Generated 2026-07-07 as a code-informed connection audit over the corrected
2026-07-05 staging run. Analysis only; no runtime behavior changed by this
document.*
