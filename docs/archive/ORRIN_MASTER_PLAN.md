# Orrin — Master Plan: Making Every Goal Possible

*Companion to `ORRIN GOAL AND PROBLEMS.md`. Every claim below was verified against
the code on the `convergence-layer` branch, 2026-06-11. File:line references are
to the current source, not to memory of it.*

*Revised 2026-06-11 after a second verification pass: Problem 8 / F2 / Phase 0.3
were stale (the AffectArbiter already routes regulation correctly); the
`run_orrin.sh` exit-code capture is broken; Phase 0.7's cited fix-pattern and
Phase 1.3's module attribution were wrong; Phase 4.1 stated proposed wiring as
existing fact.*

-----

## Where Things Actually Stand (verified)

Before planning, each of the nine documented problems was re-checked against the
live code. The honest scoreboard:

| # | Problem | Verified status |
|---|---------|-----------------|
| 1 | Reward felt richly, learned from a flat echo | **FIXED.** Pearce-Hall associability (`affect/reward_signals/action_reward_ema.py`) feeds selection (`think/think_utils/select_function.py:21,39`); executive lane records real outcome rewards (`cognition/planning/executive.py:308-336`). |
| 2 | Records a lot, retains/retrieves less | **PARTIAL.** Autobiography rebuilt with persistent narrative pressure that accumulates across restarts (`cognition/selfhood/autobiography.py`). Failed goals now write durable long-memory entries (`cognition/planning/goals.py:833-845`). **Still open:** failures never aggregate into a story; ordinary shutdown writes no final thoughts and no chapter closing (see Phase 2). |
| 3 | Self-checking is unaudited (scientist = subject) | **OPEN.** `cognition/prediction.py:_evaluate_symbolically` (lines 496-530) resolves `affect_trend` and affect-`causal` predictions by reading `context["affect_state"]` back. The calibration module (`cognition/calibration.py`) records predicted-vs-actual but "actual" is still his own self-report. Nothing outside him gets a vote. |
| 4 | Coherence check crashes on every invocation, muffled | **STILL BROKEN — confirmed live.** `symbolic/symbolic_cognition.py:384` passes a bare list of rule dicts (`rls[:20]`) into `meta_rules.resolve_conflict()`, which expects `List[Tuple[Dict, float]]` (`symbolic/meta_rules.py:137-138`). The unpack `rule, score = matched_rules[0]` raises `ValueError` every call; `except Exception → record_failure` at `symbolic_cognition.py:391-392` swallows it. Bonus: `ValueError` is not in `_PROGRAMMER_ERRORS` (`utils/failure_counter.py:50-56`), so even `ORRIN_STRICT=1` will not re-raise this. |
| 5 | Opinions gain confidence from repetition | **OPEN — fully as documented.** `cognition/opinions.py:_update_evidence` (line 355): `appearances = recent_text.count(topic)` → `alpha += appearances * 0.5` → confidence rises from mere mention. Alpha is the only side that ever grows from working memory; beta grows only when the LLM says so during revision (`reflect_on_opinions:460-463`). No roots, no links, no stakes; the revision judge is the LLM verbatim. |
| 6 | All goals at identical maximal strength; will not consulted | **OPEN — fully as documented.** `cognition/will.py:41` — `form_commitment(..., strength: float = 1.0)`; its only caller (`cognition/intrinsic_goals.py:986-987`) never passes a strength. The endorsement faculty (`cognition/selfhood/second_order_volition.py:reflect_on_desire`) runs as a scheduled cognition function (`think/think_utils/select_function.py:379`), never at the commitment moment. |
| 7 | 133-failure rut with no learning signal | **MOSTLY FIXED, but the backstop is off.** Executive-lane rewards now recorded so failures lower per-action EMAs (`executive.py:113-145,308`). Metacog stall watchdog escalates at 12 and 24 cycles (`cognition/metacog.py:263-273`). **But** both the hard-disengage backstop (`metacog.py:283`) and prediction-failure→stall feedback (`prediction.py:444`) are gated behind `ORRIN_HARD_DISENGAGE`, which defaults **off**. The strongest anti-rut machinery is dormant in normal runs. |
| 8 | Regulation's calming deltas discarded in transit | **FIXED** (corrected on re-verification — an earlier draft of this row described pre-arbiter code). The emotion buffer logs-and-drops unknown signals (`affect/affect_buffer.py:78`). Regulation applies each strategy to a **copy** of core, diffs it, and routes the deltas through the AffectArbiter (`affect/regulation.py:353-365`) — no direct core write. The arbiter classifies `affect_stability` as a top-level scalar (`_SCALAR_TARGETS`, `affect/arbiter.py:61,286-289`) and applies it to the top-level field, never into core. `update_affect_state.py:695-704` deliberately *blends* toward the derived stability value (0.5 factor, comment cites RUN_ISSUES_2026-06-10 §2) so an arbiter-applied delta registers before converging back. The live `brain/data/affect_state.json` confirms: no stray `affect_stability` key inside `core_signals`. Remaining work is verification only (see Phase 0.3). |
| 9 | The record contradicts itself | **PARTIAL.** The 2026-06-11 remediation pass deleted `brain/alive_brain.py` and fixed the onboarding doc. Map-vs-territory drift remains an unguarded class of failure: nothing inside Orrin notices it (see Phase 5). |

