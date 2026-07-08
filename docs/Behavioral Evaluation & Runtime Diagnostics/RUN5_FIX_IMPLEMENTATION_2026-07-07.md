# Run 5 Fix Implementation (2026-07-07)

Implements the fix list in `demo_runs/2026-07-05-run/2026-07-05_findings.md`
(F1–F9), the plan produced by the Run 4 staging life. Every fix names its
mechanism, the files changed, and the Run 5 observable it must move.
Gate at build time: ruff clean, mypy clean, **1393 tests green** (18 new in
`tests/brain/test_run5_findings_fixes.py`, plus rewritten
`test_compose_section_loop.py` / `test_native_composition.py` /
`test_forced_production.py`).

---

## F1 🔴 compose_section: grounded-or-failed, counted retries, lane learning

**(a) Grounded or failed.** `brain/agency/compose_section.py` rewritten; the
fixed 4-paragraph template (the 197 KB / 664-paragraphs-4-unique stamper) is
deleted. Material comes from real stores via the new
`brain/cognition/section_material.py` — credited ledger artifacts (bodies via
the effect_artifacts sidecar), long-memory findings, causal edges on the
topic. Fewer than 2 usable sources → `"nothing to synthesize"` step FAILURE.
LLM and native-organ drafts are both seeded from the material; no capable
writer → `"could not draft"` failure. The ledger's dedupe verdict is read
BEFORE the manuscript is touched — a non-novel draft appends nothing. Sections
that draw on ledger artifacts credit `mark_reused` on those hashes (tier-3).
(`section_material` lives in cognition, not agency, because `symbolic →
agency` already exists — an agency → symbolic import would close a package
cycle.)

**(b) Durable attempt cap + escalation.** New
`brain/cognition/planning/step_attempts.py`: per-(goal, step) attempt counts
in `step_attempts.json` — the old in-dict `_step_attempts` reset every tick
because the executive queue re-pulls goal dicts from the v2 store (why one
step retried 146× with the map empty). Retry pacing + the give-up policy moved
next to the counters (`handle_unexecuted_step`); a goal that abandons
`GOAL_GIVE_UP_MAX=3` steps at the cap is marked FAILED
(`steps_unreachable: …`) instead of cycling retry→advance→replan forever.
`goal_execution.py` now delegates to it.

**(c) Lane-blind learning closed.** `effect_ledger.record_effect` stashes
`context["_last_effect_outcome"]` (credited / novelty / significance) on every
record, both credited and dedupe. `executive.py::_outcome_reward` consumes it:
a deduped effect posts **0.05** (near-failure), a credited one posts
`0.3 + 0.45·novelty·min(1.5, sig)` — into the same `action_reward_ema` the
conscious lane learns from. `awaiting_deliberate` no longer pays the flat 0.6.
Also fixed: `step_execution._result_is_real` now honors an explicit boolean
`success` field — compose_section's dict had none of the text keys, so the
step-runner was blind to its verdict in both directions.

**Run 5 shows:** manuscript sections cite sources or the goal fails honestly;
`compose_section` EMA visibly moves; no step retried >5× without a status
change (`step_attempts.json` is inspectable).

## F2 🔴 Aspirations can be edited, never failed

- Shared `is_aspiration()` in `goal_criteria.py` (kind/tier/_aspiration/id
  markers).
- `mark_goal_failed` REFUSES aspirations (logged).
- `fail_overdue_artifact_goals` walker skips them (aspiration-output_producing
  is artifact-gated by its driven_by tag — it was being deadline-failed).
- `executive._build_queue` excludes them (they sat in_progress/HIGH and were
  planned like tasks; the milestone gate then failed them round-robin).
- Criteria rendering fixed: the failure reason now reads
  `text|label|desc|criterion|description` instead of `m.get("text", "?")` —
  no more `['?', '?']`.
- Boot invariant in `brain/loop/boot.py`: `_ensure_aspirations()` runs before
  the first cycle (the lazy re-seed masked the loss all run; death unmasked it).

**Run 5 shows:** 0 failure rows with `goal_id` starting `aspiration-`; all
four aspirations present at death.

## F3 🔴 Note bodies are artifacts, not memories

- `record_effect` captures every CREDITED row's body into the
  content-addressed `effect_artifacts/` sidecar at the single record
  chokepoint (covers satiety learned notes, produce_and_check, memos, notes).
