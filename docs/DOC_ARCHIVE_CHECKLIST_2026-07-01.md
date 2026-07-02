# Doc Clearance Plan — Get `docs/` to a Clean, Current State

**Date:** 2026-07-01
**Purpose.** A sequenced plan to clear the docs tree: archive what's done, correct
stale statuses, mark what's blocked (and on what), and — as the **final step** —
update the `docs/README.md` index to match. Per `docs/README.md` the convention is:
each track keeps *live* plans/audits at its top level; superseded/completed docs move
to that track's `archive/`; `demo_runs/` is permanent run history.

**Principle:** never lose the *why*. A doc archives only when its content is either
(a) fully carried by a successor doc, or (b) a completed record. Archiving = `git mv`
into the track's `archive/`, not deletion.

> **⚠️ AUDIT NOTE (2026-07-01, verified against tree + git):** `git mv` **fails on
> untracked files**, and many of the docs this plan touches were never committed.
> Untracked right now (`??` in git status): `SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md`,
> `RUN_AUDIT_2026-06-30.md`, `PRERUN_TEST_PLAN_2026-06-29.md` (D1 moves #1–3),
> plus the "live" set — `CODEBASE_AUDIT_2026-07-01.md`,
> `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01.md`,
> `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md`, `B3_DECAY_DIAGNOSIS_2026-07-01.md`,
> this checklist, `STRUCTURAL_RISK_REGISTER_2026-07-01.md`, and the `demo_runs/2026-07-01-run/`
> folder. **Fix: `git add` each untracked doc first** (so history starts before the move),
> then `git mv`. D1 moves #4–6 and the UI plan are tracked; `git mv` works there as written.

Work the phases in order. **Phase D5 (README) is last** — the index must be updated
only after all moves are final, so it never points at a doc mid-flight.

> **⚠️ AUDITED 2026-07-01 (Claude Code) — read the inline `AUDIT NOTE` blocks before
> executing; nothing original was deleted.** Every claim was verified against the tree,
> git history, and the referenced docs. Structure and most citations check out, but six
> findings require deviating from the letter of the plan: (1) D1 — `git mv` fails on the
> untracked docs (see note under the Principle); (2) D1 gated — the UI plan's B1 residual
> is already FIXED in-doc, gate passes; (3) **D2 — both proposed status lines are stale**:
> grounding-and-surface is P1–P8 built (not P1–P5), and grounded-cognition Phase 2 is
> built-but-dormant (not open) per commit `8351ea1` — use the corrected wording in the
> notes; (4) D4 — `DEMO_RUNS.md` is not at the `demo_runs` root and is not an index;
> (5) D5a — the README is stale in every track, needs a full rewrite; (6) D5b — two
> live→moved references are missing from the list (CODEBASE_AUDIT and
> IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE). Verified-safe claims (root README, no
> CLAUDE.md/AGENTS.md/Makefile/scripts refs, 06-29 run analysis left stale by design,
> Core-Arch banner truthful) all held.

---

## Phase D0 — Baseline (do first, ~10 min)

**Goal.** Know the exact current tree so the moves are reversible and reviewable.

- [x] `find docs -name "*.md" -not -path "*/archive/*" | sort > /tmp/docs_live_before.txt`
- [x] Confirm each track has an `archive/` dir (create if missing:
  `Behavioral Evaluation & Runtime Diagnostics/archive/`, `Core Architecture, Embodiment
  & Evolution/archive/`, `Language & Cognition/archive/`, `UI, Security & Desktop
  Packaging/archive/`, and the shared `docs/archive/`).
- [x] These two 2026-07-01 docs (this plan + `CODEBASE_AUDIT` + the
  `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION`) stay **live** — they're active work.
  *(Audit note: "two" should read **three** — three docs are listed.)*

> **⚠️ AUDIT NOTE:** `Language & Cognition/` currently has **no `archive/` dir** — it's
> the one that must actually be created in the step above. The other four listed
> already exist.

**Done when:** the before-list exists and every `archive/` dir is present.

---

## Phase D1 — Archive the completed/superseded docs (exit condition already met)

**Goal.** Move the docs whose content is fully carried elsewhere or is a finished
record. Each line is a `git mv`; the *reason it's safe* is stated.

| # | Move | Why safe to archive |
|---|---|---|
| 1 | `Behavioral …/SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md` → `Behavioral …/archive/` | The diagnosis; fully carried by the two implementation plans it spawned. |
| 2 | `Behavioral …/RUN_AUDIT_2026-06-30.md` → `Behavioral …/archive/` | Its fixes were applied; its open items live in the audit + AR8/GOAL_STORE_UNIFICATION. |
| 3 | `Behavioral …/PRERUN_TEST_PLAN_2026-06-29.md` → `Behavioral …/archive/` | The runs it planned are captured in `demo_runs/` + RUN_AUDIT. |
| 4 | `Core Architecture …/GROUNDED_COGNITION_DIRECTION_2026-06-29.md` → `Core Architecture …/archive/` | Direction doc, superseded by its own implementation plan (it says so). |
| 5 | `Core Architecture …/GROUNDING_EXPERIMENT_RESULTS_2026-06-29.md` → `Core Architecture …/archive/` | Completed Phase-3 verdict; a results record. |
| 6 | `Language & Cognition/orrin_llm_cognition_audit_2026-06-25.md` → `Language & Cognition/archive/` | Superseded by the system-wide LLM sweep in `CODEBASE_AUDIT` Part 7. |

**Gated within this phase (verify, then move):**
- [x] `UI, Security & Desktop Packaging/UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md` —
  all 29 items ✅. **Confirm the one residual (earlier note: a B1 timeline undercount)
  is closed or explicitly dropped.** If clean → `git mv` to `UI …/archive/`. Else leave
  live and add the residual as a one-line open item.

> **✅ AUDIT NOTE — gate verified, PASSES:** the B1 residual is already marked
> **FIXED 2026-06-17** inside the plan itself (§6 B1: "summary counted before slice",
> and step 1 of its punch list is struck through as done). The move is safe.
> Two corrections: (a) the doc contains **28** ✅ marks, not 29 — there is no 29-item
> enumeration in it, so don't hunt for a missing 29th; (b) the plan's §4 external
> desktop blockers (certs / hosting / tagged-CI) remain open **by design** — they're
> non-code, tracked outside this doc, and don't block archiving.

**Done when:** the 6 unconditional moves are committed and the UI doc is either moved or
its residual is written down.

---

## Phase D2 — Correct stale statuses on the docs that STAY live

**Goal.** Several live plans have headers that no longer match reality; fix them so the
tree is honest without moving anything.

- [x] `Behavioral …/IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md` — header says
  **"Status: Proposed."** Change to **"Status: P1–P5 built; P6 (veil residuals) + P7
  (lived-surface UI + ablation panel) open; gated on NEXT_RUN_TESTS §8."**

> **⚠️ AUDIT NOTE — the replacement status above is itself stale. Do NOT write it.**
> As of 2026-07-01 **P1–P8 are ALL built** (uncommitted, working tree on
> `structural-debt-exceptions`): P6 veil residuals (`speakability.py` + membrane-test
> edits), P7 lived surface + ablation panel (`brain/loop/lived_surface.py`,
> `frontend/src/components/brain/LivedSurfacePanel.tsx`,
> `frontend/src/pages/settings/RunConfigSection.tsx`, `brain/run_config.py`), P8
> structural tax (`Engineering & Code Health/STRUCTURAL_RISK_REGISTER_2026-07-01.md`).
> Write instead: **"Status: P1–P8 built 2026-07-01 (uncommitted); staging run +
> ten-round proof pending; gated on NEXT_RUN_TESTS §8."**
- [x] `Core Architecture …/ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md` — confirm the
  phase banner still reads truthfully (Phase 0 done; Phase 1 code done, **T1.G live run +
  T0.5 exemplars open**; Phase 2 not started). Update the top line if drifted.
- [x] `Core Architecture …/GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29.md` — note
  **Phases 1/3/4A done (commit `8351ea1`); Phase 2 (LM-as-mouth conditional decoder)
  open.**

> **⚠️ AUDIT NOTE — "Phase 2 open" is contradicted by the commit record. Do NOT write
> it.** Commit `8351ea1` is titled "…stabilizers, **LM-as-mouth**, grounding experiment
> (Phases **1-4A**)" and its message lists Phase 2A–2D as implemented: THOUGHT_OBJECT_SPEC
> (2A), capture pairs → `narration_pairs.jsonl` (2B), `conditional_render` wired into
> `compose_from_motive`, fluency-gated (2C/2D). Phase 2 is **built but dormant** — the
> fluency gate keeps templates in place until the native organ is ready, so his voice is
> unchanged today. Write instead: **"Phases 1/2/3/4A done (commit `8351ea1`); Phase 2
> built but dormant behind the fluency gate; Phase 4B fork + Phase 5 (hierarchical
> skills) open."**
- [x] `NEXT_RUN_TESTS.md` — keep live; it's the §8 gate. Add a one-line pointer that the
  **AR1–AR4** work (audit-remediation plan) is what should move signals 5/6/7/9 next run.

**Done when:** no live plan header contradicts the real build state.

---

## Phase D3 — Mark the BLOCKED docs with their unblock condition (stay live)

**Goal.** These are proposed/diagnosed but not built; they stay live and each gets a
one-line "unblocks when" so it's clear why it's still here.

- [x] `Behavioral …/B3_DECAY_DIAGNOSIS_2026-07-01.md` → *"Unblocks/archives when AR8
  (energy breathes) lands and a run shows rise-and-recover curves."*
- [x] `Core Architecture …/TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN_2026-06-27.md` →
  *"Unblocks when built on the main path, or explicitly dropped."*
- [x] `Language & Cognition/ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md` →
  *"Blocked on the AD1/D8 fork (LLM-free creativity) in the audit-remediation plan."*
- [x] The two new 2026-07-01 plans (`IMPLEMENTATION_PLAN_AUDIT_REMEDIATION`, this
  clearance plan) and `CODEBASE_AUDIT` — **stay live**; they archive together once
  AR1–AR9 land + the staging run passes (per the remediation plan's Definition of Done).

**Done when:** every blocked doc names its unblock condition in its header.

---

## Phase D4 — Run-history hygiene (`demo_runs/`)

**Goal.** Keep the permanent behavioral record intact and tidy.

- [x] **Do not archive `demo_runs/` files individually** — they're the record the audit
  reads.
- [x] Only if the folder gets crowded: move *whole old run folders* (e.g. pre-06-25)
  into a new `demo_runs/archive/` **as complete sets** — never split a single run's docs.
- [x] Leave `DEMO_RUNS.md` (the run index) at the `demo_runs` root, current.

> **⚠️ AUDIT NOTE — this bullet describes a file that doesn't exist as described.**
> The only `DEMO_RUNS.md` sits **inside `demo_runs/2026-06-17-run/`**, not at the
> `demo_runs` root, and its content is a June-17-era "public demo target" note (rut
> demo), not a run index — it lists nothing after that date. Following the bullet
> literally is a no-op. Real work: either (a) `git mv` it to the `demo_runs/` root and
> rewrite it as an actual index of the seven run folders (06-16 → 07-01), or (b) drop
> the bullet and accept there is no index. Pick (a) if D4 is done at all.

**Done when:** no partial run folders; index current.

---

## Phase D5 — Update ALL index/reference files *(LAST — only after D1–D4 are final)*

**Goal.** Make every file that *indexes or links* a moved doc match the cleared tree.
It's not just `docs/README.md` — a link needs fixing only when the **source stays live
and the target moved**. The search that found these:
`grep -rl "<moved-doc-stem>" . --include="*.md" --include="*.py" | grep -v /archive/`.

### D5a — `docs/README.md` (the primary index)
- [x] **Remove** every doc moved in D1 (SYNTHESIS, RUN_AUDIT, PRERUN_TEST_PLAN,
  GROUNDED_COGNITION_DIRECTION, GROUNDING_EXPERIMENT_RESULTS, llm_cognition_audit, and
  UI plan if moved).
- [x] **Add** the three live 2026-07-01 docs: `CODEBASE_AUDIT_2026-07-01.md`,
  `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01.md`, and this
  `DOC_ARCHIVE_CHECKLIST_2026-07-01.md` (checklist can sit at the docs root by README,
  since it spans tracks).
- [x] **Fix the stale Core-Arch entries:** the index still names `MASTER_PLAN_2026-06-16.md`
  and `ALLOSTATIC_CAPACITY_TAX_2026-06-17.md` as live — **both are already in
  `Core Architecture …/archive/`.** Replace with the real live doc
  `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md`.

> **⚠️ AUDIT NOTE — the README is stale in EVERY track, not just Core-Arch. The three
> bullets above are not enough; plan a full rewrite of `docs/README.md`.** Verified
> against the tree 2026-07-01:
> - **Behavioral** blurb names four docs that are all already in `Behavioral …/archive/`:
>   goal-system anatomy, the production-reward plan, the signal→action audit, the
>   life-capsule plan. Live reality: `CODEBASE_AUDIT`, the two implementation plans,
>   `B3_DECAY_DIAGNOSIS`, `demo_runs/`.
> - **Engineering & Code Health** blurb names "the structure audit and the cleanup plan"
>   — both archived. Live reality: `OWNERSHIP.md` + `STRUCTURAL_RISK_REGISTER_2026-07-01.md`.
> - **Capability, Benchmarks & Evidence** blurb names `CLAIMS_AND_EVIDENCE.md` as if live
>   — it's in that track's `archive/`. Live reality: `BENCHMARKS.md` only.
> - **Language & Cognition** blurb names only `ORRIN_LANGUAGE_PLAN.md` — omits the live
>   `THOUGHT_OBJECT_SPEC.md` and `ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md`.
> - **Root docs** (`NEXT_RUN_TESTS.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`) aren't
>   listed at all — add a root section while rewriting.

### D5b — the OTHER index/reference files (complementary — easy to miss)
- [x] **`frontend/README.md:17`** — links the UI master plan
  (`../docs/UI, Security & Desktop Packaging/UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md`).
  If D1 archived that plan, repoint the link to `…/archive/…` (or drop it). *This is a
  second README, separate from the two above — the easy one to forget.*
- [x] **`docs/Language & Cognition/ORRIN_LANGUAGE_PLAN.md`** — links
  `GROUNDED_COGNITION_DIRECTION_2026-06-29.md` (moved). Repoint to `…/archive/…` or to the
  live implementation plan that supersedes it.
- [x] **`docs/Core Architecture …/GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29.md`** —
  its "Implements `GROUNDED_COGNITION_DIRECTION…`" reference now points into `archive/`;
  update the path (the two are a direction→plan pair, so a pointer into archive is fine
  as long as it resolves).

> **⚠️ AUDIT NOTE — two live→moved references are MISSING from the D5b list above**
> (found by this plan's own `grep -rl` method; they're backtick mentions, not `](…)`
> links, so the D5d link-check regex will NOT catch them either):
> - [x] **`Behavioral …/CODEBASE_AUDIT_2026-07-01.md`** (stays live) — cites
>   `SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md` (line ~22) and
>   `RUN_AUDIT_2026-06-30` five times (lines ~751, 777, 840, 856, 983). After D1 moves
>   both, add an `…/archive/…` qualifier at first mention of each (prose mentions, so
>   one qualifier per doc is enough; don't rewrite every occurrence).
> - [x] **`Behavioral …/IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md`**
>   (stays live) — line 4 "Derives from: `SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md`"
>   → repoint to `archive/SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md`.
> Also minor: the `frontend/README.md` link called out above is at **lines 15–16**,
> not 17.

### D5c — verified SAFE (no change — recorded so it isn't re-checked each time)
- Root **`README.md`** — links only living docs (ARCHITECTURE, CONFIGURATION,
  ORRIN_LANGUAGE_PLAN, docs/README); none move. No change.
- **`CLAUDE.md` / `AGENTS.md` / `Makefile` / `scripts/`** — no references to any moved
  doc. No change.
- **`demo_runs/**` analyses** that mention a moved doc (e.g. the 06-29 analysis →
  GROUNDED_COGNITION_DIRECTION) — permanent point-in-time history; **leave stale on
  purpose** (a run report should reference what was live *at the time*).
- Moved-doc → moved-doc links (both land in `archive/`) — acceptable; don't chase.

### D5d — verify + diff
- [x] Link-check every live doc, not just README:
  `for f in $(find docs -name '*.md' -not -path '*/archive/*'); do grep -oE '\]\(([^)]+\.md)\)' "$f"; done`
  → confirm each target resolves (accounting for the moves).
- [x] `find docs -name "*.md" -not -path "*/archive/*" | sort > /tmp/docs_live_after.txt`;
  diff against the D0 baseline — the delta = exactly the D1 moves + the new 2026-07-01 docs.

**Done when:** `docs/README.md` **and** `frontend/README.md` **and** the two live docs in
D5b list/point only at live paths (or resolvable `archive/` paths), every live-doc link
resolves, and the before/after diff matches the intended moves. The D5c set is confirmed
untouched.

---

## One-screen: what stays live and why (post-clearance target state)

| Track | Live after clearance | Why still live |
|---|---|---|
| root | `README.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `NEXT_RUN_TESTS.md`, this plan | Reference + the §8 gate + this clearance plan |
| Behavioral | `CODEBASE_AUDIT`, `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION`, `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE`, `B3_DECAY_DIAGNOSIS`, all `demo_runs/` | Active plans + open diagnosis + run history |
| Core Architecture | `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN`, `GROUNDED_COGNITION_IMPLEMENTATION_PLAN`, `TOPDOWN_WRITEBACK` | Active/blocked build work |
| Language & Cognition | `ORRIN_LANGUAGE_PLAN`, `THOUGHT_OBJECT_SPEC`, `ORRIN CREATIVITY NOVELTY PROPOSAL` | Living specs + blocked proposal |
| Engineering & Code Health | `OWNERSHIP`, `STRUCTURAL_RISK_REGISTER` | Living reference + standing register |
| Capability… | `BENCHMARKS` | Living reference |
| UI… | (empty if UI plan archived in D1) | — |

*Authored 2026-07-01. This plan is itself LIVING — check the boxes as you go; it can
archive once the tree is clean and the README diff matches.*

**EXECUTED 2026-07-02 (all phases D0–D5).** All boxes checked. The corrected audit-note
wordings were used everywhere the plan's original text was flagged stale (D2 statuses;
D4 option (a) — `DEMO_RUNS.md` moved to the `demo_runs/` root and rewritten as a real
index; D5a full README rewrite; D5b including the two backtick-mention repoints in
CODEBASE_AUDIT). Link-check passed (every live-doc `](….md)` target resolves) and the
before/after live-list diff equals exactly the D1 moves + the DEMO_RUNS relocation.
Per D3 this checklist stays live and archives together with `CODEBASE_AUDIT` and the
audit-remediation plan once AR1–AR9 land and the staging run passes.
