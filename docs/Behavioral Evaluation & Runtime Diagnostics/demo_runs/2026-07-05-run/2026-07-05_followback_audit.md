# Follow-back audit - 2026-07-05 run

This is a fifth pass over the 2026-07-05 staging run. It follows files that
looked secondary in the first code audit: writeback, binding, goal lensing,
satiety, milestone updates, metacognition, plan pruning, quality predicates,
notes, and the older completion sweeper.

Important caveat: the working tree now contains post-run fixes. I use current
code as a map of the pathways and the run stores as evidence. I label findings
as proven, plausible, or latent instead of treating every awkward connection as
known causal history.

## Executive read

The peripheral files are not junk. A lot of them are better than the earlier
analysis gave them credit for. The quality predicate is serious. Satiety has
real no-cycle-one and check-pass gates. Metacog ignores mere step-completion
churn when judging progress. Workspace priors are bounded and decay. Notes and
checks now fail closed more often than they hallucinate progress.

The deeper problem is different: good local guards are joined by broad proxies.
Small signals become evidence somewhere else. A binding moment can become a
writeback conclusion, a writeback conclusion can become a workspace prior, a
workspace prior can help many unrelated actions at once, long-memory growth can
become a research milestone, a milestone can skip plan steps, and an old sweeper
can still append a goal after a guarded completion refused to complete it.

That is the honest shape of the system: locally improved, globally still full
of side doors.

## Quick classification

| Area | Good | Bad / awkward | Certainty |
|---|---|---|---|
| Workspace writeback | Bounded priors, decay, small affect deltas | Binding wrote back on 9,299 of 9,300 writeback cycles and nudged motivation 5,935 times | Proven in run store |
| Binding and routing | Integrates goal, affect, memory, event into one conscious situation | If every cycle is a "situation", writeback is no longer a conclusion filter | Proven frequency, plausible effect |
| Goal lens | Keeps action selection goal-relevant | Boosts `compose_section` for tracked work without checking material readiness | Proven code path |
| Long-form comprehension | Makes output goals executable | Fallback long-form plan starts by composing every part instead of gathering material | Proven code path, matches run symptom |
| Milestone updates | Strict gates for production, notes, research markers | Research milestones can be ticked by any long-memory growth or any qualifying effect for the goal | Proven code path, plausible run mechanism |
| Plan pruning | Skips only from met milestones, not raw WM | Amplifies false milestone ticks if the upstream milestone was broad | Plausible chain |
| Completion sweeper | Main `mark_goal_completed` guard is strong | `maybe_complete_goals` appends after calling the guard without verifying status | Latent/current bug |
| Maintenance satiety | Bounded, effect-gated, productive refusal path | Sweep is top-level-only while most live goals are nested subgoals | Proven code path and current store shape |
| Metacog | Watchdog measures real progress, structural alarms cannot be quieted | Other systems do not use the same progress definition | Proven code split |
| Notes/checks | Strong fail-closed behavior in current code | May look like regression if Run 5 only counts artifact volume | Evaluation risk |

## What I missed that is genuinely good

### 1. The quality predicate is not cosmetic

`brain/cognition/quality_predicate.py` is a real shared floor, not a vibe
check. It rejects short stubs, low-information bodies, machine-log shapes,
template skeletons, near-duplicates, ungrounded text when evidence exists, and
answers that only restate the question. It also explicitly uses the bad July
run shapes as anti-exemplars.

That matters because it means future failures should be less likely to come
from "the code cannot recognize slop." They are more likely to come from the
wrong thing never reaching the predicate, or from upstream evidence being too
broad.

Good implication: when `compose_section` or `leave_note` refuses to write, that
is often healthy. Run 5 should not punish lower raw artifact volume if the
missing artifacts are blocked by this floor.

### 2. Satiety has more real structure than the old docs implied

`brain/cognition/planning/goal_satiety.py` has several good gates:

- no satiety closure before real exploration work;
- filesystem goals use novelty exhaustion, not uncertainty(title);
- verifiable goals close only on a recorded `tool_run_effect`;
- satiety is a quench signal, not a bare "one action happened" signal.

`brain/loop/maintenance.py` also makes refused satiety productive: if a goal is
sated but has no qualifying effect, the sweep stamps `_sated_since_cycle` and
later degrades or disengages it instead of leaving it immortal.

That is the right architecture. The problem is coverage and identity, not the
satiety predicate itself.

### 3. Metacog learned the right lesson about fake progress

