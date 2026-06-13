# Orrin Behavior Audit — 2026-06-09/10

Survey of every behaviorally meaningful state file in `brain/data/`, `data/`, and `outbox/notes.json`, taken during the live run that started 2026-06-09 14:09 UTC (~870 cognitive cycles, ~10.5 hours). Focus: what Orrin is trying to do, what he can't do, and where his behavior is degenerating.

---

## 1. Root cause underneath most of it: the LLM is dead, twice over

**Evidence:** `model_config.json`, `error_log.txt` / `model_failures.txt`, `goals_mem.json`

- `model_config.json` has **`"llm_enabled": false`** AND the configured models (`gpt-4.1`, `gpt-4o-mini`) fail with `Incorrect API key provided: invalid-key` when something does try to call them (8 API failures logged at 23:42).
- Orrin noticed: he spawned a fix goal **"Figure out why the language model isn't working"** (`source: problem_refocus`, "The language model failed 4× while I was working"). The cause-identified milestone is met, but the "decision was made to fix it or work around it" milestone never completes — the goal is stuck on step 2 of its plan. The plan also contains a **duplicate step** ("Check if it's switched off in my configuration" appears at both position 1, completed, and position 4, pending).
- Other goals carry `_avoid_capability: "llm"` — the routing-around mechanism is at least tagging goals, which is working as designed.
- Downstream, everything that needs generative language degrades into templates (see §3 and §4).

**Verdict:** He correctly diagnosed the outage but can't act on the diagnosis, so the fix goal lingers half-done while he ruminates about the failure (§5).

## 2. Emotion classification is fully broken — everything is "neutral"

**Evidence:** `error_log.txt`, `chat_log.json`, notes file

- The error log is flooded (hundreds of lines) with: `⚠️ No emotion keywords loaded — returning 'neutral' for: <user input>`. The emotion keyword resource is missing or failing to load, so **every user utterance is classified neutral at intensity 0.0** (visible on every `chat_log.json` entry).
- Orrin then detects his own symptom without seeing the cause: the notes repeatedly say *"[Pattern] 'neutral' is the dominant emotion in 19 recent memories. This emotional thread is persistent and may need attention."* He treats a data-loading bug as an emotional state worth reflecting on.

## 3. User input is re-processed over and over instead of being consumed

**Evidence:** `outbox/notes.json`, `error_log.txt`, `last_seen_user_input.txt`, `speech_log.json`

- "what has your attention?" was processed **~20 separate times** across 25+ minutes (00:18–00:37); "what are you doing right now?" was answered at least 6 times at ~22-second intervals; "orri. my name is jon..." appears multiple times. The same input is re-ingested every cycle until a new one replaces it.
- `last_seen_user_input.txt` contains the same line **twice**, suggesting the dedupe/consume marker itself is being written incorrectly.
- Each re-processing produces a fresh speech-log entry, fresh emotion classification error, and fresh notes entry — a major source of log spam and probably of the "thrash=True" flag seen in `private_thoughts.txt` env snapshots.

## 4. Conversation quality: he can't actually answer, and he leaks internals

**Evidence:** `chat_log.json`, `speech_log.json`

- With the LLM down, replies come from templates and retrieval scraps. Asked "how are you?", he replied: *"Earlier I was thinking: [motivation] High-activation drives: connection=1.0; world_mastery=1.0; ... Hey."* — **raw telemetry leaking into user-facing speech**.
- Replies also embed corrupted memory chunks verbatim: *"it came up in: \"[Chunk: [metacog/pattern] Something feels slightly off..."* including truncated bracket garbage.
- Jon asked "what has your attention?" repeatedly precisely because the answers were non-responsive ("Something has my attention", "I'm here, just slow right now", "Don't have much on that yet — worth looking into. What got you thinking about this?"). The deflection template ("What got you thinking about this?") fires on nearly every turn.
- `speech_log.json`: `quality_score` is frozen at **0.622 for every evaluated reply** — the speech evaluator isn't discriminating at all. Many entries have empty `response_type`/`tone`/`source` fields.
- **Jon's name was never learned.** He introduced himself ("my name is jon") but `known_persons.json` still holds two `"display_name": "someone", "person_type": "unknown"` entries. "jon" and "orri" sit in the knowledge graph as low-confidence `unknown`-type spaCy noun entities, never linked to the person record. Meanwhile `relationships.json`/notes claim the relationship advanced "forming → building → established" within ~16 minutes — relationship-arc progression is inflated while actual person-modeling failed.