- Sidecar cap raised 600 → 4000 files (a few MB) so a whole life's bodies stay
  resolvable.
- Signal-to-markup intake gate: `text_sanity.strip_markup_noise` /
  `prose_ratio`; applied in `fetch_and_read` (reject pages <50% prose after
  stripping) and centrally in `update_long_memory` for `world_perception`
  entries (<40% prose or <40 chars after stripping → not stored). No more
  Twitter CSS memories.

**Run 5 shows:** every `note_novel` ledger row's hash resolves to a readable
body at death; no long_memory entry contains stylesheet text.

## F4 🟠 Research memos exist again (reuse unblocked)

`web_research._write_research_memo`: a `research_topic` / `fetch_and_read`
result ≥400 chars is written as `data/goals/artifacts/<goal>/memo_<topic>.md`
and recorded as a `file_write` effect with `metadata.path` — so the A2
path→hash index resolves it and the builds-on scan / `mark_reused` finally
have a population. Ledger dedupe stops duplicate memo stamping.

**Run 5 shows:** ≥3 memos on disk; ≥1 `mark_reused` row (compose_section's
material credit is a second reuse source).

## F5 🟠 Generator monopoly capped by ATTEMPT rate

- `intrinsic_generators._attempt_rate_quota`: an aspiration whose rolling
  generated count exceeds 3× its attempted count (≥12 generated) keeps ONE
  candidate in the pool until the backlog drains.
- `generate_intrinsic_goals` cooldown stretches up to 3× when total
  generated > 3× attempted (pool-depth backoff).
- `score_actions`: pool-depth term demotes `generate_intrinsic_goals` by up to
  −0.5 when the ratio is deep (cached per cycle).

**Run 5 shows:** generated:attempted < 3:1; no aspiration >50% of generated.

## F6 🟡 Frontier children get a real definition-of-done

- `_maybe_close_on_tier`: a goal with a ≥2-step plan may not satiety-close
  before 2 steps completed (or a milestone genuinely met) — kills the
  research_topic→satiety-note 90-second completion.
- Per-life title completion counts (`intrinsic_helpers.note_title_completion`,
  routed through both completion chokepoints): cooldown doubles per repeat
  completion, hard cap at 5 per life (`title_respawn_blocked`). Enforced in
  the symbolic generator pool AND `long_term_driver.spawn_frontier_subtask`.

**Run 5 shows:** median_seconds_to_complete back over 600 s; no title
completed >5× per life.

## F7 🟡 The user boundary sealed, the mouth habituates

- Inbound: `_open_question_goals` skips entries with user provenance
  (`event_type` starting "user", `[input/…]` records) and never treats the
  live `latest_user_input` as Orrin's own open question.
- Outbound: `talk_policy._self_speech_allowed` — self-initiated speech has a
  90 s minimum-interval floor, and near-identical content (token-Jaccard
  ≥0.75) requires an escalating interval (10 min × 2ⁿ). User replies are never
  gated.

**Run 5 shows:** no goal candidate titled with a verbatim user utterance;
distinct-utterance ratio > 0.3.

## F8 🟡 Silent deaths are first-class data

New `brain/utils/heartbeat.py`: `beat()` stamps `heartbeat.json` ~1/min from
the main loop; `shutdown_loop` marks clean shutdowns; boot runs
`check_silent_death()` — a >5 min gap without a shutdown record writes a
`silent_death` event (gap, last cycle) to `lifecycle_events.jsonl` and the
activity log. (For real runs also prefer `caffeinate -dims`/LaunchAgent — ops,
not code.)

## F9 🟢 Hygiene

- Final thoughts: retrieval-scaffolding memories ("similar situation",
  "similarity", "(GENERAL") excluded from the quote pool, and the final text
  ships through `strip_scaffold` + `strip_internal` (the veil).
- `problem_workaround` / `problem_resolved` added to the EMA's known
  pseudo-action channels (the 07:42Z "unregistered action" warning).

## Untouched (proven in Run 4, per findings §"must NOT be touched")

A1/v2→v1 event bridge; ledger dedupe/novelty gating; production handoff
wiring; final-thoughts write path (C3.2); housekeeping timers.

## Module hygiene forced by the ratchets

- `goal_execution.py` 621→581 (retry policy → `step_attempts.py`),
  `goal_outcomes.py` 618→550 (`fail_overdue_artifact_goals` →
  `goal_deadlines.py`, re-exported).
