# Behavior Fix Plan — from BEHAVIOR_AUDIT_2026-06-09

Plan to fix every issue in `docs/BEHAVIOR_AUDIT_2026-06-09.md`. Each item names the
audit section it resolves, the files involved, the concrete change, and how we'll
know it worked.

---

## Governing principle: the LLM is only a tool

This shapes every fix below. The cognitive architecture must be **fully functional
with `llm_enabled: false`**. The LLM is one entry in the tool registry — the same
standing as Wikipedia lookup, web search, or file search. Orrin can *reach for it*
when it would help; he never *needs* it to run, and its absence is no more alarming
than Wikipedia being unreachable.

Concretely, that means four rules:

1. **The LLM is called through the same tool interface as every other tool.** One
   registry entry, same invocation path, same failure semantics: a failed call
   returns "tool unavailable" like a failed Wikipedia fetch — a result to note and
   route around, not an error to escalate, ruminate on, or re-attempt every cycle.
2. **Every cognitive function declares whether it needs the LLM.** If it does and
   the LLM is unavailable, it is *skipped cleanly* (not selected, no error, no
   half-output) — it never falls back to a template that pretends to be generative
   output. Template fallbacks are exactly what produced the telemetry-leaking
   speech (§4) and the placeholder plan steps (§7).
3. **No fix in this plan may be "have the LLM do it."** Dedup, goal lifecycle,
   memory hygiene, mode arbitration, emotion keyword loading — all deterministic
   code. The symbolic layer is already the thing that works (§12: 510/510 symbolic
   resolutions, Brier 0.0607); we strengthen it.
4. **Curiosity about a broken tool is fine; consumption by it is not.** Orrin
   noticing the outage and wanting to figure it out is healthy behavior — the
   problem-refocus system did its job (§12). The bug is that the investigation
   had no attention bound: failure signals flooded every cycle, the goal hung
   half-done forever, and the impasse fed rumination (§5). The fix is bounding,
   not suppressing: the investigation goal lives as an ordinary curiosity goal
   with a capped attention budget, and tool-failure signals are rate-limited so
   one dead tool can't dominate the signal stream.

---

## Phase 0 — Root causes (single-bug fixes with outsized blast radius)

### 0.1 Emotion keywords: the model file is empty (§2)

**Root cause (verified):** `brain/data/affect_model.json` is 2 bytes — `{}`.
`load_emotion_keywords()` (`brain/affect/model.py:18`) loads it fine, gets an empty
dict, and `detect_affect_keyword()` (`brain/utils/emotion_utils.py:108`) logs the
"No emotion keywords loaded" warning on every utterance and returns neutral/0.0.

**Fix:**
- Populate `affect_model.json` with keyword lists for each core affect category
  (matching the categories used in `affect_state.json` core_signals).
- Add a startup integrity check (in `brain/ORRIN_loop.py` boot, alongside other
  data-file checks): if `affect_model.json` parses to an empty dict, log **once**
  at startup and seed it from a packaged default (`brain/affect/` should own a
  `DEFAULT_EMOTION_KEYWORDS` constant) instead of warning per-utterance forever.
- Rate-limit the per-utterance error to once per session regardless.

**Done when:** a test message containing "I'm frustrated" classifies non-neutral
with intensity > 0; error log gains zero "No emotion keywords" lines in a 50-cycle
run.

### 0.2 User input consumed exactly once (§3)

**Root cause (verified):** in `brain/think/think_utils/user_input.py`,
`handle_user_input()` calls `log_user_input_once()` — which *records* the dedup
marker — but **never uses the dedup result to gate anything**. The
`is_real_user_input(user_input)` branch (signal creation, reward release, speech
evaluation, chat summarization) runs every cycle as long as the same line is the
last line of the chat log, because `get_user_input()` "returns last non-empty
line; does NOT clear file."

**Fix:**
- Make `log_user_input_once()` return `bool` (`True` = new input, `False` =
  already seen), and gate the entire real-input branch on it: signal creation,
  `release_reward_signal`, `evaluate_last_reply`, `comprehend`, values-check.
  A duplicate line should produce the same behavior as silence.
- Fix the `last_seen_user_input.txt` double-line: `write_text` can't append, so a
  second writer exists — grep for other writers of `LAST_SEEN_USER_INPUT` and
  remove them; `_persist_last_seen` becomes the sole writer.
