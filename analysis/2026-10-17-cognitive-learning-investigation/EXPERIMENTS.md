# Controlled verification plan

Companion to [REPORT.md](</Users/ricmassey/orrin_v3/analysis/2026-10-17-cognitive-learning-investigation/REPORT.md>). **These experiments are proposed, not executed.** The completed work consists only of archive measurement and small dependency-isolated source probes documented in `probe_evidence.py`. No implementation or configuration changes are supplied here.

The purpose is to discriminate explanations, not to maximize a growth dashboard. Begin with measurement and attribution, then test whether learned state changes choices, then test whether changed choices improve outcomes on new situations. A long free-running life is a useful stress test but a poor first discriminator when several mechanisms and metrics are suspect.

## Common experimental contract

Use an isolated copy with a frozen source SHA, explicit mode/provider/tool availability, fixed resource budget and immutable initial-state snapshot. Record whether a life is fresh, resumed or warm-started; a retained rule from June is not evidence learned in October. Save exact task/input streams and random seeds. Keep acquisition and evaluation items separate, including surface paraphrases and structurally distinct cases. Do not let held-out answers enter training, replay, research snippets or operator prompts.

Compare learning-enabled state with an otherwise matched frozen-learning control. Hold tool availability and external data constant, or replay the same timestamped input stream. Use independent task scoring: actual file/test/tool result, prediction target, or blinded human assessment with explicit criteria. Internal reward, eloquence, activity and output volume are secondary diagnostic measures.

For sequential tasks, retain a performance matrix: after learning task family i, test all earlier families and held-out new cases. Report forgetting, forward transfer, backward transfer, sample efficiency, cost, unproductive repetition and task completion. Use both per-task and macro-averaged denominators so one prolific easy task cannot dominate the result.

The numerical thresholds below are **proposed acceptance criteria for these experiments**, not universal scientific definitions of intelligence. Pre-register them and a bounded sample budget before observing outcomes. If the budget cannot distinguish an effect, report inconclusive rather than silently relaxing a criterion. Future runs need their own execution authorization and isolation checks; none are being launched by this report.

## E1. Audit what reward actually rewards

**Competing hypotheses:** H1: poor behavior follows a misleading reward target. H2: rewards correctly identify useful behavior, but selection ignores them.

**Required data:** A stratified sample of at least 200 completed attempts across research, reflection, production, tools and failed/unavailable actions. Preserve pre/post state, actual function and arguments, goal acceptance criterion, every reward component, no-op/impossible flags, and independently graded outcome. Include explicit no-ops and unsuccessful calls with ordinary non-error return shapes.

**Measurements:** Reward versus external progress; reward by failure category; contribution of goal mentions/function-name bonuses; independently judged productivity among top-reward attempts; false-positive goal-progress rate.

**Pass/fail:** For reward adequacy, independently unsuccessful/no-progress attempts should not systematically outrank successful progress-matched attempts. Predeclare a target: at least 90% of known explicit failures score below successful matched attempts, and the mean reward advantage for successful work has a paired 95% interval above zero. A positive proxy reward on inactivity alone is not automatically failure if it buys documented later benefit; evaluate that separately.

**Interpretation:** If rewards are misordered, selection suppression is not the only explanation. If rewards track outcomes but picks do not, E3 becomes the stronger target. This test does not by itself show that changing reward would improve the whole runtime.

## E2. Reconstruct exact experience lineage

**Hypothesis:** Phase shifts and asynchronous overlap assign outcome evidence to the wrong action, rule, attention source or meta arm.

**Required data:** A short bounded sequence with intentionally distinguishable outcomes and alternating actions; immutable IDs for selected action, executed action, lane, goal, rule firing, tool job and memory; timestamps for selection, inner finalization, execution and outer persistence. Include one deliberate execution, one override, one background goal completion, one failure and one retrieval.

**Measurements:** For every learner update, join its evidence to the actual producing event. Compare immediate bandit, EMA, history/replay, associations, rule verifier, attention update and delayed evaluator separately. Count duplicated use of a single outcome and missing consumers.

