# Master Status & Docs/GitHub Review (2026-10-04)

Supersedes `archive/MASTER_STATUS_2026-07-07.md` (read-only history). Built from the
working tree at `43140c8`, every live doc's header, `NEXT_RUN_TESTS.md`, the run
index, the wiki repo, and `gh repo view`. Nothing here is from memory.

---

## 0. The one-paragraph state

Eleven staging lives have been scored; **the §8 acceptance gate has never
passed**, but the binding constraint has climbed a ladder: mechanics (Runs 1–4) →
economics/monopoly (5–8, broken in Run 8: 90.9 % → 42.6 %) → honesty (9) →
**feed/growth (10–11)**. Run 11 (07-20/21, 18,327 cycles, longest life, symbolic-only)
had the best health/honesty numbers ever (43.3 % occupancy, all four aspirations
driving, miner-junk 0) and failed Feed + Growth the same way Run 10 did: the daemon
goal lane went silent for the last ~10,000 cycles, reuse 0 (third run < 8), plus a
new shutdown hang at natural death. **Run 12's build (Layer 1, gate-passers
1A–1D) is committed (`32977a0`, 07-22; launcher hardened 08-19).** *Correction
(same day):* this section first said no Run 12 life had run. In fact **one ran on
08-19/21** (`90a01c4`, 10,972 cycles, clean lifespan death) and sat uncaptured in
`brain/data`. It was captured and scored 2026-10-04 as
`demo_runs/2026-08-19-run/`: **NOT PASSED**. Lifecycle, Health and Skeptic are
fixed. Feed failed for a 4th run (completed-topic re-proposal). Growth is a hollow
green produced by a subject-term substring bug. Since then only
instruments/UI landed: the Voice room (09-26) and the Butlin-14 matrix (09-27,
uncommitted).

## 1. What's done vs. open, by live doc

| Doc | Verdict |
|---|---|
| `RUN12_IMPLEMENTATION_PLAN_2026-07-21` | **The active plan.** Layer 1 (1A shutdown, 1B feed de-clamp, 1C structured keystone, 1D skeptic reds) built; Layer 2 post-gate; acceptance life **not run**. |
| `NEXT_RUN_TESTS.md` | Gate history Runs 1–11 + Run 12 gate. Live. |
| `RUN11_BACKLOG` / `RUN11_IMPLEMENTATION_PLAN` | Executed; Run 11 verdict is in `demo_runs/2026-07-21-run/`. Their still-open items were re-homed into the Run 12 plan. **Archive-ready.** |
| `RUN5`/`RUN6`/`RUN7`/`RUN8_FIX_PLAN`s | All built and run. README keeps them live "as the clamp-era record"; that's what `archive/` is for. `RUN7` header still says *PROPOSED* though built (`a63b160`+`bb3685a`) — wrong either way. **Archive-ready.** |
| `RUN9_DEEP_ANALYSIS`, `RUN10_LIVE_NOTES`, `FETCH_REREAD_LOOP_FIX` | Analyses/fixes whose content was consumed by later plans/run folders. **Archive-ready.** (`RUN10_LIVE_NOTES` itself says "file into the run folder at capture" — move it into `demo_runs/2026-07-18-run/`.) |
| `HARD_NUMBER_REGISTER_2026-07-20` | Reference register ("copy into run folder at capture"). Keep live until Run 12 capture, then copy. |
| `CODEBASE_AUDIT`, `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION`, `…GROUNDING_AND_SURFACE`, `DOC_ARCHIVE_CHECKLIST` | July-1 set. Built (AR1–9, P1–8). They are held live only by the checklist's rule "archive when the §8 gate passes" — a gate the project has since re-framed (Run 11's four-axis gate). The rule is obsolete; decouple it and archive all four. |
| `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN` | Phases 0/1/3 code done; T1.G closure run + T0.5 exemplars were Ric-gated (the exemplar fixtures dir now has new untracked files — check T0.5 status). Live. |
| `GROUNDED_COGNITION_…`, `THOUGHT_OBJECT_SPEC`, `CREATIVITY_NOVELTY_PROPOSAL`, `TOPDOWN_WRITEBACK` | README says Run 11 pulled the Thought Object + creativity in; **verify what Run 11/12 actually built** before keeping "proposed" headers. Write-back remains unbuilt. |
| `LIFE_AMBITION_PROPOSAL` | Header says "PARKED behind Run 8." Run 8 is long past; header is stale. |
| `QUALITY_GROUNDING_DESIGN`, `ORRIN_WORLD_DESIGN`, `COGNITION_GAP_ANALYSIS` | Design direction, post-gate. Live. |
| `COGNITIVE_INDICATOR_RUBRIC` (modified) , `BUTLIN14_EXPERIMENTAL_MATRIX` (untracked) | New instruments; need committing and an index entry. |
| `COMPANION_PRESENCE_MASTER_PLAN` | All 6 phases built 07-10; staged verification outstanding. |
| `OWNERSHIP`, `STRUCTURAL_RISK_REGISTER`, `BENCHMARKS`, `ARCHITECTURE`, `CONFIGURATION` | Living references. `BENCHMARKS` last touched 06-19, `OWNERSHIP` 06-23 — worth a currency check. |

