# Data-store relationship audit - 2026-07-05 run

This is a sixth pass over the 2026-07-05 staging run. It checks the large or
under-read data files against the newer findings from the code and follow-back
audits: identity gaps, broad progress proxies, writeback/binding pressure,
material availability, goal completion credit, and learned repetition.

The result is not "everything is broken." Several stores contain useful
signals. The problem is that different stores use the word "success" or
"evidence" for different things, and later consumers can accidentally treat
bookkeeping, causal edges, or repeated narration as production material.

## Files checked closely

Large or previously under-read stores:

- `brain/data/memory_graph.jsonl` - 49,307 edges, 7.5 MB.
- `brain/data/production_loop.jsonl` - 15,553 rows, 6.8 MB.
- `brain/data/telemetry_archive.jsonl` - 15,540 rows, 5.8 MB.
- `brain/data/events.jsonl` - 3,000 tail decisions, 2.0 MB.
- `brain/data/trace.jsonl` - 3,995 tail learning/choice rows, 1.2 MB.
- `brain/data/evaluator_wal.jsonl` - 661 retained delayed-reward rows.
- `brain/data/reflection_log.json` - 1,555 rows.
- `brain/data/habituation.json` - 5,038 keys.
- `brain/data/behavior_changes.json` - 250 corrective-change rows.
- `brain/data/relationships.json` - 119 KB.
- `brain/data/opinions.json` - 24 opinions.
- `brain/data/knowledge_graph.json` - 205 entities, 113 relations.
- `brain/data/causal_graph.json` - 320 causal edges.
- `brain/data/language/replay_corpus.txt`, `narration_pairs.jsonl`,
  `felt_experience.txt`, and `native_lm.pt`.
- `brain/data/effect_ledger.jsonl`, `effect_artifacts/`, `tracked_work/`,
  `comp_goals.json`, `goals_mem.json`, and `aspiration_scoreboard.json` as
  cross-check anchors.

## Executive read

The deeper data-store pattern is:

1. Long memory is dominated by instrumentation.
2. The memory graph links mostly to that instrumentation and to pruned memories.
3. The effect ledger stores real structural effects, but most credited effects
   have no readable sidecar body.
4. Production-loop success is not cycle-local proof of a produced artifact.
5. Delayed learning credit is dominated by goal-closure reward, not retrieval.
6. Completed-goal records do not consistently prove definition-of-done
   satisfaction.
7. The replay language data learned the stuck phrase directly.

Good news: the system has multiple durability channels now: effect ledger,
causal graph, knowledge graph, evaluator WAL, telemetry, and language replay.
Bad news: those channels are not typed sharply enough for downstream consumers.
Structural learning, self-instrumentation, readable material, and real goal
completion are still too easy to blur.

## 1. Memory graph is a ghost graph plus an instrumentation graph

`memory_graph.jsonl` is one of the most important files I had not inspected
closely enough.

Raw counts:

- 49,307 edges.
- 15,738 unique graph node ids.
- 2,001 retained long-memory entries at death.
- only 712 graph node ids are still present in retained long memory.
- 15,026 graph node ids are orphans.
- 98,614 endpoint references total.
- 46,147 endpoint refs point to retained long-memory ids.
- 52,467 endpoint refs point to orphan ids.
- only 3,995 edges have both endpoints retained.
- 38,104 edges are orphan -> retained.
- 7,155 edges are orphan -> orphan.

That means the graph is not just a graph of current memory. It is mostly a
graph over memories that no longer exist.

The retained side is also dominated by instrumentation:

| Retained event type | Endpoint refs |
|---|---:|
| `goal_progress` | 38,084 |
| `chunk` | 3,751 |
| `metacog_pattern` | 3,477 |
| `incubated_insight` | 218 |
| `foundational` | 154 |

The top-degree retained nodes are `goal_progress`, `chunk`, and
`metacog_pattern` entries. One top node is literally a chunk of repeated
goal-avoidance metacog patterns.

Good: `brain/utils/memory_graph.py` has a per-entry edge cap and byte-based
compaction. It already knows old edges can point at faded memories.

Bad: compaction is only by byte/line window. It does not compact against live
long-memory ids, and it does not filter out instrumentation event types. Recall
can therefore be shaped by ghost ids and by high-degree audit-log memories.

