# Run 7 (2026-07-12) — reading order

Seventh acceptance life. **11,060 cycles, ~8 h, zero crashes, clean death.**
Staging run for the Run 7 fix build (`RUN7_FIX_PLAN_2026-07-11.md` F1–F8,
commits `a63b160` + `bb3685a`).

**Verdict: gate NOT passed — but the run that isolated the cause.** The Run 7
credit/pump fixes all landed (pump dead 0.5196, memo loop gone, content-keyed
credit proven: incumbent earned 1 vs producer's 7) and the 90.9 % commitment
monopoly survived *anyway* — so it is structural, not a reward artifact. Two
reinforcing causes found: relative-penalty saturation with no eligible rival, and
a directional rotation pool with exactly one member (only `self_understanding` is
flagged `directional`). Full analysis in `DEMO_RUN_2026-07-12.md`.

| Order | File | What it answers |
|---|---|---|
| 1 | `RUN_CAPTURE_2026-07-12.md` | Run boundaries, preconditions, snapshot manifest, raw headline numbers |
| 2 | `DEMO_RUN_2026-07-12.md` | **Verdict**: nine-signal grade, F1–F8 fire check, commitment forensic timeline, root cause (§4), what improved, open items, Run 8 gate |

Data: `data/` (brain/data snapshot), `goals_daemon/` (root data/),
`artifacts_readable/` (this run's memos + synthesis), `logs/` (runtime +
goal-progress + map-territory audit + crash.log).

Raw headlines (unjudged — see the manifest for caveats): value pump **deflated**
(`self_understanding.value_ema` 0.5196 vs Run 6's poisoned 0.8142; no memo loop,
max single-file rewrite 2× vs 403×; quality revisions 13 vs 200) — yet
committed-goal share still **90.9 %** on `self_understanding`, held with
`stale_cycles` 10,291 / `avoid_streak` 6,852. First captured `synthesis.md`.
Reuse 4. Desyncs 0 (3rd clean run). Satiety closures 12. `write_exemplar`
still blocked (EACCES ×2 + the new boot-time diagnostic firing). Production
funnel still candidate-only.