`brain/cognition/metacog.py` deliberately excludes raw completed-step count from
its "advanced" signal. It tracks milestones met, novel observations, and plan
length. That directly addresses the old mode where re-planning and re-completing
the same step could reset the stuck watchdog forever.

It also treats `objective_unmet`, `stuck_step`, and `release` as structural
offers that cannot be quieted by dismissal recalibration. If the goal stays
stuck long enough, the hard-disengage path can fail it and hand it to repair.

Good implication: the monitor is one of the more mature pieces. It is not the
main source of the July 5 treadmill.

### 4. Selection is not a naive argmax

The selection stack has more brakes than I initially credited:

- `workspace_prior` is capped and skips monitor sources;
- goal-type gates suppress mismatched functions;
- goal shielding dampens blind exploration while a committed goal is active;
- pool-depth backoff demotes `generate_intrinsic_goals` when the generated pool
  is too deep;
- reward EMA no longer treats mature positive totals as all equal.

That does not mean the selector is fixed. It means the remaining problems are
composition problems: several bounded nudges can align in the same wrong
direction for many cycles.

### 5. Produce-and-check is honest within its narrow domain

`brain/cognition/produce_and_check.py` does not just claim a check happened. It
limits itself to verifiable domains, runs a self-contained sandbox check, and
records `tool_run_effect` only on pass. The six credited `tool_run_effect` rows
in the run should be treated as real computational grounding, not as template
artifact spam.

The ceiling is also clear: this proves Orrin ran a checkable primitive. It does
not prove every downstream interpretation of the topic was correct.

### 6. Leave-note is much less dangerous now

`brain/cognition/leave_note.py` now rejects bad seeds, lock/path/noise text, and
artifact goals without usable material. It credits only when there is grounded
seed content. That is a strong repair for the "write a note from nothing" path.

The old July 5 notes still vanished from the durable material economy, but the
current note writer itself is not obviously the weak point.

## Bad or awkward connections

### 1. Binding/writeback became a chronic motivation pump

This one is proven in the run data.

`brain/data/workspace_writeback.jsonl`:

- 9,300 rows.
- cycles 3 through 15,549.
- 9,300 distinct cycles with writeback, max one row per cycle.
- source counts: `binding` 9,299, `subconscious` 1.
- affect targets: `motivation` 5,935, `None` 3,364, `novelty_signal` 1.
- average salience: 0.953.
- average primed tokens: 10.81.

The good part: `workspace_writeback.py` is locally bounded. Affect deltas are
small, salience priors decay, and the stored `workspace_priors.json` at death
held only 16 low-weight tokens around 0.03-0.04. It did not create a giant
permanent prior blob.

The bad part: the source mix is not healthy. If `binding` writes back almost
every time, then "writeback" is not a special path for conclusions anymore. It
is the default conscious situation being recycled into priors and affect.

The follow-back chain is:

`binding.bind_situation` -> `global_workspace.update_workspace` ->
`workspace_writeback.record_conclusion` -> `workspace_writeback.salience_prior`
and `selection.routing.workspace_routes`.

Binding candidates are broad by design: they can include goal, affect, memory,
event/object, interlocutor, and workspace offers. Routing then merges action
priors for all facets. A single bound situation can bias `attend_goal`,
`assess_goal_progress`, `reflection`, `narrative_update`, `look_outward`, and
`search_own_files` at the same time.

That is useful when rare. At 9,299 of 9,300 writebacks, it becomes background
pressure.

Run 5 should report:

- writeback rows per 1,000 cycles;
- percent of writebacks by source;
- percent targeting `motivation`;
- top selected actions when workspace prior contributes more than 0.10;
- whether binding salience above 1.0 is common after goal-lens/prior additions.

### 2. The long-form fallback plan makes composing look correct too early

`brain/cognition/planning/goal_comprehension.py` treats long-form goals as
tracked work. In the fallback model, the parts are:

- purpose and thesis;
- outline;
- substantive sections;
- coherence review;
- final manuscript.

Then `_ensure_production_actions` attaches `compose_section` to every plan item.

`brain/cognition/goal_lens.py` then adds action prior for production actions,
with an extra boost when the active lens has `tracked_work`. For `compose_section`
on a tracked-work goal, the prior can be boosted before checking whether there
are enough usable source bodies to synthesize.

This is a clean explanation for the old manuscript treadmill:

1. The synthesis goal is interpreted as long-form tracked work.
2. Its fallback steps all become `compose_section`.
3. The lens says `compose_section` is goal-aligned.
4. The old composer wrote template text instead of refusing.
5. The ledger refused most credit, but the action stream kept treating the
   route as appropriate.