Fix shape: compact memory graph by live ids after long-memory pruning. Do not
create graph edges for `goal_progress`, housekeeping chunks, or low-content
metacog telemetry unless explicitly requested for diagnostics.

## 2. The ledger preserved effects, not readable material

The earlier audit found missing sidecars for learned notes. The data-store pass
shows the split is wider.

`effect_ledger.jsonl`:

| Kind | Rows | Credited, non-dedupe rows | Sidecar bodies present |
|---|---:|---:|---:|
| `tracked_work` | 166 | 10 | 166 rows reference the 10 retained hashes |
| `symbolic_artifact` | 157 | 129 | 0 |
| `note_novel` | 23 | 23 | 0 |
| `tool_run_effect` | 6 | 6 | 0 |
| `file_write` | 9 | 0 | 0 |

There are 158 credited, non-dedupe ledger effects with no sidecar body:
129 `symbolic_artifact`, 23 `note_novel`, and 6 `tool_run_effect`.

The `symbolic_artifact` rows are not fake. They are mostly causal graph edges:
156 of 157 symbolic rows have `metadata.kind = causal_edge`, and all 156 edge
ids map into `causal_graph.json`.

Good: the system really learned durable causal structure.

Bad: a durable causal edge is not a prose source. If production-loop or
synthesis code treats credited ledger effects as "material exists," it can
mistake structural bookkeeping for readable evidence. The composer needs
different source classes:

- readable material: note bodies, research memos, tracked-work sections;
- structural learning: causal edges, rules, graph updates;
- operational proof: tool checks and sandbox runs.

Only the first class is direct manuscript material.

## 3. Production-loop success is not cycle-local artifact proof

`production_loop.jsonl` contains useful telemetry, but it should be read with
care.

Counts:

- 15,553 rows, cycles 1-15,554.
- `committed_goal_present`: 15,551 rows.
- `goal_lens_active`: 15,550 rows.
- `goal_model_hydrated`: 975 rows.
- `production_attempt`: 352 rows.
- `production_success`: 168 rows.
- committed goal present but no committed id: 23 rows.
- attempts with no committed id: 0.
- one counter reset at JSONL row 11,010 / cycle 11,011 after relaunch.

The row-level relationship to the ledger is weaker than I expected:

- 352 production-attempt cycles.
- 350 ledger cycles.
- only 171 attempt cycles have a ledger row on the same cycle.
- only 11 production-success cycles have a positive-significance ledger row on
  the same cycle.
- 179 ledger cycles are not production-attempt cycles.

So `production_success=True` is not "this cycle wrote a positive artifact."
It is a lagged/drained/cumulative signal. It is still useful, but it cannot
stand alone as evidence of artifact quality or even same-cycle production.

Top attempt ids:

- `Turn what I know about the world into a written synthesis`: 174 attempts.
- `aspiration-self_understanding`: 45.
- `ltc_aspiration-world_knowled_1`: 18.
- `aspiration-genuine_contact`: 14.
- `aspiration-output_producing`: 11.

Top success ids:

- `aspiration-self_understanding`: 32.
- `Turn what I know about the world into a written synthesis`: 21.
- `ltc_aspiration-world_knowled_1`: 18.
- `ltc_aspiration-self_understa_1`: 10.

That confirms the earlier warning: production-loop success counts are not the
same as "the staged producer wrote a good artifact." They are broader effect
telemetry.

## 4. Delayed learning was paid by goal closure, not retrieval

`evaluator_wal.jsonl` was under-read before. It is important.

Retained WAL:

- 661 rows.
- 500 resolved.
- 161 unresolved.
- all 500 resolved rows have `resolved_by = goal_B`.
- zero retained rows resolved by `retrieval_A`.
- every resolved reward is exactly 0.55.

Resolved action credit:

| Action | `goal_B` rewards |
|---|---:|
| `generate_intrinsic_goals` | 134 |
| `assess_goal_progress` | 108 |
| `research_topic` | 65 |
| `attend_goal` | 42 |
| `thread_continue` | 40 |
| `fetch_and_read` | 30 |
| `read_a_book` | 22 |
| `look_outward` | 17 |