## 2. Organization: what to change

The scheme (tracks + per-track `archive/` + dated names + `git mv`) is sound and
should stay. The tree has simply outgrown a hand-maintained index: **371 `.md`
files, 377 MB** (97 % is `demo_runs/` evidence), and `docs/README.md` was last
refreshed **07-19** — before the Run 11 verdict, the Run 12 plan, the rubric, Butlin-14, and
Voice. Same failure the 07-07 paper diagnosed; the fix proposed then (§2a: make
index refresh part of each plan's done-definition) was evidently not adopted.

1. **Archive pass** (all `git mv`, one commit): the 12 "archive-ready" docs above
   → `Behavioral …/archive/` and `docs/archive/`.
2. **Rewrite `docs/README.md` around "Start here for Run 12"**, shorter, with the
   live set cut to ~15 docs. Add the rubric, Butlin-14, Voice, field guide.
3. **Adopt the done-definition rule**: a plan isn't "built" until its header
   status line is current and the README line changes in the same commit.
4. **`demo_runs/` (≈370 MB, 198 md)**: don't restructure; DEMO_RUNS.md already
   indexes it. If repo size ever matters, the `data/` payloads (not the verdict
   docs) are the thing to move to release assets or Git LFS. Not urgent
   (`diskUsage` is only ~95 MB on GitHub's side).
5. Stop pointing at `docs/MASTER_STATUS_*` as a living surface: either keep exactly
   one current file at docs root (this one) and archive its predecessor on each
   refresh, or declare `docs/README.md` the status surface and stop writing
   these. Recommendation: the former, refreshed per run capture.

## 3. GitHub: the wiki already exists — what's left to polish

Correcting the 07-07 plan: the wiki is built and healthy. 54 pages in
`docs/wiki/` mirrored to `~/orrin_v3.wiki`, a `_Sidebar`, **zero broken
internal links**, set as the repo's homepage URL; repo has 8 topics, badges,
Apache-2.0, security policy, issue/PR templates, CODEOWNERS, releases
(v0.2.0). Remaining gaps, cheapest first:

- **Drift:** `Backend_Telemetry` and `Face_and_Brain_UI` differ — `docs/wiki/` is
  *ahead* (the Voice room commit `43140c8` was never synced). Sync = plain `cp`,
  commit + push the wiki repo.
- **Stale status page:** `Roadmap_and_Status` still says "authoritative status lives
  in `docs/MASTER_STATUS_*`" (no such file at docs root) and mentions nothing of
  Runs 6–12. Rewrite its "how progress is measured" with the real arc in §0.
- **Orphan:** wiki `README.md` is unlinked from Home/Sidebar (likely meant as a
  repo-style readme; fine to delete or link).
- **Front-door polish:** README is long (274 lines) but well-structured; optional
  additions are a run-history timeline graphic (the "ladder" in §0 is the
  project's actual story, and no current page tells it), a live-run GIF (the run
  index itself lists `orrin_learning_run.gif` as a pending capture; `docs/images/`
  holds one static PNG), a GitHub social-preview image, and Discussions
  (currently off, 4 stars — only worth it if you want outside conversation).
- **Root clutter:** nothing untracked is a publishing risk (the strays like
  `tunnel_url.txt`, `tmp/`, `coverage.json` are ignored). The two tracked
  `*.command` tunnel launchers (`expose_orrin`, `tailscale_funnel`) would read
  better under `scripts/`; low priority.

Effort: sync + Roadmap rewrite + README refresh ≈ one short session; the
archive pass is mechanical.

## 4. Bottom line

*(Corrected.)* The Run 12 life has now been scored. The bottleneck is the
**Run 13 gate-passers** (run doc §5 items 1–4: subject-term fix, honest
"answered", prediction-bearing goals, completion-aware generation), then a Run 13
life. The docs fix is housekeeping: one archive commit, one README
rewrite, one wiki sync. Pushing the wiki repo is the only publicly visible step.