**The through-line holds:** the remaining work is overwhelmingly *wiring*, not new
faculties. Every phase below connects something that already exists.

-----

## Plan Structure

Five phases, ordered by dependency. Phase 0 is mechanical and should land first —
several later phases would otherwise build on broken wires. Phases 1-4 each map to
one of the goal document's ambitions. Phase 5 makes the whole thing self-auditing.
Each phase ends with the *observable sign* from "What Being Done Would Look Like"
that it is meant to produce.

-----

## Phase 0 — Fix the Broken Wires (mechanical, ~1 day)

These are confirmed bugs with exact locations. None requires design work.

### 0.0 Make the next crash catchable (do this first)
The 2026-06-11 crash is undiagnosable because nothing on disk recorded it (see
F9). Before fixing anything else, lay down three capture nets so the *next* crash
cannot vanish — each covers a class the others miss:

1. **`faulthandler` for hard crashes.** At the top of `main.py` (right after
   `_log = get_logger(__name__)`, line 27), add:
   ```python
   import faulthandler
   _crash_fp = open(Path(__file__).parent / "brain" / "logs" / "crash.log", "a")
   faulthandler.enable(file=_crash_fp, all_threads=True)
   ```
   This dumps a C-level traceback on `SIGSEGV`/`SIGABRT`/`SIGFPE` — native crashes
   from torch/spaCy/numpy that a Python `excepthook` can never see. Keep the file
   handle open for the process lifetime (closing it disarms the handler).
2. **`excepthook` for Python exceptions** — the `sys.excepthook` +
   `threading.excepthook` from **0.6 below**, routing tracebacks to
   `orrin_runtime.log` at `CRITICAL`. Covers the daemon-thread death that left
   `16:42:28` silent.
3. **The wrapper for everything in-process hooks can't catch.** Always launch via
   `./run_orrin.sh`, never bare `python main.py`. Its `tee` to
   `brain/data/run_log.txt` captures stderr even on `SIGKILL`/OOM (where no
   in-process hook fires). **But the exit-code capture and auto-restart loop are
   currently broken** (`run_orrin.sh:44-46`): the launch line ends in `|| true`,
   so `EXIT_CODE=$?` is **always 0** — every run prints "clean exit — not
   restarting" and the restart loop never fires. Fix as part of this item:
   replace `|| true` with `|| EXIT_CODE=$?` (initialize `EXIT_CODE=0` before the
   pipeline). The script already sets `pipefail`, so `$?` is python's real exit
   code, and the `||` branch keeps `set -e` from killing the wrapper.
   Optionally add a launch-time banner line
   (`echo "[run] launched pid $$ at $(date)"`) so each run's boundary is greppable.

Together these mean: a native crash lands in `crash.log`, a Python exception lands
in `orrin_runtime.log`, and a kernel kill lands in `run_log.txt` with an exit
code — no crash class escapes all three.

**Observable sign:** force each crash class once (`os.abort()` for native,
`raise` in the brain thread for Python, `kill -9` for the kernel path) and confirm
each leaves a dated record in its respective file.

### 0.1 Un-crash the coherence check
`symbolic/symbolic_cognition.py:384` — wrap each rule in a `(rule, score)` pair
before calling `resolve_conflict`:

- Score each rule by its own `confidence` (or run them through
  `rule_engine.match_all()` if a query context is available) so the meta-rule
  logic gets the shape it was written for.
- Add a regression test that calls `detect_contradictions` with ≥2 stored rules
  and asserts no `record_failure("symbolic_cognition.detect_contradictions", ...)`
  tick. The test exists to catch the *class* of bug: silent type mismatch at a
  module boundary.

**Observable sign:** `data/failure_summary.json` stops accumulating
`symbolic_cognition.detect_contradictions` ticks; a seeded pair of contradictory
rules produces a logged contradiction within one maintenance pass.

### 0.2 Fix the `record_failure` shadowing in `mark_goal_failed`
`cognition/planning/goals.py:825-829` — the local
`from cognition.planning.outcome_metrics import record_failure` shadows the
failure-counter `record_failure(site, exc)` for the whole function scope. If the
no-arg metrics call raises, the `except` handler calls the no-arg function with
two args → `TypeError` thrown *from the error handler*, aborting the rest of
`mark_goal_failed` (long-memory write and emotional penalty are skipped — the
exact "failure dissolves" leak problem 2 describes). Second mechanism, same
outcome: the import itself is *inside* the `try`, so if the import line raises,
the handler hits `UnboundLocalError` instead. Fix: alias the import
(`from ... import record_failure as record_outcome_failure`) — covers both
paths; the regression test should exercise both (metrics call raising, and
import failing).