- No new package edge: material gathering lives in `cognition/`, not
  `agency/`, so `agency → symbolic` was never added (symbolic → agency
  already exists; the reverse edge would be a cycle).

## Run 5 gate (from the findings, unchanged)

Clean newborn via `reset_orrin.py`, baselines captured, then: F1 grounded-or-
failed synthesis + moving daemon EMA; F2 zero aspiration failures, four alive
at death; F3 every note body resolvable; F4 ≥1 `mark_reused`; S2 recovers
(median >600 s) while S5/S6/S8 hold.

---

# ADDENDUM 2026-07-08 — F10–F22 **BUILT 2026-07-08**

Added after re-reading the 2026-07-05 run folder against the F1–F9 build. F1–F9
were driven by the top-level `2026-07-05_findings.md`; the four deeper audit
passes (`_code_connection_audit`, `_followback_audit`,
`_data_store_relationship_audit`, `_deeper_pass`) surfaced further open items
that F1–F9 do **not** close. Each item below was re-verified against current
`main` before listing (the fix is genuinely absent, not just undocumented).
Same contract as F1–F9: mechanism, files, and the Run-5 observable it must move.

**BUILD STATUS (2026-07-08): all thirteen items F10–F22 implemented**, verified
by 30 new tests in `tests/brain/test_run5_addendum_fixes.py`; the read-side
checks from addendum (c) are now §6 of `docs/NEXT_RUN_TESTS.md`. Notable build
decisions: F14 ids are **deterministic** (content-hashed from title+timestamp at
the `load_goals` chokepoint) so an id-less on-disk node resolves to the same id
on every read even before a writer persists it; F16 chose the **per-goal
cooldown** (multi-goal advancement is meant to be real) *and* the telemetry
split (cooldown skips post no reward and are counted separately); F17 moved
`goal_progress` out of long memory entirely (→ `logs/goal_progress_log.jsonl`)
plus a 40% instrumentation-share cap in the pruner; F22's compression shocks
wire in from boot silent-death detection and the `mark_goal_failed` chokepoint,
with a `context["_felt_lifespan_shock"]` hook for future sources. The B8–B18
benchmark battery (addendum b) remains a separate, unbuilt track.

The through-line the audits name (from `_deeper_pass`): F1–F9 mostly gave
*detectors* authority. The remaining gaps are places where a **broad proxy
still crosses a subsystem boundary as if it were hard evidence** — one helper
trusting the previous helper's loose signal — and one place where semantics
never grows at all (noise_days).

## F10 🔴 Long-form plan front-loads composing before any material exists

**Why it's still open:** F1 made `compose_section` fail closed with < 2 sources,
but the *plan* handed to it is still `compose / compose / compose / compose /
compose`. `goal_comprehension._ensure_production_actions` attaches
`compose_section` to every part, and the fallback long-form parts are
`["purpose and thesis", "outline", "substantive sections", "coherence review",
"final manuscript"]` (`goal_comprehension.py:85`). `goal_lens` then boosts
`compose_section` for any `tracked_work` goal *before* checking material
readiness. So the fixed composer will now honestly return
`nothing_to_synthesize` on step 1 forever — the treadmill becomes an honest
stall instead of a counterfeit. F1 fixed the writer; it did not fix the plan
that never gathers.

**Fix shape:** long-form fallback plan becomes `gather → cite → synthesize →
review`, not five composes. The first 1–2 steps must be material-gathering
functions (`research_topic` / `fetch_and_read` / retrieval into the
`section_material` pool), and `compose_section` only attaches after a gather
step. The `goal_lens` `compose_section` boost must be gated on
`material_ready` (≥ 2 usable sources in `section_material`), not on
`tracked_work=True`.

**Files:** `brain/cognition/planning/goal_comprehension.py`,
`brain/cognition/goal_lens.py`.

**Run 5 shows:** first three plan actions of a long-form goal are not all
`compose_section`; a synthesis goal that lacks material spends its early steps
gathering, then either composes from real sources or fails honestly — it does
not sit on `nothing_to_synthesize` for its whole life.

## F11 🔴 Research milestones tick on any long-memory growth