Current code likely fails better: a fixed composer should return
`nothing_to_synthesize` when there are fewer than two usable sources. But that
will expose the next planning issue: the plan still starts with composition, not
material gathering.

Fix shape: long-form fallback should be `gather/cite/synthesize/review`, not
`compose/compose/compose/compose/compose`. The `compose_section` lens boost
should depend on material readiness, not just `tracked_work=True`.

### 3. Research milestones can be ticked by broad long-memory growth

`brain/cognition/planning/env_snapshot.py` is better than it looks at first:
production milestones are strict, note milestones require a note marker, and
research milestones look for real retrieval markers.

But research/finding milestones also return true when either of these context
flags is true:

- `_goal_has_effect`;
- `_research_progressed`.

`_goal_has_effect` is any qualifying effect for the goal id. That can be valid,
but it is broader than "research happened."

`_research_progressed` is broader still. It is set when total long-memory count
is greater than the goal's `_lm_baseline`. It does not filter for research event
types.

That interacts badly with the July 5 memory profile:

- `long_memory.json` retained 2,001 entries.
- 1,431 were `goal_progress`.
- every retained `goal_progress` entry had `importance = 4`.

So routine goal-progress instrumentation could increase long memory and satisfy
"a finding was written to long memory" style milestones. I cannot prove which
completed frontier goals closed through this exact path without replaying each
goal's context, but the mechanism is real and fits the 85.5-second median
completion population.

Fix shape: research milestones should count only research-like long-memory
event types or qualifying ledger kinds. `goal_progress`, metacog traces, and
housekeeping should never satisfy a finding milestone.

### 4. Plan pruning is safe locally but amplifies false milestones

`brain/cognition/planning/goal_plan_ops.py` does the right local thing:
`prune_satisfied_steps` only skips pending steps when their tokens are largely
covered by already-met milestones. It deliberately does not use raw working
memory. That is good.

But this makes milestone truth more important. If a milestone was ticked by a
broad long-memory-growth proxy, pruning can skip downstream steps as already
satisfied. Then a plan can become terminal without the actual work happening.

The awkward chain is:

`env_snapshot._research_progressed` -> milestone marked met ->
`prune_satisfied_steps` skips plan steps -> all steps terminal ->
completion path tries to close the goal.

This is not an argument to remove pruning. It is an argument to stamp milestone
reasons with source type and block pruning from milestones whose evidence was
only broad instrumentation growth.

### 5. The old completion sweeper still has a side door

`brain/cognition/planning/goal_outcomes.py::mark_goal_completed` is now a strong
chokepoint. It refuses directional drivers, requires milestones or satiety
evidence, gates artifact goals, and withholds reward when there is no grounded
delta.

But `brain/cognition/planning/goals.py::maybe_complete_goals` still calls
`mark_goal_completed(goal)` and immediately appends that goal to its local
`completed_goals` list, sets `changed=True`, and returns true. It does not check
whether `goal["status"]` actually became `completed`.

That means a guard refusal can still be followed by:

- saving the mutated goal tree;
- writing "marked some goals as completed" to working memory;
- appending a not-completed goal to `COMPLETED_GOALS_FILE` from this sweeper's
  own append path.

I do not have run-store proof that this sweeper caused the July 5 closures. It
is called from `reflect_on_self_beliefs`, and the run logs contain
`reflect_on_self_beliefs` activity, but the exact sweeper effects are not
obvious from the retained stores. Treat this as a current latent bug with high
blast radius.

Fix shape: after every `mark_goal_completed(goal)`, the caller must check
`goal.get("status") == "completed"` before appending, saving completion
telemetry, or returning true to a parent.

### 6. Maintenance satiety is top-level-only, but the live goals are nested

`brain/loop/maintenance.py` loops over `for _g in load_goals():` and checks at
most five roots per pass. It does not recurse into subgoals.

The July 5/current goal tree shape makes that a real coverage gap:

- 35 total live nodes.
- 6 roots.
- 29 subnodes.
- 31 of 35 nodes have no id.
- `Immediate Actions` is a root with 28 pending child goals, including the
  synthesis goal and many frontier/open-question children.

So the maintenance satiety sweep can be well-designed and still miss the exact
population that needs it. Child goals may still close through pursuit paths, but
the background satiety population sweep will not see most of them.

This helps explain why satiety closures stayed at zero even while learned notes
and satiety refusal machinery existed. The predicate was not necessarily the
whole failure; the traversal boundary was also wrong.

Fix shape: use a bounded recursive iterator over eligible live nodes. Count
checked nodes, not roots. Stamp ids before satiety/effect checks.

