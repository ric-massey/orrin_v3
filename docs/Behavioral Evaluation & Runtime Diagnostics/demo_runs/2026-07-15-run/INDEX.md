# Run 8 (2026-07-15) — reading order

Eighth acceptance life. **9,785 cycles across two runtime segments split by a
mid-life crash** (`make_candidate` keyword-only dispatch TypeError at cycle
~4418 → 6.5 h zombie → relaunch with fix). Staging run for
`RUN8_FIX_PLAN_2026-07-14.md` F1+F2 (`fc2b635`) + the `invoke.py` crash fix
(applied at the seam, since committed in `e70ac98`).

**Verdict: the monopoly finally broke (90.9 % → 42.6 %) — but by F2, not F1, and
the gate as written does not return PASS.** The ≥6-run committed-goal monopoly is
gone: all four aspirations drove the slot, `genuine_contact` committed for the
first time, and it holds in both segments (54 % pre-crash / 44 % post-fix, both
< 60 %). But **F1 (the absolute staleness refractory) never fired** — F2's
aspiration rotation kept the slot turning so staleness never accumulated to the
250-cycle trip. `G2` (release must fire) is therefore unmet, and `G5` regressed
on reuse (2 < 4). Objective met; formal gate not passed; **F1 unproven → run the
`ORRIN_STALE_REFRACTORY=0` ablation next.** Full analysis in
`DEMO_RUN_2026-07-15.md`.

| Order | File | What it answers |
|---|---|---|
| 1 | `RUN_CAPTURE_2026-07-15.md` | Run boundaries (two segments + crash timeline), preconditions, snapshot manifest, raw headline numbers |
| 2 | `DEMO_RUN_2026-07-15.md` | **Verdict**: §0 crash forensics, ten-signal grade, G1–G5 gate, why F2 (not F1) broke the monopoly, open items → Run 9 |

Data: `data/` (brain/data snapshot incl. `production_loop.jsonl.gz`, the
driver-slot source), `logs/` (`crash.log`, `CRASH_TRACEBACK.txt`,
`run_boundaries.txt`, `error_log.txt`, map-territory audit),
`artifacts_readable/` (21 effect artifacts).

Gate scoring at a glance: **S1 ✅ · S2 ✅ · S3 ✅ · S4 🟡 · S5 ✅ · S6 🔴 · S7 🔴 ·
S8 ✅ · S9 ✅/🟡 · S10 ✅** — and **G1 ✅ · G2 ❌(F1 never fired) · G3 ✅ · G4 ✅ ·
G5 🟡(reuse regressed)** → `G1 ∧ G2 ∧ G4` = **NOT passed as written**, objective
achieved by F2. *(S4 softened ✅→🟡 and S7's "referent-less" retracted in the
second-pass audit — see verdict §4b: reuse rows resolve via `content_hash`, and
both reuse events are time-locked to goal failures.)*
