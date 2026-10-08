# Phase B Build Brief — the Run 14 gate (2026-10-08)

**For whoever builds next (any model).** Everything needed to build Phase B of
[`POST_RUN13_MASTER_PLAN_2026-10-07.md`](POST_RUN13_MASTER_PLAN_2026-10-07.md) without
the conversation that produced it. Phase B = items **B1–B28**, the fixes the Run 13
life showed are needed before Run 14. Code anchors were verified against `d1f2baa`
(2026-10-08); re-grep before editing, lines drift.

---

## 0. Read first (in this order)

1. `CLAUDE.md` — golden rules: `make verify` is the gate; symbolic-first (no new code may
   need an LLM); state paths only via `brain/paths.py`; no sentience language.
2. The Run 13 verdict:
   `Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-10-06-run/DEMO_RUN_2026-10-06.md`
   — **§4b and §4c are the evidence for most items below**; §1–§3 are the scorecard.
3. The master plan §2 (Phase B table, each item with its Run 13 baseline).
4. `Language & Cognition/FEELING_AND_NAMING_DESIGN_2026-10-07.md` §5 L2 and §9 (F0/F1 =
   B1/B2) and §0b (the live deep read).
5. `.claude/skills/run-analysis/SKILL.md` — how runs are captured and scored; its
   ground-truth rules apply to every fix here.

## 1. Ground rules (each one was paid for by a past run)

- **Governing principle (Ric, 2026-10-07): most of his memories should be about his
  world, not himself.** When an item has a choice, prefer the one that moves memory and
  attention outward.
- **No new clamps.** Before fixing, classify each finding: *broken pipe* (a wire that
  doesn't connect), *unopposed force* (a push with no antagonist), or *misaimed force*
  (an antagonist aimed at the wrong thing). Clamps are scar tissue for a missing
  antagonist: oppose, don't cap. (B13 removes a clamp.)
- **Test against the real artifacts.** The Run 13 capture is the ground truth. Build each
  regression test from its files (copy small excerpts into `tests/fixtures/`, as
  `tests/fixtures/run12_claims/` does). A fix whose test only uses synthetic data hasn't
  been shown to catch the real case. Confirm each new test **fails on the pre-fix code**.
- **Prefer a forced-fire harness over waiting a life** (pattern:
  `tests/brain/test_refractory_harness.py`).
- **Before trusting `make verify`**, upgrade the venv's linters to match CI (CI installs
  latest mypy/ruff unpinned): `.venv/bin/python -m pip install -U mypy ruff`.
- **Tests are hermetic** (`tests/conftest.py` redirects state). Don't write fixture files
  with pre-1980 mtimes into the shared data dir: the mind-export tests zip it.
- **Commit per cluster** (§2), with the Run 13 baseline → expected change in the message.
- **Don't touch** `tests/fixtures/quality_golden/exemplars/` except to remove junk; it's
  human-ratified. The unmerged branch `claude/orrin-dmn-equivalence-zzlw5q` is out of
  scope except B19's cherry-pick.

## 2. Build order — seven clusters

Ordered by leverage. Clusters 1–2 should clear the largest share of Run 13's reds.

### Cluster 1 — the two churn loops (B11, B20)

**B11 · Daemon-owned waiting goals are not brain goals** (verdict §4b A). A
`characterize` goal waits up to 6 h for fresh telemetry. The brain commits it, researches
its *title*, satiety-closes or step-fails it within ~2 min, `goal_reconcile` "repairs" the
still-running daemon copy, it is re-absorbed and recommitted: every ~15 min, 6 h. Caused
all 18 desyncs, 53–78 % focus in its windows, 14 completed-and-failed brain goals, and
**96 % of the daemon WAL** (the deferring step upserts every tick).
- Anchors: `brain/goal_io.py` `_EXECUTABLE_KINDS` (includes `characterize`),
  `_reconcile_open_v2_into_v1` (:340), committable-from-v1 path;
  `brain/cognition/planning/goal_reconcile.py:184` (orphan-RUNNING repair);
  `goals/handlers/characterize.py:195,204` (`_defer`); brain satiety close in
  `pursue_goal`.