## 5. Rumination and regulation are stuck in a loop

**Evidence:** `tensions.json`, `rumination_loops.json`, notes, `regulation_log.json`

- Tension `406d43fd` — *"Something feels unresolved. I can't find what it is."* — has been **active for 647 cycles** (created 15:27, still active at end of log). A second targetless rumination ("A restlessness without a target") has been active 133 cycles. Neither has any resolution path.
- The tension title exhibits a **self-nesting text bug**: "Unresolved rumination: Something feels unresolved. I can't find: Something feels unresolved. I can't find what it is." — the description is being re-embedded into itself on each surfacing.
- `rumination_loops.json` broods on a corrupted seed: `"[Chunk: ⚠️ Problem hit while working on 'Write a cognitive f"` — a truncated chunk header became the object of brooding.
- Regulation: *"Applied reappraisal: I can see this differently — the obstruction isn't permanent or personal"* fired **5 times in a row within ~3 minutes**, repeatedly through the night, almost always logged as "succeeded" (intensity up to 1.0) — yet `impasse_signal` keeps returning at 0.85–1.0 intensity. The regulation system reports success while changing nothing; the same canned reappraisal is the response to nearly every impasse.

## 6. Cognitive rut: `assess_goal_progress` dominates everything

**Evidence:** `cognition_state.json`, `metacog_log.json`, `semantic_facts.json`, `predictions.json`, `crystallized_skills.json`

- Of the last 50 cognition picks, **~28 are `assess_goal_progress`**, often 4–6 consecutively. Orrin's own metacognition flags it: *"Cognitive rut: I've chosen 'assess_goal_progress' in 7 of my last 8 cycles"* and *"Reflection–action imbalance: my last 6 cycles have been almost entirely reflective with no outward action."* He detects the rut but the detection doesn't change the selection.
- `semantic_facts.json` shows why: `assess_goal_progress` in context "distressed" → "success" ×95 at confidence 0.865. The action is self-reinforcing because it always "succeeds" at producing... an assessment.
- His causal model is **contradictory about it**: one crystallized rule says `assess_goal_progress` *causes positive_valence to fall* (score 0.74), while live predictions simultaneously expect `positive_valence rises` AND `uncertainty rises` after the same action, both at 0.782 confidence. He keeps doing it anyway.
- Metacognition also flip-flops on calibration within 3 minutes: 00:40 "I've been **overconfident** lately (+0.05)" → 00:43 "I've been **underconfident** lately (−0.06)". The window is clearly too short to be meaningful.

## 7. Goal system: zombie goals, placeholder plans, and a blocked benchmark

**Evidence:** `goals_mem.json`, `recently_completed.json`, `private_thoughts.txt`