**Pass/fail:** Every update in the known sequence must identify the intended producing event and applicable pre-state. An unrelated query must not update a previous rule merely because it is the latest firing; a replay pair must contain the action that produced its reward. Any deliberate unmatched attribution fails the local contract. Absence of an update is recorded separately from incorrect attribution.

**Interpretation:** Confirms specific feedback defects without needing a long life. A clean sequence would challenge the proposed phase interpretation or show that a presently unobserved coordinating mechanism repairs it. Larger runtime consequences still require E9.

## E3. Measure which controller wins

**Competing hypotheses:** H1: learned values have insufficient practical authority. H2: values are influential, but they learned bad outcomes or lack useful alternatives.

**Required data:** At least 100 captured decision states spanning normal, stagnant, resource-depleted and active-goal conditions. Full candidate set, dispatchability, each score term, intermediate multipliers, epsilon/reflex/meta-rut results and executed choice. Use an isolated replay of state; the real selector has side effects and must not be called casually against live stores.

**Measurements:** Counterfactual choice with only the learned-value inputs varied within their empirical range; choice with each existing regulatory contribution omitted in shadow scoring; fraction of observed low-value repeats where a better-valued executable alternative existed. Analyze goal tiers and ordinary function scores separately.

**Pass/fail:** The broad “learning is suppressed” hypothesis is supported if, in a predeclared majority of the low-value repeated states, a relevant higher-value executable alternative loses because of identifiable non-learned terms and wins when those terms alone are removed. If no better executable alternative exists, classify it as an affordance/candidate problem. If learned values already favor the repeat, investigate the target and credit instead.

**Interpretation:** Shadow choice differences demonstrate authority, not benefit. Only independently scored outcome comparisons can establish that the counterfactual choices are better.

## E4. Test task-context aliasing

**Hypothesis:** The four-bucket bandit averages incompatible task requirements, preventing useful transfer even with correct reward.

**Required data:** Two task families with the same affect state but opposite optimal methods, equivalent costs and clear external success tests. Provide sufficient balanced experience for both; evaluate new instances with unchanged affect. Retain full symbolic routing context so the experiment measures the whole system as well as the bandit.

**Measurements:** Conditional success and choice probabilities by task family; bandit values; whether symbolic rules or planning compensate for the coarse bucket; interference after alternating families.

**Pass/fail:** A whole-system pass requires at least 80% correct method selection in each family on held-out cases and a positive paired advantage over the frozen-learning control. Learning a single globally preferred method while failing one family supports aliasing. If symbolic routing compensates successfully, the limitation is local to the bandit rather than a system-wide gap.

**Interpretation:** Distinguishes missing policy expressiveness from an integration failure that existing symbolic state can already overcome.

## E5. Demonstrate that an answer changes a decision

**Hypothesis:** Current citation/reuse metrics do not imply answer-dependent behavior.

**Required data:** Matched decision problems where two different factual answers imply different correct actions. Keep topic words constant; vary the stored answer. Include an answer-absent condition and a topic-matched irrelevant-answer condition. Preserve provenance and actual retrieval; evaluate unseen instances requiring application rather than repetition.

**Measurements:** Selected action, reason, answer retrieval, internal citation, independently scored success and task cost. Counterfactually remove only the relevant learned record, leaving unrelated state fixed.

**Pass/fail:** Cite counts are not a pass criterion. A pass requires the action to change appropriately with the answer, no equivalent benefit from the irrelevant answer, and a held-out success advantage whose paired interval excludes zero. Predeclare at least a 10-percentage-point mean gain as practically meaningful for this task set. If only the reason annotation changes, decision-use capability fails this test.

**Interpretation:** Establishes causal use of knowledge. A correct changed decision without a citation would expose an instrumentation false negative rather than a learning failure.

## E6. Convert a valid prediction into useful control

**Hypothesis:** Orrin can predict resource effects but does not use that knowledge to improve a constrained task.

