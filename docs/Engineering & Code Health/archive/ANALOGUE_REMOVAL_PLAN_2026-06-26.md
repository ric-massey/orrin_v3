# Analogue Removal Plan — Drop the Biological Framing, Codebase-Wide

Date: 2026-06-26
Status: Phases 1–4 DONE IN FULL (2026-06-27), including the data-file *name*
renames (§4.7), per Ric's explicit go-ahead (overriding the "defer Phase 4
indefinitely" recommendation). See [§ Phase 4 — DONE](#phase-4-done) for the
landed sub-slices and the one naming deviation (`surprise → prediction_error_signal`).

## Phase 4 — DONE

Executed on branch `analogue-removal`, each sub-slice its own green commit
(`make verify`: 1094 backend tests + frontend typecheck/build):

- **4.1** Migration spine: `brain/data_schema.py` (schema version + per-file
  read-old/write-new key registry) hooked into `load_json`/`modify_json` (and the
  backend `_read_json`), `brain/scripts/migrate_schema_v2.py` one-time backfill,
  7 tests. Old `brain/data` files and out-of-tree backups upgrade on load.
- **4.2–4.4, 4.6** Persisted affect-state scalar keys + lifecycle timestamp:
  `homeostasis→setpoint_proximity`, `valence→reward_signal`, `mood→smoothed_state`,
  `born_at→start_time`. Wire fields kept via serializer translation.
- **4.5a/b/c** All 9 biological core-signal names → engineering, on disk in
  `core_signals` AND in the learned `emotion_function_map.json` AND every routing/
  setpoint/antagonist/appraisal table: `positive_valence→reward_positive`,
  `negative_valence→reward_negative`, `compassion→affiliation_signal`,
  `melancholy→low_affect_signal`, `jealousy→social_comparison_signal`,
  `contentment→satisfaction_signal`, `vitality→vigor_signal`,
  `surprise→prediction_error_signal` (the `_signal` suffix avoids colliding with
  the existing `prediction_error()` function — the one deviation from the names
  Ric approved), `wonder→novelty_signal`. The `wonder.py` module + its function
  names were kept as code identifiers (Phase-3 scope, and function-name churn
  risks learned data).
- **4.8** API route paths renamed backend+frontend lockstep:
  `/affect→/control-signals`, `/consciousness→/attention`,
  `/dreams→/idle-consolidation`, `/drives→/demands`, `/self→/identity`,
  `/vitals→/resources`, `/life→/runtime-lifetime` (`/lifecycle` kept — standard;
  `/api/life/capsule*` kept — diagnostics). Live WS wire fields
  (`valence/arousal/homeostasis`) stay translated at the serializer.
- **4.9** Backfill verified against the Phase-0 data snapshot (idempotent), then
  run against live `brain/data` (3 files migrated, schema v2). Restart smoke +
  leak sweep clean (residue = kept code identifiers, comments, the deferred
  `mood_state.json` file, and memory-tag/sentiment surfaces).

- **4.7** Data-file *name* renames (21 files): `affect_state.json→control_signals_state.json`,
  `emotion_function_map.json→signal_function_map.json`, `mood_state.json→smoothed_state.json`,
  `conscious_stream.json→workspace_broadcast.json`, `dream_log.json→idle_consolidation_log.json`,
  `autobiography.json→run_history.json`, `body_sense.json→resource_self_monitor.json`,
  `interoceptive_model.json→cost_prediction_model.json`, `lifespan.json→runtime_lifetime.json`,
  `self_model.json→identity_state.json`, `alive_brain_state.json→runtime_state.json`,
  `drive_aspiration_credit.json→demand_objective_credit.json`, … (full map in
  `brain/data_schema.FILE_RENAMES`). A `resolve_read_path()` read-old-path fallback
  in `load_json`/`modify_json`/the backend reader keeps old files + backups loading;
  the backfill renames them on disk (verified on the snapshot + run live, idempotent).
  The lone git-tracked seed (`affect_model.json`) was re-tracked under its new name.
  The `paths.py` constant *identifiers* (e.g. `AFFECT_STATE_FILE`) were left as-is
  to bound blast radius — only the filename they point at moved.

---

