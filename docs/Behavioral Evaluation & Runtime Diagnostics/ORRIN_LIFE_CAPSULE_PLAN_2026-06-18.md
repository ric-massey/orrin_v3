# The Orrin Life Capsule — Seeing One Run, Whole

*Design report — 2026-06-18. Brief: make it easy to see what Orrin is doing and has
done — for **one run** (no A/B comparison needed), accessible from **both the codebase
and the UI**, with the data **pre-split so an LLM can immediately problem-solve, spot
issues, and see what he made**, and packaged into **one comprehensible file** rather than
a pile of logs.*

*This supersedes the earlier observatory sketch. The shift: stop thinking "query layer
over scattered files," start thinking **"one self-describing evidence capsule per run."**
The analysis engine still exists — but it is the **builder** that fills the capsule, and
the capsule is the product.*

*All file names, formats, caps, and counts below were read off the live `brain/data/`
tree on 2026-06-18 (cycle ≈10,300, a ~9.4-hour run), and all "connect to existing code"
claims were verified against the current source.*

---

## Addendum (deeper data pass) — what a first survey missed

*A second, deeper pass over the data corrected three load-bearing assumptions in the
original draft. They're folded into the sections below, but called out here because they
change the build, not just the prose.*

1. **The richest behavioral record is a tagged plain-text stream, not the JSON events.**
   `activity_log.txt` + its `rotated/` archive carry **40+ semantic tags** that already
   function as an event taxonomy: `[inner_loop_sym]` ×24.5k, `[analogy]` ×16k,
   `[symbolic_search]` ×14k, `[router]`, `[intrinsic]`, `[pursue_goal]`,
   `[stagnation_signal]`, `[dream]`, and — decisively — `[leave_note]` ×533,
   `[express_to_user]` ×538, `[web_research]` ×321. **The productive/communicative
   "what did he make" record lives here**, in plain text, parseable by tag.

2. **`tools_used` is dead and the action rate is ~1%.** Across all 3,000 `DECISION`
   events, `tools_used` is empty **100%** of the time and only **29 (~1%)** are actions.
   So `artifacts.csv` must be sourced from the activity-log tags (point 1), **not** from
   `tools_used`. The ~1% action rate is itself a headline run finding.

3. **Do not embed the whole raw mind — it's a size *and* privacy mistake.** The mind
   contains `native_lm.pt` = **42 MB of model weights** (no analytic value) and
   `private_thoughts.txt` (1.6 MB live + ~30 MB rotated) — the most sensitive content in
   the system. The existing `diagnostics.py` exporter *deliberately excludes*
   private_thoughts and the conscious stream; a blanket `mind_archive` embed would violate
   that posture and produce a ~150 MB capsule dominated by a binary blob. **`raw/` must be
   selective** (exclude model weights; gate private_thoughts to local-only / strip for
   share), reusing the diagnostics allowlist.

*Also newly accounted for: a full **log-rotation system** (`brain/utils/log.py`: live files
trim to the last 500 KB, history accrues in `rotated/`, ~50 MB / 35 files — the same
"live file undercounts, archive holds truth" trap as the JSON caps); the **daemon WAL
trees** (`data/goals/wal.log`, `data/memory/wal/{events,items}.jsonl`) as the authoritative
goal/memory event source; and the live UI's already-assembled `hub.state` + history
snapshot, tappable for a "run so far" capsule. `observability/metrics.py` was confirmed
**liveness/host-only** — no behavioral-metric duplication.*

---

## TL;DR

- **One run → one file.** Each run seals into a single
  `orrin_life_capsule_<RUNID>.orrinlife.zip`: raw data preserved untouched, plus cleaned
  tables, a queryable SQLite DB, computed metrics, auto-generated charts, a **claims
  ledger**, and an **LLM-ready bundle**. Hand someone the file and say *"open
  EXECUTIVE_SUMMARY.md, then claims_report.md, then query orrin_life.sqlite"* — they
  understand the run **without running Orrin**.

- **Raw stays raw; cleaned becomes tables; interpretation becomes claims.** That
  separation is the whole point — it's what makes the evidence trustworthy and what lets
  an LLM reason without reverse-engineering the codebase. Raw never gets edited; every
  derived artifact traces back to it via `file_hashes.csv` + `provenance.json`.

