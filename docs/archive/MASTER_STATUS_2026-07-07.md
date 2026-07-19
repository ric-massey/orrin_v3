# Master Status & Docs Organization Review (2026-07-07)

> **Addendum 2026-07-09 — what's changed since this was written.** §0's "built
> but uncommitted" state is over: F1–F22 were committed (`f0c4698`), staging
> **Run 5 lived and ended 2026-07-08** (verdict in `demo_runs/2026-07-08-run/`:
> gate NOT passed — S8/S7 held, S6/S9 fail, committed-goal monopoly 99.9 %),
> and the **Run 6 build** landed 2026-07-09 (`RUN6_FIX_PLAN_2026-07-08.md`,
> commit `584b76a`). §2c's archive moves are done. §3's wiki plan is executed
> and exceeded: the wiki exists with ~50 pages, sourced from `docs/wiki/` and
> synced to `orrin_v3.wiki.git`. §1's track table and §4 are otherwise still
> accurate. This doc is now read-only history pending the next status pass.

**Purpose.** Two things in one paper: (1) a current-truth pass over every live
doc — what's actually done vs. open, correcting drift since the last index
refresh — and (2) an assessment of the docs tree's organization plus a
concrete plan for a GitHub Wiki. Written by reading `docs/README.md`,
`DOC_ARCHIVE_CHECKLIST_2026-07-01.md`, every live plan doc, and the git
working tree (which is dirty — see §0).

---

## 0. What's actually true right now (the thing the index doesn't say yet)

`docs/README.md` was last rewritten **2026-07-01** and hasn't been touched
since. Two things have happened since that it doesn't reflect:

1. **Run 4** (`demo_runs/2026-07-05-run/`, dirty-instance staging life)
   happened and produced a verdict: **S8 passed** (0 desyncs / 223
   completions — the v1/v2 seam is finally proven closed), production funnel
   went nonzero for the first time (292/124/28), but the *making* organ was
   discovered to be a 197 KB template stamped 166 times, aspirations can be
   failed by the deadline walker (one died 104 s before death), and learned
   notes were being eaten by the pruner. This produced
   `demo_runs/2026-07-05-run/2026-07-05_findings.md` (F1–F9).
2. **Run 5's fixes (F1–F9) are built**, per
   `RUN5_FIX_IMPLEMENTATION_2026-07-07.md` — but **uncommitted**. `git
   status` shows 30 modified files + 7 new files (`section_material.py`,
   `step_attempts.py`, `goal_deadlines.py`, `heartbeat.py`,
   `test_run5_findings_fixes.py`, plus the two new docs) all untracked/
   modified right now. The doc claims 1393 tests green (18 new), but **no
   staging run has been done against this code yet** — it's built and
   unit-tested, not behaviorally proven, exactly the same gap every prior
   round had at this stage.

**So:** `RUN4_FIX_PLAN_2026-07-04.md` and `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md`
are fully superseded now (their fixes shipped, ran, and produced Run 4's
verdict + a new findings doc) — they're archive candidates today, not live
plans. `NEXT_RUN_TESTS.md`'s §8 gate is still open (this is now effectively
"Run 5 result" pending). See §2 for the specific moves.

---

## 1. Status by track (corrected as of today)