- Direction: mark daemon-executed waiting goals (kind `characterize`, or any v2 goal whose
  current step is deferring) as **not committable / not brain-pursuable**; the brain
  learns their outcome only from the daemon's terminal event. Make the deferring check
  step not write a WAL row per tick (write on state change only). Let characterization
  re-ask across a life (appetite) — only 3 predictions in 28 h.
- Observables: 0 orphan-RUNNING repairs on characterize (18); characterize WAL rows < 5 %
  (96 %); no waiting goal > 10 % focus (78 %); ≥ 4 predictions/life (3).

**B20 · "Answer:" follow-ups must reach the daemon** (§4b C). When a question closes
unanswered, `brain/cognition/epistemic_closeout.py:291` `spawn_followup_goal` adds the
follow-up straight to the v1 tree (`add_goal`), so it never passes
`sync_proposed_goals` → 0 hand-offs, 567 brain-side commits, **51 failures** ("steps
abandoned at the 3-attempt cap", the largest class) and one goal "completed" 19×.
- Direction: emit the follow-up through `context["proposed_goals"]` (the path
  `generate_intrinsic_goals` uses), kind `research`, with a real query (the topic, not
  the whole question sentence).
- Observable: 0 "Answer:" steps-unreachable failures (51).

### Cluster 2 — the feed (B13, B6, B7, B5, B4)

**B13 · Remove the one-cycle debt gate on goal generation** (§4b B).
`brain/cognition/intrinsic_goals.py:199`: `if action_debt > 0 and bound_goal: skip`. One
unacted cycle blocks origination; debt was > 0 nearly all life, so ~90 % of
`generate_intrinsic_goals` calls were thrown away. Main driver of the feed silences
(7 > 30 min, max 247). This is a clamp: replace it with an antagonist, e.g. let goal
generation's own value rise when the research pool is thin (B6), and leave avoidance to
the breaker. Observables: generation skips < 10 % of calls; no daemon silence > 30 min.

**B6 · Generation earns value when the pool is thin.** `generate_intrinsic_goals` EMA
0.522 (rank 43): making a goal earns no credit itself. Credit it when its proposals are
queued and later produce work (delayed credit through the ledger), or raise its drive
pull with pool emptiness. Observable: generation picks rise when research no-ops.

**B7 · No-op actions earn nothing and aren't goal service.**
`brain/cognition/web_research.py:365` returns "no fresh topic — everything tried
recently" ~95 % of late-life calls, yet `research_topic` keeps value and counts as goal
service (the breaker spares it). Observable: research no-op < 20 %.

**B5 · Brake on follow-on rounds.** `brain/goal_io.py:422` `_FOLLOWON_ANGLES` repeats
after round 4, so later rounds re-fetch the same pages (round 21 of *The Daily Stoic*; 34
"no URLs" failures). Stop at the angles' end, or derive angles from the prior claims'
entities. Topic satiety keys rounds to the base title (`intrinsic_helpers._title_key`) but
didn't slow them. Observable: max round ≤ 4.

**B4 · Knowledge-graph concept cleanup.** Research topics come from KG concepts
(`web_research.py:249` `_topic_from_knowledge_graph`); only 25 exist, many junk ("round
the sun", "world a world", "See More Results Suggestions", his own "Make things"). The
`definition` extractor (`brain/cognition/knowledge_graph_extract.py:~437`) takes
fragments. Share one chrome/fragment cleaner with `goals/handlers/research_claims.py`
(`_strip_chrome`) and reject his own goal/aspiration titles. Also "the free encyclopedia
This article is about…" got through as an answer (3×): add it to the shared cleaner.
Observable: 0 junk concepts.

### Cluster 3 — memory about his world (B1, B3, B2)

**B1 · F0: telemetry out of working memory.** `brain/think/think_utils/finalize.py:77`
writes `🧠 Chose: {fn} — {reason}` into WM; metacog threshold alarms, chunk-merge and
compaction notices also land there; `brain/cog_memory/working_memory.py:353,380`
promote/compact them into long memory. Route them to trace/telemetry. Observables: 0 WM
`🧠 Chose:` entries; self-log summaries < 10 % of LTM (74 % at death).

**B3 · Long memory protects world findings.** `brain/cog_memory/long_memory.py:21`
`MAX_LONG_MEMORY = 2000`; pruning (`:250,293`) evicts by its own rules while self-log
summaries flood in. Give world findings (research, perception, claims) eviction
protection and self-observation a bounded share. Observable: world findings ≥ 25 % of
LTM (2.8 %).

**B2 · F1: appraisal reads structured events.**
`brain/control_signals/appraisal.py:289` `appraise_working_memory` scores WM *text* with
word sets (`_SELF_WORDS`, `_BLOCK_WORDS` …), so it appraises his own alarms. Called from
`brain/control_signals/signal_patterns.py:206`. Feed it structured events (goal-step
outcomes, effect-ledger credit, failure `last_error` for agency); keep the text path only
for genuinely textual input (a message from Ric). Design: Feeling doc §5 L2. Observable:
no appraisal deltas triggered by his own alarm text; agency ≠ self on world failures.

### Cluster 4 — reward honesty (B8, B21, B16, B17, B23, B24)

**B8 + B21 · The impossible action.** `decide_to_write_code` ran 273× in symbolic mode,
every time `brain/agency/code_writer.py:467` "no LLM body available — not writing a
stub"; it is never marked impossible
(`brain/control_signals/reward_signals/impossibility.py:94` `mark_impossible`), and the
per-cycle reward (`cognition_history` `reward`, mean **0.54**) pays it, so its EMA climbs
(0.608, rank 9). Mark it impossible at the bail-out and make the cycle reward honour
impossibility (zero-with-prejudice). Observable: 0 picks while no LLM body; EMA → floor.

**B16 · Native-LM drafts are not production.** With no LLM,
`brain/agency/compose_section.py:65` drafts with `native_lm.generate`. The organ babbles
his status lines ("[I_model] I've been running for 2h 0. It's afternalouses on
ednesday") and **75 such sections were credited** (54 to *Making things*). Babble is
always novel to the ledger. Require the organ's fluency gate (as
`conditional_render` does) **and** a self-talk/log check before crediting; the organ's
corpus must exclude his logs (`cognition/language/acquisition_noise.py` misses
`[world_model]`-style lines). Observable: 0 credited tracked-work sections that fail
fluency/self-talk (75).

**B17 · Value headroom.** `brain/cognition/planning/commitment_value.py:268`
`_fold_credit`: self-understanding reached 0.9999 (direct credits from B16's babble +
item-11 propagation). Add headroom (e.g., diminishing step near 1). Observable: no
aspiration value ≥ 0.99.

**B23 · Growth counts dedupe by question.** 26 answered stamps = 14 distinct questions;
the ladder's 38 entries = 17 distinct (rung 5 inflated);
`brain/cognition/growth_ladder.py:54` `note_verified_success` and close-out credit should
count a question once. `brain/cognition/answer_citation.py:81` `annotate_reason` cited the
junk "world a world" answer 1,546×: count once per question per decision window.

**B24 · Rule-hit runaway.** One rule has 110,813 hits (~7/cycle);
`brain/symbolic/rule_engine.py:272,350` increment `hits` with no refractory (the Run 10
refractory covers reinforcement only). Observable: top rule ≤ ~1 hit/cycle.

### Cluster 5 — affect and pressure (B9, B10, B25, B26)

**B9 · Inhibition habituates.** `brain/cognition/inhibition.py:50`
`apply_inhibition_costs` charges uncertainty and frustration every time a wanted function
isn't picked (~170/h, mostly for goal generation). A repeatedly-unchosen want should
habituate. **B10 · Breaker duty** fires on 48 % of cycles
(`brain/cognition/metacog_analyze.py:99`); much of it follows from B11/B13/B7. Target
< 10 %. **B25 · Binding write-back pressure:**
`brain/cognition/workspace_writeback.py:210` `write_back` ran on 66 % of cycles, 36 %
pushing `motivation` +0.06 (a constant push on "drive"); give it habituation per
situation. **B26 · Affect range and a dead gauge:** `valence` stayed 0.58–0.71 all life,
`stability` ≥ 0.95 for 62 %; `allostatic_load` reads 0.000 all life:
`brain/cognition/cost_prediction.py` writes `_allostatic_load` (:248) but the telemetry
row reads it from another dict (:301). Fix the wire or delete the gauge.

### Cluster 6 — instruments and hygiene (B14, B15, B18, B19, B22, B27, B28)

- **B14** `citing_goal_id` on every `mark_reused_path` caller: `brain/goal_io.py:411`,
  `brain/cognition/web_research.py:453`, `brain/cognition/language/library.py:424`
  (only 114/833 reuse rows carry a citer).
- **B15** Exemplar gate (`brain/cognition/quality_standard/originality.py:198`
  `is_self_talk`, and `gate.py`): count any internal tag (`[intrinsic_goal]`,
  `[world_model]` were missed), handle single-paragraph artifacts, veto verbatim
  `source: research_topic` memos, and reject garbled text. Run 13 promoted 3 junk of 5;
  the 5 files are in the run folder's `promoted_exemplars/` as fixtures.
- **B18** Death reason: natural lifespan death is recorded "operator_stop" via
  `brain/loop/services.py:135`; pass the real reason.
- **B19** Cherry-pick only the ToM timing fix from `claude/orrin-dmn-equivalence-zzlw5q`
  (ToM computed in sense before the reply that uses it).
- **B22** Private-thoughts log kept for a whole life (rotation kept the last ~10 h only);
  `run_orrin.sh`/capture already note `tracked_work/`.
- **B27** `brain/think/speech_log.py:105` stamps `intent` from `comprehension`, which was
  empty for all 26 rows: stamp the typed intent so speech grounding can be scored.
- **B28** Production attempts (1,275) vs producer runs (164): reconcile what counts as an
  attempt.

### Cluster 7 — time (B12)

**B12 · CT-A clock time** (`Core Architecture, Embodiment & Evolution/CONTINUOUS_TIME_DESIGN_2026-10-04.md`
§2): time constants in seconds, not cycles; builds on
`brain/cognition/runtime_lifetime.py:292` `detect_suspension`. Last, because it touches
many constants and would blur attribution of the clusters above.

## 3. Before Run 14

1. `make verify` green (after upgrading mypy/ruff).
2. **Smoke life** (~2k cycles) to confirm the cluster 1–2 observables move: churn gone,
   no silence > 30 min, generation not skipped.
3. **Reset:** `python3 reset_orrin.py --hard`, then restore the two committed seeds every
   life rewrites — `git checkout -- brain/data/control_signals_model.json
   brain/data/cognitive_functions.json` — then `python3 reset_orrin.py --verify`.
4. **Launch with the staged lifespan band** (without it the default is 1–2 *years*):
   `ORRIN_LIFESPAN_MIN_DAYS=1.1 ORRIN_LIFESPAN_MAX_DAYS=1.3 ./run_orrin.sh`, plugged in, lid
   open; the launcher verifies caffeinate.
5. The website status card's feeder is
   `~/RicsWebsite/projects/orrin/producer/push_status.py`; `run_orrin.sh` starts and
   stops it with the life (A6; `ORRIN_STATUS_PRODUCER=0` to skip).

## 4. Done means

- Each item's observable is met in a test (forced-fire where reachable) or will be read
  from Run 14.
- Master plan §2 rows marked BUILT with commit hashes; `NEXT_RUN_TESTS.md` gets a "Run 14
  gate" block listing B1–B28 observables with their Run 13 baselines.
- A plain-English progress note on the website:
  `python scripts/site_update.py --kind build --title … --body … --href <commit> --publish`.
