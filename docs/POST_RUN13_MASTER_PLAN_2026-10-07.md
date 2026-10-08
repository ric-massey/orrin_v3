# Post-Run-13 Master Plan (2026-10-07)

**Status: ACTIVE — the single to-do list after Run 13.** Drafted during Run 13 (repo
run-locked), finalized 2026-10-07 at capture with the Run 13 verdict
(`Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-10-06-run/DEMO_RUN_2026-10-06.md`).

**Governing principle (Ric, 2026-10-07): most of his memories should be about his world,
not himself** — and he should *wander* the world, not pick from lists. Every phase below
serves one of those two.

**What this is:** the single ordered list of everything still to build or verify,
assembled from a full sweep on 2026-10-07 of every live doc, the archived plans that
still had open phases, git history (several status headers are stale), and branches.
Each item links its source. **This list supersedes the open items of the plans it
names**; those plans stay as the reasoning, not the to-do list.

**Ordering rule:** dependency first, then leverage. Small independent fixes that unblock
honest measurement come before big redesigns; redesigns that share a migration are
merged into one item (§8 lists the overlaps).

---

## 1. Phase A — capture & housekeeping (tonight, 10-07)

| # | Item | Source |
|---|---|---|
| A1 | ✅ Capture + score Run 13 (done 10-07; NOT PASSED, Growth green first time) | run-analysis skill |
| A2 | ✅ `FEELING_AND_NAMING_DESIGN_2026-10-07.md` in `docs/Language & Cognition/`; pointer in `THOUGHT_OBJECT_SPEC.md` | memory `project_feeling_naming_design` |
| A3 | ✅ This plan finalized and in `docs/` | — |
| A4 | ✅ Fixed stale headers: `RUN7_FIX_PLAN` ("PROPOSED", built a63b160+bb3685a), `LIFE_AMBITION_PROPOSAL` ("PARKED", built 15b372e), `QUALITY_GROUNDING_DESIGN` ("Not started", rung 0 + ladder built), `TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN` ("proposed", `workspace_writeback.write_back` built and wired in `loop/deliberate.py`) | this sweep |
| A5 | Archive pass + `docs/README.md` "Start here" refresh + wiki sync (drift: `Backend_Telemetry`, `Face_and_Brain_UI`, `Roadmap_and_Status`) | `MASTER_STATUS_2026-10-04` §2–3 |
| A6 | Producer auto-start: `run_orrin.sh` starts/stops `RicsWebsite/projects/orrin/producer/push_status.py` with each life | memory `project_orrin_site_updates` |

## 2. Phase B — stop the bleeding (Run 14 gate-passers)

Small, mostly independent fixes from the Run 13 live deep read
(`FEELING_AND_NAMING_DESIGN` §0b). Each is "broken pipe / unopposed / misaimed" classified.