- Add a regression test: feed the same line for 5 simulated cycles → exactly one
  user_input signal, one speech reply, one reward event.

**Done when:** the test passes; a live "what has your attention?" produces exactly
one reply and one notes entry.

### 0.3 LLM-as-tool: absence is normal, curiosity is bounded (§1, §11)

**Make it a tool call like any other:**

- Register the LLM as an entry in the tool registry (alongside the existing
  sandbox/search tools in `brain/behavior/tools/`), invoked through the same
  interface and returning the same shaped result on failure ("tool unavailable")
  as a dead Wikipedia fetch. No call site anywhere imports a model client
  directly.
- `model_config.json`: make the config self-consistent — if `llm_enabled: false`,
  nothing attempts calls and logs API-key failures. Find the 8 callers that
  bypassed the flag and route them through the single tool-call gate.
- Create a single `llm_available()` predicate (config flag AND no recent hard
  failures) in one module; the tool wrapper checks it. No call site catches its
  own failure and silently degrades to a template.
- Tag every cognitive function in the registry with `requires_llm: bool`.
  `select_function` (`brain/think/think_utils/select_function.py`) filters
  `requires_llm` functions out of the candidate set when `llm_available()` is
  false — same mechanism as the existing `_avoid_capability: "llm"` goal tag,
  extended to function selection. This permanently retires `simulate_future_selves`
  / `self_supervised_repair` failing every run (§11): when the LLM is down they
  simply aren't candidates.

**Let him wonder about it without being consumed by it:**

- The §1 fix goal ("Figure out why the language model isn't working") is
  *legitimate* — keep it. But it competes as an ordinary curiosity goal, not a
  crisis: cap its motivational_weight (≤ ~0.4) and exempt it from
  `problem_refocus` re-boosting, so a broken tool can never outrank his actual
  goals.
- Give the investigation real, finishable steps he can do *symbolically*: read
  `model_config.json` (he can: file tools), read `model_failures.txt`, conclude
  "disabled in config / key invalid — needs the operator." That conclusion
  satisfies the "decide to fix or work around" milestone honestly: the decision
  is "work around it and note it for the operator." The goal then completes like
  any other — no auto-closing by the framework, no eternal half-done state.
- **Rate-limit tool-failure signals:** one "LLM unavailable" signal per N cycles
  (not 8 failures logged in one minute, each becoming a penalty signal via the
  error-file scan in `user_input.py`). A dead tool produces a fact, not a
  drumbeat. Same rule applies to every tool in the registry.
- Tool outages never spawn tensions or rumination seeds (wire into Phase 2.3's
  seed filter): "a tool I sometimes use is down" is not an unresolved inner
  conflict.
- If the operator later enables the LLM, no migration needed: the tool starts
  answering again, `requires_llm` functions rejoin the candidate set, done.

**Done when:** with `llm_enabled: false` and no key, a 100-cycle run logs zero
model-API failures and zero `simulate_future_selves` errors; the fix goal either
completes via the workaround decision or sits at low weight without consuming
selection cycles (< 5% of picks); no tension or rumination loop references the
LLM outage.

---

## Phase 1 — Memory hygiene (the corruption vector, §8)

The chunk-strip logic already added in `brain/cog_memory/working_memory.py:99-164`
(de-nesting `[Chunk:` prefixes, including truncated ones) addresses *new* writes.
Remaining work:

1. **Migration pass over existing state.** One-shot cleanup script
   (`brain/scripts/clean_corrupted_memory.py`) that walks `working_memory.json`,
   `long_memory.json`, `rumination_loops.json`, `tensions.json`,
   `reflection_log.json`: strip nested `[Chunk:` wrappers, drop entries that are
   mid-word truncations of other entries (suffix-match against full versions),
   and reset the reference count of the 243-times-referenced corrupted chunk so
   it stops dominating recall.
2. **Truncate at sentence boundaries, not byte counts.** Wherever the 500-char cap
   is applied before storage, cut at the last sentence/whitespace boundary and
   append a clean ellipsis — truncation artifacts must not be re-ingestible as
   content (`"...may need atte]"` from §8).
3. **Raise the chunk-similarity threshold.** §12 notes chunking merges at
   sim=0.25–0.28. Raise the floor to ~0.55 (tune empirically) so only genuinely
   related items merge; log skipped merges for one session to validate.
