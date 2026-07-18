# Run 9 deep analysis — 2026-07-15 (no-run diagnosis pass)

*Purpose: replace diagnostic staging lives with static analysis. Every remaining
red in the Run 8 verdict is traced to a root cause here, from code + the Run 8
capture + the still-live daemon WAL (`data/goals/wal.log`, which survived the
capture and holds the full step-level record the capture's empty `goals_daemon/`
folder lost). No code was changed in this pass — findings only.*

**Headline: the "contribution layer" is much healthier than Run 8 scored it.
The failures were manufactured by a daemon race; the reuse was real. The two
biggest remaining problems are a concurrency bug in `goals/runner.py` +
`goals/goals_daemon.py`, and a measurement-design mismatch on `genuine_contact`
that no unattended staging run can ever fix.**

---

## Finding 1 — the research-goal failures are a runner race, not real failures

### The evidence (quantum goal `g_432cda2780`, WAL records 118–158)

Every step of this "FAILED" goal **succeeded**. On disk right now:
8 fetched Wikipedia docs (`doc_01..08.txt`), a 12.4 KB `research_memo.md`, and a
search artifact with 8 valid URLs and 10 results. The WAL shows what happened
to it anyway:

```
17:36:31  goal NEW → 3 steps (search → fetch → synthesize)
17:36:32  search DONE (real URLs)          ← then re-ticked DONE 3 more times
17:36:38.38  fetch DONE att=0/3            ← the real fetch: 8 docs written
17:36:38.47  fetch DONE→FAILED att=1/3 "no URLs to fetch"   ← re-tick #1
17:36:38.55  fetch att=2/3 "no URLs"       ← re-tick #2 … attempts climb to 9/3
17:36:38.65  goal FAILED ↔ RUNNING flapping (GoalFailed emitted 8+ times)
17:36:38.67  synthesize runs ANYWAY (zombie step on a FAILED goal):
             cites prior memo → mark_reused fires → memo written → step DONE
17:36:38.69  final goal state: FAILED, last_error=None (reason clobbered)
```

The history goal (`intrinsic-…15:46:13`) shows the same race with a *different
terminal verdict*: RUNNING×11 → FAILED×4 ("no URLs to fetch") → **DONE**. The
math goal (08:04) ended FAILED. Same code, three verdicts — **the terminal
state of a raced goal is decided by write ordering, not by what happened.**

### The four interacting defects

1. **No in-flight guard** (`goals_daemon.py` `_schedule_ready_steps` →
   `_enqueue_step`): the scheduler re-collects READY steps from the store each
   tick. A step being worked (fetch took 5.7 s) is still READY in the store, so
   it is enqueued again — with **3 workers** (`workers: int = 3`), the same
   step runs concurrently.
2. **Stale-copy writebacks** (`runner.py`): workers receive a Step *object* and
   upsert their private copy back. Lost updates everywhere: `DONE att=2/3`
   overwriting `FAILED att=3/3`, attempts reaching **9/3** (each racer
   increments its own stale count past max).
3. **`_load_latest_json(art_dir, startswith="")`** (`research.py`): steps load
   "the newest JSON in the dir" instead of their own step's artifact. After the
   first successful fetch writes `*_docs.json`, any re-tick of *fetch* loads
   the docs manifest (no `urls` key) → `ValueError: no URLs to fetch` — **a
   re-tick of an already-successful step is converted into a failure.** The
   filenames already carry step-id prefixes (`{step.id}_search.json`); the
   loader just doesn't use them.