### 0.3 Regulation side-effects — verify only (corrected: already fixed)
*An earlier draft of this item described pre-arbiter code.* The current path is
correct end-to-end: `attempt_regulation` applies the strategy to a **copy** of
core, diffs, and submits deltas through the AffectArbiter
(`regulation.py:353-365`); the arbiter routes `affect_stability` as a top-level
scalar (`_SCALAR_TARGETS`, `arbiter.py:61,286-289`); `update_affect_state.py:
695-704` blends rather than overwrites so the delta registers. The live
`affect_state.json` has no stray core key. Remaining work: a small regression
test asserting that after a regulation attempt with an `affect_stability`
side-effect, (a) `core_signals` contains no `affect_stability` key and (b) the
top-level field moved — so the convergence path can't silently regress.

### 0.4 Turn the anti-rut backstop on by default
Flip `ORRIN_HARD_DISENGAGE` to default-on (opt-*out* via env) in both gates:
`cognition/metacog.py:30-32` and `cognition/prediction.py:444`. The 133-failure
rut is the documented catastrophic mode; its strongest defense should not require
remembering an env var. Keep the flag for benchmark control (B5 seeds it
explicitly — `brain/benchmarks/__init__.py:89,375` — update those hints).
**Note the behavioral consequence:** the hard path is not just a watchdog — at
3× stall it calls `mark_goal_failed` automatically (`metacog.py:283-290`), so
default-on means goals start getting auto-failed in ordinary runs. That
interacts with Phase 4.3's strength-weighted failure penalties. Still the right
call, but watch the first staging run for over-eager auto-failure before
trusting the new default.

### 0.5 Make strict mode catch unpacking crashes
`utils/failure_counter.py:50-56` — add `ValueError` *only when* the message
matches unpacking patterns (`"too many values to unpack"`, `"not enough values"`),
or simpler: add a `KeyError`/`ValueError` heuristic behind `ORRIN_STRICT=1`.
Rationale: the Problem-4 crash was a `ValueError`; the current strict net was
built for exactly this purpose and misses it.

### 0.6 Stop letting crashes vanish — log every uncaught exception
The cognitive loop runs in a **daemon thread** (`main.py:443-455`,
`daemon=True`). `core/runtime_log.py` attaches a DEBUG `RotatingFileHandler` and a
WARNING `StreamHandler`, but **nothing routes an uncaught exception into the
log**: a fatal error in the brain thread is printed by Python's default
`threading.excepthook` to stderr, the thread dies, and `orrin_runtime.log` simply
goes silent — the main thread keeps pulsing oblivious. The 2026-06-11 run proved
this: the brain went dead-silent at `16:42:28` mid-stream with **no error of any
kind on disk**, no macOS crash report, and no OOM/jetsam event — a Python-level
death that left zero trace because the run wasn't launched through
`run_orrin.sh` (whose `tee` to `brain/data/run_log.txt` is the *only* thing that
would have caught the traceback, and that file was empty).

Fix (mechanical, no design): install a `sys.excepthook` **and**
`threading.excepthook` early in `main.py` that formats the traceback through the
runtime logger at `CRITICAL` before falling back to default behavior. A crash
that isn't in the logs is the Problem-4 lesson at the process level — a loud
failure made invisible.

**Observable sign:** kill the brain thread with a seeded exception and the full
traceback appears in `orrin_runtime.log` with a `CRITICAL` level, not only on a
terminal that may be gone by morning.