| # | Item | Class | Observable (Run 13 baseline) |
|---|---|---|---|
| B1 | **F0** — telemetry, selection logs, chunk/compaction notices, threshold alarms out of working memory (trace only) | broken pipe | WM `🧠 Chose:` = 0; self-log summaries < 10 % of LTM (79 %) |
| B2 | **F1** — `appraisal.py` appraises structured events (ledger, failures, goal steps), adds `about`; text path only for real textual input | broken pipe | appraisal no longer fed by his own alarm text; agency ≠ self on world failures |
| B3 | **Most memories about his world** (Ric's principle): LTM eviction protects world findings from self-log summaries (capped at 2,001); self-observation gets a bounded share | misaimed | world findings ≥ 25 % of LTM (2.8 % at death); self-log summaries ≤ 10 % (74 %) |
| B4 | Knowledge-graph concept extraction: no fragments, no page chrome, no own titles | broken pipe | 0 concepts like "round the sun" / "See More Results Suggestions" (25 concepts, many junk) |
| B5 | Real brake on follow-on rounds; angles don't repeat | unopposed | max round ≤ 4 (16) |
| B6 | Goal generation earns value when the research pool is thin (antagonist to starvation, not a clamp) | unopposed | WAL silence ≤ 30 min (161 min) |
| B7 | A no-op action (`research_topic` "no fresh topic") earns nothing and isn't goal service | broken pipe | research no-op rate < 20 % (98 %) |
| B8 | `decide_to_write_code` marked impossible at its `code_writer` bail-out (4th run red) | broken pipe | 0 picks while no LLM body (207) |
| B9 | Inhibition cost habituates for a repeatedly-unchosen want | unopposed | frustration pumps per hour ↓ (≈170/h overnight) |
| B10 | Breaker duty | — | fires < 10 % of cycles (~50 %) |
| B11 | Characterization re-asks over a life; a goal waiting on data yields focus | unopposed | ≥ 4 predictions/life (2); no waiting goal > 40 % focus |
| B12 | **CT-A** clock time instead of cycle time (subsumes Run 13 item 5's detector) | — | cadence-invariance test |
| B13 | **Desync root cause** (round-k follow-on minting vs the v1 tree) | broken pipe | 0 store-desync repairs (18) |
| B14 | `citing_goal_id` on every `mark_reused_path` caller (web_research, library, goal_io spec refs) | broken pipe | citer coverage 100 % (14 %) |
| B15 | Exemplar gate: self-talk on any internal tag and single-paragraph artifacts; copy veto on `source: research_topic` memos; corrupted-text check | broken pipe | 0 junk promotions (3 of 5) |
| B16 | Character stripper in the `compose_section` path ("hat is there", "ednesday") | broken pipe | 0 dropped-letter artifacts |
| B17 | Parent-value saturation guard on aspiration credit (item 11 propagation) | unopposed | no aspiration value ≥ 0.99 (self 0.9999) |
| B18 | Death-reason label: natural lifespan death recorded as such, not "operator_stop" | broken pipe | final-words reason = lifespan |
| B19 | Cherry-pick the ToM timing fix from `claude/orrin-dmn-equivalence-zzlw5q` (fast reply read the previous turn's ToM) | broken pipe | ToM computed before the reply that uses it |

**Gate:** Run 14, symbolic-only, observables above, scored per run-analysis.

## 3. Phase C — a world to wander (design first)

Merges `FEELING_AND_NAMING_DESIGN` §10 (Ric 10-07: "it shouldn't be a list"),
`ORRIN_WORLD_DESIGN_2026-07-18` §3 (internet as houses), memory `project_internet_as_world`.

| # | Item |
|---|---|
| C0 | **Write the Wandering design doc** (pages as places, links/terms/unknown words as roads, curiosity picks, trail, satiety stops; arrival as signal) |
| C1 | Keep roads: fetched pages retain links and defined terms (today discarded) |
| C2 | Wander step: curiosity-chosen next road, trail, interest-based stopping; lists become starting points only |
| C3 | World root ≠ his own repo; `_WORLD_WATCH_DIRS` populated with safe sources: `/usr/share/dict/words`, man pages, machine facts |
| C4 | Consent tiers (Ric's decision): website repo, personal folders — closed by default, opened folder by folder |

## 4. Phase D — a structured mind (one migration, not three)

Merges `FEELING_AND_NAMING_DESIGN` F2–F5, Run 11 backlog §4 T1 stages 2–4 + T2
(`RUN11_IMPLEMENTATION_PLAN` Slice 1), and `THOUGHT_OBJECT_SPEC` amendments.

| # | Item |
|---|---|
| D1 | Shared lexicon seed (10–15 core feeling words + background language; license check) + attention-gated naming via `introspection.felt_affect` |
| D2 | Vocabulary as its own semantic store: word hubs, recently-met buffer, dream consolidation; `vocabulary.json` populated (words met while wandering, C) |
| D3 | Working-memory records (feelings first, then observations/intents/findings) with a text shadow; migrate the ~12 string readers; drop the shadow; T2 world events enter as structure |
| D4 | Ric-labeling channel + miss review; labeling → `regulation.py` damping, measured |
| D5 | **The DMN branch** `claude/orrin-dmn-equivalence-zzlw5q` (Sept 27–28, ~730 lines, "Run 12.5" gate), split three ways (Ric, 2026-10-07): **(a)** ToM timing bug fix → cherry-picked in Phase B (B19); **(b)** state awareness (energy shift, felt absence, ToM misread offered only *when it shifts or persists*) → re-land with D1 naming, as structured records; **(c)** the default-mode → workspace wiring → re-land **after** B1/B3 and Phase C, so mind-wandering replays *world* memories (what he read, the wander trail) rather than his logs, and its routes can go outward (chase a loose thread, `find_unexpected_link`, imagine a next step = F2) not only to `narrative_update`/self-reflection. Today its fragments are templates ("That unfinished thing — {goal} — surfaces again") fed by self-talk |

## 5. Phase E — continuous time (after D's records exist)

`CONTINUOUS_TIME_DESIGN_2026-10-04`: CT-B.0 StateHub (single state owner) → CT-B
interruptible stream → CT-C activities with duration (+ ablation-retire clamps).
CT-A already moved to B12.

## 6. Phase F — accelerators & self-checks

| # | Item | Source |
|---|---|---|
| F1 | 2.0 `origin` field (cheap; may pull earlier, overlaps D3 provenance) | `RUN12_IMPLEMENTATION_PLAN` Layer 2 |
| F2 | 2.1 prospection / means-end in goal origination | same |
| F3 | 2.2 accelerators: passion, play, anger | same |
| F4 | 2.3 self-checks: source epistemology, self-testing, audience, counterfactual regret | same |
| F5 | 2.4 reasoning ratchet (design note) | same |
| F6 | Creativity Issue D / N2: drain-fast/recover-slow symmetry from demand-relief learning | `CREATIVITY_NOVELTY_PROPOSAL`, `RUN11_IMPLEMENTATION_PLAN` 2C |
| F7 | Creativity Issue B re-check: audit the 4 remaining `_LLM_TOOL_CALLERS` (tool-use stays, understanding migrates) | same |
| F8 | Quality grounding soundness passes on sources of good #2–5 | `QUALITY_GROUNDING_DESIGN` |

## 7. Phase G — the Predictive Core program, and evidence

| # | Item | Source |
|---|---|---|
| G1 | Predictive Core (generative-model/error loop), absorbing Grounded Cognition Phase 4B fork + Phase 5 hierarchical skills and the novelty-drive root fix | `RUN11_BACKLOG` §11, `GROUNDED_COGNITION_IMPLEMENTATION_PLAN` |
| G2 | Decay-authority sweep (affect core; deferred from Run 11 L1 task 3) | `RUN11_IMPLEMENTATION_PLAN` |
| G3 | Benchmarks B8–B18 (offline claims-vs-evidence battery) | `RUN11_BACKLOG` L4 |
| G4 | Butlin-14 experiment hooks (E1/E3/E7a run on flags today; rest need hooks) | `BUTLIN14_EXPERIMENTAL_MATRIX` |

**Verification only (no build):** Core Architecture T1.G closure (Run 13 effectively
is it; score in A1), **T0.5 exemplars (Ric authors)**, TE.0 measurements;
Companion & Presence staged verification (built 07-10, never staged); desktop builds on
real machines.

## 8. Overlaps merged (so nothing gets built twice)

| Merged item | Was in |
|---|---|
| D3 working-memory records | Feeling F4 · Run 11 T1 stages 2–4 · Run 11 T2 · Thought Object spec §5 |
| Phase C wandering | Feeling §10 · ORRIN_WORLD_DESIGN §3 · internet-as-world memory |
| G1 Predictive Core | Run 11 §11 · Grounded Cognition 4B/5 · novelty-drive root cause (D3 interim) |
| B12 CT-A | Continuous Time CT-A · Run 13 item 5 detector |
| B1/B2 | Feeling F0/F1 · Run 13 deep-read fixes 3 |

## 9. Parked on purpose / not code

Native-LM Phase-2 schooling (multi-month GPU arc), vector cortex, Seam #4
developmental-arc fork (parked: coherent-but-adult), desktop signing/notarization and
auto-update hosting (needs Apple Developer + Windows certs, hosting), old June stash on
`convergence-layer` (inspect, then drop).

## 10. Decisions only Ric can make

1. **T0.5 exemplars:** write the positive quality exemplars (blocks the shared predicate's calibration).
2. **World consent tiers** (C4): website repo / personal folders, open or closed.
3. **Lexicon source** (D1): hand-curated seed (recommended) vs a published list.
4. **DMN branch** (D5): merge, re-land through records, or drop.
5. **Phase order after B:** C (wander) before D (structured mind) is recommended, since
   wandering feeds the vocabulary.

## 11. Supersedes (archive at finalization)

Open-item lists of: `RUN11_BACKLOG_2026-07-19`, `RUN11_IMPLEMENTATION_PLAN_2026-07-19`,
`RUN12_IMPLEMENTATION_PLAN_2026-07-21` (Layer 2), `CREATIVITY_NOVELTY_PROPOSAL`,
`QUALITY_GROUNDING_DESIGN` (sequencing), `GROUNDED_COGNITION_IMPLEMENTATION_PLAN`
(4B/5), `MASTER_STATUS_2026-10-04` (replace with a status line pointing here). Design
reasoning in each stays authoritative.