### 7. Goal identity is the connector behind several "separate" issues

The earlier code audit already called this out, but the follow-back pass makes
it more important, not less.

Several peripheral files quietly rely on stable ids:

- binding only carries `facets["goal_id"]` when the raw goal has an id;
- satiety effect closure uses `goal.get("id") or title`, but effect checks are
  strongest with a real id;
- maintenance skips the committed goal by id;
- `_goal_has_effect` in milestone updates uses `gid = goal.id`;
- scoreboard stages cannot become a true funnel without per-goal event ids;
- step attempts need a stable goal/step key.

The live run store had 31 of 35 nodes id-less. Store unification passed S8, but
identity integrity did not. That is the common denominator behind many awkward
fallbacks.

Fix shape: id-stamp every goal and subgoal at ingress and during tree load.
Treat an active artifact-gated or executable goal without an id as a telemetry
error.

### 8. Metacog and milestone logic disagree about what progress means

Metacog's progress signature is mature:

- milestones met;
- novel observations;
- plan length.

It explicitly ignores step-completion churn.

Milestone/pruning/completion paths still let broader evidence through:

- total long-memory growth for research progress;
- token overlap for generic milestones;
- terminal plan steps as a close trigger in `maybe_complete_goals`.

This means the watcher can correctly say "no real progress" while a planning
helper says "milestone met" or "plan done." The system has two progress
definitions, and the stricter one is not the universal authority.

Fix shape: promote metacog's progress definition into a shared helper or at
least make completion/step pruning consume the same evidence classes.

### 9. Web research and notes have better gates, but provenance is still weak

Current `web_research.py` is more careful than the July 5 behavior:

- concrete/external topic filters;
- memo artifact writing;
- markup/prose-ratio checks in fetch paths.

Current `leave_note.py` is also much stricter about seed quality.

The remaining awkward bit is provenance. Topic candidates can still be drawn
from recent working-memory questions, and the code does not consistently mark
whether the source was user-originated, self-generated, or external. The old run
showed user text spawning "Open question: What do you think?" candidates. That
class of boundary leak is not solved merely by concrete-topic filters.

Fix shape: carry provenance tags on question/topic candidates and let generator
or research code reject user-originated prompts unless the user explicitly asked
Orrin to adopt them as goals.

## A combined failure chain to watch

The most worrying follow-back chain is this:

1. Binding wins the workspace almost every cycle.
2. Writeback records binding as a conclusion and often nudges motivation.
3. Workspace routing gives several action priors from the same broad situation.
4. Goal lens boosts output-looking actions for tracked-work goals.
5. Long-form fallback marks every part as `compose_section`.
6. If composing cannot produce material, current code fails closed; old code
   wrote templates.
7. Meanwhile, long-memory instrumentation can tick research milestones.
8. Pruning can skip steps covered by those milestones.
9. A completion helper may call the guarded close and then treat the call as
   success anyway.

No single piece in that chain is obviously broken in isolation. The problem is
that each helper trusts the previous helper's broad proxy a little too much.

## Run 5 instrumentation I would add

1. `workspace_writeback`: source share, motivation-nudge share, and selected
   action when writeback-derived workspace prior exceeds 0.10.
2. `binding`: count of binding candidates offered, binding winners, and binding
   winners with a real goal id.
3. `goal_lens`: top selection components plus `material_ready` for
   `compose_section`.
4. `goal_comprehension`: first three plan actions for long-form goals; fail if
   all are `compose_section` before any gather/research/source step.
5. `env_snapshot`: milestone tick reason, evidence event type, and whether the
   tick came from broad long-memory growth.
6. `prune_satisfied_steps`: skipped step plus milestone id/reason used to skip
   it.
7. `maybe_complete_goals`: count of completion calls where status remained not
   completed after the guard.
8. `maintenance.satiety`: roots checked, subgoals checked, skipped because
   id-less, closed, refused, degraded.
9. `long_memory`: percent of retained entries that are instrumentation
   (`goal_progress`, metacog traces, housekeeping) vs durable findings/artifacts.
10. `question/topic provenance`: user-originated vs self-generated vs external
    source for every generated candidate.

## Bottom line

The "unimportant" files make the system look both better and more fragile than
the earlier audit.

Better: many local components now fail closed, use bounded signals, and reject
known fake work. The July 5 run was not caused by one crude missing `if`.

More fragile: broad proxies still cross subsystem boundaries as if they were
hard evidence. The biggest remaining risk is not that Orrin cannot detect bad
work. It is that the wrong broad signal gets promoted into "progress" before
the bad work reaches the detector.