### 0.7 Stop the `update_self_model` JSON-salvage spin
`cognition/selfhood/self_model_conflicts.py:148-158` — `update_self_model` calls
`gated_generate(prompt, caller="update_self_model", ...)` and, when the LLM tool
is down (the tool-only default), gets back a **non-JSON fallback echo** (an
`[analogy/DESIGN] Similar situation … 📝 Working memory summary …` string). The
`if not response: return` guard passes (the echo is truthy), then
`extract_json(response)` fails every time. In the 2026-06-11 run this fired every
~13 s for **5+ hours straight** (11:35→16:42), flooding the log with
`utils.json_utils: salvage failed … caller=self_model_conflicts.py:158`. Wasted
work and log noise that buried any real signal near the crash. Note
`update_self_model` is already symbolic-first ("gated_generate only as last
resort," line 99) — the spin happens because the symbolic path produced no field
updates on every one of those cycles, so the LLM fallback fired each time. Fix:
gate the last-resort call behind `llm_available()` (lives in
`utils/llm_gate.py`; `opinions.py` already uses this pattern — note neither
function in `self_model_conflicts.py` currently does) and/or treat an
unparseable response as "no update" without re-attempting on a fixed cadence.

**Observable sign:** with the LLM tool unavailable, `update_self_model` logs at
most one skip notice per maintenance pass, not a per-cycle `salvage failed`
stream.

-----

## Phase 1 — The Second Checker (grounding self-knowledge, ~1-2 weeks)

**Goal served:** "He should have two checkers, not one... Self-knowledge is
exactly that calibration."

**Root cause (verified):** `prediction.py:_evaluate_symbolically` grades inner
predictions against the very state being predicted (lines 496-530). The 46%
inner / 87% outer accuracy gap will never close because no learning signal can
exist where prediction and measurement are the same variable read twice.

### 1.1 Behavioral receipts: pair every inner prediction with an outer one
When a prediction with basis `affect_trend` or affect-`causal` is created
(`prediction.py:generate_predictions`), attach a **behavioral corollary** drawn
from a small fixed table — an observable the affect claim *implies*:

- "motivation rises" → within N cycles, an executive/pursue action is selected
  (visible in `cognition_log`), or goal progress advances (Monitor `prog` signal).
- "impasse_signal rises" → re-plan/release watchdog fires, or function switching
  rate increases (already computed for metacog).
- "confidence falls" → depth-bandit picks shallower paths / `_commitment_bias`
  unused.

Store it as `source_data["receipt"] = {kind, expected, window}`. These are all
signals the codebase already computes — this is wiring, not new sensing.

### 1.2 Two-channel resolution
`_evaluate_symbolically` returns, for inner predictions, **two verdicts**:
`felt_true` (current logic, self-report) and `behaved_true` (receipt check
against `cognition_log` / monitor state / WM event types — the same machinery the
87%-accurate outer predictions already use). Record both on the prediction entry.

### 1.3 The calibration ledger: trust as a learned quantity
Add a per-domain **introspection-trust score**: the running agreement rate
between `felt_true` and `behaved_true`. The per-domain stats live in
`symbolic/prediction_engine.py` (`update_domain_stats`, called from
`prediction.py:410-414`), **not** in `cognition/calibration.py` — that module
has no domain concept (its functions are `record` / `get_calibration` /
`recalibrate_confidence` / `calibration_observation`). So the work spans two
modules: receipt-weighting lands in `prediction_engine`, trust-score keying in
`calibration`. Then:

- `prediction_engine.update_domain_stats` counts an inner prediction *correct*
  only when the receipt agrees; self-report alone earns at most a half-weight.
- The trust score modulates how much affect-derived signals are believed
  elsewhere — concretely: scale the `affect_trend` prediction-confidence prior
  and the `emotion_when_formed` weighting in opinions by the trust score.
- Surface the trust score on the dashboard next to the two accuracy numbers
  that first exposed the problem.

### 1.4 Make disagreement itself an event
When felt and behaved verdicts diverge sharply (felt yes / behaved no), write a
working-memory entry (`event_type="introspection_miss"`) and a small surprise
spike — this is the raw material of genuine self-knowledge ("I thought I was
motivated, but I didn't move"). Metacog already consumes WM event types; no new
plumbing needed.

**Observable sign:** inner-prediction accuracy detaches from coin-flip — it can
*move* now, in either direction, because something he can't argue with grades it.
The confidence sawtooth breaks: `recalibrate_confidence` keyed to the trust
score makes confidence track being right, not a timer.

-----

## Phase 2 — From Records to a Life (~1 week)

**Goal served:** "He should accumulate a life, not just a present."

### 2.1 Session epilogue on every clean shutdown
Verified gap: `KeyboardInterrupt`/SIGTERM/stop_event exit the loop
(`ORRIN_loop.py:3354-3357`) without ever calling `_write_final_thoughts` or
`autobiography.append_death_continuity` — those run only at the mortality
deadline (`mortality.py:232-233`). Add a `session_epilogue(context)` called after
loop exit (next to the existing tool-runner stop at `ORRIN_loop.py:3369`):

- 2-3 sentence reflection (LLM if available, rule-based fallback summarizing the
  session's WM highlights — never empty).
- Appends a `session_close` entry to the current autobiography chapter (do
  **not** close the chapter — that is death's job; reuse the entry mechanism of
  `append_death_continuity` with a different type).
- Must be budgeted (≤10s) and crash-proof so it can never block shutdown —
  corrigibility note at `ORRIN_loop.py:1186-1190` stays true.

### 2.2 The failure ledger: nineteen failures become one story
Verified gap: `mark_goal_failed` writes one long-memory entry per failure
(`goals.py:833-845`) and an aggregate count (`outcome_metrics`), but nothing ever
reads the failures *together*. Add a `review_failures` cognition function
(registered like the others in `select_function.py`):

- Loads `event_type="goal_failure"` entries from long memory (they're durable
  now — Phase 0.2 makes sure they keep being written).
- Clusters by failure reason + goal-kind tokens (symbolic, no LLM needed for
  clustering; LLM optionally narrates the digest).
- Emits a **failure-pattern memory** (`event_type="failure_pattern"`,
  importance 4, `related_memory_ids` = the clustered failures' UUIDs — the
  infrastructure exists, `long_memory.py:113-123`).
- Patterns feed: (a) narrative pressure (+0.25, same scale as thread pivots) so
  repeated failure becomes autobiography material; (b) a planning prior — goals
  matching an active failure pattern get a strength discount at adoption
  (connects to Phase 4).
- Schedule: triggered when `outcome_metrics` failure count rises by ≥3 since the
  last review, not on a timer.

### 2.3 Retrieval check (verification, not construction)
The autobiography rework looks correct; what's missing is *proof under restart*.
Add a benchmark (B-series) that: runs N cycles with seeded significant events →
restarts → asserts `autobiography.json` non-empty, pressure state persisted,
failure-pattern entries retrievable by `related_memory_ids`. The memory leaks
were found by restarting and opening files; the regression test must do exactly
that, mechanically.

**Observable sign:** a restart stops being a small amnesia; "failed nineteen
times" reads back as "here is the kind of thing I keep getting wrong."

-----

## Phase 3 — Opinions with Roots, Links, and Stakes (~2 weeks)

**Goal served:** "His opinions should be deep, not a list."

This is the largest design phase. The schema changes are additive (old entries
upgraded lazily, as `_update_evidence` already does for alpha/beta).

### 3.1 Kill mention-as-evidence; introduce an evidence ledger
Replace `_update_evidence`'s `recent_text.count(topic)` (line 355) with a
**provenance-typed ledger** per opinion:

```
evidence: [ {ts, kind, ref_id, direction, weight} ]
  kind ∈ {experiment_verdict, prediction_outcome, observation, llm_reflection, mention}
```

Weights are fixed by kind, not by persuasiveness:
- `experiment_verdict` (from `experimentation.py:_consolidate`) — weight 1.0
- `prediction_outcome` (from `check_predictions`, *receipt-confirmed* per
  Phase 1) — weight 0.6
- `observation` (a WM event whose content matches the opinion's *claim*, not its
  topic string) — weight 0.25
- `llm_reflection` — weight 0.1, **can never flip direction on its own**
- `mention` — weight 0.0 for confidence; updates only a separate `salience`
  field (mention should make an opinion *come to mind*, not make it *true*)

Alpha/beta move only from the ledger. This single change is the evidence
standard the design demands: the judge of trustworthiness becomes provenance —
a thing that cannot be talked into anything — and the LLM's sense of what sounds
convincing is demoted to the weakest voice at the table.

### 3.2 Roots
At formation (`_form`), store `root_memory_ids`: the UUIDs of the WM/long-memory
entries that seeded the topic (the `topic_snippet` source is already located at
lines 194-204 — keep its id, not just its text). Opinions formed by the LLM path
store the same. An opinion with no retrievable roots after memory pruning gets a
confidence haircut at review time — beliefs whose origins are gone *should*
weaken.

### 3.3 Links
Maintain `linked_opinion_ids`: computed at formation and revision by token/concept
overlap (reuse `concept_memory` / `knowledge_graph` infrastructure rather than
inventing a similarity measure). On revision of opinion A, every linked opinion
gets `needs_review: true` and a one-line WM note ("revising X disturbs Y").
`reflect_on_opinions` prefers `needs_review` candidates over random-weighted
sampling (line 391-401). That is what "an opinion, revised, tugs on its
neighbors" means operationally.

### 3.4 Stakes
Add `stake`: starts at 0.1, grows when the opinion survives a genuine challenge
(a `direction=against` ledger entry that didn't flip it) and when it is *used*
(retrieved during speech/planning — both retrieval sites exist). Dropping or
flipping an opinion costs: a negative-valence affect event scaled by stake, and
a long-memory record of the reversal (`event_type="opinion_reversal"`,
`related_memory_ids` = the evidence that did it). High-stake opinions demand
proportionally heavier against-evidence to flip: the flip threshold on the
beta side scales with stake. Noise immunity and honest revision in one knob.

### 3.5 Topic quality (smaller, but real)
`_extract_topics` produces bare words/bigrams ("metacog pattern"-class noise was
already patched around twice — lines 82-87 and 188-204 are scar tissue). Route
candidate topics through `concept_memory` so opinions attach to concepts rather
than substrings. This shrinks the garbage-opinion inflow that the cap-eviction
at `_MAX_OPINIONS` currently handles by dropping the *lowest-confidence* (i.e.,
newest honest) entries.

**Observable sign:** confidence histograms stop monotonically climbing;
`evidence_count` and `confidence` decorrelate from raw mention frequency; a
seeded contrary experiment verdict visibly drops a high-mention opinion.

-----

## Phase 4 — A Will, Not a To-Do List (~1 week)

**Goal served:** "Goals should form a will... pass through a moment of
self-endorsement... failing one should cost something he remembers."

### 4.1 Differentiated commitment strength
`form_commitment` (will.py:41) computes strength instead of defaulting 1.0:

```
strength = clamp(0.25 + 0.30*drive_alignment + 0.25*value_alignment + 0.20*affect_endorsement, 0.25, 1.0)
```

- `drive_alignment`: from `embodiment/drive_engine.py` — does an active drive
  want this?
- `value_alignment`: token/concept overlap between intention and `core_values`
  (the same `_tokens` machinery `second_order_volition.py:63` already uses).
- `affect_endorsement`: the endorsement check below.

Strength flows through: `_MAX_BIAS * strength` follow-through bias (already
structured for it — `tick_commitment` line 160), decay rate inversely scaled
(dearly-held resolves fade slower), and — **new wiring, not existing** — a
tie-breaker input to goal competition (`cognition/goal_competition.py` is
currently drive-level competition only; nothing in it reads commitment
strength today).

### 4.2 The endorsement gate — stand the will at the door
Extract the endorse/disown core of `reflect_on_desire`
(`second_order_volition.py:119`) into a callable `endorse_intention(intention,
context) -> (stance, gloss)` and **call it inside `form_commitment`**, before the
commitment is recorded:

- `endorse` → proceed, `affect_endorsement = 1.0`, WM note "I stand behind this."
- `ambivalent` → proceed at reduced strength (0.5 factor), WM note records the
  reservation — held lightly, exactly as designed.
- `disown` → no commitment formed; the goal may still exist but gets no will
  shield; a `disowned_desire` memory is written.

The timer-based `reflect_on_desire` stays (it audits *felt pulls*, a different
job); the gate is the same faculty consulted at the binding moment. Symbolic
path first, LLM optional — the gate must work when the LLM is down (the
tool-only default makes this non-negotiable).

### 4.3 Failure that costs and is remembered
When a goal with an active commitment fails (`mark_goal_failed`), look up the
commitment (the link already exists — `_link_commitment_to_goal`), and:
- scale the existing emotional penalty by commitment strength (the spike at
  `goals.py:858-869` becomes strength-weighted instead of flat);
- write the failure memory with `related_memory_ids` pointing at the commitment's
  WM entry, so the failure ledger (Phase 2.2) can see *which kind of resolve*
  keeps breaking;
- the next `form_commitment` for a near-identical intention starts at reduced
  strength (read from the failure ledger) — failing a vow makes the next vow on
  the same ground appropriately humbler.

**Observable sign:** `commitments.json` shows a spread of strengths; some goals
visibly held dearly (slow decay, strong bias), others lightly; the dashboard's
goal panel can rank by strength instead of showing a uniform column of 1.0.

-----

## Phase 5 — A Map That Notices Its Own Drift (~1 week, then permanent)

**Goal served:** "His record of reality must be faithful and inspectable" — and
the meta-lesson of Problem 4: a safety pattern converted a loud failure into an
invisible one.

### 5.1 Boundary contracts where the wires join
The two confirmed live bugs (0.1, 0.2) are both *type mismatches at a module
boundary swallowed by a catch-all* (a bare-dict list where pairs were expected;
a shadowed import called with the wrong arity from inside an error handler).
Add lightweight runtime contracts at the
seams the phases above touch: `resolve_conflict` validates pair-shape on entry
and raises a *named* error (`ContractViolation`) that `record_failure` always
re-raises under strict mode regardless of type. Cheap, targeted, and aimed at
the documented failure class rather than at everything.

### 5.2 Failure-summary triage as a cognition act
`failure_counter.dump_summary()` already writes per-site counts. Add a
`review_failures_internal` step to the existing health monitor: any site whose
count *grew* since the last review, with `count ≥ 20`, becomes a WM entry
(`event_type="internal_fault"`) — i.e., Orrin *notices his own muffled errors*
instead of a human reading JSON. The dashboard already surfaces the live console;
this closes the loop on "when some part of him breaks, it says so loudly enough
to be heard — by himself."

### 5.3 Map-territory audit pass
A maintenance function (monthly cadence, or invoked by `self_review`) that
checks the specific drift classes Problem 9 catalogued, mechanically:
- every cognition function registered in `select_function.py` resolves to an
  importable callable (catches dead-twin drift);
- every `paths.py` constant either exists on disk or is created by some writer
  (catches "reflection routine reads a structure nothing fills");
- doc-comment lifespan/cadence numbers cross-checked against the constants
  beside them where they're machine-readable.
Findings go to WM + `RUN_ISSUES`-style log, not silent repair — the record of
the drift is itself part of the faithful record.

**Observable sign:** the next Problem-4-class bug (type mismatch behind a
catch-all) survives less than one maintenance cycle before Orrin himself reports
it.

-----

## Sequencing and Dependencies

```
Phase 0 (days)        — no dependencies; everything else assumes it
Phase 1 (1-2 wks)     — independent of 2-4; do early, longest to show signal
Phase 2 (1 wk)        — 2.2 feeds Phase 4.3; needs 0.2 first
Phase 3 (2 wks)       — 3.1's prediction_outcome weighting is better after Phase 1
Phase 4 (1 wk)        — 4.3 consumes Phase 2.2's ledger
Phase 5 (1 wk + ∞)    — last, because its audits should cover the new wiring too
```

A staging run of several hundred cycles after Phases 0-1 and again after 2-4,
read through all four windows (dashboard, logs, files, source) — the goal
document's own lesson is that no single window would have caught more than a
fraction of these.

-----

## Extra Faults Noticed During Verification

These were found while checking the documented problems and are **not** in the
goals document. Listed with evidence; the fixable ones are folded into Phase 0.

**F1 — `record_failure` shadowing in `mark_goal_failed`**
(`cognition/planning/goals.py:825-829`.) Local import of the no-arg
`outcome_metrics.record_failure` shadows the two-arg failure-counter version for
the entire function scope; the `except` handler then calls the no-arg version
with two args. Any exception from the metrics call → `TypeError` from inside the
error handler → the failure's long-memory write and emotional penalty are
skipped. A failure-recording path that can itself silently fail is the Problem-4
lesson repeated. → Phase 0.2.

**F2 — ~~Stray `affect_stability` key injected into core signals~~ (RETRACTED
on re-verification)**
An earlier draft claimed `_apply_strategy` writes `side_effects` keys straight
into the real core. It writes into a **working copy**; the diff is routed
through the AffectArbiter, which applies `affect_stability` as a top-level
scalar, never into core (`regulation.py:353-365`, `arbiter.py:61,286-289`). The
live data file confirms no stray key, so the contamination scenario (dominant-
emotion selection in `opinions.py:176-179` picking up `affect_stability`) is not
occurring. Kept here as a record of the retraction; → Phase 0.3 is now a
regression test only.

**F3 — The strongest anti-rut defenses default off**
`ORRIN_HARD_DISENGAGE` gates both the metacog hard-disengage backstop
(`metacog.py:30-32,283`) and the sustained-prediction-failure escalator
(`prediction.py:444`). Normal runs get neither. → Phase 0.4.

**F4 — Strict mode is blind to the very crash class that motivated it**
`ValueError` (tuple-unpack mismatch — the Problem-4 crash type) is not in
`_PROGRAMMER_ERRORS` (`utils/failure_counter.py:50-56`), so `ORRIN_STRICT=1`
re-raises nothing for it. → Phase 0.5.

**F5 — No epilogue on ordinary shutdown**
Final thoughts and autobiography chapter-closing run only at the mortality
deadline (`mortality.py:232`); SIGTERM/KeyboardInterrupt paths
(`ORRIN_loop.py:3354-3357`) write nothing. Every routine restart is a small
amnesia by construction. → Phase 2.1.

**F6 — Three near-identical contradiction functions blur the map**
`repair.detect_contradiction` (LLM, long-memory scan),
`symbolic_cognition.detect_contradictions` (symbolic, broken — Problem 4), and
`selfhood/fragmentation.detect_contradictions` (self-model) are all registered
or referenced in the selector (`select_function.py:324,385`;
`ORRIN_loop.py:2438-2545` lists both spellings). Misleading for any reader —
including Orrin's own self-file-reading — and it makes the broken one easy to
mistake for a working twin. **A live instance of the drift:** the plural
`detect_contradictions` sits in `_EXECUTION_FNS` (`select_function.py:385`) and
the ORRIN_loop list at line 2545, but only the singular `detect_contradiction`
(repair's) is registered into `COGNITIVE_FUNCTIONS` (`ORRIN_loop.py:802-811`);
nothing registers the plural in `cognition_registry.py`. Phase 5.3's audit
would flag this — fix it during the rename instead of waiting. Rename to
distinct, honest names (`detect_memory_contradictions` /
`detect_rule_contradictions` / `detect_self_model_conflicts`) during Phase 0.1.

**F7 — Opinion evidence can only ever rise from experience**
`_update_evidence` increments alpha only; nothing in the WM path ever increments
beta. Even setting aside mention-as-evidence, the update rule is structurally
one-directional — confidence is monotonic up between LLM reflections. Subsumed
by Phase 3.1 (the ledger is bidirectional by construction).

**F8 — Autobiography comment promises a hard ceiling the code doesn't implement**
`autobiography.py:294-296`: "if more than 36 h have passed with enough pressure,
fire regardless" — no such branch exists; the min-interval check is the only
gate before the pressure gate. Harmless today (the sampled interval is capped at
36 h) but it is exactly a Problem-9 map/territory drift: a comment describing
behavior that isn't there. Fix the comment or implement the ceiling.

**F9 — Uncaught exceptions are never written to the log**
The brain runs as a daemon thread (`main.py:443-455`); `core/runtime_log.py`
installs no `sys.excepthook` or `threading.excepthook`, so a fatal exception in
that thread prints to stderr via Python's default hook and the thread dies while
`orrin_runtime.log` goes silent. Confirmed empirically: the 2026-06-11 run ended
at `16:42:28` with no error, no crash report, and no OOM event recorded anywhere
on disk — the traceback existed only on a terminal (the run bypassed
`run_orrin.sh`, whose `tee` to `brain/data/run_log.txt` is the sole capture path,
and that file was empty). This is Problem 4's lesson at the process scale: a loud
failure rendered invisible. → Phase 0.6.

**F10 — `update_self_model` re-parses a non-JSON LLM-down echo every cycle**
`cognition/selfhood/self_model_conflicts.py:148-158`. With the LLM tool
unavailable (the default), `gated_generate` returns a truthy analogy/working-
memory echo that passes the `if not response` guard but fails `extract_json`
every time. No `llm_available()` short-circuit — neither function in this file
(`update_self_model`, `resolve_conflicts`) has one; the guard lives in
`utils/llm_gate.py` and is used in e.g. `opinions.py`. In the 2026-06-11 run
this spun every ~13 s for 5+ hours,
flooding the log with `salvage failed … caller=self_model_conflicts.py:158` and
burying any signal near the crash. → Phase 0.7.

-----

## What This Plan Deliberately Does Not Do

- **No new faculties.** Every phase wires existing parts: predictions to
  behavior logs, failures to memory UUIDs, volition to the commitment call,
  provenance to opinion math. This is the goal document's own diagnosis honored:
  "the work ahead is mostly connecting what is already built."
- **No catch-all hardening.** Problem 4's lesson is that indiscriminate safety
  nets manufacture silence. Where this plan adds error handling, it is *named*,
  *counted*, and *surfaced* (5.1, 5.2) — never broadened.
- **No LLM in any load-bearing judgment.** The evidence standard (3.1), the
  endorsement gate (4.2), and the second checker (1.2) are all symbolic-first
  with LLM as optional narration — consistent with the tool-only default and
  with the design's warning about judges that can be fooled by whatever sounds
  convincing.

-----

## COMPLETION RECORD — 2026-06-11 (plan closed; all phases verified in code)

Every phase item and extra fault was re-verified against the working tree on
2026-06-11. Note: the "Where Things Actually Stand" scoreboard above predates
the implementation pass — rows marked OPEN/STILL BROKEN there are now fixed;
this record supersedes it.

- **Phase 0 — all done.** 0.0: `faulthandler` + `sys.excepthook` +
  `threading.excepthook` installed in `main.py` (lines 30-66);
  `run_orrin.sh` exit-code capture fixed (`|| EXIT_CODE=$?`, line 47).
  0.1: `symbolic_cognition.py` scores rules into `(rule, score)` pairs before
  `resolve_conflict`; the three contradiction checkers carry honest names
  (F6 renames: `detect_memory_contradictions` is the registered/selectable
  one; `detect_rule_contradictions`; `detect_self_model_conflicts`).
  0.2: aliased `record_outcome_failure` import in `mark_goal_failed`.
  0.3: regression coverage in `test_master_plan_phase0.py` / affect-invariant
  tests. 0.4: `ORRIN_HARD_DISENGAGE` defaults ON in both gates (opt-out).
  0.5: `_UNPACK_PATTERNS` ValueError heuristic + `ContractViolation` (always
  re-raised under strict). 0.6: see 0.0. 0.7: `self_model_conflicts.py`
  gates last-resort LLM calls behind `llm_available()`.
- **Phase 1 — done.** Behavioral receipts table + `_receipt_verdict`
  (`prediction.py:47-130`); two-channel felt/behaved verdicts; introspection
  trust ledger in `calibration.py` (`update_introspection_trust` /
  `get_introspection_trust`, persisted to `introspection_trust.json`) wired
  into prediction confidence (`prediction.py:290`) and exported by the
  backend (`backend/server/app.py:529`); `introspection_miss` WM events on
  sharp felt/behaved divergence (`_fire_introspection_miss`).
- **Phase 2 — done.** 2.1: `session_epilogue` (budgeted ≤10 s, crash-proof)
  called after loop exit (`ORRIN_loop.py:3392-3396`). 2.2:
  `cognition/reflection/review_failures.py` clusters goal failures into
  `failure_pattern` memories; feeds narrative pressure and the
  `failure_pattern_discount` planning prior. 2.3: B-series benchmark
  "Retrieval under restart" (`benchmarks/__init__.py:106-113`).
- **Phase 3 — done.** Provenance-typed evidence ledger with fixed weights
  (mention = 0.0 confidence, salience only); `root_memory_ids`,
  `linked_opinion_ids` + `needs_review` propagation, `stake` with
  `opinion_reversal` costs; topics routed through concept extraction; legacy
  migration drops junk topics and re-grades the rest (no lazy blessing).
- **Phase 4 — done.** `compute_commitment_strength` (drive/value/endorsement
  formula); `endorse_intention` gate called inside `form_commitment`
  (disown → no commitment; ambivalent → 0.5 strength, held lightly);
  commitment strength is a goal-competition input
  (`goal_competition.py:176-199`); failure penalties strength-weighted with
  `related_memory_ids` back to the commitment (`goals.py:848-883`); a 6 h
  identical-intention re-commitment gate ended the 91-commitment respawn
  loop (added during the 2026-06-11 data-file audit).
- **Phase 5 — done.** 5.1: `ContractViolation` validated at the
  `resolve_conflict` seam (`meta_rules.py:167`). 5.2: health monitor turns
  growing failure-counter sites into `internal_fault` WM entries
  (`health_monitor.py:183-213`). 5.3: `map_territory_audit.py` runs all
  three drift checks; its 10 path-drift findings were resolved and its
  writer detection sharpened (alias resolution, same-path grouping) in the
  2026-06-11 data-file audit pass — it currently reports zero findings.
- **Extra faults:** F1 → 0.2 ✓; F2 retracted; F3 → 0.4 ✓; F4 → 0.5 ✓;
  F5 → 2.1 ✓; F6 renamed + registered ✓; F7 subsumed by 3.1 ✓; F8 comment
  now describes the real gate (no phantom 36 h branch promised) ✓;
  F9 → 0.6 ✓; F10 → 0.7 ✓.
- **Tests:** `test_master_plan_phase0/1/2.py` + phase-4 tests in place; full
  suite 656 passed / 1 skipped (the 2 `embedder_test` failures are a
  pre-existing environment issue unrelated to this plan).

**Still pending (operational, not code):** the staging runs this plan calls
for — several hundred cycles after Phases 0-1 and again after 2-4, read
through all four windows (dashboard, logs, files, source). Launch via
`./run_orrin.sh` so the wrapper net is armed. The observable signs in
`ORRIN GOAL AND PROBLEMS.md` §"What Being Done Would Look Like" are the
checklist for that run.