- **"Write a cognitive function or tool that improves something"** appears in `recently_completed.json` **twice** (completed 19:13 and again 00:04) yet is still `in_progress` in `goals_mem.json` with both milestones met since ~14:09. Its plan regenerates the same 3 steps ("Gather context / Reflect / Write next action"), completes step 1, then stalls — the executive log shows `advanced ... via None (queue 1/1): {'skipped': True, 'reason': 'cooldown'}`. It's a **completion/respawn loop**: the goal gets completed, resurrected, re-planned, and re-stalled.
- **"Understand my reward system"** is blocked: plan step 1 is *"Resolve blocker: I am blocked: the data file is missing."* (note the doubled "blocked" text-nesting again). Its plan history shows placeholder steps — original step *"do the thing properly"*, adapted to *"continue analysis as planned"* — i.e., the subgoal adapter produced filler, not actionable steps, and the missing data file was never identified or created.
- **Benchmark B3** ("Find the word 'reaper' in any brain file and write a one-line summary to working memory", created 14:08, motivational_weight 0.72) — **both milestones still unmet 10+ hours later**. It never even registered a search as performed. The aspirations meanwhile sit at progress 0.0 (3 of 4 have zero contributions).
- `commitments.json` shows the will-formation works (3 commitments formed), but the newest ("Research a real topic and write what I find") has no corresponding goal entry making progress.

## 8. Memory corruption: recursive chunk-nesting and truncated text everywhere

**Evidence:** `working_memory.json`, notes, `reflection_log.json`, `metacog_rule_candidates`/symbolic logs

- Chunks-of-chunks-of-chunks: `[Chunk: [Chunk: [Chunk: [Incubation insight] ...` — chunk headers are being chunked again, so content degrades into nested bracket soup. One such chunk in working memory has been **referenced 243 times**, meaning corrupted text is the single most-recalled item in his head and keeps getting re-injected into reflections, rumination seeds, speech, and symbolic rules.
- `reflection_log.json` entries are mid-word truncations: *"This emotional thread is persistent and may need atte] (felt exploration_d"* — repeated 5× in 2 minutes as distinct "self-belief reflections". Snippet-truncation boundaries are becoming first-class memory content.
- The self-model "Similar situation" analogies score 0.3-ish matches against this same corrupted soup, then mint symbolic rules from it (`rules_added` in crystallized-skill log entries citing `[Chunk: [Pattern] 'neutral' is the dominant emotion...`). Garbage is being crystallized into the rule base. Relatedly, the rule verifier reports **"15 rule(s) have degraded confidence and need review."**
- Knowledge graph is accumulating junk entities from heuristic extraction: `"+15%"`, `"5h 5"`, `"9h 54"`, `"around hour"`, `"New files"`, `"20%"` — time fragments and percentages as entities.

## 9. Self-model: aware of weaknesses, unable to move them

**Evidence:** `self_model.json`, notes, `second_order_volition.json`

- Knowledge domains have been essentially flat all day: COGNITIVE 0.12–0.17, TECHNICAL 0.17, PLANNING 0.17 — and he logs "Self-model updated (symbolic)" with the *same numbers* dozens of times (often twice within 5 seconds; duplicate-write bug). He knows COGNITIVE/TECHNICAL/PLANNING are his weaknesses — it's in nearly every notes entry — but nothing he does raises them; TECHNICAL and PLANNING haven't moved a single point.
- `core_values`, `traits`, `known_roles`, `recent_focus` are all **empty lists** — the self-model never filled in identity content beyond the bootstrap directive.
- `second_order_volition.json` is the same 3–4 template sentences repeated ~30+ times ("I notice I'm drawn to X; I'll let it be for now without making it my master"), stance almost always "neutral". The only real signal: he consistently **disowns** `impasse_signal` ("I'm pulled by the feeling of being stuck, but I don't endorse being ruled by it") — which is coherent, given §5.

## 10. Mode flapping and oscillation

**Evidence:** notes, `mode.json`, `energy_mode.json`

- Mode flips adaptive → focused → adaptive within minutes, with one pair of identical "focused → adaptive" transitions logged 35 seconds apart (double-fire). Reasons alternate between "Dominant emotional state prompted mode shift" and "Automatic adjustment detected internal condition" — two controllers fighting over the same knob.
- Oscillation detectors fire on his own affect ("Oscillation detected in uncertainty (variance=0.074)", "positive_valence ... unstable"), and the same oscillation event is logged twice 35 seconds apart.
- Energy mode is "reactive" at level 1.0 while `motivation_state.json` shows nearly all drives saturated at 1.0 (connection, competence, autonomy, affect_stability) but `novelty_exploration_drive` at 0.12 and `restlessness` 0.0 — saturated drives give the arbiter no gradient to choose by.