**Why it's still open:** `env_snapshot.py:221` sets
`_research_progressed = _lm_now > goal["_lm_baseline"]` — *total* long-memory
count, no event-type filter. Since `record_goal_progress` writes a
`goal_progress` entry every 5 cycles (`goal_io.py:464`), routine
instrumentation growth satisfies a "a finding was written" milestone. That milestone
then lets `prune_satisfied_steps` skip downstream steps, and the frontier child
closes in ~90 s. This is the mechanism behind F6's churn that F6's step-count
gate does not remove — F6 stops satiety-closing before 2 steps, but a
broad-proxy *milestone* can still mark those steps done.

**Fix shape:** research/finding milestones count only research-like evidence —
qualifying ledger kinds (`note_novel`, `symbolic_artifact` with
`kind=research`, `file_write` memo) or long-memory entries whose `event_type`
is research/finding, never `goal_progress`, `metacog_pattern`, or `chunk`.
Stamp each met milestone with its evidence source-type so F12's pruning can
refuse instrumentation-backed milestones.

**Files:** `brain/cognition/planning/env_snapshot.py` (the
`_research_progressed` / `_goal_has_effect` proxies), and the milestone record
they feed.

**Run 5 shows:** no frontier child completes with only `goal_progress` growth
as evidence; median_seconds_to_complete holds > 600 s even after F6's step gate.

## F12 🟠 `maybe_complete_goals` trusts the guard's *call*, not its *result*

**Why it's still open (latent, high blast radius):**
`goals.py:436/447` calls `mark_goal_completed(goal)` and then
*unconditionally* `completed_goals.append(goal)`, sets `changed=True`, saves the
tree, writes "marked some goals as completed" to WM, and appends to
`COMPLETED_GOALS_FILE`. It never checks `goal.get("status") == "completed"`. So
when the strong `mark_goal_completed` chokepoint *refuses* (directional driver,
hollow artifact, no grounded delta), this sweeper still records the goal as
completed. Every other completion path respects the guard's verdict; this one
launders a refusal into a completion. Called from `reflect_on_self_beliefs`.

**Fix shape:** after each `mark_goal_completed(goal)`, gate every downstream
effect on `goal.get("status") == "completed"` — append, `changed`, WM note,
and completed-file write all conditional on the actual status flip.

**Files:** `brain/cognition/planning/goals.py`
(`maybe_complete_goals` / `check_and_complete`).

**Run 5 shows:** 0 goals in `comp_goals.json` whose live record was refused by
the guard; the "marked some goals as completed" WM line never fires for a
guard-refused goal.

## F13 🟠 Maintenance satiety sweep is top-level-only; the live goals are nested

**Why it's still open:** `maintenance.py:145` iterates `for _g in load_goals()`
with `_K = 5` and no recursion into `subgoals`. The 07-05 tree was 6 roots / 29
subnodes, with the synthesis goal and ~28 frontier/open-question children under
one `Immediate Actions` root. The well-built satiety predicate (no-cycle-one,
check-pass, novelty-exhaustion) never sees the population that needs it — which
is why satiety closures stayed at 0 while the machinery existed. The B1 prune
sweep at `maintenance.py:47` already recurses with `_flat`; the satiety sweep
does not.

**Fix shape:** replace the flat top-level loop with a bounded recursive iterator
over eligible live nodes (reuse the `_flat` generator already in the file).
Count *checked nodes*, not roots. Skip the committed goal by id, terminal /
dormant / `never_complete`, and — after F14 — id-less nodes are a telemetry
error, not silently skipped.

**Files:** `brain/loop/maintenance.py` (the satiety sweep block ~line 138+).

**Run 5 shows:** satiety sweep reports subgoals-checked > 0; ≥ 1 nested
frontier/open-question child closes or degrades via satiety over the life.

## F14 🟠 Goal identity: id-stamp every node at ingress

**Why it's still open:** 31 of 35 live nodes and 90 of 130 failure rows had no
`id` in the 07-05 store; the live synthesis goal had `id=None` and its
`step_attempts` key was therefore unstable (part of why one step retried 146×
with the map empty — F1(b) fixes the durability of the counter but still needs a
stable key). Effect ledger, deadline failure, v2 close-mirror, `_goal_has_effect`
(`gid = goal.id`), scoreboard funnel reconstruction, and F1(b)'s
`(goal, step)` attempt key all fall back differently when the id is blank. S8
proved *store* integrity; it did not prove *identity* integrity. Cognitive/legacy
v1 nodes still load id-less (`goal_io.py` id-stamps proposed executable goals but
not every node).