Good: using later goal closure as delayed reward is a reasonable idea. A goal
finishing within the window should teach the selector something.

Bad: in this run, cheap frontier completions were the dominant completion
population. The WAL then paid many surrounding actions a flat 0.55 for being
near a goal that closed. It did not prove those actions produced the closure,
and it did not use retrieval evidence at all in the retained rows.

Code connection: `EvaluatorDaemon._check_goal_closure` checks whether the
origin goal id exists in `COMPLETED_GOALS_FILE` while the WAL entry is within
the age window. It does not compare the completion timestamp to the decision's
origin cycle. That can over-credit if a completed id remains visible or if a
goal id/title is reused.

This is a likely reinforcement path for the generator/completion loop:

`cheap completion -> goal_B delayed reward -> generator/research/assess actions
look good -> more candidates and fast closures`.

Run 5 should report delayed reward by source: retrieval, goal closure,
artifact effect, pruned, and apply-failed. Goal closure reward should include a
chronological check and ideally require a qualifying effect for the closed goal.

## 5. Completed goals are terminal, but not all are definition-of-done proven

`comp_goals.json` gives a more precise completion picture:

- 51 completed goals.
- 13 distinct completed titles.
- 8 completed goals missing ids.
- all 51 have terminal plans.
- 0 completed goals still have pending plan steps.
- 42 completed goals have no milestones.
- 9 completed goals have at least one unmet `definition_of_done` criterion.
- 43 completed goals have a credited ledger effect under id/title fallback.
- 8 completed goals do not have a credited ledger effect under id/title
  fallback.

The eight completed goals without a credited effect are all
`Understand Make things - produce work that didn't exist before more deeply`
frontier children. Their plans are terminal, usually one completed step and two
skipped steps.

Good: the old "completed goal with live pending steps" symptom is not present
here. Completed goals are terminal in the plan sense.

Bad: terminal plan does not mean definition-of-done was met. The `definition_of_done`
field is not a reliable proof field in this run. Completion could come through
plan exhaustion, milestone absence, effect fallback, or satiety paths.

This ties directly to the follow-back audit's concern: if broad milestone or
plan-pruning signals make the plan terminal, a completed record can look tidy
while its richer success criteria remain false or absent.

## 6. The aspiration scoreboard cannot support causal reconstruction

`aspiration_scoreboard.json` contains 1,783 events:

- 1,508 `generated`.
- 224 `attempted`.
- 51 `completed`.

But each event has only:

- `ts`;
- `asp`;
- `stage`.

There is no `goal_id`, no title, and no event-local object id. This confirms
the earlier audit: it is pressure telemetry, not a reconstructable funnel.

Good: it tells which drives dominated generation pressure.

Bad: it cannot answer whether a generated candidate became an attempted goal
and then became a completed goal. It cannot diagnose cross-drive credit leaks.

Run 5 needs scoreboard event ids or a separate true funnel file.

## 7. Relationship storage created one noisy failure, not thousands of model failures

`model_failures.txt` has 5,708 lines. All 5,708 are the same class:

`context.json bloat guard: stripped key 'relationships'`

This matters because the raw count looks like broad model instability. It is
not. It is one repeated storage-boundary warning.

`relationships.json` has only six top-level entries, but their histories are
repetitive:

| Relationship | History rows | Main repeated content |
|---|---:|---|
| `peer_reward_auditor` | 59 | unresolved feedback rate |
| `peer_goal_auditor` | 100 | unresolved goals including `Immediate Actions` |
| `peer_signal_historian` | 100 | elevated motivation/confidence and repeated triggers |
| `peer_architect` | 32 | warning about `decide_to_write_code` |
| `anon_e48ccc` | 29 | user/session person state |

Good: the bloat guard did its job. It stopped `relationships` from swelling
`context.json`.

Bad: the failure log became uselessly noisy, and the relationship histories are
mostly repeated peer warnings. The same `Immediate Actions` structural problem
became relationship bloat, model-failure noise, and attention content.

Fix shape: rotate/dedupe peer relationship histories by semantic hash and log
the bloat warning once per store/version, not every cycle.

## 8. Opinions carry orphan evidence and junk topics

`opinions.json` is smaller than the headline stores, but it connects to the
same material-retention problem.

Counts:

