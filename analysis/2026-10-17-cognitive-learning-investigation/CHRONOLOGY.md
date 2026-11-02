# Chronological behavioral evidence

Companion to [REPORT.md](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/REPORT.md>). This is a history of **experiments and engineering changes**, not an inferred developmental biography. Changes between builds cannot be attributed to autonomous learning. Runs differ in duration, retained state, modes, available tools and stopping conditions; they are not randomized matched comparisons.

The [archive index](</Users/ricmassey/orrin_v3/docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/DEMO_RUNS.md>) was used for discovery. Independently derived counts are in [archive_measurements.json](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/archive_measurements.json>) and [probe_results.json](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/probe_results.json>). Report-only historical statements below are marked explicitly. Dates are UTC where a timestamp is given; folder dates are not assumed to be launch dates.

## Early experiments: June to early July

| Date / experiment | Expected behavior and reported change | Observed or reported result | Learning interpretation and present status |
|---|---|---|---|
| June 16, first learning diagnosis | Value estimates should discourage low-yield diversive actions | Mid-run diagnosis identifies selection/value mismatch; this is a report checkpoint, not a full-life denominator | Established the right question: stored value can disagree with actual selection. Current outcome-devaluation and mature-value terms address it partially |
| June 17 | Metacognitive rut detection should break avoidance | Index describes an 8,040-cycle checkpoint with phantom action debt and mode flapping. Final ZIP independently contains **10,707 decision records by summed counts and 10,707 ignition messages** after skipping one byte-identical rotated log | Do not treat 8,040 as the final archive denominator. Final snapshot: `seek_novelty` 2,616 at mean reward .3024; generator 2,580 at .3183; `look_outward` 1,750 at .1671; research 623 at .5070. Low measured value coexisted with high selection frequency |
| June 18 | Repair phantom debt, unstable mode transitions and telemetry retention | Prior reports claim avoidance 2,251→5 and mode flips 3,415→6. Final ZIP independently contains **11,396 recorded decisions and 11,402 ignition messages**, after removing one duplicate log | Those report checkpoint comparisons were not independently reproduced here; final counters are not identical sampling windows. Generator still runs 3,768 times at .2545, while research runs 540 at .5403. Repairing one control defect did not establish value-sensitive useful behavior |
| June 19 | Binding, goal lens and effect-based production should connect intention to actual work | Report: 11,633 cycles; 146 effects, zero credited production under the stricter gate | A stricter honest measurement can look worse while improving validity. Counts remain report-level in this investigation |
| June 24–25, new goal architecture | Broader autonomous goal generation and execution | ZIP: **17,352 production rows and recorded decisions**, cycles 1–17,352. One goal, “The causes of rich internal state with no environmental coupling,” occupies **14,297/17,352 = 82.39%**. `look_outward`: 5,082 calls at .1983; generator: 4,392 at .4795; research: 339 at .6032 | Direct evidence of goal monopoly and low-reward repetition before the July aspiration system. A verbal diagnosis of disconnection itself became the dominant goal |
| June 29, short diagnostic | Diagnose affect regulation and surface/grounding defects | Report: 1,459 cycles over ~47 minutes, operator stopped, “hot and flat” signal behavior | Short diagnostic is not a continual-learning test. It motivated appraisal/habituation and surface changes |
| June 29, separate grounded-concept experiment | Learn an execution-outcome predictor and transfer to unseen commands | Results report: initial naive-Bayes variant passes 7/12 randomized families; logistic version passes 12/12 and both exit/stdout observables. Current tests encode narrow held-out transfer | Historical claims were not rerun or independently reconstructed from raw trial files here. Current mechanism is inspected and credible; normal runtime integration is still absent. [Results record](</Users/ricmassey/orrin_v3/docs/Core Architecture, Embodiment & Evolution/archive/GROUNDING_EXPERIMENT_RESULTS_2026-06-29.md>) |
| July 1 | Effect-gated goal closure and disengagement should prevent merely narrated progress | Report: 14,472 cycles; first longer life under this closure architecture | Important integration change, not evidence that all closure became epistemically valid |
| July 2, acceptance Run 2 | Production, significance, aspiration credit and regulation gates | Report: 10,071 cycles; some significance/selection-value checks improved, aspiration credit/lane separation failed; rest-drive ignition source ~74%; missing web-search context hook | Different bottlenecks coexist. “Rest” dominating an ignition reason did not mean actual restorative behavior. Report-only quantitative claims |
| July 3, acceptance Run 3 | Research should produce real memos and credit aspirations | Report: first 11 research memos; social-presence ignition source ~84% | Real external intake emerged, while a different drive replaced the former ignition monopoly. This is evidence of relocated control pressure, not a general learning breakthrough |
| July 5, Run 4, dirty instance | Correct goal-store desynchronization and enable production/reuse | Report: 0 desyncs over 223 completions, nonzero production funnel, but 197 KB template manuscript, learned-note pruning and zero research memos | Successful plumbing exposed artifact-quality and retention failures. Dirty/mid-change provenance prevents a clean causal before/after inference |