**Required data:** Frozen environment with several ways to acquire information, known resource costs and a held-out information task. Let Orrin gather resource observations and form predictions before a later memory-constrained phase. Compare learned-state, prediction-removed and frozen-learning controls. Use actual resource measurements and task correctness; avoid attributing concurrent processes to a single function without controlling them.

**Measurements:** Prediction error on fresh samples, method selection, peak RSS/latency, answer correctness, completion rate, and whether choices respond to a changed cost regime.

**Pass/fail:** A prediction pass requires out-of-sample accuracy above a declared baseline. A behavioral-learning pass additionally requires at least 20% lower cost at matched correctness, or greater task success under the same hard budget, relative to controls. Correct prediction with unchanged/worse constrained behavior supports a prediction-to-policy integration gap.

**Interpretation:** Extends Run 13's strongest evidence to the currently missing improvement leg. A failed prediction under controlled repetition would also challenge the historical causal interpretation of RSS association.

## E7. Test persistence through consolidation and contrary evidence

**Hypothesis:** Correct local revisions can be overwritten, diluted or rehabilitated away during subsequent maintenance.

**Required data:** A small set of independently tested rules/opinions and one weak-area revision with explicit evidence IDs. Snapshot before learning, after learning, after reflection, after consolidation and after restart. Include useful rare facts and frequently repeated false statements. Exercise both writers of the self-belief revision file in an isolated environment.

**Measurements:** Evidence identity/schema, confidence, tombstone status, retrieval rank, decision effects and task performance at each stage. Distinguish valid reconsideration after new evidence from silent restoration caused by reconstruction.

**Pass/fail:** Persistence passes if the revision and its provenance survive all intended stages, the same novel-task decision benefit survives restart, and repeated unsupported statements do not reverse the evidence-backed conclusion. Any silent schema replacement or return to the old belief without new evidence fails retention. Contrary independent evidence should still be able to reverse the belief within the declared evidence budget.

**Interpretation:** Separates useful stability from resistance to correction, and mere file persistence from retained behavioral competence.

## E8. Determine whether replay helps or entrenches a rut

**Competing hypotheses:** H1: replay preserves useful strategies. H2: it amplifies misattributed proxy successes and stale self-repetition.

**Required data:** Matched stored histories containing useful sequences, repeated no-progress sequences and failures; exact action/outcome joins from E2. Compare existing replay enabled/disabled in isolated matched states. Record replayed IDs, overlap multiplicity, bucket destination and chain bonuses. Do not introduce corrected production behavior and replay changes simultaneously.

**Measurements:** Retention on old tasks, transfer to new variants, repeated-action fraction, external return and calibration; number of effective independent experiences versus replay updates.

**Pass/fail:** Helpful replay must improve retention or transfer with a paired interval above zero and without a predeclared material increase (e.g. >5 percentage points) in unproductive repetition. Better internal reward or stronger chains alone does not pass. Harm concentrated in shifted histories supports the attribution explanation rather than replay being inherently harmful.

**Interpretation:** Tests the consolidation-pathology hypothesis directly, while preserving the possibility that replay is beneficial with valid experience records.

## E9. End-to-end autonomous learning and transfer

**Hypothesis:** The existing connected machinery can support a bounded complete autonomous learning cycle under a frozen implementation.

**Required data:** A predeclared suite of at least three independently scored task families with train/held-out variants; unfamiliar but discoverable tool or causal relationships; an observation/compute budget; a matched frozen-learning control. Start with one bounded family as a pilot before authorizing a broader run. The operator supplies the environment and success criteria, not each hypothesis or next action.

**Measurements:** All ten operational steps, acquisition costs, hypothesis/test provenance, persistent revisions, held-out success, retention after intervening tasks and restart, and sensitivity to removal of the learned state. Include cases with no learnable relationship to test whether investigation stops appropriately.

**Pass/fail:** For the declared suite, require ≥10 percentage points improvement over both pre-experience and frozen-learning baselines on held-out cases, with a paired 95% interval above zero, no more than 5 points average forgetting on earlier tasks, and selective loss of benefit when the relevant learned state is removed. Report every family, including failures. Surface-changed duplicates alone establish only narrow transfer.