| Track | Live docs | State |
|---|---|---|
| **Behavioral Evaluation & Runtime Diagnostics** | `CODEBASE_AUDIT_2026-07-01`, `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01` (AR1–AR9 built), `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30` (P1–P8 built), `RUN4_FIX_PLAN`/`RUN4_ISSUES` (superseded, see §2), `RUN5_FIX_IMPLEMENTATION_2026-07-07` (built, uncommitted, unverified) | All code-complete through F1–F9; **the §8 acceptance gate has never passed** across 4 runs (Run 1–4). This is the project's actual bottleneck — not missing features, missing proof. |
| **Core Architecture, Embodiment & Evolution** | `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25` (Phase 0/1/3 code done; T1.G live-closure run + T0.5 exemplars open — both non-code, both Ric-gated), `GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29` (Phases 1/2/3/4A done, Phase 2 built-but-dormant behind the fluency gate; 4B fork + Phase 5 open), `TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN_2026-06-27` (proposed, unbuilt) | Two of three live docs are code-complete waiting on human-gated steps (a live run, and Ric authoring quality exemplars). Only the write-back plan is genuinely unbuilt. |
| **Language & Cognition** | `ORRIN_LANGUAGE_PLAN`, `THOUGHT_OBJECT_SPEC` (spec, Phase 2A — implemented per grounded-cognition Phase 2), `ORRIN CREATIVITY NOVELTY PROPOSAL` (blocked on the AD1/D8 fork) | Native LM exists, trained, wired as the mouth (dormant behind fluency gate). Creativity proposal is the one open architectural decision here. |
| **Engineering & Code Health** | `OWNERSHIP` (reference), `STRUCTURAL_RISK_REGISTER_2026-07-01` (standing register, B5/B6) | Living references, not plans — nothing "to finish" here, they're maintained on a cadence. |
| **Capability, Benchmarks & Evidence** | `BENCHMARKS` | Living run guide, no open work. |
| **UI, Security & Desktop Packaging** | none | **Fully closed.** All 28 items done; only non-code external blockers remain (certs, hosting, tagged CI) and those are explicitly tracked outside docs. |

**One-paragraph state of the organism** (from Run 4's own verdict, still the
most accurate summary): the skeleton is sound — stores don't desync, garbage
doesn't get paid, production hands off — but the *making* organ had no real
content inside it, the failure machinery could kill values, and the memory
system kept spam while composting real writing. F1–F9 target exactly those
three things. Whether they land is Run 5's job, not yet observed.

---

## 2. Docs organization: assessment + concrete moves

**The scheme itself is good and should not change.** Seven tracks, each with
its own `archive/`, a root index, dated filenames, "archive = `git mv`, never
delete." This is already better than most solo-maintainer repos. The problem
isn't structure, it's that **the index (`docs/README.md`) drifts within days
of a run landing**, because runs land faster than index-refresh passes get
scheduled. Two structural fixes, then the actual moves:

### 2a. Make the index self-correcting (structural fix)
Fold "update `docs/README.md`" into the *last step of every fix-implementation
doc*, the same way `RUN5_FIX_IMPLEMENTATION` already ends with a gate
section — add one line: "update `docs/README.md`'s track blurb before this
doc is considered done." Right now README refresh is its own separate
checklist pass (`DOC_ARCHIVE_CHECKLIST`) that has to be remembered
independently, which is exactly why it's stale again four days later.