- **It is a third sibling of exporters we already ship.** Orrin already has
  `mind_archive.py` → `.orrindmind` (the **mind**, for restore) and `diagnostics.py` →
  ops-log bundle (operational logs, allowlisted, *never* memory). The Life Capsule is the
  **evidence** export. It reuses their exact plumbing: the streaming-zip endpoint pattern
  (`/api/diagnostics`, `/api/mind/export`), the owner-guard `_authorize_control`, the
  native file-dialog bridge, the schema-version tag, and `mind_archive.export_bytes()` to
  embed the raw mind. **Not an outside add-on — a new organ wired into existing ones.**

- **Built automatically at the moments that matter:** normal shutdown (`atexit`),
  **crash recovery on next boot** (the reaper already knows the last shutdown was unclean
  via `runstate.clean`), and **end-of-life** (hooked into `mortality._write_final_thoughts`,
  which already runs at the deadline) — plus rolling periodic checkpoints so a hard crash
  never loses the run.

- **Two original additions worth calling out:** (1) a **within-run before→after** — first
  quartile of cycles vs last quartile, inside the *same* capsule — gives the README's
  "before→after→because" proof from a **single run**, exactly fitting the "we only need A"
  constraint; (2) an **auto-extracted "windows of interest"** bundle so the LLM reads ~50
  decisive cycles, not 10,300.