4. **Zombie steps + reason clobbering** (`runner.py` finalization): synthesize
   ran and recorded effects *after* the goal was FAILED, and
   `last_error=last_step.last_error` (runner.py:482) takes the *last* step's
   error (synthesize's `None`), erasing the real reason.

### What this manufactured downstream

- **S4 is scored on noise.** All three traceable "failures" this life were this
  race; the work of all three exists on disk. The one *real* upstream failure
  mode observed is transient (math's search legitimately returned 0 URLs once
  — 6 s after goal creation, likely a network blip; there is no retry
  backoff, so a single empty search kills the goal within seconds).
- **The reuse↔failure time-lock is fully explained.** The verdict §4b noted
  both reuse events landing ≤ 250 ms before failures. Mechanism: the *zombie
  synthesize step* of a goal the race had already failed cites a prior memo
  (`mark_reused`, sig 1.0), writes a real memo, finishes DONE — while the
  GoalFailed event from the racing fetch copies is being drained and logged.
  Reuse and failure are the same runner tick of the same goal.
- **Orrin is emotionally punished for succeeding.** `mark_goal_failed` inflicts
  a genuine penalty (impasse_signal + reward_negative, by design). The race
  routes that penalty to goals whose work succeeded — negative affect as a
  concurrency artifact. (The Run 8 error log's "emotional response triggered"
  is this reaction line — `sense.py:251` — not a failure cause.)
- **v2 GoalFailed spam** (8+ emissions per goal) is absorbed by the drain's
  per-gid dedupe and `mark_goal_failed`'s idempotency — two prior fixes
  quietly containing this bug's blast radius. `goals_failed` = 7 vs 3 logged
  reconciles through other `mark_goal_failed` callers (deadline criteria etc.),
  not through the spam.

### Fix shape (Run 9 build — small, surgical)

- **R9-F1** — in-flight set in the daemon: don't enqueue a step whose id is
  queued or running; clear on terminal upsert. (One set + two touch points.)
- **R9-F2** — workers re-read the step fresh from the store at tick start and
  skip if not READY (kills both stale-copy writebacks and zombie steps).
- **R9-F3** — `_load_latest_json(art_dir, startswith=f"{step.id}_…")` or match
  the expected suffix (`_search`, `_docs`) — the data is already namespaced.
- **R9-F4** — finalization takes `last_error` from the *failed* step, and
  attempts guard: never increment past `max_attempts`.

Each is independently testable without a life: a `workers=3` runner test with a
slow fake handler reproduces the WAL trace deterministically.

---

## Finding 2 — `genuine_contact` cannot score in an unattended life (by construction)

Two person-dependent gates are stacked:

1. **Generation** (`intrinsic_generators.py::_contact_goals`): returns `[]`
   unless `user_present_recent` (set only by real user input recency,
   `action_gate.py:83`) or `latest_user_input`. Unattended run → zero contact
   goals *generated*. This matches the Run 8 scoreboard exactly: zero events at
   any stage, and the only aspiration with no `recent_hashes`.
2. **Credit** (`speech_evaluator.py` F3c): contribution requires the person to
   *reply* and the reply-scored quality ≥ 0.5 (rate-capped 1/h). Unattended →
   unreachable even if goals existed.

Both gates are *correct* individually (F3c's engagement requirement is what
keeps contact credit ungameable). The problem is the **measurement design**:
S6's "contact > 0" is scored against lives in which contact is impossible.
Three options for Ric (decision, not code):

- **(a) Scripted-interaction arm:** staging runs get a small scheduled stimulus
  (2–3 messages over the life). Cheapest honest fix; keeps F3c untouched.
- **(b) Headless outbox channel:** allow contact goals keyed to *deferred*
  contact — compose a message for Ric to read after the run; credit only when
  he actually replies (even post-life). Keeps the ungameable property (the
  reply is still the credit event) while letting generation work alone.
- **(c) Score S6-contact only on attended lives** and say so in the gate.

Recommendation: (b) + (c). (b) is the behavior a companion should have anyway
(leave a note when the person is away); (c) makes the gate honest meanwhile.

---

## Finding 3 — `_find_prior_memo` matches on title boilerplate → cross-topic reuse

`_topic_tokens` strips a stoplist but not the goal-title scaffold: every
research goal is titled "Understand X **more deeply**", and both "more" and
"deeply" are ≥ 4 chars and absent from `_TOPIC_STOP`. The ≥ 2-shared-token
threshold is therefore satisfied by *any* two goals' titles. Proof in the
capture: the **quantum** goal's synthesis cites the **history** memo
(`84f366…` — reuse row 2). The reuse arc is real machinery, but its topical
relevance test is currently vacuous.

Fix shape: **R9-F5** — add scaffold words (`more`, `deeply`, `into`, `about`…)
to `_TOPIC_STOP`, and require the overlap to come from the goal's *subject*
tokens. One-line change + a characterization test with two boilerplate titles.

---

## Finding 4 — ledger attribution: the anti-pump held, but the headline counts overcount

- **21 `file_write` rows = 15 distinct artifacts.** Six rows are exact re-writes
  of segment-1 content, recorded 15:36–15:51 — the first minutes of segment 2.
  This is a **crash-recovery re-production sweep**: post-relaunch state lost
  the "already produced" markers and re-did the work. All six were caught by
  Run 7's content-keyed dedupe (`dedupe=true, sig=0.0`) — **zero credit paid**,
  and reuse credit still resolved to the true first owner. The anti-pump
  machinery holding across a crash boundary is a stronger validation of the
  Run 7 fix than anything in the Run 7 verdict itself.
- Consequence: the Run 8 "21 concrete artifacts" headline should read
  **15 novel + 6 dedupe'd recovery re-writes**, and any future
  cross-run artifact comparison should count distinct hashes, not rows.
- Residual telemetry gaps: `mark_reused` hard-codes `cycle=0` and records no
  path (**R9-F6**: stamp the real cycle + owning path — the referents exist,
  the rows just don't carry them).

---

## Finding 5 — F1 does not need an ablation life

- The refractory (`brain/cognition/planning/commitment_value.py`) is a pure
  state update on `note_driver_selected`, env-gated
  (`ORRIN_STALE_REFRACTORY`), with `stale_cycles` a leaky integrator
  (observed values are fractional; credit zeroes it; grace 30; saturation 120;
  trip 250). With F2's rotation the longest Run 8 hold was 75 cycles → max
  stale 8.8 — a **28× margin**. F1's code path is unreachable in any life
  where F2 works.
- **R9-F7** — a forced-fire harness test replaces the ablation arm: drive
  `note_driver_selected` with a single uncredited driver for 280+ calls;
  assert `refractory_events` appends, `recommit_block_pulls` blocks re-commit
  for the configured pulls, and a credited effect resets cleanly. Then rewrite
  gate G2 to score the harness, not a life. F1 stays as a zero-cost backstop.
- This deletes one full staging life from the Run 9 plan.

---

## Finding 6 — exemplars: unlocked and verified, but the location is the design flaw

- Live check this pass: `paths.QUALITY_EXEMPLARS_DIR` resolves and is
  **writable now** (post-capture `uchg`/mode cleanup held). Next life is the
  first in which promotion *can* fire — watch for the boot probe's absence.
- Root design flaw: the runtime-writable exemplars dir lives inside
  **`tests/fixtures/quality_golden/`** — runtime state in the source tree.
  That is what exposed it to the backup/sync tool's lock re-application three
  runs straight, and it strains the two-state-trees rule. **R9-F8 (proposal):**
  move the *promoted* exemplars under a data tree via `brain/paths.py` with the
  committed-seed pattern; the human-ratified golden fixtures can stay in
  `tests/fixtures` read-only. Needs Ric's sign-off (quality-standard design
  says Orrin can't edit the golden set — relocation must preserve that split).

---

## Finding 7 — goals complete, but competence does not compound (no difficulty ladder)

The question behind all the gates: is Orrin learning to do *harder* goals?
**No — and the reasons are structural, not behavioral.**

### 7a. The completed goals are flat

Run 8's completions: 13 titles, one shape ("Understand X more deeply"), one
pipeline (search → fetch → stitch memo), median **112.7 s** to complete. Memo
#16 is not deeper than memo #1 — the offline fallback stitches same-sized
excerpts every time (`_offline_fallback_memo`, fixed 1,200-char snippets).
Nothing in the system *measures* goal difficulty, so nothing can escalate it.
These are reps at fixed weight.

### 7b. Both mechanisms designed to create progression have zero live runtime

- **The quality ratchet** (quality_standard golden set — "good" is defined by
  his own demonstrated-good work, so the bar rises as work improves):
  exemplar promotion has **never fired in any life** — three runs of EACCES,
  unblocked only 2026-07-15 (Finding 6). The ratchet exists; it has 0 hours.
- **The compounding arc** (reuse — work N+1 starts where N ended): 2 events
  all life, one of them cross-topic via the boilerplate match (Finding 3).
  Compounding is barely alive and its relevance test is vacuous.

No ratchet + no compounding = no ladder, regardless of completion counts.

### 7c. The outcome-learning signal was poisoned

Learning "harder goals of this kind pay off" requires true outcome labels.
The runner race (Finding 1) marked successful research FAILED and inflicted
real negative affect for it — so the reward EMAs, the Pearce–Hall adaptive
rate, and `value_ema` were trained on partially **inverted** labels. Any
gradient toward harder work was noise-swamped. (Corollary: treat all
outcome-conditioned learned state from Runs ≤ 8 as suspect where research
goals are involved.)

### 7d. What Orrin *did* learn — the other axis

Selection-level learning is real and visible: `look_outward` demoted
4,899 → 755 picks across runs, `research_topic` promoted (0.65 avg reward),
credit un-pumpable, commitment un-monopolized. That is **regulatory**
learning — a metabolism that no longer eats itself — and six runs of it was
the right order. It is "learned to stay healthy," not "learned to do harder
things." The S1–S10 gates measure exactly and only this axis.

### 7e. The ladder already exists in pieces — they are just not connected

| Existing piece | What it would do in a ladder |
|---|---|
| `definition_of_done` criteria on v2 goals | Get stricter on a success streak (difficulty escalation) |
| Quality golden set (now writable) | Ratchet the bar for what counts as done-well |
| Reuse chains (post Finding-3 fix) | Require new work to *build on* prior artifacts, not restart |
| Frontier/aspiration goal generation | Consume "what have I already mastered" instead of sampling flat |

The growth loop is one wiring job: *recent verified-success streak → harder
`definition_of_done` + build-on-prior required → quality bar ratchets from the
resulting exemplars*. Nothing exotic. **Sequencing:** it must come *after*
Run 9′ — a curriculum built on race-noised verdicts would learn garbage. Order:
honest verdicts (R9-F1..F4) → first life with exemplar promotion firing →
ladder design (target: the Run 11 conversation).

This is also the honest framing of the "when is goals not experimental"
question: the current gate proves **stability**; escalating competence is the
axis *after* it, and it is the one that matters.

## Connections map (what's coupled that the gates treat as independent)

| Connection | Consequence |
|---|---|
| S4 failures ↔ S7 reuse are the **same runner tick** (zombie synthesize in a raced goal) | Fixing the race (F1) moves both signals at once; do not tune either gate before it lands |
| Race → `mark_goal_failed` → **negative affect for successful work** | Affect telemetry from Run 8 is partly concurrency noise; interpret any "setback" learning with suspicion |
| Race-noised verdicts ↔ outcome learning (reward EMAs, Pearce–Hall, value_ema) | Outcome-conditioned learned state from Runs ≤ 8 is suspect where research goals are involved; no curriculum work until verdicts are honest (Finding 7c) |
| Quality ratchet (0 hours live) ↔ reuse chains ↔ `definition_of_done` ↔ frontier generation | The four pieces of a difficulty ladder, currently unwired (Finding 7e) — the post-gate growth axis |
| Crash → segment-2 **re-production sweep** → dedupe'd rows | Recovery re-work is invisible in success metrics; only the ledger shows it. Worth a "resumed, not new" marker post-restart |
| `_find_prior_memo` boilerplate match ↔ reuse legitimacy | Reuse count will inflate once research volume grows; fix the stoplist *before* raising the S7 target to 8 |
| Three cycle counters (pulse stdout, heartbeat, production_loop) disagree under failure | The watchdog cycle-stall tripwire (owed from Run 8 §0) must key on production_loop stamps |
| v1 intrinsic ids flow into daemon goals; daemon `g_` ids do not flow back into `comp_goals` | The 17-vs-16-vs-14 completion-count spread; racing DONE/FAILED verdicts also desync v1's archive from v2's truth |
| Contact generation gate ↔ presence subsystem (Companion & Presence, built 07-10) | The generator already keys on presence signals; option (b) above is a small extension of existing wiring, not new architecture |

## What this does to the two-run plan

The plan holds, and the odds improve: the "contribution layer" needed
*diagnosis*, and the diagnosis is now done without a life. Run 9′ becomes a
**verification** life for: R9-F1..F5 (race + loader + stoplist), R9-F6
telemetry, R9-F7 harness-instead-of-ablation, R9-F8 if approved, plus the two
owed items (invoke.py regression test, watchdog tripwire). Run 10′ confirms.
The only open *product decision* is Finding 2 (contact channel) — everything
else is mechanical.

**And the plan's scope is now explicit:** passing this gate twice makes the
goals system *stable*, not *growing*. Finding 7 is the roadmap for the axis
after — the difficulty ladder — and its precondition is exactly this gate
(honest verdicts + a live quality ratchet). Stability first, then escalation.

*Written 2026-07-15. Sources: `demo_runs/2026-07-15-run/` capture,
`data/goals/wal.log` + `state.jsonl` (live daemon state), code as of `e70ac98`.*