The early ZIPs lack the later standard run stamps. Their log-message totals are deduplicated exact-file counts, not reconstructed boot-complete life identities. The scripts preserve this limitation instead of inventing segment boundaries.

## Full-cycle captures: July to October

“Largest commitment” below means the most frequent `committed_goal_id` in **production rows**. “Ignition duty” means ignition-message count divided by the complete production-row count where the logs support that comparison. Neither is the proportion of actions that advanced a goal. Reuse rows are raw effect-ledger kinds, not validated useful transfers.

| Run / launch or archive date | Source build recorded by run documents | Production denominator | Largest commitment | Ignition count / duty | Raw reuse rows; with citer |
|---|---|---:|---:|---:|---:|
| Run 5, July 8 12:43 UTC | `f0c4698` | 12,330, contiguous | 12,223; **99.13%** | 12,330; 100% | 8; 0 |
| Run 6, **July 10 20:48**; folder July 11 | `584b76a` + `e4abfe7` | 13,341, contiguous | 12,274; **92.00%** | 13,341; 100% | 2; 0 |
| Run 7, July 12 16:33 | `a63b160` + `bb3685a` | 11,060, contiguous | 10,052; **90.89%** | 11,060; 100% | 4; 0 |
| Run 8, folder July 15 | `fc2b635`, mid-life fix `e70ac98` | **9,784 retained rows**, cycle 4,418 missing | 4,166; **42.58% of retained rows** | Only 441 retained ignition lines; no full-life duty inferred | 2; 0 |
| Run 9′, July 17 04:51; two boot stamps | R9 build, no reproducible committed SHA established by its report | 10,278, contiguous cycle sequence across restart | 4,165; **40.52%** | 10,278; 100% | 1; 0 |
| Aborted attempt, July 18 12:04 | `b175ed2` | 2,671 | 1,492; **55.86%** | 2,671; 100% | 0; 0 |
| Run 10, **July 19 03:12**; folder July 18 | `4d69ce5` | 11,565, contiguous | 4,667; **40.35%** | 11,565; **100%** | **6; 0** |
| Run 11, July 20 17:02; folder July 21 | `423e201` | 18,327, contiguous productive segment | 7,941; **43.33%** | 17,996; **98.19%** | 0; 0 |
| Run 12, Aug 19 23:15, captured Oct 4 | `90a01c4` | 10,972, contiguous | 4,852; **44.22%** | 7,367; **67.14%** | 34; 0 |
| Run 13, Oct 6 19:35–Oct 8 ~00:23 | `a6045bc` | 15,392, contiguous | 4,914; **31.93%** | 10,679; **69.38%** | **833; 114** |

The raw logs contain five Run 11 boot stamps, but only one productive cycle sequence. Its report identifies four post-death relaunches. Those restarts are not four additional learning lives. Likewise, Run 8's 9,785 cycle endpoint is not 9,785 retained production rows. Run 10's reported 42.3% “ignition monopoly” describes a dominant **source share**, not ignition duty: all 11,565 cycles have an ignition message.

### Run 5 → Run 6: action-value influence improved, credit pumping took over