4. **Quarantine, don't crystallize, garbage.** Before symbolic-rule minting
   (`crystallized_skills` path) and analogy matching, reject source text that
   fails a sanity filter: contains `[Chunk:`, unbalanced brackets, or ends
   mid-word. The 15 degraded-confidence rules flagged by the verifier get a
   one-shot review pass: delete any whose source text fails the same filter.
5. **Knowledge-graph entity filter.** In the heuristic extractor, reject entities
   that are pure numbers/percentages/durations (`"+15%"`, `"5h 5"`, `"around
   hour"`) — require at least one alphabetic token that isn't a stopword/unit.
   Migration: prune existing junk entities from `knowledge_graph.json`.

**Done when:** after migration + a 100-cycle run, zero entries in working memory
contain `[Chunk: [Chunk:`; no new rule cites text containing a chunk header; KG
gains no number-only entities.

---

## Phase 2 — Behavior loops

### 2.1 Break the `assess_goal_progress` rut (§6)

The detectors work (metacog flags the rut, `thrash=True`); the selection loop
ignores them. Close the loop in `select_function.py`:

- **Repetition penalty:** score multiplier that decays with consecutive picks of
  the same function (e.g. ×0.6 per consecutive repeat beyond 2, floor 0.1).
  Deterministic, always on — not dependent on metacog noticing.
- **Internal success ≠ reward.** The `semantic_facts` self-reinforcement
  ("success" ×95 because assessing always produces an assessment) is the engine
  of the rut. Reflective functions whose only output is internal state should
  record success at reduced weight (or require a downstream effect — a goal step
  advanced, an action taken — to count as full success). Touch the
  success-recording path in `brain/cognition/metacog.py` /
  `brain/cognition/planning/goal_progress.py`.
- **Metacog rut signal acts:** when metacognition emits a rut/imbalance note, it
  also writes a temporary suppression entry (function name + N-cycle cooldown)
  that `select_function` honors. The note alone changed nothing all day.
- **Calibration flip-flop (§6):** widen the overconfident/underconfident
  assessment window so it can't flip sign in 3 minutes — minimum sample count
  (e.g. n ≥ 30 predictions) before emitting a calibration self-note.

**Done when:** in a 100-cycle run, no function is picked more than 4× in any
10-cycle window; `semantic_facts` confidence for `assess_goal_progress` declines
when it produces no downstream goal movement.

### 2.2 Goal lifecycle (§7)

In `brain/cognition/planning/goals.py`, `pursue_goal.py`, and
`cognition/intrinsic_goals`:

- **Completion is terminal.** When a goal enters `recently_completed`, atomically
  remove it from `goals_mem.json` active set in the same write. The respawn
  guard: intrinsic-goal generation checks `recently_completed` (with a cooldown
  window) before re-creating a goal with the same normalized title.
- **De-dupe plan steps** on every `set_goal_plan` call (`pursue_goal.py:349,643,657,778`):
  normalized-text uniqueness within a plan; refuse to append a step that already
  exists in any status.
- **Ban placeholder steps.** `adapt_subgoals` output is validated: steps matching
  a placeholder blacklist ("do the thing", "continue as planned", "reflect",
  bare "gather context") are rejected; if the adapter can't produce a concrete
  step *symbolically*, the goal is marked `blocked: needs_capability` with the
  missing capability named — honest blockage beats fake plans. (LLM-as-tool rule:
  the adapter may *optionally* use the LLM when available, but its failure mode
  is "blocked", never filler.)
- **Fix the "Resolve blocker: I am blocked:" text-nesting** — blocker steps are
  built from a description that already contains the prefix; build from the raw
  reason only.
- **Benchmark B3 never executed (§7):** the milestone "find the word 'reaper' in
  any brain file" requires a file-search *action*. Verify the step-execution path
  (`brain/cognition/planning/step_execution.py`) can map a search-shaped step to
  the sandbox/file-search behavior tool; B3 becomes the regression test for
  "plans cause actions."
- **Commitments link to goals:** when `commitments.json` gains an entry, assert a
  corresponding active goal exists or create one; nightly consistency check logs
  orphaned commitments.

**Done when:** B3 completes end-to-end; "Write a cognitive function" goal exists
in exactly one of {active, recently_completed}; no plan contains duplicate or
blacklisted steps after a 100-cycle run.