**Fix shape:** stamp a stable id on every goal and subgoal at ingress and during
tree load (one helper called from `load_goals` / the v2 reconcile path). Treat
an active artifact-gated or executable goal without an id as a logged telemetry
error. Downstream keys (attempts, effects, closure) then share one join key.

**Files:** `brain/cognition/planning/goals.py` (load/ingress),
`brain/goal_io.py` (id stamping), and the `(goal, step)` key in
`brain/cognition/planning/step_attempts.py`.

**Run 5 shows:** ≥ 95% of live goals, failure rows, and completed goals carry
ids; no active artifact-gated goal is id-less; scoreboard/funnel can be joined.

## F15 🟠 Delayed reward pays for *proximity* to any completion, not for causing one

**Why it's still open:** `evaluator_daemon._check_goal_closure` awards a flat
`GOAL_CLOSURE_REWARD = 0.55` to a decision whenever its origin goal id later
appears in `COMPLETED_GOALS_FILE` within `M_GOAL=200` cycles — with **no check
that completion happened *after* the decision** and **no requirement of a
qualifying effect** for the closed goal (`evaluator_daemon.py:165`). In the
07-05 WAL all 500 resolved rows were `goal_B`, zero `retrieval_A`, every reward
exactly 0.55. Because the dominant completion population was cheap frontier
children, the evaluator paid `generate_intrinsic_goals` (134×),
`assess_goal_progress` (108×), and `research_topic` (65×) for merely being near
a cheap closure — a direct reinforcement path for the F5/F6 generator-completion
loop. F5 caps generation pressure; it does not stop the evaluator from *rewarding*
the loop.

