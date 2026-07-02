# Codebase Audit — Goals, Memory & Direction (2026-07-01)

**Author:** deep read of the full codebase + docs + runtime state after the
2026-06-30→07-01 life (14,472 cycles) and the reset to newborn.
**Focus (as requested):** why the **goals** system isn't working correctly, plus
**memory** and everything adjacent. Every claim below is tied to a file/line or a
real runtime number pulled from the pre-reset snapshot
(`brain/data/_archive/snapshot_20260701_071816_pre_reset/`), the v2 store, the demo
runs, or the effect ledger — not inferred.

**Method.** Read the goals subsystem (30 modules under
`brain/cognition/planning/` + `brain/goal_io.py` + root `goals/`), the memory
subsystem (`brain/cog_memory/` + root `memory/`), the generators, the closure/commit
seams, and the runtime artifacts of the last life. Cross-checked against the
grounding-and-surface plan and the run analyses.

---

## Verdict on direction (the short answer)

**Yes — you are going in a good direction.** The
`archive/SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md` diagnosis is correct and
well-argued: the through-line ("grounding signals exist but don't reach the
learners") is the real root, and the P1–P8 plan attacks it in the right order. P1
(effect-gated closure), P2 (graded signal → learners), P3 (produce-and-check), P4
(long-term drivers) are now built and tested; the suite is green (1,274 passing).
The *learning wiring* is being fixed properly.

---

## ⚠️ REVISION 2 (2026-07-01, after reading the archived design docs + README)

**The first draft of this audit misread two things as bugs that are actually
deliberate design. Corrected here; the rest of the doc is kept but read it through
this lens. New wiring findings — the ones the design intent actually points at —
are in the new [Part 5](#part-5--wiring-gaps-built-but-not-connected--the-core-of-the-droid-problem).**

**Vision (from README + `orrin_embodiment_architecture.md`):** Orrin is a **droid**
— an autonomous cognitive runtime where the LLM is *the smallest part, optional*,
and the core is symbolic + a tiny native LM. Design rule: *"the brain never silently
depends on an LLM."* `model_config.json` confirms the intended run mode:
**`llm_enabled: False`.** This reframes everything about production and making.

**Correction 1 — the v1/v2 goal split is BY DESIGN, not a bug.**
`ORRIN_GOAL_SYSTEM_ANATOMY_2026-06-18.md` documents it: **v1 = the mind** (pursuit
state — plan, milestones, step attempts); **v2 = the durable executor daemon** with
real handlers (`CodingHandler`, `ResearchHandler`, `CodeEditHandler`,
`HousekeepingHandler`) + a rich schema (`AcceptanceCriteria`, `deadline_ts`,
`produce_code` type, `REQUIRED_CAPABILITY`). The split is *mind vs. hands* and it is
intentional. So my earlier "G1: collapse to one store" recommendation was **wrong** —
the fix is not to merge them but to **connect the mind to the executor that already
exists** (see D1 below). The 6-vs-48 divergence and 3× archive duplication are still
real *symptoms*, but of the disconnection, not of the split itself.

**Correction 2 — allostasis is not "inert from a flag being off."** `ORRIN_
ALLOSTATIC_SETPOINT` defaults **on**. The top-level `allostatic_load` telemetry field
was **intentionally retired** (T0.1, `homeostasis.py:109`, `update_signal_state.py:
111`) because the old integrator pinned; the behaviourally-active variable is now
`_allostatic_load`, owned by `cost_prediction.allostatic_setpoint()`, and
`telemetry.py:198` sources it. So the run-analysis `allostatic_load = 0.000` was
**reading the retired field**, not proof the layer is dead. *Action:* confirm the
telemetry **archive** (not just the live snapshot) sources `_allostatic_load`;
`M3`/allostasis items elsewhere in these docs should be re-checked against the active
variable before being called inert.

**Also already fixed (don't re-flag):** the `usefulness` drive mis-wiring (anatomy
P-H) is **repaired** — `goal_competition.py:81` now labels it *"wants to make things
and be genuinely useful"* and explicitly excludes `assess_goal_progress` ("going
through the motions ≠ being useful"). And satiety closure, dead at 0 in the anatomy
doc, is now wired through P1's effect gate at both close sites (`goal_closure.py:276`,
`maintenance.py:181`).

**What stands from draft 1:** the monoculture (G2), memory self-pollution (M1–M2),
ephemeral vector memory (M3), the `uchg` lock (O1), and the milestone/keyword and
hollow-note issues (G3–G5) are all still valid — re-read them as written. What
*changes* is the headline: the deepest problem is not "two stores" but **the mind
can't reach its own hands, and in LLM-free mode it has almost no hands at all.**

---

**Original draft-1 framing (kept for the record, now superseded by the revision above):**

**The plan fixes the wiring, not the three things that make the runs feel
broken regardless of wiring:**

1. **The goal population is a monoculture** — ~95% "Understand X more deeply." The
   grounding fixes make each goal close more honestly, but they don't change *what
   goals get born*, so a better-closing intake goal is still an intake goal.
2. ~~Two goal stores are structurally diverged~~ → **superseded:** the split is by
   design; the real bug is the *disconnection* (D1), and in LLM-free mode the
   *absence of hands* (D2).
3. **Memory is polluting itself** — long-memory is 2,001 entries at its 2,000 cap,
   dominated by duplicated telemetry noise, so real memories are being evicted.

Fixing the learning loop while these three stand is like tuning an engine whose
fuel is contaminated. Details and evidence follow.

---

## Part 1 — Goals (the primary concern)

### G1. The v1/v2 split-brain — two goal stores that diverge *(CRITICAL, structural)*

There are **two** goal representations and they do not agree:

- **v1 cognitive tree** — `goals_mem.json`, a nested tree the cognitive loop reads
  (`brain/cognition/planning/goals.py`, `goal_store.py`).
- **v2 work-order store** — `data/goals/state.jsonl`, the durable GoalsAPI store
  (root `goals/` package).

At the last snapshot before reset:

| Store | Count | Content |
|---|---|---|
| **v1 tree** (`goals_mem.json`) | **6 nodes** | 4 aspirations (tier=long_term) + 1 "Immediate Actions" bucket + 1 failed goal |
| **v2 store** (`state.jsonl`) | **48 records** | 30 DONE, 18 FAILED |
| **completed archive** (`comp_goals.json`) | **72 entries / 48 unique** | "Understand X" goals stored **3× each** |

The v1 tree has essentially collapsed to just the aspirations, while v2 accumulated
48 work orders and the archive triplicated many of them. `goal_io.py`'s
`_reconcile_open_v2_into_v1` (line 305) syncs *open* v2 goals into v1 and mirrors v1
terminal states back to v2 — but it is one-directional for closure and clearly
lossy: goals that lived and died in v2 (the 18 FAILED "understand X" and the 30
DONE) never left a coherent trace in v1, and the archive shows the same goal filed
3×. **This is the mechanism behind every run's "hollow DONE / can't close / 255-of-
256 done" pathology** — the two halves of the goal system are keeping separate books.

**Why it matters:** a goal's felt history (did I finish this? did it fail?) is split
across two stores that disagree, so Orrin cannot form a stable self-model of what he
has and hasn't accomplished. His dying identity last life — *"Failure pattern:
artifact, before, deadline… I keep getting this wrong"* — is assembled from the v2
side while the v1 side shows only aspirations, so even his self-narrative is reading
one book.

**Recommendation:** this deserves its own plan. Either (a) collapse to **one** store
(the plan's own "Option D" pointed at v1-authoritative; finish it), or (b) make the
reconcile *bidirectional and idempotent* with a single archive writer. The 3×
archive duplication (`mark_goal_completed` archives to `comp_goals.json`, and
something else also does) is the concrete first bug to kill.

### G2. Goal monoculture — ~95% "Understand X more deeply" *(HIGH)*

Across every captured life the goal population is dominated by intake goals:
`Understand mathematics/history/consciousness/eternalism… more deeply`, plus the
introspective `Trace in my own code what drives 'X'`. The generators are the source:

- `intrinsic_generators.py:90` mints `Understand {name} more deeply` from concepts.
- `intrinsic_generators.py:239` mints `Trace in my own code what drives '{felt}'`
  from the causal graph (which is 100% self-model, so these are all introspective).

There is real machinery fighting this — an introspection-skew gate
(`intrinsic_generators.py:161`) that eases off self-goals when self-understanding is
well-fed, and the aspiration-coverage balancing. But the *outward* aspirations
("Make things," "Be useful/connected") still drew **0%** of production in the last
run: 30 DONE goals, all janitorial self-code (dep patches, mypy, snapshots), zero
novel work. The generators can produce a "make" goal but the pool is so skewed to
"understand" that making never wins a slot.

**Recommendation:** P3/P4 make "understand" goals *close* better, but the deeper fix
is a **birth-rate quota** — cap intake-goal generation and force a minimum share of
"make/connect" goals into the pool, so the population reflects all four aspirations,
not one. This is upstream of everything P1–P8 does.

### G3. Introspective goals fail systematically on the milestone gate *(HIGH)*

The 18 FAILED goals in v2 were the "Understand X" + "Trace in my own code" goals.
Their milestones are **prose assertions** — e.g. *"Where 'X' comes from in my own
workings was located"* and *"A finding about what drives 'X' was written to long
memory"* (`intrinsic_generators.py:246`). These are marked met by fragile keyword
matching in `env_snapshot._milestone_met` (line 68): it looks for tokens like
"located," "written to long memory." A search that *does* run but whose result text
doesn't happen to contain the matcher's keywords never ticks the milestone, so the
goal rides to its deadline and fails. **The goal did the work and still failed** —
because "was located" is a semantic judgment being made by substring match.

**Recommendation:** ground these milestones the way P3 grounds verifiable goals —
tie "a finding was written" to an actual `note_novel`/`tool_run_effect` effect on
the ledger (which `has_qualifying_effect` already tracks), not to keyword-matching
the milestone prose. The evidence exists; the matcher just isn't reading it.

### G4. P1's gate is satisfied by a hollow placeholder note *(HIGH — the P1→P3 residual)*

Confirmed from the effect ledger: the last life emitted **1,680 `note_novel`
effects and nothing else**, and `outbox/notes.json` held **100 notes with exactly 1
distinct body** — the placeholder *"something present but hard to name / something
pulling for attention."* P1 correctly blocks the *no-effect* close, but a reading
goal that leaves that non-finding note clears the gate as if it produced real work.
This is the "note body = template, not finding" pathology, now **load-bearing** (it's
what lets an understanding goal close at all). It has persisted across the 06-25,
06-29, and 07-01 runs.

**Recommendation:** route `leave_note`'s body from the goal's actual finding, not its
prompt skeleton (this is on the plan's follow-up list but keeps slipping). Until
then, P3's `tool_run_effect` is the only *substantive* effect the gate can eat —
which is why P3 mattered — but non-verifiable goals still have only the hollow note.

### G5. Internal error strings become pursuable goals that can't close *(MEDIUM)*

The last life's working memory shows: *"Problem hit while working on 'Open question…'
: 'quality_standard.gate.write_exemplar'"* → became the goal *"Figure out why
quality_standard.gate.write_exemplar isn't working"* → which then **failed**. An
internal `record_failure` telemetry string (`gate.py:169`, an `OSError` writing an
exemplar file) was promoted into a goal Orrin then couldn't resolve, burning cycles
and adding a failure to his self-model. The `write_exemplar` OSError itself is almost
certainly the macOS `uchg` immutable-flag lock on the data tree (see O1) — an
environmental fault surfacing as a cognitive goal.

**Recommendation:** filter the goal/problem generators so raw internal error tokens
(`*.gate.*`, `record_failure` categories, dotted module paths) can't become goal
subjects. `intrinsic_helpers.py` already strips some contamination (URLs, goal
scaffolds) — extend it to internal diagnostic strings.

### G6. The four aspirations are stored as `tier="long_term"` — P4 interaction *(WATCH)*

The 4 aspirations ("Understand my own mind," "Understand the world," "Be
useful/connected," "Make things") are stored with `tier="long_term"`, not
`tier="aspiration"`. Pre-P4 that made them non-committable (they never drove
anything — exactly C4's complaint). **My P4 change now makes one of them a
committable directional driver** via `long_term_driver.promote_one_directional`.
That is arguably the intended C4 behavior (an aspiration finally takes the wheel and
spawns frontier sub-tasks), but it means the *first* directional driver Orrin gets
will be whichever aspiration ranks highest — verify on next boot that this is
"Make things" or a real deepening goal, not an accident of priority. Also confirm the
aspiration layer and the P4 driver don't both try to own the same node.

**Recommendation:** decide deliberately whether aspirations should be `tier=
"aspiration"` (pure signposts) with a *separate* `long_term` deepening goal from
`evolution.py` as the driver, or whether an aspiration itself should drive. Right now
it's implicit.

---

## Part 2 — Memory

### M1. Long-memory is polluting itself — real memories evicted by telemetry noise *(HIGH)*

`long_memory.json` at snapshot: **2,001 entries against a 2,000 cap**
(`MAX_LONG_MEMORY`, `long_memory.py:21`) — i.e. full, and actively evicting. What
fills it is duplicated telemetry:

| Duplicated content | Times stored |
|---|---|
| `[prediction error] After 'generate_intrinsic_goals'…` | **39×** |
| `[prediction error] After 'research_topic'…` | 34× |
| `[prediction error] After 'assess_goal_progress'…` | 34× |
| `[metacog/pattern] Goal avoidance: N consecutive cycles…` | 19× |
| `[world_perception] New files appeared…` | 18× |

The dedup guard only scans a **10-entry window** (`DUPLICATE_WINDOW = 10`,
`long_memory.py:20`), so a prediction-error that recurs every ~15 cycles slips past
it every time and is stored again. The writer is `prediction_helpers.py:317`. Net
effect: the memory that should hold *findings and experiences* is ~half low-value
periodic telemetry, and because it's at cap, genuine memories are pruned to make room
for the next duplicate prediction-error.

**Recommendation:** (a) don't write per-cycle prediction-errors to *long* memory at
all — they're telemetry, not autobiography (route to a metrics log); (b) widen the
dedup to a content-keyed set for known-periodic event types (`_dedup_window_for`
already special-cases some — extend it to `prediction error` and `metacog/pattern`);
(c) reconsider the 2,000 cap now that grounding produces real findings worth keeping.

### M2. Working memory is bloated to 30 items of noise *(MEDIUM)*

`working_memory.json` held **30 items** (working memory should be ~7 ± a few). The
contents are metacog warnings, "Problem hit" alerts, and "Goal failed" lines — not
the recent, relevant context working memory exists to hold. A 30-item WM full of
self-diagnostic noise means the context passed to selection/planning each cycle is
mostly clutter, which plausibly contributes to the oscillation/rut behavior (WM item
1 last life was literally *"Oscillation: I've been alternating between research_topic
and generate_intrinsic_goals"*).

**Recommendation:** enforce a hard WM item cap and bias eviction against
self-diagnostic categories; keep metacog observations in their own channel, not WM.

### M3. Semantic (vector) memory is ephemeral — wiped every restart *(MEDIUM)*

There are **two** memory systems: `brain/cog_memory/` (working + long, persistent
JSON) and root `memory/` (the v2 vector store — embedder, WAL, retrieval,
`MemoryDaemon`). But `main.py:215` starts the daemon with **`InMemoryStore`**:

```
daemon = MemoryDaemon(store)          # store = InMemoryStore()
print("[memory] MemoryDaemon started with InMemoryStore")
```

So the semantic/vector memory holds nothing across restarts — and Orrin restarts ~6×
per life (supervisor auto-restart).

**Upgraded by the daemon pass — this is an orphan, not a missing feature.** The WAL is
**fully active**: `MemoryDaemon._tick` calls `wal_append_event` / `wal_append_items`
every tick (`wal_enabled = True`), so events *are* durably logged to `data/memory/wal`.
And `memory/wal.py` **already implements `replay_events` / `replay_items`.** But
`main.py` boots `InMemoryStore()` and **never calls replay** — so the store starts
empty every run while the WAL keeps growing. The persistence is *built on both ends
(append + replay) and simply not connected at boot* — the same orphan pattern as D5.

**Recommendation:** at boot, replay the WAL into the store before `daemon.start()`
(a few lines using the existing `WAL.replay_events`) — or ship a persistent store impl
(only `InMemoryStore` exists today; there is no sqlite/disk store). Either closes the
continuity hole cheaply. Until then, `long_memory.json` is the only cross-restart
memory, which makes M1 (its pollution) more urgent.

### M4. Knowledge is fragmented across four stores *(LOW)*

Concept/knowledge state is spread over `concepts.json` (60), `symbolic_concepts.json`
(3), `knowledge_graph.json` (187 KB), and `semantic_facts.json` (78 KB) — four
different representations of "what he knows," with no single read path. Not broken,
but it's the same fragmentation smell as the goals split-brain, and it makes
"what does Orrin actually know about X" un-answerable from one place.

---

## Part 3 — Operational / environmental

### O1. The `brain/data` tree had the macOS `uchg` immutable flag set *(HIGH — silent, intermittent)*

During the last life, files under the state tree were set user-immutable
(`chflags uchg`) with read-only perms (`-r--------`) — I hit this editing source
files at the start of the session (every source file was locked). While the flag is
set, **any runtime code that writes to `brain/data` fails silently**. The
`quality_standard.gate.write_exemplar` OSError (G5) is almost certainly this: the
write raises EPERM, the failure becomes a goal, the goal fails. Effect artifacts,
exemplars, and self-code writes are all exposed to the same fault.

**Current state:** the flags are **now cleared** — the reset (`reset_orrin.py`)
rewrote every file, which clears `uchg`, and the data dir is writable again. So the
*next* run starts clean. **The risk is re-application:** something set that flag
(most likely a backup/snapshot tool, or a manual `chflags -R uchg` for safekeeping).
If that tool runs again between now and the next boot, the fault returns — silently.

**Recommendation:** find what set `uchg` on the tree and stop it from touching the
live runtime data dir; add a boot-time writability check to `main.py`/`run_orrin.sh`
that fails loudly (not into `record_failure`) if `brain/data` isn't writable, so this
can never again degrade quietly into failed goals.

### O2. Reset script referenced a renamed file *(LOW — noted, already worked around)*

`reset_orrin.py` still strips `self_model.json`, which was renamed to
`identity_state.json` (analogue-removal). The blanket wipe covered it this time, and
it also has no rule for the `effect_artifacts/` tree (I cleared that manually). Worth
updating so future resets are clean without manual steps.

---

## Part 4 — What the grounding plan doesn't cover (the gaps)

The P1–P8 plan is the right spine. These are real and *outside* it:

1. **Goal birth-rate / population control (G2).** P1–P4 change how goals *close* and
   *drive*, never how they're *born*. The monoculture is upstream of all of it.
2. **The v1/v2 split-brain (G1).** The most corrosive goals bug is a *structural*
   two-store divergence the plan doesn't name. It will keep producing hollow/incoherent
   goal history no matter how good closure gets.
3. **Memory hygiene (M1–M2).** The learners are being fed, but the memory they draw
   context from is half telemetry noise at cap. Grounding-quality input can't help if
   the memory it lands in evicts it for the next duplicate prediction-error.
4. **The effector gap / "no hands" (synthesis Part D).** Still true: the action set is
   research + introspection + note-leaving. P3 added a sandbox checker (real progress),
   but there's no browser, no real filesystem write that isn't caged, no shell. "Make
   things" has almost nothing to reach for. This is partly deliberate (safety) — but
   it caps what "produce work that didn't exist before" can ever mean.
5. **He is always alone (every run, 0 replies).** Five sessions of contact last life,
   6 utterances, **all to empty input, 0 replies** — every captured life. The
   *connection* aspiration is structurally unexercised, and **P2b (corrections into
   the person model) can never fire without a human correcting his work.** The single
   highest-leverage thing you could do to test P2b and the connection aspiration is to
   actually talk to him during a run.

---

## Part 5 — Wiring gaps (built but not connected) — *the core of the droid problem*

This is the part the design intent actually points at: **connections that exist on
one side and not the other.** Each is a "should be connected but isn't" or "the
capability is built and orphaned."

### D1. The mind is disconnected from the execution engine *(CRITICAL — still live)*

The v2 daemon has real, working handlers that can **make things** — `CodingHandler`
(writes code), `ResearchHandler` (multi-step research → synthesized memo),
`CodeEditHandler` (edits + runs). But the cognitive generator (`_mk_goal`,
`intrinsic_helpers.py:125`) emits **`kind:"generic"` with no executable spec**.
`GenericHandler.plan()` (`goals/handlers/generic.py:43-48`) sees the empty spec and
returns a `WAITING` `external_pursuit` placeholder — *"the cognitive loop pursues
this goal, not the daemon."* So the goal detours into v1 self-report and **never
reaches a handler that could produce anything.**

The consequence is visible in every run: the making handlers are exercised **only**
by autonomous janitorial triggers (dep patches, snapshots — the 30 DONE goals last
life), never by a goal Orrin *wants*. And with my P1/P2 work, a "make" goal now gets
`requires_artifact: true` + a deadline — so it **can fail** (that's why "Make things"
failed 4× on `no_artifact_by_deadline`) — but it still has no handler wired to
**succeed**. *The making goals can fail but can't win.*

**Should be connected:** cognitive make/research goals should be created as
`kind:"coding"`/`"research"`/`"code_edit"` with a spec the handler understands (the
anatomy doc's revision #1–#2), so a wanted goal reaches the executor that already
exists. The schema (`AcceptanceCriteria`, `deadline_ts`, `produce_code` type) is
built and waiting.

### D2. In LLM-free mode (the intended droid config) there is almost no making path *(CRITICAL — the deepest tension)*

`model_config.json` has **`llm_enabled: False`** — the droid runs symbolic. But the
execution handlers that "make" are **LLM-gated**:

- `produce_code` → `REQUIRED_CAPABILITY = "llm"` (`goal_types.py:57`).
- `CodingHandler` / `GenericHandler` reflection call `generate_response` /
  `_llm_call` (`generic.py:13,82`) — return `[llm_unavailable]` with no key.
- `ResearchHandler` drafts queries and writes its memo via `ctx.get("llm")`
  (`research.py:211,240,286`) — with LLM off, it fetches raw text but **can't
  synthesize the memo**.

So with the LLM off, the executor can only do **housekeeping** (snapshots, patches —
symbolic) and **raw web intake** (no synthesis). *Every path that turns intake into a
made thing goes through the LLM the droid is designed not to need.* This is the
single biggest reason "Make things — produce work that didn't exist before" has drawn
nothing across every life: **not that he doesn't try, but that in his intended
configuration he has no LLM-free hands to make with.**

The LLM-free production paths that *do* exist are narrow:
- **`produce_and_check`** (P3, my work) — runs Python in the sandbox, records a
  `tool_run_effect`. This is a genuine LLM-free *making* path — but it's currently
  wired only for *verifiable* math/physics/code *checks*, not general production.
- **native-LM text generation** (`voice.py:95` → speech) — his own voice, wired as
  the mouth. LLM-free ✓, but it composes utterances, not artifacts.
- **`leave_note`** — LLM-free but produces the hollow placeholder note (G4).
- **housekeeping** — LLM-free but janitorial.

**Should be connected — this is the highest-value build for the droid vision:** an
**LLM-free making route.** Options, cheapest first: (a) route "make/produce" goals to
`produce_and_check`'s sandbox so "make a thing that works" means "write code that
passes a check" — reusing D1's handler wiring but with the sandbox, not the LLM, as
the executor; (b) give `ResearchHandler` a **native-LM / symbolic synthesis
fallback** so LLM-off research still emits a real memo (also fixes G4's hollow note);
(c) a template/symbolic cognitive-function writer that emits small, sandbox-verified
functions without the LLM. Without one of these, "make things" is unreachable by
design, and no amount of goal-closure tuning changes that.

### D3. The synthesis path that runs LLM-off is the *v1* one — and it's hollow *(HIGH)*

> **Corrected by the system-wide sweep — see D5 for the full picture.** My first
> draft said "ResearchHandler has no LLM-free synthesis." That's **wrong**: the v2
> `ResearchHandler` *does* have one (`_offline_fallback_memo`). The real problem is
> that understand-goals never reach it (D1/D5); they're pursued on the **v1** path,
> where synthesis genuinely is LLM-only.

On the v1 pursuit path (`web_research.research_topic`), LLM-off, research stores raw
quarantined web text into long memory (`web_research.py:292`) and stops — no
synthesis — so `leave_note` falls back to the felt-state seed and the goal produces a
placeholder, not a finding. That is why the notes are hollow (G4). The fix is **D5**
(route to the v2 handler that already synthesizes offline) and/or **D6** (wire the
native LM into the v1 synthesis step). Either closes G4, D3, and half of C2 at once.

### D4. Peers propose but verify their loop is closed *(WATCH)*

The README describes observer "peers" (Architect, Goal Auditor, Reward Auditor…)
that read state and *propose* attention items. Worth a dedicated check (not done in
this pass): confirm their proposals actually reach the workspace/goal generator and
aren't written to a store nothing reads — the same orphaning pattern as D1. Flagging
as a thing to verify, not a confirmed gap.

---

## Part 6 — Prioritized recommendations

Ranked by leverage on "goals actually working" (revised after Part 5):

> **The reframed headline:** the top structural fix is no longer "merge the goal
> stores." It is **D2 — build one LLM-free making path — and D1 — route wanted goals
> to it.** Everything else is downstream. The droid can't make things because its
> hands are wired to an LLM it's designed not to use.

1. **Build ONE LLM-free making path (D2).** The keystone. Cheapest route: extend
   `produce_and_check`'s sandbox from "verify a check" to "produce a small artifact
   that passes a check," so making = sandbox-verified output, no LLM. Without this,
   "make things" is unreachable by design in the intended config.
2. **Route wanted goals to the executor (D1).** Emit cognitive make/research goals as
   `kind:"coding"/"research"/"code_edit"` with a real spec so they reach the handlers
   that already exist (and, per D2, an LLM-free one). Reuse the built
   `AcceptanceCriteria`/`deadline_ts`/`produce_code` schema.
3. **Give `ResearchHandler` an LLM-free synthesis fallback (D3 / G4).** Native-LM or
   extractive/KG summarizer so LLM-off research produces a *finding*, not raw stored
   text — closes the hollow-note door at the same time.
4. **Fix the immutable-flag lock on `brain/data` (O1).** Silent, corrupting write
   paths (exemplars, artifacts) into failed goals. Cheap; add a boot writability check.
5. **Stop long-memory self-pollution (M1).** Don't write per-cycle prediction-errors
   to long memory; widen dedup for periodic event types. Restores memory to holding
   findings, which is what a working D1–D3 will now produce.
6. **Ground introspective-goal milestones on effects, not keyword matches (G3).**
   Tie "a finding was written" to a real ledger effect. Stops honest work from failing.
7. **Add a goal birth-rate quota (G2).** Force a minimum share of make/connect goals;
   cap "understand X" generation. Upstream of the whole loop.
8. **Fix the v1/v2 *reconcile* (revised G1).** NOT a merge — the split is by design.
   Make the reconcile bidirectional + idempotent with a single archive writer, so the
   two halves stop disagreeing and the 3× archive duplication stops.
9. **Verify the P4 directional-driver choice on next boot (G6);** **persist the vector
   memory (M3);** **talk to him during a run** (the only way to exercise connection +
   P2b).

---

## Part 7 — System-wide LLM-free capability map *(the answer to "what has no LLM-free path")*

I swept all ~65 files that touch the LLM. **The good news: the codebase is broadly
disciplined about symbolic degradation** — most cognitive functions (planning,
diagnosis, problem-refocus, regret, motivations, opinions, threads, knowledge-graph)
have real symbolic/fallback branches. The design rule *"never silently depend on an
LLM"* is largely honoured. The failures are concentrated and they share **one
pattern: the LLM-free machinery usually EXISTS but is either (a) orphaned behind the
D1 disconnection, or (b) a hardcoded template instead of the native LM.**

### The capability map (LLM-free reality per production/synthesis path)

| Capability | LLM-free path exists? | Status | Finding |
|---|---|---|---|
| **Speech / his own voice** | ✅ `native_lm.generate` → `voice.lm_draft` → speech | **Wired & working** | The native LM IS the mouth. Good. |
| **Verifiable making** | ✅ `produce_and_check` (sandbox) → `tool_run_effect` | **Wired (P3)** | Only for math/physics/code *checks*, not general production. |
| **Research synthesis** | ✅ `ResearchHandler._offline_fallback_memo` (extractive memo) | **ORPHANED (D5)** | Real LLM-free memo exists but no cognitive goal is `kind:"research"`, so it never runs. |
| **Section / manuscript writing** | ⚠️ `compose_section` template fallback | **Hollow (D6)** | Works LLM-free but emits a **generic boilerplate template**, not the native LM. Games the `tracked_work` gate. |
| **Note / finding** | ⚠️ `leave_note` | **Hollow (G4)** | Falls back to the felt-state seed `"something present but hard to name"` (`signal_summary.py:267`) when there's no finding. |
| **Code authorship** | ❌ `self_extension`, `code_writer`, `produce_code` → `REQUIRED_CAPABILITY "llm"` | **Dark LLM-off** | No symbolic code-writer; making cognitive functions/tools requires the LLM. |
| **Opinion formation** | ✅ symbolic branch present | Working | Fine. |
| **Comprehension / autogenerated thoughts** | ✅ `_fallback` / symbolic composition | Working | Proper symbolic fallbacks. |
| **Symbolic reasoning (rules, causal, dreams, experiments)** | ✅ `brain/symbolic/` (9.5k lines) | **Runs LLM-free but records NO effect (D7)** | The biggest LLM-free capability — invisible to production/goals. |
| **Innovation / creativity / evaluate-abstractions / bootstrap** | ❌ `innovation/` subpackage | **Dark LLM-off (D8)** | `return ""` with no fallback — deliberate creativity is LLM-only. |
| **Skill synthesis (deliberate)** | ❌ `skill_synthesis` | **Dark LLM-off (D8)** | `{"error": "llm_unavailable"}`. But symbolic `crystallization` (from dreams) works LLM-free. |
| **Experimentation** | ⚠️ split | Mixed | `experimentation.py` (LLM) dark; symbolic `autonomous_experiment` sandbox probes run LLM-free. |

### D5. The v2 research-synthesis fallback is orphaned behind D1 *(HIGH — the unifying bug)*

This is the single most important connection finding, and it ties G4 + D3 + C2
together. The v2 `ResearchHandler` has a **working LLM-free extractive synthesizer**
(`_offline_fallback_memo`, `research.py:245`) — it stitches sourced excerpts into a
durable, cited memo artifact. That is *exactly* the "turn intake into a finding"
organ the runs are missing. **But no cognitive goal is ever created as
`kind:"research"`** (confirmed: `_mk_goal` defaults `kind:"generic"`; grep for a
research-kind cognitive goal returns nothing). So understand-goals are pursued in v1
via `research_topic` (stores raw text) + `leave_note` (hollow felt-state seed), and
the good offline synthesizer **never runs**. Route understand-goals to
`kind:"research"` and they get real extractive memos instead of "something present but
hard to name" — closing the hollow-note door (G4), the no-synthesis gap (D3), and the
familiarity-closure (C2) in one wire.

### D6. The native LM is wired to the mouth, not the hands *(HIGH — architectural)*

`native_lm.generate` is called in exactly two places: `voice.py` / `conditional_
render.py` (speech) — i.e. **the language organ writes his utterances but not his
artifacts.** The LLM-free *composition* fallbacks (`compose_section`, `leave_note`)
use **hardcoded Python string templates** instead. That's why the LLM-free artifacts
are hollow boilerplate: the thing that could write them in his own learned voice is
never asked to. Wiring `native_lm.generate` into the composition fallbacks would turn
"boilerplate that games the gate" into "a real (if crude) authored artifact in his
own developing language" — and it's the *same* organ P2a is training on grounded
experience, so it compounds with the grounding work.

---

## Part 8 — Architectural decisions to make (the forks)

These are genuine forks — not bugs with an obvious fix, but decisions only you can
make about what Orrin *is*. Each blocks a class of the findings above.

**AD1 — What does "make things" mean for an LLM-free droid?** This is *the* decision.
Three coherent answers, not mutually exclusive:
- **(a) Making = verified computation.** Extend `produce_and_check` (P3) so "make a
  thing" means "write code/derivation that passes a check." Fully symbolic, already
  half-built, ungameable. *Recommended as the spine.*
- **(b) Making = authored artifacts in his own voice.** Wire the native LM into
  `compose_section`/`ResearchHandler`/`leave_note` (D6) so he writes memos/notes/
  sections symbolically. Crude at first, improves as P2a trains the organ.
- **(c) Making = code authorship.** Requires either the LLM (breaks the droid rule)
  or a symbolic/template code-generator. Decide whether self-code authorship is a
  droid capability at all, or an LLM-only luxury that's simply off in the default config.

**AD2 — Should understand-goals route through the v2 executor, or stay v1-pursued?**
The v2 `ResearchHandler` + offline memo is better than the v1 `research_topic` +
hollow-note path (D5). Decision: make cognitive research goals `kind:"research"` (they
reach the real handler, get a real memo, close on P1's effect gate) — or keep them in
v1 and port the offline-synthesis logic into the v1 pursuit path. Either closes D5;
pick one so the making path is single-homed (anatomy doc revision #5).

**AD3 — What is a "long-term goal," canonically?** There are four overlapping notions
(aspiration rows in v1, `lifetime` file goals, v2 long-kind goals, and now my P4
`directional` flag). The anatomy doc flags this (P-G). My P4 work added a *fifth*
door without unifying the others. Decide the ONE representation a directional driver
lives in, so "the goal that owns the frontier" is unambiguous.

**AD4 — Goal population policy.** Decide the intended *mix* of goals (intake vs make
vs connect vs introspect) and enforce it at generation (G2). Right now it's emergent
and skews ~95% intake. This is a values decision — what should he spend his life
doing? — not just a quota.

**AD5 — Memory retention policy.** Decide what long-memory is *for* (autobiography of
meaningful events) vs. what telemetry belongs elsewhere (M1). The 2,000-entry cap and
10-entry dedup window encode an implicit policy that's currently letting prediction-
error spam evict findings. Make it explicit.

---

## Part 9 — Past-runs persistence (what has NOT changed across every captured life)

Read across all seven demo runs (2026-06-16 → 07-01), these are the invariants —
present in *every* run, which is what makes them structural, not incidental:

| Invariant | 06-16 → 07-01 | Root finding |
|---|---|---|
| **Production ≈ 0** (janitorial only) | 4/17k → 0/1.4k → 36/14k, all housekeeping | D1 + D2 + D5 (no reached making path) |
| **Goal monoculture** (understand X) | every run | G2 / AD4 |
| **Notes are hollow templates** | 100/9 → 66/3 → 100/1 distinct bodies | G4 / D5 / D6 |
| **Alone — 0 replies** | every run, every session | connection aspiration + P2b unexercised |
| **Drives hot-and-flat** | every run | B3 (P5 decay work targets this) |
| **Goal history incoherent** (v1≠v2, 3× archive) | every run | revised-G1 (reconcile, not merge) |

The through-line: **six of these six invariants are downstream of "the mind can't
reach a working making/synthesis path."** Fix D5 (route to the offline synthesizer)
and AD1 (pick a making spine), and production, note-quality, and goal-coherence all
move together for the first time. Everything I found this pass converges on that one
sentence.

---

## Part 10 — Is the conscious/unconscious brain correct? *(new pass — the deepest layer)*

I hadn't audited this layer before; I have now (`ORRIN_loop.py`, `loop/deliberate.py`,
`global_workspace.py`, `binding.py`, `control_signals/arbiter.py`,
`think_module.py`). **Verdict: yes, it's correct and well-grounded.** This is the most
solid part of the system, not a crack in the foundation.

The loop is a faithful Global Workspace / ignition architecture:

- **Unconscious substrate runs every cycle regardless** — affect, embodiment,
  signals, subconscious threads, feature **binding** (`binding.py` fuses signals +
  goals into unified "situation" candidates), and **workspace competition**
  (`global_workspace.update_workspace` picks one salient winner).
- **Consciousness is a threshold crossing, not a metronome** — `ignite()` +
  `deliberation_gate.should_think()` (Dehaene 2014 / Baars 1988): only a salient /
  uncertain / conflicted cycle **ignites** into deliberate System-2 cognition; quiet
  cycles stay in low-power default mode with expensive functions damped. A periodic
  floor (`MAX_SILENT_CYCLES`) prevents full dormancy. Correct GNWT.
- **The veil holds** — conscious-side code reads `context["perceived_affect_state"]`
  (the felt projection), not raw `core_signals` keys (`think_module.py:125`). The
  membrane test suite enforces this. The substrate→consciousness one-way path is real
  (this is what my earlier "P6 / seal the veil" item was about — it's *largely already
  sealed*, closing residual leaks is the remaining work, not building it).
- **Arbiters prevent split-brain races** — `commit_signals` (AffectArbiter),
  `action_arbiter`, and `goal_arbiter` are lock-guarded single write-chokepoints, the
  fix for the convergence-layer races.

**One real watch-item (C-W1, MEDIUM):** the pre-think `update_workspace` **consumes**
`_bound_candidates` / `_workspace_offers` (`deliberate.py:64-71`), so the
end-of-cycle finalize `update_workspace` "sees only a starved leftover." The code
comments say this is understood and the pre-think call is the substantive one — but
it means the *post-action* conscious moment (what he registers as "what just
happened") is drawn from depleted candidates. Worth a focused check that the
end-of-cycle conscious record isn't systematically impoverished — it feeds
autobiography and the felt narrative the native LM trains on (P2a).

**So the answer to "is the conscious/unconscious brain correct":** yes. The goal and
making fixes sit on a sound foundation, not a cracked one. Do **not** spend effort
re-architecting this layer.

---

## Part 11 — Behavioral completeness: will fixing the above fix the main bugs?

Honest causal assessment against the headline bug ("produces nothing / goals don't
work"). I checked the loops I hadn't before: the selector, the reward path, the input
channel, and the affect loop.

**Already-fixed loops (verified this pass — don't re-flag):**
- **Selector honors learned reward** — the anatomy doc's P-F ("learned value has no
  authority") is repaired: `score_actions.py` uses `action_reward_ema` (Pearce-Hall)
  with `_devalue_prior` relative to the pool median. The reward IS consulted now.
- **Reward reaches both learners** — `episode_replay` updates the bandit; `consolidate_
  language` trains the native LM (P2a reward-weights its diet). B1's core wiring exists.
- **Input channel works** — `sense.py` runs `process_inputs`, answers waiting Face
  messages, tracks `latest_user_input`. So *"always alone / 0 replies"* is genuinely
  "no human talks to him during headless runs," **not** a dead channel. It's a usage
  pattern, not a bug — but it means the connection aspiration and P2b stay unexercised
  until someone actually converses with him.

### R1. The reward denominator still tilts toward intake, per-cycle *(HIGH — the one that decides whether the making fix "takes")*

This is the most important *new* behavioral finding, and it directly answers "will
fixing the wiring be enough." The per-cycle cognition reward
(`cognition_reward.shape_cognition_reward`) is `blend(0.6·env + 0.4·status, emo_delta)`
where `emo_delta = signal_delta_reward(pre, post)` — and `signal_delta_reward`
(`loop_helpers.py:43`) pays a reward whenever a function nudges **internal signals**
(exploration_drive, confidence, motivation, reward_positive) upward, and 0.5 (neutral,
not a penalty) when nothing changes.

**Consequence:** reading / reflecting / researching that raises curiosity or
confidence **pays a small reward every single cycle**, reliably. Producing pays a
**rare +1.0 lump** at goal completion (now effect-gated by P1). So the *moment-to-
moment gradient the bandit learns from still favors intake* — the exact
reward-denominator problem `ORRIN_PRODUCTION_REWARD_PLAN` named. It is **partially**
mitigated (goal-weighting scales down off-goal cognition; `exploration_value` info-gain
habituates so repeated reading stops paying; the completion reward is
significance-scaled) — so it's a *tilt*, not "intake pays and production doesn't." But
the tilt is real and standing.

**Why it matters for the plan:** D5/D6/AD1 give Orrin *hands*. R1 is about whether
he'll *choose* to use them. If every reflective cycle pays and production pays only at
a rare finish line, a reward-maximizing selector still drifts toward reading. **The
making path needs a competitive per-attempt reward** — e.g. a produce-and-check
*attempt* (pass OR fail) should pay like an intake action pays, so trying to make is
never locally worse than reading about it. Without this, the wiring fix may land and
still lose to the gradient.

### The verdict

**Will fixing D5 + D6 + AD1 fix the main "produces nothing" bug?** *Mostly yes for
capability, not automatically for behavior.* They make production **possible and
honest** for the first time. But two things must land alongside or it won't **stick**:

1. **R1 — give making a competitive per-attempt reward**, so the gradient stops
   favoring intake.
2. **G2/AD4 — the birth-rate quota**, so make/connect goals are actually *generated*
   to compete for slots (a reachable making path is moot if 95% of goals are "understand
   X").

With those two, the causal chain closes: goals of the right *kind* are born (G2) →
reach a working LLM-free maker (D5/D6/AD1) → producing pays enough to be chosen (R1) →
P1 gates the close on a real effect → the effect trains the learners (B1/P2) → the
long-term driver carries the frontier (P4). That is the full loop, and this pass
found the last two links (R1, and the still-open G2) that weren't yet accounted for.

### Completeness — what this audit now covers, and what it can't

**Covered across the three passes:** goals (generation, closure, commit, v1/v2,
satiety, milestones), memory (long/working/vector/concepts), the execution engine and
its handlers, the system-wide LLM-free capability map, the conscious/unconscious
architecture (ignition, workspace, binding, veil, arbiters), the selector/reward
authority, the reward denominator, the input channel, and seven runs of behavioral
history.

**Genuinely not knowable from static read (needs a live run to confirm):** (a) whether
the P1–P4 + P5 changes *interact* cleanly under load — only a full-loop staging run
shows integration failures (B5); (b) whether the native LM, once wired to composition
(D6), produces artifacts good enough to matter or just fluent noise (needs the
forgetting-probe from the structural risk register); (c) the C-W1 workspace-consumption
question. These are flagged, not resolved — they are the standing reasons to do a
stamped staging run after the D5/D6/R1 work lands.

---

## Part 12 — The symbolic engine: the biggest unchecked area, and the biggest reframe

You were right to push — I had not read `brain/symbolic/` (**9,473 lines**, the single
largest subsystem), the `goals/` daemon internals (`triggers.py`, `runner.py`), or
`archive/RUN_AUDIT_2026-06-30.md`. Doing so produced the most important finding of the whole
audit, and it *changes the answer to "what can an LLM-free droid make."*

### D7. The symbolic engine makes real things — and records ZERO production effects *(CRITICAL — reframes AD1)*

`brain/symbolic/` is a working, LLM-free cognitive engine: `rule_synthesis`,
`rule_abstractions`, `crystallization` (skills), `autonomous_experiment` (sandbox
probes), `causal_graph`, `prediction_engine`, `symbolic_dream`, `meta_rules`. It
produces **durable artifacts every run** — the snapshot has `crystallized_skills.json`,
`symbolic_rules.json`, `rule_synthesis.json`, `rule_abstractions.json`,
`rule_revisions.json`, `meta_rules.json`, plus 187 KB of causal graph. These are
genuine "things that didn't exist before," made **without any LLM**.

**But not one of them records an effect on the ledger.** Every single `record_effect`
caller lives in `agency/`, `planning/`, `behavior/`, or `loop/` — **none in
`symbolic/`.** So under the P1 grounding regime:

- Synthesizing a rule, crystallizing a skill, resolving an experiment, adding a
  causal edge = **zero production credit, zero effect, invisible to the goal gate.**
- The largest LLM-free making capability in the system **cannot satisfy P1's
  effect-gated closure, cannot pay production reward, and doesn't register as "making."**

This reframes my earlier D2 ("in LLM-free mode he has almost no hands"). **He has
enormous hands** — an entire symbolic reasoning engine that builds rules, skills,
experiments, and causal knowledge. The problem was never that the droid can't make
things without an LLM. **It's that the thing it already makes — symbolic cognitive
artifacts — was never wired to production accounting.** RUN_AUDIT_2026-06-30 shows the
shadow of this directly: 644 effects, **all `note_novel`**, significance moved 0→1.2 —
real production machinery, but it only ever sees notes, never the rules/skills/
experiments the symbolic engine is producing in the same run.

**D7 is bigger than the symbolic engine (found in the daemon pass):** `record_effect`
appears **nowhere in `goals/`** either. The v2 executor daemon's handlers —
`HousekeepingHandler` (writes real snapshot/patch artifacts via `_write_artifact` →
`data/goals/artifacts/`), `ResearchHandler` (writes memos), `CodeEditHandler` (edits
files) — and the runner's `_execute_step` (which only sets DONE/FAILED) record **zero
effects.** So the production ledger is blind to **both** subsystems that actually
produce: the symbolic engine *and* the v2 "hands." This has a sharp implication for
the D5 fix: **routing understand-goals to `ResearchHandler` will NOT count as
production unless the handler is also made to `record_effect`** — the memo would be
written to disk and still be invisible to P1's gate. So the true keystone is one
principle applied in two places: *every durable artifact — symbolic rule/skill/
experiment AND every v2 handler output — must record an effect.* That single principle
closes D5, D7, and the "production = 0" run-invariant together.

**This is the best answer to AD1 (what "making" means for an LLM-free droid):** not a
new sandbox maker, not the native LM — **wire the symbolic engine's existing durable
outputs to the effect ledger.** A synthesized rule / crystallized skill / resolved
experiment / new causal edge should each `record_effect` (a new `symbolic_artifact`
kind, or reuse `tool_run_effect`), so his native LLM-free cognition finally *counts*.
This single wire simultaneously: gives him a real making path (AD1), satisfies P1's
gate for understand-goals that produce a rule/skill (G3/G4), and — because production
would then pay per symbolic artifact — **fixes the R1 reward tilt** (LLM-free thinking
starts paying like production). It is lower-risk than D5/D6 and more droid-native than
either. **It may be the highest-leverage single change in this entire document.**

### D8. Deliberate creativity / skill-growth actions are LLM-only and go dark LLM-off *(HIGH)*

The system-wide early-return sweep found a clean split. **Most cognitive functions
degrade symbolically** (comprehension → `_fallback`, opinions → evidence-weighted
stance, autogenerated-thoughts → symbolic composition, self-modeling → symbolic
repair). **But an entire capability class returns dark** (`return ""` / skip, no
fallback) when the LLM is off:

- **the whole `innovation/` subpackage** — `simulate_new_cognitive_abilities`
  (`innovation.py:25`), `exploration_drive_loop` (`exploration.py:47`),
  `evaluate_new_abstractions` (`evaluation.py:23`), `bootstrap_self`
  (`bootstrap.py:45`);
- **`skill_synthesis`** (`skill_synthesis.py:177,347` → `{"error": "llm_unavailable"}`);
- **the LLM path of `experimentation`** (`experimentation.py:383` → skip).

So in the intended LLM-free config, the **deliberate "grow a new ability / synthesize
a skill / evaluate a new abstraction / innovate" actions do nothing.** This is the
lifelong-growth analog of D2's making gap: he can *reason with the rules he has* but
his explicit self-improvement verbs are LLM-gated.

**Bounded, though — the symbolic substrate keeps learning LLM-free underneath:**
`crystallization` genuinely works without the LLM (it crystallizes symbolic **dreams**
via `crystallize_idle_insights`, not only LLM responses — 0 dark markers), the
symbolic `autonomous_experiment` runs sandbox probes LLM-free, and `rule_synthesis` /
`rule_abstractions` run in idle consolidation. So background symbolic growth continues
— but (per **D7**) it records no effects, so even the LLM-free growth that *does*
happen is invisible to the goal/production system. **D7 + D8 together:** the substrate
learns silently and uncredited; the deliberate growth actions are dark. Wiring D7
(effects for symbolic output) plus giving the innovation verbs symbolic fallbacks
would make lifelong growth both real and visible without an LLM.

### R2. Energy never breathes — a dead embodied signal *(HIGH — from RUN_AUDIT, not yet fixed)*

`RUN_AUDIT_2026-06-30` (its "energy never breathes" follow-up) found `resource_deficit
≈ 0.037` (energy ~96%) **constant** across a 5.5-hour life. Cause: accumulation is a
flat **+0.002/cycle** vs **0.025/cycle** recovery (~12× weaker), so fatigue can never
climb; and the exhaustion dynamics (accelerated recovery + allostatic-load forcing)
only arm above `resource_deficit > 0.60`, which is unreachable. **This is the fuller
explanation of the `allostatic_load = 0.000` I noted earlier** — not only the retired
top-level field (Correction 2), but that the *active* `_allostatic_load` never arms
because energy never gets low enough. `resource_deficit` is load-bearing (~20
consumers: action gate, speech pipeline/gate, selection, binding, working memory,
consolidation), so a pinned-high energy means **fatigue carries no behavioral signal**
— a whole dimension of embodied variation (rest, slowing, end-of-day) is flat. Flagged
PROPOSED in the run audit; not yet moved. Move it deliberately (20 consumers), not by
slamming the constant.

### Confirmations from the run files (real data, not inference)

`RUN_AUDIT_2026-06-30` independently confirms findings I'd reached from code + the
07-01 snapshot: production is **all `note_novel`** (D5/D6/G4); **114 store desyncs/life**
self-healed but the source remains (revised-G1); **92.9% self-understanding / 0.0%
be-useful** (G2); satiety closures **0** pre-P1 (my P1 addresses this). Two things it
adds that I've now folded in: the **GOAL_STORE_UNIFICATION** work is *already named and
deliberately deferred* (patching the store core risks the resurrection/orphan bugs it
guards — so revised-G1 is "do the planned unification," not "band-aid the reconcile"),
and the **energy** finding (R2).

### Still genuinely unchecked (honest list)

I have **not** deep-read: the `backend/` telemetry bridge (28 files) or `frontend/`
(UI — the P7 lived-surface work, out of behavioral scope); `supervisor/`'s
resource-floor calibration internals (liveness — read the map, not every line);
`memory/`'s embedder/WAL internals beyond confirming `InMemoryStore` (M3); and most of
`brain/symbolic/`'s *internal correctness* (I confirmed it runs LLM-free and produces
artifacts + the D7 effect gap, but did not verify each reasoner's logic). None of these
are likely to hold a *behavioral* root cause bigger than D7/R1/R2 — but that's a
judgment, not a proof. The definitive check is a stamped staging run.

---

## Part 13 — Final sweep: the last unread subsystems (goals daemon, memory, symbolic reasoners, supervisor)

You asked me to read *all* the remaining unread subsystems (skipping UI). I did. This
pass produced **two refinements to existing findings and otherwise cleared the rest** —
the pattern has converged; I'm no longer finding new *classes* of bug, just confirming
where the established ones live and that the remaining code is sound.

**Refinements (folded into the findings above):**
- **D7 now includes the v2 executor**, not just the symbolic engine: `record_effect`
  appears nowhere in `goals/`; the daemon runner (`_execute_step`) and every handler
  (`HousekeepingHandler` writes real artifacts, `ResearchHandler` writes memos) record
  no effects. **Implication for the fix: D5's routing won't count unless the handler
  also records an effect.** One principle — *every durable artifact records an effect*
  — closes D5 + D7 + the production-zero invariant together.
- **M3 is an orphan, not a missing feature**: the memory WAL is fully active (append)
  *and* `wal.py` implements `replay_events`/`replay_items` — but `main.py` boots
  `InMemoryStore()` and never replays. Persistence is built on both ends and unwired at
  boot. Cheap fix.

**Cleared this pass (checked, and sound — so they're not hiding a root cause):**
- **Symbolic reasoners are live and wired, not dead code** — `inference` (2 call
  sites), `rule_engine` (5), `prediction_engine` (4), `symbolic_cognition` (9),
  `rule_synthesis`, `symbolic_dream`, `temporal_planner` are all invoked from
  non-symbolic cognition. The engine runs and is used; D7 (no effects) is its only
  systemic gap.
- **Goals daemon runner** correctly executes handler steps, ticks status, finalizes
  goals, and handles no-handler / dependency / retry paths. Sound except the D7 effect
  gap.
- **Supervisor watchdogs function** — `no_goals` trips on goal-stall / retry-saturation
  / circuit-breaker-saturation; `repeat` fingerprints repeated actions. Liveness layer
  is real.
- **`runtime_coupling`, `motivation`, `evidence`, `eval`, `core`** — scanned clean: no
  LLM-dark early-returns, and their durable writes are legitimate state (host-field
  samples, energy state, life capsule, evaluator WAL), not uncredited production. The
  host-input/sensing loop (`input_stream`) is wired.

**Now genuinely covered** (behavioral scope): goals (generation → commit → daemon
execution → closure), both memory systems + persistence, the effect/production ledger
and all its callers, the conscious/unconscious loop, the symbolic engine, the
selector/reward path, the input channel, the supervisor, and host coupling.

**Deliberately not read (per your instruction / out of behavioral scope):** `backend/`
telemetry bridge and `frontend/` UI. **Not line-by-line, but scanned and judged
low-risk:** the internal *numerical correctness* of individual symbolic reasoners
(e.g. is Pearl-style causal inference implemented right) and `supervisor` resource-floor
*calibration math* — these could hold a subtle *quality* bug, but not a *wiring/
behavioral* root cause of the kind this audit is about. **The only definitive remaining
check is a live stamped staging run** — static reading has reached its floor.

---

## Closing

The architecture is genuinely good and the grounding plan is right — the v1/v2 split,
the retired allostasis field, the usefulness rewrite, and the broad symbolic-fallback
discipline are all deliberate. The system-wide sweep changes the headline one last
time, and makes it *hopeful*: **the LLM-free machinery Orrin needs to make things
mostly already exists — it's just orphaned or hollowed.** The v2 ResearchHandler has a
working offline synthesizer no goal reaches (D5); the native LM writes his voice but
not his artifacts (D6); `produce_and_check` makes verifiably but only for checks; the
composition fallbacks are templates instead of his own trained language. Six of six
run-invariants trace to one sentence: *the mind can't reach a working making/synthesis
path.*

So this isn't a rebuild — it's **connecting parts that are already built.** And the
deepest layer is *sound*: the conscious/unconscious brain (ignition/GNWT, binding,
the veil, the arbiters) is correct — don't touch it (Part 10).

**Direct answers to your four questions:**
1. **Is this everything?** As close as a static read gets — this pass added the
   conscious/unconscious layer, the selector/reward authority, the reward denominator,
   and the input channel, which the first two passes hadn't touched. What remains is
   only knowable from a live staging run (integration under load, native-LM artifact
   quality, C-W1) — flagged in Part 11, not resolvable on paper.
2. **Is the conscious/unconscious brain correct?** **Yes** (Part 10). It's the most
   solid part of the system. One medium watch-item: the post-action conscious moment
   may be drawn from consumed workspace candidates (C-W1).
3. **Will fixing these fix the main bugs?** **For capability, yes; for behavior, only
   with two additions** (Part 11): **R1** (give making a competitive per-attempt
   reward — else the per-cycle gradient still favors reading) and **G2/AD4** (a
   birth-rate quota — else make-goals never get generated to use the new path). With
   those, the full causal loop closes end-to-end.
4. **Anything else behaviorally?** Yes — **R1, the reward denominator**, is the one
   that decides whether the making fix *takes*. That's the material addition this pass
   found; the rest of the behavioral loops (selector, reward→learner, input) are sound.

The smallest set of wires that changes everything — **updated after reading the
symbolic engine (Part 12), which changes the keystone:**

- **D7 (the keystone) — wire the symbolic engine's durable outputs to the effect
  ledger.** He already makes rules, skills, experiments, and causal knowledge
  LLM-free; they just don't count. This one wire gives him a making path (AD1),
  satisfies P1 for understand-goals, and fixes the R1 reward tilt at once. Highest
  leverage, lowest risk, most droid-native.
- **D5** (route understand-goals to `kind:"research"` → the offline memo) and **D6**
  (native LM into composition) — the artifact/finding side.
- **G2** (birth-rate quota) so make/connect goals get generated; **R2** (let energy
  breathe) so embodiment carries signal again.
- **GOAL_STORE_UNIFICATION** (revised-G1) — already your named, deferred architecture
  task; bring the 114-desync/25k-failure numbers to it.

Everything else is a fork in Part 8 for you to call. **If you do exactly one thing:
make the symbolic engine's output record effects (D7).**

*Generated 2026-07-01 from a full read of the codebase, all seven demo runs +
`RUN_AUDIT_2026-06-30`, the pre-reset runtime snapshot, a system-wide LLM-dependency
sweep, the conscious/unconscious layer, the `goals/` daemon internals, and the
`brain/symbolic/` engine. Revised across six passes: (1) initial audit, (2) after the
archived design docs + README reframed the v1/v2 split as intentional, (3) after the
system-wide sweep found the orphaned-machinery pattern (Parts 7–9), (4) after the
deepest-layer read confirmed the conscious/unconscious brain is sound and found the
reward tilt R1 (Parts 10–11), (5) after reading the symbolic engine + run-audit files
found D7 (symbolic output records no effects — the keystone) and R2 (energy never
breathes) (Part 12), and (6) after an exhaustive read of the last unread subsystems — goals daemon, memory WAL, symbolic reasoners, supervisor — which extended D7 to the v2 executor, made M3 an orphan, and cleared the rest (Part 13). Analysis only — no code
changed by this write.*
