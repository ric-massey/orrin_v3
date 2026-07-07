# 2026-07-05 Run — Index

**Life:** born 2026-07-05T03:02Z, 15,554 cycles, ~16 h alive in a ~26 h span,
two segments (silent mid-life death + relaunch), operator stop 04:54Z Jul 6.
**Dirty instance** (habituation/EMA carried over) — staging run, not the
official Run 4 acceptance.

> The 2026-07-06 first-pass versions of these docs contained material errors
> (wrong run boundaries; "synthesis goal stalled"; 166 tracked_work rows read
> as healthy production). The core run docs below are the corrected second pass;
> `2026-07-05_deeper_pass.md` is a third-pass synthesis built on that correction,
> `2026-07-05_code_connection_audit.md` is a fourth pass from the code/data
> seams, `2026-07-05_followback_audit.md` is a fifth pass through secondary
> helpers that turned out to matter, and
> `2026-07-05_data_store_relationship_audit.md` is a sixth pass through large
> data stores and their cross-file meanings.

## Read in this order

1. **[DEMO_RUN_2026-07-05.md](DEMO_RUN_2026-07-05.md)** — verdict + the nine
   §8 signals. Headline: **S8 PASSED (0 desyncs / 223 completions, A1
   proven)**; production-loop telemetry first-ever nonzero (tail segment
   292/124/28; reset-safe row totals 528/352/168); the 197 KB "manuscript" is
   one template stamped 166×.
2. **[2026-07-05_run_analysis.md](2026-07-05_run_analysis.md)** — forensic
   detail: timeline, manuscript autopsy, aspiration-failure loop, candidate
   economy (1,508→224→51), lane-blind EMA, reproduction commands.
3. **[2026-07-05_deeper_pass.md](2026-07-05_deeper_pass.md)** — third-pass
   synthesis: the shared architectural pattern behind F1-F9, especially the
   split between semantic knowledge and control authority.
4. **[2026-07-05_code_connection_audit.md](2026-07-05_code_connection_audit.md)**
   — fourth-pass code/data connection audit: production counter reset,
   candidate-only funnel, sidecar/material mismatch, memory instrumentation
   flood, id-less goals, and classifier seams.
5. **[2026-07-05_followback_audit.md](2026-07-05_followback_audit.md)**
   — fifth-pass follow-back through peripheral helpers: binding/writeback,
   goal lens, satiety traversal, milestone proxies, plan pruning,
   `maybe_complete_goals`, and the good guards worth preserving.
6. **[2026-07-05_data_store_relationship_audit.md](2026-07-05_data_store_relationship_audit.md)**
   — sixth-pass data-store audit: memory graph orphans, ledger/material
   classes, production-loop lag, evaluator reward, completed-goal consistency,
   relationship bloat, opinions, knowledge graph, and replay-language data.
7. **[2026-07-05_who_is_he.md](2026-07-05_who_is_he.md)** — the life as
   lived: 3 h of real introspection, 20 h of treadmill, 388 copies of one
   sentence, a value executed 104 s before death, and the first clean will.
8. **[2026-07-05_findings.md](2026-07-05_findings.md)** — F1–F9 fix list for
   Run 5 with mechanisms, fix shapes, and pass criteria.

## One-line verdict

The skeleton is finally sound — stores don't desync, garbage doesn't get
paid, production hands off — but the *making* organ has no content inside it,
the failure machinery can kill values, and the memory system keeps the spam
and composts the writing.

## Top blockers for Run 5

1. **F1** compose_section: template stamper + retry treadmill + daemon lane
   invisible to the reward EMA
2. **F2** aspirations fail-able (`output_producing` died at 04:52:30Z)
3. **F3** learned-note bodies destroyed by pruning/decay; CSS junk kept