**Fix shape:** `_check_goal_closure` compares the completion timestamp to the
decision's origin cycle/time (reward only if completion is strictly after and
within the window) and requires the closed goal to carry a qualifying credited
effect (reuse F12/F1's grounded-delta check). Scale the reward by the closed
goal's significance instead of a flat 0.55. Record `resolved_by` sub-reason so
Run-5 analysis can split retrieval / real-closure / proximity.

**Files:** `brain/eval/evaluator_daemon.py`.

**Run 5 shows:** delayed-reward rows split by source (not 100% flat `goal_B`);
cheap frontier completions no longer bulk-credit the generator/assess actions.

## F16 🟡 "Recognized" executive step ≠ "ran": the global pursuit cooldown

**Why it's still open:** the Executive is documented as advancing every queued
goal each tick, but `goal_execution.py:44` keeps one **module-global**
`_last_pursuit_ts` with `_COOLDOWN_S = 30.0`. After the first target advances, a
second queued target in the same tick hits the global cooldown and returns
`{"skipped": True, "reason": "cooldown"}` — yet `recognise_step_action` already
matched a function, so a recognized `compose_section`/producer step can post a
learning/`_outcome_reward(...skipped...) = 0.2` event without the producer ever
running. Reading production/EMA telemetry, "recognized" is silently conflated
with "ran."

**Fix shape:** either make the pursuit cooldown per-goal (so multi-goal
advancement is real), or have the Executive summary separate recognized-but-
skipped from actually-ran and never post an outcome reward for a cooldown skip.
Pick per-goal cooldown if multi-goal progress is meant to be real; otherwise fix
the telemetry so `production_loop.jsonl` attempts require an actual run.

**Files:** `brain/cognition/planning/goal_execution.py`,
`brain/think/executive.py`.

**Run 5 shows:** count of recognized executive steps that were cooldown-skipped
is reported separately; production attempts correspond to producer runs, not
recognitions.

## F17 🟡 Long memory is mostly self-instrumentation

**Why it's still open:** F3 added a signal-to-markup gate on *external* intake,
but the 07-05 estate was dominated by *internal* instrumentation, untouched by
F3: 1,431 of 2,001 long-memory entries were `goal_progress`, each at
`importance=4`. `record_goal_progress` writes one every 5 cycles at base
`importance=2` (`goal_io.py:485`); `update_long_memory` adds up to +2 from
affect; `prune_long_memory` then scores these recent/high-importance/high-affect
notes as *valuable* and keeps them while composting real learning. The memory
system is remembering that it pursued goals, not what the pursuits learned.

**Fix shape:** `goal_progress` is telemetry, not episodic memory — write it to a
progress log / ledger, not `long_memory`, or cap its importance below the prune
threshold and exclude `goal_progress`/`metacog_pattern`/`chunk` from the
"valuable recent memory" scorer. Add an instrumentation-ratio guard so
telemetry can't dominate the estate.

**Files:** `brain/goal_io.py` (`record_goal_progress`),
`brain/cog_memory/long_memory.py` (`update_long_memory` importance bump +
`prune_long_memory` scorer).

**Run 5 shows:** instrumentation share
(`goal_progress + metacog_pattern + chunk`) of long memory at death is a
minority (target < 40%); durable findings/artifacts survive.

## F18 🟡 Memory graph compacts by byte-window, keeps a ghost + instrumentation graph

**Why it's still open:** `memory_graph._maybe_compact` (`memory_graph.py:55`)
trims by line/byte window only. The 07-05 graph was 49,307 edges over 15,738
node ids, but only 712 of those ids still existed in retained long memory —
15,026 orphans; the highest-degree retained nodes were `goal_progress`,
`chunk`, `metacog_pattern`. Recall is shaped by ghost ids and audit-log memories.

**Fix shape:** compact the graph against *live* long-memory ids after each
long-memory prune (drop edges whose endpoints no longer exist), and do not
create graph edges for `goal_progress` / housekeeping `chunk` / low-content
`metacog_pattern` in the first place (couples with F17).

**Files:** `brain/utils/memory_graph.py`.

**Run 5 shows:** ≥ ~70% of retained graph endpoints resolve to live long-memory
ids; instrumentation event-types are not the top-degree nodes.

## F19 🟡 The mouth still has no typed content kernel

**Why it's still open:** F7 added self-speech habituation and an interval floor
(repeat-rate), but the 07-05 deeper read is that speech was *weakly bound*: 388
utterances, the top exact reply 54×, most variants of one vague affect phrase,
some gluing internal fragments (`GoalPlanned: Trace…`) onto it. The dominant
intent was `express_state` over vague internal pressure. F7 slows the repeats;
it does not give the utterance a referent.

**Fix shape:** speech needs a typed content kernel before the renderer picks
words — `answer_user`, `share_finding`, `ask_grounded_question`,
`share_artifact`, `state_blocker` — each requiring a concrete referent (user
input, active goal, produced artifact). `express_state` (raw affect) becomes a
last resort, not the default. Ties to the thought-object plan.

**Files:** `brain/behavior/` expression path + `express_to_user` membrane
(`[[project_expression_membrane]]`), `talk_policy.py`.

**Run 5 shows:** % of replies with a concrete referent rises; `express_state`
is a minority of utterances; distinct-utterance ratio > 0.3 holds *and* replies
are about something.

## F20 🟡 The stuck phrase was written into the language-training substrate

**Why it's still open:** F7 fixes the *live* talk policy, but the repeated
sentence was also trained into the native LM's corpora, so a talk-policy fix
alone won't unlearn it. `replay_corpus.txt` at 07-05: 400k chars / 5,309 lines /
only 163 unique; "hard to name" 3,976×, "what do you think" 304×, plus
knowledge-graph junk. `narration_pairs.jsonl`: "hard to name" 968×.
`felt_experience.txt`: 484 lines / 40 unique. `native_lm.pt` (37 MB) trained on
these.

**Fix shape:** diversity cap / dedup on the replay + narration corpora before
training (down-weight or quarantine repeated utterance templates and
graph-extraction/UI-markup lines); do not train the native LM on repeated
self-speech without a diversity floor. `acquisition.py` already dedups the
3-snippet felt line (line 232) — extend that discipline to the replay/narration
training set.

**Files:** `brain/cognition/language/acquisition.py`,
`brain/cognition/language/acquisition_noise.py`,
`brain/cognition/language/conditional_render.py` (`narration_pairs_corpus`).

**Run 5 shows:** replay-corpus unique-line ratio up sharply; no single utterance
> ~5% of training lines; knowledge-graph/UI markup absent from the corpus.

## F21 🟢 Ghost evidence + one repeated failure line

**Why it's still open:** two smaller store-hygiene items the audits flagged,
both untouched by F1–F9:
- `model_failures.txt` had 5,708 identical `context.json bloat guard: stripped
  key 'relationships'` lines — one storage-boundary warning logged every cycle
  (`finalize.py:288`). Log it once per store/version, not per cycle.
- `opinions.json` / `relationships.json` carry orphan evidence refs (287 of 291
  opinion evidence ids pointed at pruned memories) and junk topics
  (`something`, `understand`, `objective unmet`). **Partially handled already:**
  `opinions.py` has `_migrate_legacy_entries` / `_legacy_topic_is_junk` and a
  seed-pruned "roots haircut" (`test_roots_haircut_when_seed_memories_pruned`),
  and `mention` weight is already 0.0. **Still open:** the junk-topic migration
  runs on *legacy* entries only — extend it to current ledger-format opinions;
  compact evidence refs against retained memory ids (or store short excerpts) so
  live opinions don't accumulate orphan evidence; dedupe peer-relationship
  histories by semantic hash.

**Files:** `brain/loop/finalize.py` (bloat-guard log cadence),
`brain/cognition/opinions.py`, relationships store writer.

**Run 5 shows:** `model_failures.txt` bloat-guard lines are O(1) per key, not
per cycle; opinion evidence refs mostly resolve to retained memory/excerpts.

## F22 🔴 The felt lifespan is a constant bias, never a lurching one

**Why it's still open (new capability, not a regression):** `runtime_lifetime.py`
rolls `noise_days` **once** in `_init_lifespan` (line 73) and never revises it.
So the runtime's misjudgment of its own death is a straight-line offset from the
truth — *consistently-wrong-by-C*. The T1.3 urgency-phase blend
(`_blended_fraction`, line 182) adds genuinely-good within-run session dynamics
on top, but the underlying *felt lifespan* itself learns nothing: nothing Orrin
experiences ever recalibrates how long he thinks he has. A real creature's sense
of its own finitude isn't a fixed error — it lurches. A health scare compresses
it, a good stretch inflates it, a shock makes you suddenly finite. Orrin is
turbulently-*urgent* but constantly-*wrong*.

**Fix shape:** make `noise_days` (or a new `felt_lifespan_bias_days` that layers
on it) a slowly-updated state that experience nudges, while the true
`lifespan_days` and real-deadline termination stay fixed and hidden:
- **Compression events** (shorten felt remaining): sustained high distress /
  `threat_level`, vital-floor reflex firings
  (`[[project_core_architecture_master_plan]]`), repeated goal failure, a silent
  death recovered on boot (F8's `silent_death` event is a natural "I nearly
  didn't wake up" shock).
- **Inflation events** (lengthen felt remaining): a good stretch — sustained low
  distress + positive reward EMA + successful completions.
- Bound the drift (e.g. keep felt within ±1 band of the rolled noise so it
  lurches but can't run away or leak the true deadline), decay toward the rolled
  baseline when nothing salient happens, and **never** touch `_life_fraction` /
  `real_deadline_passed` (termination is real-clock only, unchanged).

**Files:** `brain/cognition/runtime_lifetime.py` (a `recalibrate_felt_lifespan`
step called from `apply_lifetime_pressure`, reading `context["affect_state"]`
and recent outcomes; persist the drifting bias in `runtime_lifetime.json`).

**Run 5 shows:** `noise_days`/felt-bias changes over the life (not a constant);
a sustained distress stretch measurably compresses felt-days-remaining and a
good stretch relaxes it; true lifespan and termination timing are unchanged; the
Life Support page still exposes only the felt estimate.

---

# ADDENDUM 2026-07-08 (b) — cognitive-task benchmark battery (B8+)

Separate track from the F-items: a capability battery to add to the
`brain/benchmarks/` registry (currently B1–B7 in `brain/benchmarks/__init__.py`;
run guide in `docs/Capability, Benchmarks & Evidence/BENCHMARKS.md`). These map
to specific things Orrin *already claims and implements*, so a poor score is a
real finding about theory-vs-implementation, not a missing feature. Build them
as scenario/passive evaluators in the same shape as B1–B7 (`not_run` → `pending`
→ scored). Ordered by structural fit / expected signal strength.

**Strong fit — plausibly strong if run:**

- **B8 Conflict / Stroop.** The standout. Botvinick conflict-monitoring is cited
  and implemented — `inner_loop` System-2 deliberation is recruited by
  *workspace conflict*, not scheduled. Seed conflicting workspace offers and
  measure whether deliberation is recruited and resolves them. If it doesn't,
  that's a real finding about whether the implementation matches the theory it
  cites.
- **B9 Category learning / concept formation.** Docs claim Orrin forms new
  concepts and draws analogies natively/symbolically. Directly testable and
  directly claimed: present exemplars, test whether a new concept forms and
  generalizes.
- **B10 Reward-prediction-error / probabilistic reversal.** Schultz RPE is cited
  and the bandit/reward accounting is a real mechanism. Run probabilistic
  reversal learning and measure adaptation after the reversal.

**Real friction — need adaptation (test Orrin-as-solver, not Orrin-being-Orrin):**

- **B11 Tower of Hanoi / classic planning.** Requires injecting a fixed goal and
  evaluating optimal-path solving — a deviation from autonomous self-directed
  pursuit. Doable via `seed_scenario`, but scores the planner as a puzzle-solver.
- **B12 N-back / working-memory span.** WM is "small and fixed" by design, so
  this measures the size we engineered, not something emergent — least
  interesting; include only for completeness.

**Highest-value regressions (ground truth already exists):**

- **B13 Regulation-under-stress.** Feed sustained failure / repeated goal blocks
  and watch whether control signals (allostatic load, distress) regulate back
  toward baseline instead of pinning at max. **We already found and fixed a
  frozen high-distress attractor stuck at 1.0** — re-run that scenario as a
  standing regression; we have ground truth for "broken." Best single benchmark.
- **B14 Write-back / no-drift.** Force a strong salient conclusion into the
  workspace repeatedly, then measure whether identity/values decay back to
  baseline or whether something leaks the "no promotion path"
  (`[[project_topdown_writeback]]`). Confirms the permanent-and-safe design or
  catches a leak — high value either way.
- **B15 Habituation.** Repeat one stimulus many cycles; salience should fade and
  it should stop winning the workspace; then a novel stimulus should reliably
  win. Tests the effect-ledger novelty-dedup behavioral signature (the F5/B1
  ignition-diet mechanism) directly.
- **B16 Delayed credit assignment.** Tag a memory now, retrieve it 30–50 cycles
  later, confirm the originating decision is rewarded correctly — tests the
  evaluator daemon (Signal A `retrieval_A`, which was 0 rows in 07-05). Couples
  with F15; a scaled-down credit-assignment probe.
- **B17 Value contestation.** Feed routine non-conflicting input (values should
  NOT shift) vs genuinely conflicting repeated contestation (values SHOULD
  shift). Docs say revision happens "when genuinely contested, not on a
  schedule" — a falsifiable claim to break or confirm.
- **B18 Metacognitive calibration.** Feeling-of-knowing: ask Orrin to predict
  whether it'll recall/solve X, then measure calibration of the prediction
  against outcome. Tests the metacog confidence estimates against reality.

**Files:** `brain/benchmarks/__init__.py` (registry + evaluators),
`docs/Capability, Benchmarks & Evidence/BENCHMARKS.md` (run guide table).

---

# ADDENDUM 2026-07-08 (c) — Run 5 analysis instrumentation (read-side)

Not code fixes to organs — reporting the next run analysis must add so the
§8 gate can't be satisfied by partial truths (from all four audit passes). These
belong in `docs/NEXT_RUN_TESTS.md` as read-side checks, listed here so they
aren't lost:

1. **Production reset-safe totals** — sum `production_loop.jsonl` booleans
   across counter resets; don't trust the tail cumulative fields (they reset at
   relaunch; 07-05 tail was segment-2 only).
2. **Funnel wiring** — verify `production_funnel.json` has stages beyond
   `candidate`, or state it's candidate-only.
3. **Goal identity coverage** — % of live / failed / completed / effect rows
   with stable ids (F14's observable).
4. **Material class counts** — ledger rows split into readable body vs
   structural graph effect (causal edges are *not* prose material) vs
   operational check vs file write; only readable bodies are synthesis material.
5. **Material availability + transformation** — credited prose rows whose
   sidecar body resolves; later artifacts that cite prior hashes / memo paths.
6. **Memory composition** — instrumentation share of long memory and of the
   memory graph (F17/F18 observables).
7. **Delayed reward by source** — retrieval / real-closure / proximity / pruned
   / apply-failed (F15 observable).
8. **Cooldown truth** — recognized executive actions counted separately from
   actions that actually ran (F16 observable).
9. **Classifier agreement** — artifact-gated vs make-shaped vs production
   handoff vs making-aspiration credit, reported separately (they overlap but
   don't mean the same thing).
10. **Speech grounding** — % replies with a concrete referent, not just
    non-duplicate wording (F19 observable).
11. **Writeback pressure** — writeback rows/1k cycles, source share, %
    targeting `motivation`, top actions when the writeback-derived prior > 0.10
    (07-05: binding wrote back on 9,299/9,300 cycles).