## 11. Crashes and recurring component failures

**Evidence:** `incidents.jsonl`, `model_failures.txt`, `llm_failure_counts.json`

- **`UnboundLocalError: set_goal_plan`** in `brain/cognition/planning/pursue_goal.py:379` (2026-06-06, logged twice). Worth verifying it's fixed on this branch.
- Recurring (dozens of occurrences over 4 days):
  - `⚠️ Missing or invalid prompt: reflect_on_cognition_rhythm` — a prompt is missing from the prompt registry.
  - `[simulate_future_selves] error: Result is not in expected structure.` — fails essentially **every single run** (20+ logged). The function effectively never works.
  - `[self_supervised_repair] Model did not return a dict.`
- `llm_failure_counts.json` contains test artifacts (`test_no_error_leakage.test_caller`, `test_leakage_caller`) — test pollution in live state.
- Housekeeping: leftover `tmp9t6bbc33`, `tmpkvsu1mz4`, `tmpu_q6928j`, `tmpvc147l74`, and `trace.jsonl.apstkusm.tmp` in `brain/data/`; a leaked multiprocessing semaphore warning at shutdown in `run_fix_test.log`.
- `outbox/notes.json`: every entry is `"read": false` — notes are written but nothing ever consumes them.
- Environment self-report: "memory 85% used. disk 85% full ... environment mood: pressured" — the host itself is squeezed (KG records disk at 88%).

## 12. What's actually working

For balance — these subsystems look healthy:

- **Health monitor**: status nominal, 163 healthy cycles, milestones firing.
- **Calibration core**: Brier 0.0607 over n=866 is genuinely good; bias small (−0.07).
- **Symbolic fallback**: 510/510 queries resolved symbolically with 109 rules; COGNITIVE prediction accuracy 75% (n=509). Rule rehabilitation/demotion in `self_improvement_log` is making sensible, small adjustments.
- **Problem refocus** correctly detected the LLM outage and spawned a properly-shaped fix goal (it just can't finish it).
- **Interoception/temporal sense** produce coherent self-reports (prediction-error tracking, session arc, "very far into this").
- Working-memory chunking, dedupe ("Skipped duplicate memory"), and compaction run regularly — though chunking at sim=0.25–0.28 is merging items that barely resemble each other, which feeds §8.

---

## Priority fix list (highest leverage first)

1. **Restore the LLM**: set a valid API key and decide whether `llm_enabled: false` is intentional; if intentional, make the fix goal's "work around it" branch actually complete so it stops haunting him (§1).
2. **Fix emotion keyword loading** — single bug, removes the "everything is neutral" pattern spam and gives the affect system real input (§2).
3. **Consume user input exactly once** — fix the re-processing loop / `last_seen_user_input` double-write (§3).
4. **Stop chunk-header re-chunking and snippet truncation from entering memory** — sanitize `[Chunk:` prefixes before re-storage, and raise the chunk-similarity threshold (§8). This is the main corruption vector for rumination, speech, and symbolic rules.
5. **Break the `assess_goal_progress` rut** — the anti-repeat/stagnation machinery sees it (`thrash=True`, rut detected) but doesn't penalize selection; close that loop (§6).
6. **Goal lifecycle**: completed goals must leave the active set (no complete/respawn loop), de-dupe plan steps, and replace placeholder plan steps from adapt_subgoals (§7).
7. **De-duplicate event emission** (self-model updates, mode changes, oscillation alerts logged 2× seconds apart) and strip telemetry from user-facing speech (§4, §10).
8. Smaller: register the `reflect_on_cognition_rhythm` prompt; fix or disable `simulate_future_selves`; link spaCy person names to `known_persons`; clean tmp files; remove test entries from `llm_failure_counts.json`.