### Original plan (PROPOSED — superseded by the status above)
Owner: Ric
Revision: 2026-06-26b — second full-codebase pass. Added the **emotion/mood**
family (missed in the first pass, ~800+ hits), the **`reaper/` package** (a
death metaphor), and — most important — corrected the frozen boundary to cover
**three** wire surfaces, not just JSON keys (see § persisted data). Read the
second-pass findings in [§ What the second pass added](#what-the-second-pass-added).

## What this is

A complete switch away from biological-analogue terminology to engineering
terminology across the **entire** codebase **and** the UI. The biological
dialect is removed, not toggled. Engineering language becomes the only
language.

This **reverses** the prior `docs/UI, Security & Desktop Packaging/ENGINEERING_FRAMING_PLAN_2026-06-23.md`,
whose explicit non-goals were "do not remove biological mode" and "do not
rename internal Python modules." Those non-goals no longer hold. When this plan
lands, that document should be moved to `archive/` with a one-line note that it
was superseded here.

## Why this goes all the way to internal names

These modules are not private scratch code. They are intended to be read by
other engineers, and individual modules are expected to spin out into their own
standalone products/packages over time. That makes a module/package name a
**product boundary**, not just an internal label: `affect`, `mortality`,
`selfhood`, `reaper` would become a shipped package name, an import path in
someone else's codebase, and the first word a prospective adopter reads. The
biological-perception problem the UI switch solves would simply relocate to the
package manifest.

Consequence for this plan: the internal rename (Phase 3) is in scope, not
optional, and each new name should be chosen as if it were a **public package
name** — clear to an outside reader with no Orrin context — not merely a private
identifier. There is no "presentation-only, keep internals" tier; the internals
are part of the presentation to other engineers. (The frozen data/wire/signal
surfaces in the next section are the one exception, for compatibility reasons,
not optics.)

## What "analogue" means here

Every place the system borrows a biology / neuroscience / personhood word to
name an engineering mechanism. Concretely, the vocabulary families:

- **Mind / brain / body / organism** → runtime, dashboard, host budget
- **Consciousness / conscious stream** → attention arbitration / workspace broadcast
- **Affect / valence / arousal / mood / feelings / "felt"** → control signals / activation / internal-state estimate
- **Homeostasis / setpoints** → setpoint regulation (the eng word is already close)
- **Mortality / death / born_at / lifespan** → lifecycle / runtime lifetime / termination policy
- **Metabolism** → resource cadence policy
- **Nervous system / interoception / body_sense** → health telemetry sampler / resource self-monitoring
- **Selfhood / self-model / autobiography** → identity & policy state / system self-descriptor / run history
- **Dreams / dreaming** → idle consolidation
- **Drives / wants / aspirations / intrinsic goals** → priority weights / standing objectives / intrinsic objectives
- **Neurotransmitters** (dopamine, acetylcholine/ACh, Pearce-Hall) → reward-prediction error / learning-rate gain / adaptive learning rate
- **Subconscious** → background processing

The canonical mapping table is in [§ Term Map](#term-map). Everything in code,
docs, and UI should resolve to the right column.

## The one decision that controls all the risk: persisted data

A naive global rename is **not safe**. The biological words are not just
identifiers — they are keys in data we have already written to disk and stream
over the wire:

| Key | Occurrences in persisted JSON (`brain/data`, `data/`) |
| --- | --- |
| `valence` | ~18,921 |
| `homeostasis` | ~18,914 |
| `arousal` | ~17,550 |
| `mood` | ~13,365 |
| `affect`, `felt_*`, `born_at` | hundreds |

These also appear as field names in `backend/server/routers/*` telemetry
payloads and in `goals/` WAL records. Renaming them in place would:

- invalidate every existing backup / state archive,
- break restart continuity (the loop reads its own prior state on boot),
- break the live telemetry contract between backend and frontend, and
- force a lockstep change across writer + reader + every historical file.

**The frozen boundary is FOUR surfaces, not one.** The second pass found the
risk is wider than just JSON keys. All four of these are stable contracts that
break callers/readers (and the *learned* model) if renamed in place:

1. **JSON keys** inside the data — `valence`, `arousal`, `homeostasis`, `mood`,
   `affect`, `born_at`, … (counts above).
2. **Data file names / paths** the loop reads and writes — e.g.
   `brain/data/affect_state.json`, `affect_model.json`, `conscious_stream.json`,
   `mood_state.json`, `emotion_*.json`, `dream_log.json`, `autobiography.json`,
   `interoceptive_model.json`, `lifespan.json`, `self_model.json`,
   `body_*.json`, and root `data/alive_brain_state.json`. Renaming a file is an
   on-disk path migration the running loop and the state archive depend on.
3. **API route paths** the frontend calls — `/affect`, `/consciousness`,
   `/dreams`, `/drives`, `/self`, `/vitals`, `/life`, `/lifecycle`, and the
   `embodiment` router. Renaming a route breaks the frontend fetch unless both
   sides change in the same commit.
4. **The internal signal vocabulary** — the 23 core-signal names
   (`positive_valence`, `negative_valence`, `threat_level`, `exploration_drive`,
   `confidence`, `motivation`, `impasse_signal`, `stagnation_signal`,
   `uncertainty`, and the feeling-flavored `melancholy`, `jealousy`,
   `compassion`, `wonder`, `contentment`, `boldness`, `surprise`, …). These exact
   strings are the **most cross-referenced identifiers in the system**: they are
   persisted keys in `affect_state.json`, **learned** weights in
   `emotion_function_map.json` (signal→function→value), and the keys of every
   routing/setpoint/antagonist table (`emotion_routing._ROUTES`,
   `drive._EMO_DRIVE_MAP`, `homeostasis.ANTAGONISTS`, `setpoints.CORE_BASELINES`).
   Renaming one breaks persisted state, *destroys learned associations*, and
   desyncs four tables at once. `melancholy`/`jealousy`/`wonder` look like prime
   analogue targets — they are **off-limits as identifiers**. Translate them to
   engineering labels ONLY at the presentation boundary (the UI already maps them
   to display words in `identity._ADJ` / `AffectRings`).

**Decision (recommended): freeze all four.** Do NOT rename persisted keys,
data-file paths, route paths, or signal names in place. Instead:

1. Treat them as **stable wire identifiers** — an internal contract, not
   user-facing copy. They keep their current spelling. (Route renames, if ever
   wanted, are a lockstep backend+frontend change, done deliberately in Phase 4,
   not as a side effect of identifier renames.)
2. Rename freely at every layer the user or a code reader sees: Python
   identifiers/functions/modules/comments/logs, and all UI copy.
3. Put translation at the **presentation boundary** (backend serializer and/or
   frontend adapter), where the stable key `valence` renders as e.g. "Reward
   signal."
4. If we later want the disk schema itself to use engineering keys, do it as a
   separate, versioned migration (§ Phase 4) with a schema-version bump and a
   read-old/write-new shim — never as part of the bulk rename.

This is the safety hinge. It lets Phases 1–3 (the visible 90%) proceed with
near-zero data risk, and quarantines the dangerous 10% (Phase 4) behind an
opt-in migration. If you disagree and want the disk schema renamed too, that is
allowed — but it must be Phase 4, gated, and reversible, never folded into the
identifier rename.

## Term Map

Engineering is the only column now. (Seeded from the 2026-06-23 plan's table,
extended to the deep concepts.)

| Biological (remove) | Engineering (use) |
| --- | --- |
| Mind | Runtime / runtime state |
| Brain (the dashboard) | Runtime dashboard |
| Body | Host / process resource budget |
| Consciousness (workspace/broadcast) | Attention arbitration / selected context / attention winner |
| Conscious vs unconscious cycle (`consciousness_trigger`) | Deliberation gate / LLM-dispatch decision (run expensive reasoning this cycle, or stay silent) |
| Stream of consciousness | Workspace broadcast log |
| Conscious now | Broadcast winner (this cycle) |
| Affect / affective | Regulated internal signal-state vector (homeostatic). Downstream it feeds priority modulation / internal weighting — but affect itself is the *state*, not the modulation |
| Emotion / emotional | Named control signal (e.g. `threat_level`, `exploration_drive`); `emotion_routing` = signal→function-selection bias. NOT discrete "events" |
| Mood | Smoothed state / running signal average |
| Feeling | Internal state estimate |
| Embodied state / embodiment | Runtime state / host-state feedback / environment-coupled state |
| Felt state | Internal state estimate / machine-state awareness |
| Felt time | Internal clock estimate |
| Valence | Reward signal (sign − ↔ +) |
| Arousal | Activation level |
| Mood | Smoothed state |
| Homeostasis | Setpoint proximity / setpoint regulation |
| Metabolism | Resource cadence policy |
| Nervous system | Health telemetry sampler |
| Interoception / body_sense | Resource self-monitoring |
| Selfhood | Identity & policy state |
| Self-model | System self-descriptor |
| Autobiography | Run history |
| Mortality / death | Finite runtime horizon / lifecycle / termination |
| born_at | Start time |
| Lifespan | Lifespan constraint / runtime lifetime budget (long-term budget) |
| Consciousness (selected content) | Active workspace / selected context / attention winner |
| Dreams / dreaming | Idle consolidation |
| Drives / wants | Demand-pressure accumulators (integrate over time; inject a weighted priority signal when pressure crosses a threshold; deplete when satisfied, then rebuild) — NOT static "priority weights" |
| Aspirations | Standing objectives |
| Intrinsic goals | Intrinsic objectives |
| Subconscious | Background processing |
| Will / volition / second-order volition | Decision policy / meta-policy |
| Vital / vitals / vital floor | Resource threshold / health-floor check |
| Sleep / wake / asleep / awake | Idle / suspend / resume / active |
| Fatigue | Cost penalty / throttle |
| Plasticity | Adaptation / online update |
| Sensory stream | Input stream |
| Reaper (package) | Liveness/health monitor / supervisor |
| Liveness cycle / heartbeat detector | Liveness probe (heartbeat is acceptable infra term) |
| Alive / alive_brain_state | Running / runtime-state |
| Dopamine signal | Reward-prediction error (RPE) |
| Acetylcholine / ACh | Learning-rate gain |
| Pearce-Hall | Adaptive learning rate (associability) |
| Moral override / ethics gate | Policy gate |
| Export Mind | Export State Archive |
| Restore Mind | Restore State Archive |
| Keepsake | Backup |
| he / him / his (for Orrin) | it / the runtime |

This table is the single source of truth. If a term is missing, add it here
first, then change code.

**Accuracy-checked against the code (2026-06-26b).** The engineering terms are
not just analogy-swaps — each was verified against what the module actually
does. Exact matches: metabolism = budget→cadence policy w/ hysteresis;
homeostasis = setpoint restoring forces; mood = EMA; dreams = idle
consolidation; reaper = loop kill-switch/supervisor; nervous_system = EWMA
health sampler. Three were corrected because the first-pass term mislabeled the
mechanism: **drives** are accumulating demand integrators, not static priority
weights; **emotions** are named continuous signals feeding selection bias, not
discrete "events"; **consciousness** splits into the workspace broadcast
(attention winner) *and* `consciousness_trigger`, which is a separate
LLM-deliberation gate. Rule for adding terms: name what the code *does*, then
confirm by reading the module — never name by analogy alone.

## What the second pass added

The first pass under-counted. The full-codebase re-sweep surfaced these, which
the implementer must not miss:

- **The emotion/mood family** — entirely absent from the first pass and large:
  `emotion` ~802 hits in code. Modules: `brain/cognition/emotion_routing.py`,
  `brain/utils/emotion_utils.py`, `brain/peers/emotion_historian.py`,
  `brain/cognition/mood.py`, `brain/think/think_utils/dreams_emotional_logic.py`.
  Data: `emotion_drift.json`, `emotion_function_map.json`, `emotion_sensitivity.json`,
  `mood_state.json` (and `mood` ~13k in stored JSON — a **frozen key**).
- **`reaper/` is a death metaphor at the package level** — `reaper.py`,
  `lifespan.py`, `liveness_cycle.py`, `heartbeatdetector.py`, `vital_floor.py`,
  `vital_floor_calibration.py`, `no_goals.py`. Renaming the package touches many
  imports; treat it as its own Phase-3 concept.
- **`embodiment` is both a code dir and a backend router** (`backend/server/routers/embodiment.py`).
  The router is a **route surface** (frozen). The dir
  (`brain/embodiment/`: `drive_engine`, `plasticity`, `sensory_stream`,
  `setpoint_regulation`, `social_presence`, `subconscious`, `system_presence`,
  `world_model`) is code (renameable).
- **`will` / `volition` / `second_order_volition`** (~163 / 22 hits) — free-will
  / personhood framing in `brain/cognition/selfhood/`.
- **`vital` / `vitals` / vital_floor** (~67 hits) — `reaper/vital_floor*.py`,
  `frontend/.../VitalSignsRow.tsx`, `/vitals` route.
- **sleep / wake / fatigue / alive** — lifecycle and existence framing across
  the loop, DeathScreen, and `data/alive_brain_state.json`.

## Borderline — keep these, do NOT over-rename

Dropping the analogues should not become a purge of legitimate engineering
words. Leave these as-is unless a specific instance is clearly personifying:

- **`reflection` / `introspection`** — these are standard CS/runtime terms
  (reflective programming, Python `inspect`). The `brain/cognition/reflection/`
  and `introspection/` trees can keep their names; only fix copy that reads as
  "soul-searching" rather than "the system inspects its own state."
- **`heartbeat` / `pulse`** — normal infrastructure liveness vocabulary. Keep.
- **`watchdog`** (`watchdogs.py`) — standard. Keep.
- **`world_model`, `system_presence`, `setpoint_regulation`, `trend`** — already
  engineering-neutral. Keep.
- **`reward` / `reward_signals`** — RL vocabulary, not biology. Keep.

When unsure, apply the test: does the word name a *mechanism* (keep) or borrow a
*body/mind/person* (rename)?

## More implementation cautions (second pass)

Four things the implementer must handle that are NOT simple find-replace:

1. **Scientific citations stay — verbatim.** Modules cite the research their
   design is based on (Russell & Barrett 2000 / Cannon 1932 in affect &
   homeostasis; Watson & Tellegen 1985 in mood; Pearce-Hall for the adaptive
   learning rate; Barrett 2017). These are design *provenance*, not biological
   framing — they explain why the mechanism is shaped the way it is. Keep them as
   docstrings/comments even after the surrounding identifiers go engineering. Do
   not strip a citation because it sits next to the word "affect."

2. **LLM-prompt wording is behavior, not chrome.** Prompts in `brain/behavior/speak.py`,
   `brain/cognition/wonder.py`, `self_extension.py`, `brain/loop/execute.py`,
   etc. tell the model things like "how you feel." That copy is authored, but it
   is *behaviorally load-bearing* — it shapes how Orrin describes itself and what
   it does. Do NOT bulk-swap feeling-language to mechanism-language in prompts:
   rewriting "you feel anxious" as "your threat_level signal is high" can change
   the runtime's self-description and outputs. Treat prompt edits as behavior
   changes — make them deliberately and re-run the behavior eval, separate from
   the UI/identifier rename.

3. **Log strings become persisted data once written.** `log_private`/`log_activity`
   text lands in `conscious_stream.json`, `reflection_log.json`, etc. Renaming a
   log message only changes *future* entries; old entries keep their original
   wording as verbatim history. So: don't rewrite existing logs, and don't expect
   a post-rename `grep` of historical data to come back clean — that residue is
   data, not a leak.

4. **Function-name renames break learned data too.** `emotion_function_map.json`
   keys learned weights on **function-name strings** (`look_outward`,
   `assess_goal_progress`, …); bandit arms and `meta_rules.json` do the same. If
   any function is renamed during Phase 3, its string references in these stores
   must be migrated in the same commit or the learning silently resets. Prefer
   not renaming public function names at all unless they are themselves
   biological.

## Phase 0 — Back up before touching anything

The user asked specifically for a strong backup. Do all of this before Phase 1:

1. **Land or stash current work.** The tree currently has uncommitted changes;
   get to a clean, committed state on a dedicated branch
   (`analogue-removal`).
2. **Annotated safety tag** at the pre-migration commit:
   `git tag -a pre-analogue-removal -m "snapshot before biological->engineering switch"`.
3. **Out-of-tree git bundle** (survives a broken repo):
   `git bundle create ../orrin-pre-analogue-removal.bundle --all`.
4. **Data snapshot.** Tar `brain/data/` and `data/` (the persisted state) to an
   external path, since Phase 4 is the only phase that could corrupt them and we
   want a known-good restore point regardless.
5. **Green baseline.** Record that `make verify` and `cd frontend && npm run build`
   both pass *before* the migration, so any later red is attributable.

Rollback at any point: `git reset --hard pre-analogue-removal` (code) and
restore the data tar (state). Each later phase also lands as its own
independently-revertable commit/PR.

## Phase 1 — Collapse the UI to one language (highest visible impact, lowest risk)

Goal: the biological dialect disappears from the UI; engineering copy is the
only copy; the toggle is gone.

Files (from the wiring scan):
- `frontend/src/lib/lexicon.ts` — collapse each `{ bio, eng }` entry to the
  `eng` string; drop `LexMode`, `getLexMode`, `setLexMode`, `useLexicon`'s mode
  switching and the `tip` glossary. Keep `lex(id)`/`LexText` as a thin
  string lookup so call sites don't all have to change at once.
- `frontend/src/lib/thoughts.ts` — remove the bio/eng `Dialect` branching; keep
  the engineering thought line only.
- `frontend/src/components/Header.tsx` — remove the Biological/Engineering toggle.
- `frontend/src/pages/settings/LanguageSection.tsx` — remove the dialect chooser
  (or repurpose the section; do not leave a dead control).
- `frontend/src/components/FirstWake.tsx` — remove the "As a mind / As a machine"
  choice; lead with the runtime description.
- Hardcoded leaks to rewrite per the Term Map (known offenders): `Face.tsx`,
  `Brain.tsx`, `Cognition.tsx`, `Life.tsx`, `Memory.tsx`, `Learning.tsx`,
  `Watch.tsx`, `DeathScreen.tsx`, `NarrativeStatusCard.tsx`.
- `Lex.tsx`, `AffectRings.tsx`, `CognitiveSphere.tsx`, `ConsciousnessPanel.tsx`
  and the other `brain/` panels — drop `useLexicon` mode usage; titles/subtitles
  resolve to the engineering string.
- `localStorage` key `orrin.terminology.v1` — stop reading/writing it. Leave the
  key abandoned (harmless) rather than migrating.

Rule preserved from the old plan: **translate the chrome, never the mind's
output.** Orrin-generated speech, goal titles, memory summaries, log lines, and
thought records still render verbatim — even if an older record contains the
word "valence." We are renaming authored copy, not rewriting history.

Component **file** renames (e.g. `AffectRings.tsx` → `ControlSignalRings.tsx`,
`ConsciousnessPanel.tsx` → `AttentionPanel.tsx`, `DreamsPanel.tsx` →
`IdleConsolidationPanel.tsx`) are optional polish — do them in Phase 3 with the
code renames, not here, to keep this phase a pure copy change.

Acceptance: every visible string matches the engineering column; no toggle
exists; `npm run typecheck && npm run lint && npm run build` green; screenshots
of Face/Brain/Life/Cognition/Memory/Learning/Settings show no biological copy.

## Phase 2 — User- and company-facing docs

- `README.md`, `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/CONFIGURATION.md`
  lead with the runtime framing.
- Archive `ENGINEERING_FRAMING_PLAN_2026-06-23.md` (superseded).
- Keep the engineering positioning sentence from the old plan as the canonical
  one-liner. Historical run notes and dated proposals under `docs/.../archive/`
  are left as-is (they are a record, not live copy).

Acceptance: a new reader hitting README/ARCHITECTURE sees only engineering
framing; no doc still pitches Orrin primarily as a "mind/organism."

## Phase 3 — Rename code internals (the bulk; do it concept-by-concept)

Do NOT do one giant find-replace. Take one concept at a time, fully, with the
import graph and tests updated in the same commit, then `make verify` green
before the next. Suggested order (low blast-radius first):

1. **Neurotransmitter terms** (dopamine 8, ACh 1, Pearce-Hall 8 hits) — trivial,
   warms up the process.
2. **Metabolism** (`brain/cognition/metabolism.py`, 33 hits) → resource cadence.
3. **Mortality / lifespan / born_at-in-code** (`brain/cognition/mortality.py`,
   ~80 + 209 hits) → lifecycle. *Watch the boundary:* `born_at` as a stored key
   stays (Phase 4); only the code identifiers/comments around it change.
4. **Nervous system / interoception / body_sense** → telemetry sampler.
5. **Dreams / dreaming** (`brain/cognition/dreaming/*`, 575 hits) → idle
   consolidation.
6. **Selfhood** (`brain/cognition/selfhood/*`, 61 hits) → identity & policy.
7. **Aspirations / intrinsic goals / drives** (`drive` 1199, `aspiration` 206) →
   priority weights / standing objectives. Large; split further if needed.
8. **Consciousness** (375 + 111 hits) → attention arbitration.
9. **Reaper package** (`reaper/`) → liveness/health supervisor. Many importers;
   rename the package and fix every `from reaper...` import. `vital_floor`,
   `liveness_cycle`, `heartbeatdetector` → resource-threshold / liveness probe.
10. **Embodiment dir** (`brain/embodiment/`) → host-coupling / runtime-state
    modules. `plasticity`, `sensory_stream`, `subconscious` get engineering
    names; `world_model`/`system_presence` stay. The `embodiment` **router file**
    can be renamed but its **route paths stay frozen** (Phase 4).
11. **Will / volition** (`second_order_volition.py`, etc.) → decision/meta-policy.
12. **Emotion / mood** (`emotion` ~802) — `emotion_routing.py`, `emotion_utils.py`,
    `emotion_historian.py`, `mood.py`, `dreams_emotional_logic.py`. Rename code
    identifiers and log strings. **Stop at the persisted boundary**: serialized
    keys (`mood`, …) and data files (`emotion_*.json`, `mood_state.json`) are
    Phase 4.
13. **Affect** (2069 hits) — the largest. Rename code identifiers, functions,
    `brain/affect/` modules, and log strings. **Stop at the persisted boundary**:
    in-memory variables and function names change; serialized keys
    (`valence`/`arousal`/`homeostasis`/`mood`) and data files
    (`affect_state.json`, `affect_model.json`) do NOT — Phase 4.

Mechanics for each concept:
- Module/dir/file renames via `git mv` (e.g. `brain/affect/` →
  `brain/control_signals/`), then fix imports across `brain/`, `backend/`,
  `goals/`, `tests/`. `grep -rl old_module` to find importers.
- Identifier renames: targeted, reviewed search-replace within the concept's
  files, never repo-wide blind.
- Update `brain/data/meta_rules.json` and any registry/catalog that lists
  function names if those names change (the Cognitive Sphere reads a function
  catalog — verify it still resolves).

Acceptance per concept: `make verify` green; the concept's old biological
identifier no longer appears in code except as a frozen persisted key.

## Phase 4 — Persisted schema migration (optional, gated, last)

Only if you want the on-disk/on-wire keys themselves to be engineering words.
This is the dangerous phase; it is isolated on purpose.

- Bump a schema version in the state archive / telemetry envelope.
- Writers emit new keys; readers accept **both** old and new (read-old shim) so
  existing `brain/data` files and old backups still load.
- One-time backfill/migration script for `brain/data` and `data/`, run against
  the Phase-0 data snapshot first.
- Update the backend↔frontend telemetry contract in lockstep, or keep the
  serializer translating (preferred — then the frontend never sees the change).

Recommendation: **defer Phase 4 indefinitely** unless there is a concrete reason
to change disk keys. The presentation-boundary translation from Phase 1 already
removes the biological words from everything a human sees. Phase 4 is pure
internal hygiene with high risk and low visible payoff.

## Phase 5 — Tests

61 test files reference the biological modules. They get renamed/updated
alongside their target concept in Phase 3 (same commit), not in a separate pass —
that keeps each Phase-3 commit green. A final sweep renames test *files*
themselves (`test_affect_*` → `test_control_signals_*`) for consistency.

## Phase 6 — QA, leak sweep, sign-off

Static leak sweep (should return only frozen persisted keys, archived docs, or
verbatim runtime data):
```sh
rg -niE "consciousness|\baffect|emotion|\bmood\b|valence|arousal|homeostas|mortal|metabol|nervous|selfhood|\bdream|aspiration|volition|\bvital|embodi|reaper|\bmind\b|\bhis mind|he feels|keepsake" \
  brain backend goals frontend/src docs reaper observability \
  --glob '!**/archive/**' --glob '!**/.venv/**' --glob '!**/dist/**' --glob '!**/node_modules/**' -S
```
Expected residue: frozen keys/paths/routes (Appendices D–F), borderline-keep
terms (§ Borderline), and verbatim runtime data — nothing else.
Then:
- `make verify` (full Python gate) green.
- `cd frontend && npm run typecheck && npm run lint && npm run build` green.
- Screenshot pass on Face/Brain/Life/Cognition/Memory/Learning/Settings.
- A clean restart of the runtime that successfully loads pre-migration
  `brain/data` (proves the frozen-key boundary held).

## Risk register

| Risk | Mitigation |
| --- | --- |
| Renaming persisted keys breaks restart + backups | Frozen-key boundary; Phase 4 gated + versioned + read-old shim |
| Renaming a signal name destroys learned associations | Signal vocabulary is frozen (surface #4); translate at UI only, never as an identifier |
| Renaming a function breaks `emotion_function_map`/bandit/`meta_rules` | Don't rename non-biological function names; migrate string refs in lockstep if you must |
| Bulk-swapping prompt wording changes Orrin's behavior | Prompts are behavior, not chrome — edit deliberately + re-run behavior eval |
| Stripping citations as "biological" | Citations are design provenance — keep verbatim |
| Backend↔frontend telemetry contract drift | Translate at serializer; keep wire keys stable |
| Giant find-replace corrupts unrelated code | Concept-by-concept, reviewed, `make verify` between each |
| Function-catalog / meta_rules names go stale after rename | Update registry in the same commit; verify Cognitive Sphere resolves |
| Over-translating runtime data | Hard rule: authored copy is translated, generated data is verbatim |
| `dist/Orrin.app/...` copies look like source | They are build artifacts — ignore; rebuild, don't edit |

## Decision points (my recommendations baked in)

1. **Disk schema:** freeze it; translate at the boundary. (Phase 4 optional.) ✅ recommended
2. **Component file renames:** yes, but in Phase 3 with code, not Phase 1.
3. **`he/him` → `it`:** yes, runtime is "it"; this is part of dropping personhood framing.
4. **Old `orrin.terminology.v1` localStorage:** abandon, don't migrate.
5. **Archived dated docs / past run notes:** leave as historical record.

## Execution note

Each phase is an independently revertable commit on `analogue-removal`, behind
the `pre-analogue-removal` tag. Phases 1–2 deliver the entire visible payoff at
near-zero data risk and can ship first. Phases 3–5 are mechanical but large;
pace them concept-by-concept. Phase 4 is opt-in and should probably stay unbuilt.

---

## Appendix A — Biologically-named Python modules (rename targets)

```
brain/affect/                         (33 files — affect_*, homeostasis, appraisal, setpoints, regulation, …)
brain/cognition/metabolism.py
brain/cognition/mortality.py
brain/cognition/interoception.py
brain/cognition/host_interoception.py
brain/cognition/body_sense.py
brain/cognition/intrinsic_aspirations.py
brain/cognition/aspiration_scoreboard.py
brain/cognition/dreaming/            (compose, dream_cycle, dream_symbolic, episode_replay, semantic_extractor)
brain/cognition/selfhood/            (autobiography, identity, relationships, tensions, ethics, values_check, …)
brain/cognition/mood.py
brain/cognition/emotion_routing.py
brain/utils/emotion_utils.py
brain/peers/emotion_historian.py
brain/embodiment/                     (drive_engine, plasticity, sensory_stream, subconscious, social_presence, system_presence, setpoint_regulation, world_model)
brain/motivation/drive.py
brain/eval/drive_expectations.py
brain/symbolic/symbolic_dream.py
brain/symbolic/embodied_actions.py
brain/think/consciousness_trigger.py
brain/think/think_utils/dreams_emotional_logic.py
brain/utils/affect_utils.py
observability/nervous_system.py
reaper/                               (reaper, lifespan, liveness_cycle, heartbeatdetector, vital_floor, vital_floor_calibration, no_goals)
backend/server/routers/embodiment.py  (router FILE renameable; route PATHS frozen)
```
NOTE: exclude `.venv/` and `dist/` — those are third-party / build artifacts,
never edited by hand. Borderline-keep modules (`reflection/`, `introspection/`)
are intentionally absent from this list per § Borderline.

## Appendix E — Frozen data-file paths (do NOT rename; Phase 4 only)

```
brain/data/: affect_state.json, affect_model.json, conscious_stream.json,
  mood_state.json, emotion_drift.json, emotion_function_map.json,
  emotion_sensitivity.json, dream_log.json, symbolic_dream_log.json,
  autobiography.json, body_sense.json, body_bands.json, body_bands_dream.json,
  body_host_bands.json, interoceptive_model.json, introspection_trust.json,
  lifespan.json, self_model.json, symbolic_self_model.json,
  self_belief_revisions.json, self_improvement_log.json,
  reflection_log.json, reflection_stats.json, neutral_reflection_count.json,
  drive_aspiration_credit.json
data/: alive_brain_state.json
```

## Appendix F — Frozen API route paths (do NOT rename; lockstep Phase 4 only)

```
/affect   /consciousness   /dreams   /drives   /self   /vitals
/life   /lifecycle   + the embodiment router mount
```

## Appendix B — Term frequency (code only: *.py/*.ts/*.tsx, excl. node_modules)

```
brain 4549   affect 2069   drive 1199   valence 409   conscious 375   mind 375
felt 356      dream 575     body 580     lifespan 209  aspiration 206  homeostas 125
consciousness 111  mortal 80  neuro 66  selfhood 61  arousal 62  metabol 33
nervous 9  dopamine 8  pearce 8  acetylcholine 1
```

## Appendix C — Frontend dialect wiring (Phase 1 surface)

```
lib/lexicon.ts, lib/thoughts.ts, components/Header.tsx, components/FirstWake.tsx,
components/brain/Lex.tsx, AffectRings.tsx, CognitiveSphere.tsx, ConsciousnessPanel.tsx,
components/face/NarrativeStatusCard.tsx,
pages/Brain.tsx, Cognition.tsx, Life.tsx, Memory.tsx, Watch.tsx,
pages/settings/LanguageSection.tsx
localStorage key: orrin.terminology.v1
```

## Appendix D — Frozen persisted keys (do NOT rename in place; Phase 4 only)

```
valence (~18.9k)  homeostasis (~18.9k)  arousal (~17.6k)  mood (~13.4k)
affect, felt_true/felt_*, born_at        + telemetry fields in backend/server/routers/*

Plus the 23-name SIGNAL VOCABULARY (also learned in emotion_function_map.json):
positive_valence negative_valence expected_gain threat_level risk_estimate
confidence boldness motivation impasse_signal stagnation_signal uncertainty
conflict_signal rejection_signal social_deficit exploration_drive wonder surprise
compassion melancholy jealousy contentment vitality  (+ reflective/analytical modes)
```