- **One UI surface:** a **Capsule** room (or a panel in the existing **Life**/**Brain**
  rooms) that lists capsules, renders the executive summary + figures inline, exposes a
  read-only SQL box over the embedded DB, and offers **Download capsule** and **Copy LLM
  context** buttons. Same backend pattern as the diagnostics download already in `app.py`.

---

## Part I — The design decision: one capsule, not a query farm

The earlier plan proposed a persistent SQLite "observatory" you query across runs and an
A-vs-B comparison engine. Per the brief, that's more than needed and the wrong shape. The
better shape is a **per-run evidence capsule**, because:

- **It's portable and self-describing.** A `.zip` you can email, archive, or drop into a
  PR. No tool, no server, no codebase needed to read it — the structure *is* the
  documentation.
- **It matches what Orrin already does at run boundaries.** Orrin has a mortality clock,
  a reaper that detects unclean shutdown, persistent state, and a mind-export format. A
  capsule sealed at shutdown/crash/death is the natural artifact of a life that ended.
- **A single run is enough.** We don't need run B. A run's *own* early-vs-late slice
  (Part VII) shows behavior change; its claims ledger shows what's supported. Cross-run
  comparison becomes trivial later (two capsules, same schema) but is explicitly **not**
  the v1 goal.

So: the analysis engine from the prior plan (normalize the scattered streams, classify
actions, audit signal→action) is retained — but it runs **once per run, into a capsule**,
and the capsule is what humans, scripts, and LLMs consume.

---

## Part II — How it connects to what already exists

This is the part that keeps it from being a bolt-on. Verified against current source:

| Existing piece | What it gives the capsule |
|---|---|
| `brain/utils/mind_archive.py` (`export_bytes`, `export_filename`, `build_meta`) | Optional **local-only** raw layer: a full importable mind. **Not** the default for a shareable capsule (see Addendum #3 — it carries `native_lm.pt` 42 MB + private thoughts). The share build uses a *selective* raw set built from the diagnostics allowlist instead. |
| `brain/utils/diagnostics.py` (allowlist, `_tail`, `build_manifest`, `_state_tag`) | The privacy allowlist + boot/death/crash state tag are already written; reuse the allowlist logic for `privacy/` and the state tag for `provenance.json`. |
| `backend/server/app.py` `/api/diagnostics`, `/api/mind/export` | The capsule download endpoint is a **copy** of these: `_authorize_control(request)` → `Response(zip, media_type="application/zip", Content-Disposition)`. Owner-guarded, opt-in, no silent telemetry — same contract. |
| `backend/server/bridge.py` `export_mind` native dialog | Native "Save capsule…" dialog in the desktop app via the same bridge method. |
| `brain/cognition/mortality.py` `_write_final_thoughts`, `mark_final_thoughts_written`, terminal phase | The end-of-life hook point, and the source of `FINAL_THOUGHTS.md` (kept **separate** from the objective evidence — Part VIII). |
| `reaper/` + `runstate.json` (`clean`, `started_at`) | Crash detection: if the last `runstate.clean` was false on boot, build a crash-recovery capsule from the previous run's data before it's overwritten. |
| `brain/utils/schema_migration.py` (schema-version spine) | Stamp a `capsule_schema_version` so capsules stay machine-readable across builds, same way state is versioned. |

**The three exports, clearly separated** (so they don't blur):

- `.orrindmind` — *the mind*, for **restore/transplant**. Full state, importable.
- diagnostics bundle — *operational logs + state tag*, for **debugging a malfunction**.
  Allowlisted; deliberately excludes memory and the conscious stream.
- `.orrinlife` capsule — *the evidence*, for **understanding and judging a run**. Raw +
  tables + DB + metrics + claims + LLM bundle. This is the new thing.

---

## Part III — Capsule anatomy

My structure (judgment, not a copy): the organizing rule is **raw → cleaned → derived →
interpreted**, each layer downstream-only.

```
orrin_life_capsule_<RUNID>/
  README.md                      # what this is + how to read it (the 4 entry points)
  EXECUTIVE_SUMMARY.md           # plain-English: what happened, in 2 minutes (human entry)
  manifest.json                  # run_id, capsule_schema_version, build reason, contents map
  provenance.json                # git SHA, resolved ORRIN_* flags, LLM provider/state, lifespan, host
  file_hashes.csv                # sha256 of every file — tamper-evident, traces derived→raw

  raw/                           # NEVER edited; selective (no model weights; private thoughts gated)
    selected_streams/            # verbatim copies of the streams the tables came from
    orrin_mind.orrindmind        # LOCAL builds only — full importable mind (excluded from --share)

  database/
    orrin_life.sqlite            # the one file to query (Part IV) — the analytic core

  tables/                        # cleaned, normalized, joinable CSVs (mirror the DB)
    cycles.csv  decisions.csv  rewards.csv  affect.csv  emotions.csv
    goals.csv  memory_events.csv  behavior_changes.csv  signals.csv
    artifacts.csv  errors.csv  host_resources.csv  peers.csv

  metrics/                       # computed JSON — no prose, just numbers
    run_summary.json  action_distribution.json  reward_summary.json
    rut_summary.json  goal_summary.json  memory_summary.json
    signal_followthrough.json  anomaly_summary.json  early_vs_late.json

  figures/                       # auto-rendered PNGs (optional dep; skipped if absent)
    cycle_timeline.png  action_distribution.png  repeat_rate_over_time.png
    reward_over_time.png  stagnation_vs_repetition.png  goal_progress.png

  claims/                        # interpretation, evidence-linked (Part V)
    claims_ledger.json  claims_report.md

  llm/                           # curated, token-budgeted (Part VI)
    LLM_README.md  llm_context_summary.md  llm_index.json
    claim_cards.jsonl  important_windows.jsonl  trace_samples.jsonl

  privacy/
    redaction_report.json  sensitive_paths_removed.txt

  FINAL_THOUGHTS.md              # only on end-of-life — Orrin's own voice (subjective)
  FINAL_EVIDENCE_REPORT.md       # only on end-of-life — the analyzer's voice (objective)
```

---

## Part IV — The analytic core: `orrin_life.sqlite`

One file anyone can open — Python, an LLM tool, `sqlite3`, a researcher. It's the prior
plan's normalized frame, now materialized into a relational schema. The hard work it does
is the **join we currently can't do by hand**: the streams use four time encodings
(`events` ISO + `tick`; `telemetry`/`trace`/`ground_truth` float epoch; `trace` has *no*
cycle at all) and there's **no run-id in the data**. The builder reconciles these once.

Tables (keyed on `cycle` where present, nearest-`ts` otherwise):

- **`cycles`** — the spine: `cycle, ts, lane, is_action, choice, action_class`.
- **`decisions`** — `cycle, choice, candidate_count, top_candidates, ranked(json),
  weights(json), features_on(json)` (from `events.jsonl` + `cognition_history.json`).
- **`rewards`** — `cycle, reward_signal, novelty, acceptance_passed`.
- **`affect`** — `cycle, valence, arousal, homeostasis, energy, fatigue, motivation,
  confidence, curiosity, distress, stability, allostatic_load` (from
  `telemetry_archive.jsonl`, the *full* 10k-row series — not the 240-cap copy).
- **`emotions`** — `cycle, dominant_affect, stagnation_signal, impasse_signal,
  threat_level, …` (from `trace.jsonl`).
- **`signals`** — derived: each detected `rut / goal_avoidance / stagnation / threat /
  user_input / host_distress` with onset cycle.
- **`behavior_changes`** — armed corrections + (new) `outcome`.
- **`goals`, `memory_events`, `artifacts`, `errors`, `host_resources`, `peers`** — the
  rest, so "what did he make / remember / fail at / who watched him" are one query each.

This makes Orrin's life **queryable**:

```sql
-- what did he do most?
SELECT choice, action_class, COUNT(*) n FROM cycles GROUP BY choice ORDER BY n DESC;

-- did productive action ever follow a goal_avoidance signal, and did the signal relax?
SELECT s.onset_cycle, c.action_class, e.stagnation_signal
FROM signals s JOIN cycles c USING(cycle) JOIN emotions e USING(cycle)
WHERE s.kind='goal_avoidance' AND c.cycle BETWEEN s.onset_cycle AND s.onset_cycle+25;
```

CSV mirrors live in `tables/` for anyone who'd rather not touch SQL; the DB is the source
of truth and the CSVs are exported from it (so they can't disagree).

### The action-class taxonomy (the audit lens)

Every `choice` is tagged with one class so behavior is summarizable: `reflex,
regulatory, orienting, communicative, productive, maintenance, metacognitive,
failed/blocked`. Two seeds, not one: the `_OUTWARD_HIGH/MED/LOW` tiers in
`brain/think/think_utils/select_function.py`, **and the 40+ `[tag]`s already emitted into
`activity_log.txt`** (`[leave_note]`, `[express_to_user]`, `[web_research]`, `[dream]`,
`[pursue_goal]`, `[stagnation_signal]`, …), which are a de-facto taxonomy in plain text
(Addendum #1). Mapped to the classes in one authoritative file. This is the lens
`SIGNAL_TO_ACTION_AUDIT_2026-06-18.md` (R1) said does not yet exist.

**`artifacts` is parsed from the activity-log tags, not `tools_used`** — the latter is
empty in 100% of events (Addendum #2). Outward acts are exactly the `[leave_note]` /
`[express_to_user]` / `[web_research]` / file-write tag lines, deduped by content hash.

---

## Part V — The claims ledger (what makes it credible)

The capsule doesn't assert "Orrin learns." It organizes **evidence around claims**, each
with status, supporting data, counter-evidence, confidence, and the next test. Each
**issue detector becomes a claim generator**:

```json
{
  "claim_id": "rut_detection_001",
  "claim": "Orrin entered a repeated-action rut and his stagnation machinery responded.",
  "status": "candidate_supported",
  "evidence": ["tables/decisions.csv", "tables/signals.csv", "metrics/rut_summary.json"],
  "metrics": {"repeat_rate": 0.61, "longest_same_action_streak": 6,
              "signal_followthrough_rate": 0.08},
  "counter_evidence": ["Corrective was armed but preempted by survival 212x (closed loop ran open)."],
  "confidence": "medium",
  "next_test": "Check action_class distribution in the 25 cycles after each stagnation onset."
}
```

Status vocabulary: `candidate_supported / supported / insufficient_evidence /
refuted`. The detectors that produce these (carried over from the prior plan, now writing
claims): **closed-loop-running-open** (corrective armed but survival/threat preempts for
N cycles — the exact 2026-06-14 failure), **silenced-monitor** (a monitor whose influence
decays to zero / a peer with empty interaction history — the idle-monitor `0.90→0.48`
decay), **redundant-output** (artifact dedupe ratio — the "100 near-duplicate notes"),
**reward-collapse** (reward signal → noise), **distribution-collapse** (action entropy
falls). `claims_report.md` renders the ledger as the prose a human writes today.

---

## Part VI — The LLM bundle (pre-split for problem-solving)

An LLM must **not** be handed 76 MB of raw logs. `llm/` is a curated, **token-budgeted**
(hard ceiling, e.g. ≤ 200 KB) view that always fits a context window:

- **`llm_context_summary.md`** — the framing the model needs *before* reasoning: what
  Orrin is (symbolic-first prototype), and the guardrails the README itself demands — *do
  not assume consciousness, do not infer beyond the data, prefer metrics over anecdotes,
  separate observed behavior from interpretation, use the claims ledger.*
- **`llm_index.json`** — a map: "to answer X, read table Y / metric Z." So the model
  navigates instead of grepping.
- **`claim_cards.jsonl`** — one self-contained Q/A chunk per question, each naming its
  supporting tables/metrics and its **limitations** (so the model can't overclaim):

  ```json
  {"claim_id":"action_dist_001","question":"What did Orrin do most?",
   "answer":"Most-selected: search_own_files (orienting class).",
   "supporting":["tables/decisions.csv","metrics/action_distribution.json"],
   "limitations":"Frequency is not usefulness; says nothing about reward."}
  ```
- **`important_windows.jsonl`** — *my addition*: the builder auto-detects the most
  informative cycle windows (rut onset, reward collapse, first user turn, host distress,
  the early/late slices) and bundles just those ~50-cycle trace slices. The LLM reads what
  matters, not 10,300 cycles.
- **`trace_samples.jsonl`** — a small representative sample of full-detail cycles for
  grounding.

### Privacy first (grounded in a real finding)

Two concrete sensitivities, both found in the data: (1) `world_perception.json` is Orrin's
**own file tree with absolute user paths** (`/Users/ricmassey/orrin_v3/...`); (2)
`private_thoughts.txt` (1.6 MB live + ~30 MB rotated) is the **most sensitive content in
the system**, and the existing `diagnostics.py` exporter pointedly **excludes** it and the
conscious stream (Addendum #3). So `privacy/` reuses that exact allowlist discipline:
scrub absolute home paths, and **omit private thoughts / conscious stream / private memory
from any `--share` build entirely** (they survive only in a `--local` build's `raw/`).
`native_lm.pt` (42 MB model weights) is excluded from `raw/` in both modes — referenced by
hash in `provenance.json`, never embedded. Everything removed is recorded in
`redaction_report.json`. A `--share` build is strictly a subset of a `--local` build.

---

## Part VII — Before→after from a *single* run (the "because")

The README's flagship proof is *before → after → because*. Since we only need run A, the
builder computes it **within the run**: split cycles into first-quartile ("before") and
last-quartile ("after") and diff them in `metrics/early_vs_late.json`:

```
                       early 25%   late 25%    Δ
action entropy            1.62        2.20    +0.58
productive %               1.8%        9.1%   +7.3pp
mean reward_signal         0.12        0.24   +0.12
rut episodes / 1k cyc      8.0         2.1    -5.9
goal_avoidance relief     6%          54%    +48pp
```

The **"because"** is the behavior-change ledger joined to the slice: which corrective
mutations armed (and, with the Part IX `outcome` field, *landed*) between early and late.
This delivers the demo's structure from one life — no second run required — and a real
two-capsule comparison stays trivially available later because the schema is fixed.

---

## Part VIII — In the codebase: the builder organ

A first-class subsystem, `brain/evidence/life_capsule.py` (the *Autopsy Engine* /
*Life Recorder*), with one public entry:

```python
build_life_capsule(reason: str) -> Path   # reason ∈ {normal_shutdown, crash_recovery,
                                          #           mortality_end_of_life, checkpoint, manual}
```

Build flow (atomic): freeze writes if possible → copy the **selective** raw set
(streams + `rotated/` history; model weights excluded, private thoughts gated by build
mode) → normalize tables (incl. parsing the `activity_log` tag stream) → build SQLite →
compute metrics →
render figures (skipped if matplotlib absent) → generate claims → write human +
LLM summaries → hash everything → zip into `.building/<run_id>/` → **atomic rename** to
`exports/life_capsules/orrin_life_capsule_<RUNID>.orrinlife.zip` only on success.

**Hook points (all into existing code):**

- **Normal shutdown:** `atexit.register(lambda: build_life_capsule("normal_shutdown"))`
  in `main.py` / `ORRIN_loop.py`.
- **Crash recovery:** on boot, if the prior `runstate.clean` was false, build
  `crash_recovery` from the previous data *before* it's overwritten (reaper/startup
  already reads `runstate`).
- **End-of-life:** call `build_life_capsule("mortality_end_of_life")` alongside the
  existing `mortality._write_final_thoughts()` at the terminal deadline. `FINAL_THOUGHTS.md`
  (Orrin's voice) and `FINAL_EVIDENCE_REPORT.md` (analyzer's voice) are written as **two
  separate files** — never mixed, so the subjective narrative can't contaminate the
  objective evidence.
- **Don't rely on shutdown alone** (a hard crash skips `atexit`): a rolling **checkpoint**
  every ~1 h writes a partial capsule to `exports/life_capsules/checkpoints/`, so even a
  sudden death leaves analyzable evidence. Final/crash/checkpoint live in separate subdirs.

A thin **rolling-append** option (the loop appends normalized rows to a `current/` working
set in real time) makes "the run so far" instantly sealable and keeps checkpoint cost near
zero — sealing = compute metrics/figures/claims + zip.

---

## Part IX — In the UI: one Capsule surface

Mirror the existing diagnostics-download pattern exactly:

- **Backend:** `GET /api/life/capsule?run=latest` → `_authorize_control(request)` →
  stream the `.orrinlife.zip` (`media_type="application/zip"`, `Content-Disposition`).
  `GET /api/life/capsules` lists available capsules; `GET /api/life/capsule/{id}/summary`
  returns the executive summary JSON for inline rendering. Native desktop "Save capsule…"
  via the `bridge.py` file-dialog method, same as `export_mind`.
- **Frontend:** a **Capsule** panel (its own room, or a card in the existing **Life** /
  **Brain** rooms). It lists capsules with build reason + run length, renders
  `EXECUTIVE_SUMMARY.md` and the figures inline, shows the **claims ledger** as a
  status-colored table, and offers two buttons: **Download capsule** and **Copy LLM
  context** (copies `llm/llm_context_summary.md` + `claim_cards.jsonl` to clipboard so you
  can paste a run straight into any LLM). Optional: a read-only SQL box over the embedded
  DB (sql.js client-side, or a guarded `/api/life/query` server-side) for ad-hoc questions.

The bio↔eng dialect toggle already in the UI applies to the rendered summary, consistent
with every other surface.

---

## Part X — Save-side prerequisites (small, single-run scope)

The capsule can be built from today's data via heuristic run segmentation (split on
`ts` gaps / `cycle` resets, cross-checked with `runstate.started_at`). These additions
make it **trustworthy** rather than reconstructed — and they're the minimum, since we no
longer need cross-run identity for v1:

1. **A `run_id` minted at boot + a `provenance` snapshot** (git SHA, resolved `ORRIN_*`
   flags, LLM provider/state, lifespan, host) so the capsule's `provenance.json` is
   recorded, not guessed. This is also the only missing input for the within-run "because".
2. **Emit `reason` as real JSON (uncapped)** in `DECISION` events instead of the current
   truncated string — the structured "why" currently survives only in the 500-cap
   `cognition_history.json`.
3. **An `outcome` field on behavior changes** (filled K cycles later: `signal_delta`,
   `expected_class_rose`, `preempted_by`) — turns "armed" into "landed/worked", which the
   claims ledger and Part VII "because" both need.
4. **A thin `artifacts.jsonl` ledger** (one row per outward act + `dedupe_hash`) — makes
   "what did he make" and the redundancy claim countable. `tools_used` is almost always
   empty today, so productive output is currently invisible.

All additive and fail-safe: if the builder never runs, the loop is unaffected.

---

## Part XI — Other ideas worth folding in

- **Content-addressed & verifiable.** `file_hashes.csv` + a top-level capsule hash make it
  tamper-evident and let a reviewer confirm the tables really derive from the raw.
- **Deterministic rebuild.** Same `raw/` → same `tables/` and `metrics/`. The builder is a
  pure function of the raw layer, so anyone can reproduce the derived artifacts and check
  our work.
- **Capsule schema version.** Stamp `capsule_schema_version` (via the existing
  `schema_migration` spine) so future tools and LLMs know the layout and old capsules stay
  readable.
- **Suggested-analysis-order in `README.md`.** Encode the sensible order — run integrity →
  action behavior → reward → goals → memory → rut→detection→change — so a fresh analyst (or
  LLM) doesn't start with theory before confirming the run even ran cleanly.
- **"Run integrity" first metric.** `run_summary.json` leads with did-it-actually-run:
  cycle count, wall-clock span, timestamp sanity, crash markers, log continuity. Cheap, and
  it stops every downstream conclusion built on a broken run.
- **Anomaly summary as a triage list.** `anomaly_summary.json` is the detectors' findings
  ranked by severity — the first thing to read when something looks wrong.

---

## Part XII — Phased implementation

| Phase | Scope | Outcome |
|---|---|---|
| **0 — builder + raw/tables/DB** | `life_capsule.py`: heuristic run segmentation, normalize streams → SQLite + CSVs, embed raw via `mind_archive`. `reason="manual"` only. | A real `.orrinlife.zip` from **today's** data, no loop changes. The single queryable file exists. |
| **1 — metrics + claims + LLM bundle** | taxonomy, detectors→claims, `metrics/`, `llm/`, `early_vs_late`, privacy redaction. | The capsule becomes self-interpreting and LLM-ready. |
| **2 — hooks** | `atexit` shutdown, crash-recovery on boot, mortality end-of-life, periodic checkpoints, atomic build. | Capsules appear automatically at the moments that matter; no manual step. |
| **3 — UI + save-side** | `/api/life/*` endpoints + Capsule panel + native dialog; Part X stamps (run_id, json reason, outcome, artifacts). | One-click view/download in app; capsules become authoritative rather than reconstructed. |
| **4 — figures + polish** | matplotlib charts, FINAL_THOUGHTS/FINAL_EVIDENCE split, share-vs-local redaction modes. | Hand-to-anyone quality. |

Phase 0 alone replaces the hand-written per-run analysis scripts with one reproducible
artifact — a good proof of value before touching the loop or UI.

---

## Appendix — stream inventory (live, 2026-06-18, cycle ≈10,300)

- **Trees:** `brain/data/` (~230 files, 143 MB, "the mind") + `data/` (goals/memory WAL +
  snapshots).
- **Per-cycle spine the tables come from:** `events.jsonl` (3k `DECISION`, ISO+`tick`),
  `cognition_history.json` (500, the structured "why"), `telemetry_history.json` (240) /
  `telemetry_archive.jsonl` (10,290 rows, 9.4 h — the full series), `trace.jsonl` (26 MB,
  full emotion vector, float-`ts` only, **no cycle**), `behavior_changes.json` (250),
  `ground_truth.jsonl`.
- **Tagged plain-text behavioral logs (the real "what did he do" record — Addendum #1):**
  `activity_log.txt` + `rotated/activity_log.*` (40+ `[tag]` event types, ~24 MB of
  history); `private_thoughts.txt` + `rotated/` (~30 MB, **redaction-critical**);
  `run_log.txt`. Rotation via `brain/utils/log.py` (live trims to 500 KB; `rotated/` holds
  the rest — read both for full history).
- **Daemon WAL trees (authoritative goals/memory events):** `data/goals/wal.log` +
  `state.jsonl` (lifecycle upsert/status), `data/memory/wal/{events,items}.jsonl`.
- **Large binaries (referenced, never embedded):** `brain/data/language/native_lm.pt`
  (42 MB model weights).
- **Delayed-learning / symbolic:** `evaluator_wal.jsonl`, `rule_firings.jsonl`,
  `memory_graph.jsonl` (5 MB), `habituation.json` (609 KB), `context.json` (384 KB).
- **Point-in-time stores:** `long_memory.json` (2,001 typed), `conscious_stream.json`
  (200), `monitor_verdicts.json`, `relationships.json`, `commitments.json`,
  `world_perception.json` (absolute paths — redaction target), affect/body internals.
- **Existing exporters to reuse:** `brain/utils/mind_archive.py` (`.orrindmind`),
  `brain/utils/diagnostics.py` (ops bundle + allowlist), `backend/server/app.py`
  `/api/diagnostics` & `/api/mind/export`, `backend/server/bridge.py` `export_mind`,
  `brain/cognition/mortality.py` `_write_final_thoughts`, `runstate.json` (`clean`).
- **Confirmed absent (Part X targets):** any `run_id`/boot/session concept; a per-boot
  provenance snapshot; structured (untruncated) `reason` in events; an `outcome` on
  behavior changes; a unified artifact ledger; a `cycle` key on `trace.jsonl`.

*Design report generated from runtime data on 2026-06-18. Analysis and proposal only; no
runtime code changed.*