### 2.3 Rumination and regulation (§5)

- **Tension TTL + escalation:** a tension active > N cycles (e.g. 200) without
  resolution progress is automatically downgraded to a logged open question and
  cleared from the active tension set — targetless rumination ("can't find what
  it is") must not run for 647 cycles.
- **Fix the self-nesting title bug:** tension re-surfacing rebuilds the title
  from the original description field, never from the previous (already
  prefixed) title. Same class of bug as the "I am blocked: I am blocked"
  nesting in 2.2 — audit all string-builders that re-ingest their own output.
- **Regulation honesty (`brain/affect/regulation.py`):** "success" requires a
  measured effect — the target signal (e.g. `impasse_signal`) must drop by a
  minimum delta within K cycles, otherwise the attempt is logged as
  *ineffective*. Ineffective strategies enter a cooldown so the same canned
  reappraisal can't fire 5× in 3 minutes; after M consecutive ineffective
  attempts on the same tension, regulation stops and the tension routes to the
  TTL/escalation path instead.
- Rumination seeds pass the Phase 1 sanity filter (no brooding on truncated
  chunk headers).

**Done when:** no tension exceeds its TTL in a long run; regulation log shows
ineffective-marked entries and varied strategy selection; `impasse_signal` no
longer pins at 0.85–1.0 for hours.

---

## Phase 3 — Conversation quality (§4)

- **Speech source filter (`brain/behavior/speak.py:432` region):** the "Earlier I
  was thinking:" path picks from memory candidates that include telemetry lines
  written by `brain/motivation/substrate.py:324` (`[motivation] High-activation
  drives: ...`). Tag all telemetry/diagnostic memory writes (`internal_telemetry`
  tag at write time) and exclude that tag — plus anything matching the Phase 1
  sanity filter — from speech candidate retrieval. User-facing text never
  contains `[bracketed]` system prefixes; add an output-side assertion that
  strips/logs any that slip through.
- **Honest unavailability beats deflection.** Per the LLM-as-tool principle:
  when no grounded answer exists, the speaker says so plainly (short, varied
  "I don't have a good answer to that yet") instead of the "What got you
  thinking about this?" deflection template firing every turn. Cap any single
  template at once per conversation window.
- **Speech evaluator (`brain/think/speech_evaluator.py:138`):** quality_score
  frozen at 0.622 means the inputs are constant — likely because every reply got
  identical neutral/0.0 emotion features (fixed by 0.1) and duplicate
  re-evaluations (fixed by 0.2). After those land, verify scores vary; populate
  the empty `response_type`/`tone`/`source` fields at generation time, not
  evaluation time.
- **Person linking (`brain/cognition/selfhood/person_detector.py`):** on a
  self-introduction pattern ("my name is X", "I'm X"), update the active
  `known_persons.json` record: set `display_name`, `person_type: "named"`, and
  link the KG entity for the name to the person record. Merge the two duplicate
  "someone" records. **Relationship-arc gating:** arc stage cannot advance past
  "forming" while the counterpart person record has `person_type: "unknown"` —
  fixes the inflated forming→established-in-16-minutes arc.

**Done when:** scripted conversation test — "my name is jon" → `known_persons`
has a named record; "how are you?" → reply contains no `[` telemetry; repeated
question → at most one deflection; quality_score varies across replies.

---

## Phase 4 — Control-system stability (§10) and event hygiene (§4, §9, §10)

- **One mode authority.** `brain/affect/modes_and_affect.py:53` ("Automatic
  adjustment...") and `brain/affect/update_affect_state.py:547` ("Dominant
  emotional state prompted mode shift") both write the mode — two controllers
  fighting one knob. Route both through a single mode arbiter (mirroring the
  existing AffectArbiter pattern in `affect/arbiter.py`) with: minimum dwell
  time per mode (e.g. 50 cycles), hysteresis on the triggering signal, and one
  logged transition per actual change.
- **Drive saturation (§10):** drives pinned at 1.0 give the arbiter no gradient.
  Add a soft normalization/decay in `brain/motivation/substrate.py` so
  competing drives stay differentiable (renormalize toward a fixed total
  activation budget rather than independent clamps).
- **De-duplicate event emission:** the duplicated self-model writes (twice in 5
  s, §9), mode-change double-fires, and repeated oscillation alerts share one
  fix: an idempotency guard at the event-emission layer (`brain/events.py`) —
  drop an event identical (type + payload hash) to one emitted within a short
  window. Also: only write "Self-model updated" when a value actually changed.
- **Self-model identity content (§9):** `core_values` / `traits` /
  `known_roles` / `recent_focus` are empty since bootstrap. Seed them from the
  existing bootstrap directive symbolically (deterministic mapping, not LLM
  prose), and make `recent_focus` maintained mechanically from the goal/WM
  state each consolidation pass. Domain scores that haven't moved all day (§9)
  should move when Phase 2.2 makes plans produce actions — add a metric hook so
  completed concrete steps credit the matching knowledge domain.

**Done when:** mode transitions ≥ 5 minutes apart in a long run, each logged
once; no duplicate self-model/oscillation events; self-model identity fields
non-empty; TECHNICAL/PLANNING move after completed concrete steps.

---

## Phase 5 — Cleanup and guardrails (§11)

| Item | Action |
|---|---|
| `UnboundLocalError: set_goal_plan` (`pursue_goal.py:379`, dated 2026-06-06) | Top-level import exists now (`pursue_goal.py:41`); confirm no shadowed local assignment remains, add a regression test, close. |
| Missing prompt `reflect_on_cognition_rhythm` | The `ORRIN_loop.py:753` lambda stub papers over it. Either register a real prompt or remove the function from selection registries (`ORRIN_loop.py:2328,2386`) — per LLM-as-tool, if it needs the LLM it gets `requires_llm: true` and the 0.3 gate handles it. |
| `simulate_future_selves`, `self_supervised_repair` failures | Covered by 0.3 (`requires_llm` gating). Delete dead error-handling paths. |
| Test pollution in `llm_failure_counts.json` | Point tests at a tmp data dir (fixture); migration deletes `test_*` keys from live state. |
| tmp files (`tmp9t6bbc33` etc., `trace.jsonl.*.tmp`) in `brain/data/` | Atomic-write helper must clean up on failure; add startup sweep deleting `tmp*`/`*.tmp` older than 1 day. |
| `outbox/notes.json` all `"read": false` | Decide the consumer story: either the backend hub (`backend/server/hub.py`) marks notes read on delivery, or drop the field. Dead protocol fields invite false debugging leads. |
| Multiprocessing semaphore leak at shutdown | Ensure pools/executors are context-managed in `ORRIN_loop.py` shutdown path. |
| Host pressure (memory/disk 85–88%) | Operator note: not a code fix, but log-rotation for `error_log.txt` (hundreds of duplicate lines/hour pre-0.1) and the Phase 1 memory compaction will cut disk churn substantially. |

---

## Sequencing and verification

Order: **0.1 → 0.2 → 0.3** (root causes; everything downstream is unmeasurable
while input re-processing and neutral-emotion spam pollute every log) → **Phase 1**
(stop corruption before fixing consumers of corrupted data) → **2.x in parallel**
→ **3 → 4 → 5**.

Each phase ends with the same harness: a scripted soak run (the audit was ~870
cycles / 10.5 h; use a 100-cycle smoke + overnight soak) plus the B1–B5 benchmark
suite. The audit itself is the regression spec — re-run the same survey of
`brain/data/` after the soak and diff against `BEHAVIOR_AUDIT_2026-06-09.md`
section by section.

Success criteria for the whole plan, in one line each:

1. Orrin runs indefinitely with the LLM disabled — zero LLM-related errors; the
   LLM is just a registry tool he can call when it's up, and being down costs
   him at most a low-weight curiosity goal, never his attention (§1, §11).
2. Emotion classification returns non-neutral for emotional text (§2).
3. One input → one processing pass → one reply (§3).
4. User-facing speech contains no telemetry or bracket garbage; Jon gets named (§4).
5. No tension lives past its TTL; regulation reports honest effectiveness (§5).
6. No function dominates selection; internal-only success is discounted (§6).
7. Goals complete terminally; plans contain only concrete, unique steps; B3 passes (§7).
8. No nested-chunk or truncation artifacts in memory, rules, or KG (§8).
9. Self-model has identity content and domain scores that respond to action (§9).
10. One mode controller, with dwell time; no duplicate events (§10).