Run 5 expected the new production and goal mechanisms to yield balanced useful activity, but the driver slot was almost entirely self-understanding. Run 6 increased learned-value authority and introduced commitment rotation pressure. Its report compares `look_outward` 4,899→88 choices, a positive mechanism result. The raw terminal decision statistics and goal occupancy support a substantial behavioral redistribution, but they do not isolate learning from the source changes.

Run 6 then exposed timestamp-bearing memo rewrites defeating novelty deduplication. The report counts 387 credited rewrites and value EMA .8142, alongside independently verified 92% commitment occupancy. This is a reward-specification failure: learning from the ledger can rationally reinforce a duplicate-producing strategy if the ledger labels it novel. Current content normalization, deduplication and bounded commitment credit must be distinguished from this historical bug.

### Run 7 → Run 8: an existing escape mechanism needed alternatives

Run 7's anti-pump build reduced the reported self-understanding value to .5196 and eliminated the dominant rewrite loop, yet raw commitment occupancy remained 90.89%. Run 8 broadened the directional aspiration pool and added stale refractory behavior. Occupancy fell to 42.58% of retained rows, with all four aspirations represented.

The Run 8 report says the refractory never fired: rotation prevented its preconditions. That makes the alternative-pool change a stronger explanation than the newly added refractory, although a controlled ablation was not performed here. The report's strong word “proving” structural cause should be read as converging mechanism evidence, not randomized causal identification. Useful behavior still did not satisfy the full gate; rotation is necessary in some traps but is not sufficient learning.

### Runs 9′ and 10: more honest execution, insufficient research feed

Run 9′ documents real resource-watchdog intervention and promoted exemplars, but its single raw reuse event falls below the intended research/reuse gate. Run 10's first attempt was externally terminated; its 2,671 cycles cannot be treated as a completed acceptance life. The shutdown/broken-pipe failure is operational history, not proof of a cognitive-learning defect.

The clean Run 10 expected reproducible execution, originality checks, resource attribution and reusable research. Its report describes successful originality vetoes, no twin-ID desyncs and a starvation interval in the goal daemon. The raw ledger contains six generic reuse rows, whereas the report's gate says zero. All six lack a citer; they do not establish the goal-attributable reuse demanded by later gates. These should be reported as **different measurements**, not silently conflated.

### Run 11: structural health without epistemic growth

The “Growth Run” expected the feed/answer/reuse cycle to operate. The raw production log confirms 18,327 productive cycles and distributed commitments. The terminal goal tree contains nine answer stamps, all false; the raw effect ledger has no reuse rows. Its report describes the final ~12.3-hour creation drought and shutdown hang.

Blocked code-generation calls numbered 1,967 in activity logs while the report records a positive reward EMA. That is a strong historical example of a capability restriction being detected operationally without an appropriately low learned desirability. Current code deliberately distinguishes tool availability, impossible results and explicit no-ops; the Run 11 behavior is not evidence that all those later corrections fail.

### Run 12: apparent growth was semantically weak

Ignition duty fell from 98.19% to 67.14%, and blocked-code activity improved according to the report. The raw terminal goal tree has **7 true answer stamps among 15 stamps**, with seven distinct question strings. The raw ledger has 34 reuse rows, none carrying a citer.

The subsequent run analysis traces false answering to template/subject terms and reports 0/10 topical structured reuses. Fixtures preserve representative malformed claims; current subject-term and closeout code contains safeguards absent then. This was not a lack of all research machinery—it was a failure of its answer validator and feed semantics. The report also identifies a 12.4-hour whole-process freeze; host sleep is a plausible historical explanation, not independently proved here.

### Run 13: real narrow prediction, inflated use metrics, recurring feed problems

This is the strongest archived positive evidence for a full runtime hypothesis→later-data-test path. Independent recomputation validates the two RSS predictions. The archive contains **133 claims files**, only **three with non-null predictions**: two confirmed RSS claims and one inconclusive CPU claim. “26 answered” must therefore not be read as 26 empirically tested hypotheses.

Distinct retained stores have different denominators:

- Brain goal snapshot: 216 nodes, including subgoals; 135 answer stamps; 26 true stamps across 14 distinct question strings.
- Answer index: 17 records; 12 with citations; 2,501 citation increments.
- Growth history: 43 events = 38 answered-question events + 5 exemplars; 22 distinct `(kind, ref)` pairs = 17 question references + 5 exemplar references. “38 versus 17” refers to answer events, not the whole history.
- Effect ledger: 2,613 rows; 833 reuse, of which 114 have a citer, 105 specifically pointing to claims files. Generic use and epistemic use are different.
- LTM: 2,001 rows; 1,445 `summary` entries (72.21%); 1,405 entries with the conservative internal-log markers (70.21%). These independently reproducible classifications are not identical to the prior report's 74% “self-log summaries.”
- Causal graph: 500 retained edges; 489 self-domain, 11 world-domain; 485 tagged intervention. Only three have a positive counterfactual count.
- Ground-truth ledger: 218 retained speech outcomes, zero nonempty rule IDs; rule-grounding map `{}`.

The large CPU characterization goal held commitment for 2,884 cycles while waiting for recurrence; the two RSS goals held 676 and 669. Thus useful prediction machinery itself could occupy foreground control while its experiment needed elapsed telemetry rather than deliberate attention. Current daemon-only routing addresses that interface.

The report's starvation/desync/no-op diagnoses are plausible and supported by corresponding source changes and fixtures. This investigation did not reproduce every prior report's no-op-rate or silence statistic, so they are not presented as newly measured quantities. The decisive independently verified facts are narrower: goal occupancy, logged action rewards, claimed prediction sample statistics, store composition and metric semantics.

## Post-Run-13 changes: what is current, what remains unknown

| Historical problem | Current source/change evidence | Current assessment |
|---|---|---|
| Waiting `characterize` goals competed for foreground attention; repeated reconciliation | `eadcaf5`, then direct-commit correction `c297a75`; `goal_io.is_daemon_only`; fixture-based tests | Corrective path exists at both bridge and commit boundaries; no later complete-life result |
| Follow-up research stayed in brain tree without executable daemon steps | `epistemic_closeout.spawn_followup_goal` queues daemon proposal; continuation handoff fixed again in `1c51dfb` | A smoke-discovered boundary hole was corrected; longitudinal effectiveness unknown |
| Completed-topic adoption, research-feed drought and runaway rounds | Feed heartbeat, open-lane bonus, seed/neighbor topics, bounded follow-on angles in `2d95798` and smoke changes | Additional feed paths exist; they also add selection pressure that should be measured for interference |
| Research no-ops and impossible code work received reward | `execute.py` explicit-noop zeroing, code-writer impossible response, current tests | Specific cases corrected. General goal-progress proxy and failure-sign erasure remain |
| Self-log memory and self-appraisal loops | `827f611` filters/retention; `decc1f9` habituates inhibition/writeback | Historical composition cannot be assumed current; broader retrieval/replay feedback still warrants testing |
| Low-quality generated text/exemplars and duplicate growth | `251b9c0` fluency/self-talk gates, unique question credit and citation windows | Better validation/counting, but citations still do not measure causal influence |
| Rule hits multiplied within cycle | Shared refractory now covers `apply` and `reinforce_rule` | Current hit count capped per known cycle; independent evidence is still not guaranteed across cycles |
| Time, output instrumentation and lifecycle gaps | Instrument/clock clusters `36c4da3`, `6c9584e` | Targeted records/tests exist; no new full-life validation |

The [Phase B build brief](</Users/ricmassey/orrin_v3/docs/PHASE_B_BUILD_BRIEF_2026-10-08.md>) reports 1,796 tests green at its checkpoint. This investigation did not rerun them. Current tests were inspected for their assertions: no-op handling, daemon-only commitment, feed handoff, archived fragment rejection, memory filtering, citation-window deduplication, rule-hit refractory and characterization falsification. They establish intended local contracts; they do not establish end-to-end transfer.

The evidence therefore supports **progressive repair of operational failures, repeated relocation of bottlenecks, and a small amount of genuinely tested prediction**. It does not yet support a measured trend in autonomous competence on controlled new situations.