### 2b. Retire the root-level orphans
`TEMPLATES.md` and `ORRIN_ACTIVITY_REPORT.md` sit at the **repo root**,
outside `docs/` entirely, dated 2026-06-13/06-14, not linked from anywhere,
not indexed. `ORRIN_ACTIVITY_REPORT.md` is a point-in-time snapshot fully
superseded by every `demo_runs/*/who_is_he.md` since. `TEMPLATES.md` is a
one-time code catalog that's likely stale (templates named in it — e.g. the
compose_section stamper — have since been deleted per F1). Move both into
`docs/archive/` (or delete `TEMPLATES.md` if a fresh catalog is ever wanted;
it's a `grep`-generated artifact, not authored content).

### 2c. Specific archive moves (do these now)
| Move | Why |
|---|---|
| `RUN4_FIX_PLAN_2026-07-04.md` → `Behavioral …/archive/` | Fixes built, run, verdict recorded; superseded by `RUN5_FIX_IMPLEMENTATION`. |
| `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md` → `Behavioral …/archive/` | Same — its issue list is now `2026-07-05_findings.md`'s job. |
| `TEMPLATES.md`, `ORRIN_ACTIVITY_REPORT.md` (root) → `docs/archive/` | Orphaned, stale, unindexed. |
| `DOC_ARCHIVE_CHECKLIST_2026-07-01.md` | **Do not archive yet** — per its own D3 rule it archives together with `CODEBASE_AUDIT` + the audit-remediation plan once the staging run passes §8. That gate is still open (now pending on Run 5). Leave live, but note in it that the D0–D5 work it describes is functionally complete. |
| `docs/README.md` | Rewrite to reflect Run 4's verdict + Run 5's build status (§0 above), and drop the two archived RUN4 docs from its Behavioral blurb. |

### 2d. Everything else is fine as-is
`demo_runs/` (7 dated folders, ~162 MB — almost entirely the permanent
behavioral record, correctly never split) needs no change. The per-track
`archive/` folders (78 docs total) are appropriately sized for the project's
age; no track needs sub-folders yet. Don't over-engineer this further —
adding more taxonomy (tags, a wiki-only nav, a second index) before the
existing one is kept current would just create a second thing to drift.

---

## 3. GitHub Wiki: feasibility and a concrete plan

**Verdict: easy, low-risk, and worth doing — but as a curated front door, not
a mirror of all 158 files.**

### How it actually works
- A GitHub wiki is **its own git repository**: `https://github.com/ric-massey/orrin_v3.wiki.git`.
  It renders Markdown exactly like the rest of GitHub (same GFM), supports a
  custom sidebar (`_Sidebar.md`) and footer (`_Footer.md`), and pages are just
  files with no extension requirements beyond `.md`.
- **One-time gate:** the wiki repo doesn't exist until (a) Wikis is enabled in
  repo Settings → Features, and (b) at least one page is created **through the
  GitHub web UI** (this initializes the git repo). After that first page,
  it's clonable/pushable like any other repo — so the rest of the population
  can be scripted (write files locally, `git push` to the `.wiki.git` remote).
- Images: the wiki repo can hold its own image files (commit them alongside
  the pages) or reference `docs/images/` via raw GitHub URLs — either works.

### Why "curate, don't mirror"
Mirroring all 158 docs (many are dated forensic run-analyses meant for you,
not a reader) would produce a wiki that's just as hard to navigate as the
current tree, and it'd immediately go stale the same way `docs/README.md`
does — now in two places instead of one. A wiki earns its keep as the thing a
visitor reads *before* deciding to dig into `docs/`.

### Concrete page plan (small, high-leverage)
| Page | Source | Purpose |
|---|---|---|
| `Home.md` | new, short | What Orrin is (condense root `README.md`'s opening), links to everything below. |
| `Architecture.md` | `docs/ARCHITECTURE.md` | The system-fits-together reference, as-is or lightly trimmed. |
| `Current-Status.md` | this doc, §1 | The living "what's done / what's open" table — **this is the one page worth actively maintaining**, since it's short and high-traffic. |
| `Benchmarks.md` | `docs/Capability…/BENCHMARKS.md` | Run guide. |
| `Roadmap.md` | condensed from the 3 Core-Architecture/Language live plans | Where the big open work is (T1.G run, write-back, Phase 4B/5, the creativity fork). |
| `Run-History.md` | `demo_runs/DEMO_RUNS.md`-style index | Link out to the dated run folders in `docs/`, one line each, for anyone who wants the receipts. |
| `_Sidebar.md` | new | Persistent nav across all pages above. |

That's 6 content pages + a sidebar — a few hours of editing, not a large
project, since the source material already exists and is well-written; the
work is condensing, not authoring from scratch.

### What I'd need from you to execute
Enabling Wikis and creating the first page has to happen through the GitHub
web UI (or `gh` if you'd rather script it — `gh api` can create the first
page too, but the UI is one click). After that, I can draft all the page
content from the docs above and push it in one batch. This is a
publicly-visible change to your repo, so I'd want you to say go before I
touch anything on GitHub itself.

---

## 4. Bottom line

- The docs tree's *structure* doesn't need fixing — its *upkeep cadence*
  does (§2a). Do the five moves in §2c now and the tree is current again.
- The project's real bottleneck is behavioral proof, not more building: four
  runs, zero passes of the §8 gate, each one closer (Run 4 passed S8 outright
  for the first time). Run 5 is built and waiting on a staging run.
- A GitHub Wiki is cheap to stand up and would make the repo's front door
  much friendlier without duplicating the working docs tree — recommend the
  6-page curated version in §3, gated on you flipping on Wikis.