- 24 opinions.
- 849 evidence refs.
- 291 unique evidence ids.
- 0 unique evidence ids are present in retained `long_memory.json`.
- 4 unique evidence ids are present in current working memory.
- 287 unique evidence ids are orphaned.
- evidence kinds: 798 `mention`, 51 `observation`.

Good: `mention` has weight 0.0 in the current opinions code, so repeated
mentions do not directly create belief confidence.

Bad: the store still carries topics like `something`, `understand`, `symbolic`,
`concept`, `unknown`, `resolve`, `failed`, and `objective unmet`. Many views
are about words surfacing rather than real stances. Evidence refs mostly point
to memories that no longer exist.

This is a second example of a ghost evidence ledger: like memory graph, opinions
preserve references after the source memories are pruned.

Fix shape: opinion evidence refs should be compacted against retained memory ids
or store short evidence excerpts. Junk-topic migration should run on current
ledger-format opinions too, not only legacy entries.

## 9. Knowledge graph and language replay learned the run's junk

`knowledge_graph.json` is not the worst store, but it did ingest external and
UI junk:

- 205 entities.
- 113 relations.
- entity sources: 74 `web_research`, 33 `long_memory_heuristic`,
  27 `fetch_and_read`, 26 `spacy_propn`, 11 `research`.
- entity types: 106 `unknown`, 38 `organization`, 23 `person`, 23 `concept`.

Top-mentioned entities include:

- `MacBookAir.hsd1.tn.comcast.net` - 2,202 mentions.
- `MacBookAir` - 909.
- `ui` - 418.
- `Changelog` - 280.
- `Radix` - 279.
- `January 2023` - 278.
- `Server Open` - 278.
- `Sections Introduction Components Installation Theming CLI` - 140.
- `Dark Mode CLI Monorepo Skills` - 139.

Some of this came from web/fetch pages and UI documentation. The current
knowledge-graph extractor has good noise gates, but the retained store still
shows the old ingestion path.

The language data makes the consequence visible:

`brain/data/language/replay_corpus.txt`:

- 400,000 chars.
- 5,309 nonempty lines.
- only 163 unique lines.
- `hard to name` appears 3,976 times.
- `what do you think` appears 304 times.
- `metacog` appears 6 times.
- knowledge-graph junk appears in the head and tail.

`brain/data/language/narration_pairs.jsonl`:

- 484 rows.
- `hard to name` appears 968 times across the JSONL.

`brain/data/language/felt_experience.txt`:

- 484 nonempty lines.
- only 40 unique lines.
- top line appears 51 times: "Something present but hard to name. I found
  something I wanted to do."

`native_lm.pt` is a 37 MB learned model modified during the run. I did not load
the binary model, but its adjacent corpus files show what it was trained from.

Good: local language learning is real; there is a replay corpus and a trained
native model artifact.

Bad: it learned the stuck speech pattern and some knowledge-graph junk. Speech
repetition was not only a live talk-policy issue. It was also written into the
language-training substrate.

Fix shape: quarantine or downweight repeated utterance templates before replay.
Do not train native language on graph extraction lines, UI markup, or repeated
self-speech without diversity caps.

## 10. Attention, behavior changes, and habituation all agree on chronic pressure

`attention_history.json` tail:

- 500 rows.
- `signal_source`: 357 `emotion`, 130 `drive_mastery`, 10
  `peer_signal_historian`, 3 `prediction_check`.
- dominant affect: 333 `motivation`, 98 `confidence`, 60 `expected_gain`,
  9 `exploration_drive`.
- hijacks: 0.

This matches the follow-back finding that binding/writeback and the broader
affect system were creating chronic motivation/confidence pressure. The monitor
was visible but not hijacking the tail.

`behavior_changes.json`:

- 250 corrective-change rows.
- 235 are `goal_avoidance`.
- 246 outcomes marked `resolved`.
- only 25 landed.
- 125 relieved.

Good: the adaptation system was not silent. It repeatedly noticed
goal-avoidance and tried to increase action pressure.

Bad: most corrective changes did not land. Many "resolved" rows still show
`expected_class_before = 0`, `expected_class_after = 0`, and
`expected_class_rose = false` in their outcome payloads. The system noticed the
rut but often failed to convert noticing into the expected productive class.