**Interpretation:** A pass supports meaningful bounded autonomous learning. A failure must be localized to opportunity, hypothesis quality, execution, feedback, retention or policy use; it does not establish universal incapacity. This is the main experiment that could justify the user-facing claim “Orrin improves through experience.”

## E10. Test whether meta-learning improves learning efficiency

**Hypothesis:** Adaptive depth, thresholds and attention make later learning more efficient, rather than merely predicting proxy reward.

**Required data:** Repeated novel-task families with varying difficulty; matched adaptive and frozen meta-policy conditions; measured compute/observation costs and independent outcomes. Hold ordinary knowledge learning constant across conditions where possible.

**Measurements:** Success per external observation, time and cost to criterion, unnecessary deliberation, overconfidence, and transfer of a learned computation strategy to new task families. Record allocated arm and actual rounds separately.

**Pass/fail:** Adaptive meta-control should achieve a predeclared ≥15% cost reduction at matched success or a clear success gain at fixed budget, with a paired interval excluding zero. Changed threshold statistics or higher self-rated quality is insufficient. Benefit only on the training family is task adaptation, not general strategy improvement.

**Interpretation:** Distinguishes learning how to learn from ordinary parameter accumulation and confidence calibration.

## E11. Assess the post-Run-13 integration changes without conflating goals

**Hypothesis:** Phase B repairs the feed, waiting-goal and memory loops without moving the failure into new pressure or starvation patterns.

**Required data:** A bounded current-build life with complete birth-to-stop logs, raw production rows, daemon WAL, emitted candidates, executed actions, no-op flags, artifact lineage and retained memory. Record the current operational gate alongside the independent task measures from E1/E9. Preserve suspension and actual provider availability.

**Measurements:** Waiting-goal foreground occupancy, daemon silence durations, valid research completions, explicit no-op rate, distinct useful facts, self-log retention, independent answer quality, actual action changes after learning and side effects of the new empty-lane bonus.

**Pass/fail:** Use the already declared operational thresholds in `NEXT_RUN_TESTS.md` for their intended plumbing questions. A learning pass additionally requires independent answer quality and behavioral-transfer evidence; “answer cited later” is not sufficient. If feed improves while new low-value generation dominates, classify the original issue as moved, not solved.

**Interpretation:** Establishes whether historical defects remain relevant to today's checkout and whether local tests compose into useful sustained behavior.

## E12. Separate neural-language improvement from cognitive improvement

**Hypothesis:** Native-language training improves emission quality without necessarily improving fact use or policy competence; contamination may reduce fluency/retention.

**Required data:** Existing model snapshots, training-source mix and a genuinely held-out clean corpus plus fixed thought-to-language tasks. Compare pre/post learning on identical inputs. Separately evaluate grounded content correctness and action selection. This is potentially resource-intensive and should follow explicit budgeting, not be bundled into a runtime audit.

**Measurements:** Held-out perplexity, repetition, fluency, factual preservation, old-corpus retention and stable task decisions. Track whether self-generated prose leaked into evaluation or overwhelmed clean sources.

**Pass/fail:** A language-learning claim requires better held-out generation metrics and no unacceptable old-task degradation. A cognitive-learning claim requires separate improvement in grounded task performance. Provider fine-tuning success or a new checkpoint alone passes neither criterion.

**Interpretation:** Prevents language fluency from masking control defects and avoids misdiagnosing symbolic repetition as neural catastrophic forgetting.

## Decision sequence

E1–E3 establish whether the measurements, experience records and policy authority are valid. E4–E8 isolate representational, use, retention and replay limits. E9 is the primary competence test; E10 asks whether that competence becomes cheaper to acquire. E11 validates current integration under sustained operation. E12 is a separate language-learning assessment.

If E1–E3 expose defects, that supports the integration hypothesis without proving it is sufficient. If they pass and E4/E9 still fail, representation, experiment quality or task affordances become stronger explanations. If E9 passes narrowly but not across families, report bounded competence rather than generalizing beyond the evidence.