`habituation.json`:

- 5,038 keys.
- first-seen timestamps date back to 2026-06-30.
- top function counts include `assess_goal_progress` 73,929,
  `generate_intrinsic_goals` 69,569, and `research_topic` 39,914.

This confirms the dirty-instance caveat. The run was not clean with respect to
habituation or bandit history.

## 11. Prediction and causal stores are useful but overconfident around broad actions

`causal_graph.json`:

- 320 edges.
- 156 established.
- 300 source `intervention`.
- 308 domain `self`.
- top causes: `generate_intrinsic_goals`, `assess_goal_progress`,
  `research_topic`, `attend_goal`, `thread_continue`.
- top effects: signal rises/falls such as `exploration_drive rises`,
  `motivation rises`, `impasse_signal rises`, `uncertainty falls`.

`prediction_metrics.jsonl`:

- 2,102 rows.
- average mismatch 0.619.
- every row has mismatch >= 0.5.

`predictions.json` tail:

- 150 predictions.
- 70 evaluated, 80 pending.
- evaluated frequency predictions: 34/34 correct.
- evaluated causal predictions: 11/36 correct, average mismatch 0.349.

`rule_candidates.json`:

- 75 candidates.
- 33 promoted.
- several promoted causal candidates have more fails than confirms, for
  example `generate_intrinsic_goals -> uncertainty falls` at 270 confirms /
  528 fails and `generate_intrinsic_goals -> exploration_drive rises` at
  325 confirms / 476 fails.

Good: prediction mismatch is recorded, and frequency prediction did correctly
notice repeated `metacog_pattern` and `chunk` events.

Bad: the causal/action learning layer is still broad and noisy. It learns that
common actions move common affect signals, but many of those claims have weak or
mixed evidence. Because causal edges also become credited symbolic artifacts,
this noise can leak into the effect ledger and production-loop success counts.

Run 5 should distinguish:

- causal edge established by strong intervention evidence;
- causal edge created but contested;
- causal edge merely observed as a signal correlation;
- causal edge eligible as "material" for synthesis.

## What this changes from the earlier audits

The earlier docs were right that sidecar material and long-memory quality were
central. This data pass adds four sharper links:

1. The memory graph also needs pruning/quality gates. Long memory was not the
only memory store polluted by instrumentation.
2. Causal-edge artifacts are real effects but not prose material. Production
success and synthesis readiness need separate counters.
3. Delayed reward was dominated by goal closure, so cheap completions likely
reinforced many nearby actions.
4. The repeated speech was written into replay-language data, so fixing only
the talk policy may not remove the learned phrase.

## Run 5 checks to add

1. Memory graph live-id ratio: percent of graph endpoints whose ids still exist
   in long memory.
2. Memory graph event-type mix for retained nodes, especially `goal_progress`,
   `chunk`, and `metacog_pattern`.
3. Ledger material class counts: readable body, structural graph effect,
   operational check, file write.
4. Production success with same-cycle positive ledger row, lagged ledger row,
   and readable sidecar body.
5. Delayed reward by source: retrieval, goal closure, artifact effect, pruned,
   apply-failed.
6. Goal-closure delayed reward must verify completion happened after the
   decision and within the intended window.
7. Completed goals with unmet definition-of-done criteria, no milestones, no
   credited effect, or title-fallback-only identity.
8. Scoreboard events with stable goal ids.
9. Relationship history duplicate rate and context-bloat warning rate.
10. Opinion evidence refs that still resolve to retained memory or stored
    excerpts.
11. Replay-corpus duplicate rate and banned-source share.
12. Native language training data diversity before `native_lm.pt` is updated.

## Bottom line

The large data files make the system look more alive and more entangled.

Alive: it really was learning causal edges, writing effect ledgers, tracking
delayed outcomes, maintaining a memory graph, adapting behavior, and training a
native language model.

Entangled: those stores were not separated by evidence type. Instrumentation
became memory topology. Causal edges became production success. Cheap goal
closures became delayed reward. Repeated speech became replay data. Orphaned
memory ids remained evidence.

The next audit should not ask only "did an artifact/effect/reward exist?" It
should ask "what kind of thing was it, can a downstream consumer read it, and
does its source still exist?"

