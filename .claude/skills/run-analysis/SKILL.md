---
name: run-analysis
description: Standing discipline for Orrin staging-run work — capturing a life, scoring it against the gate in docs/NEXT_RUN_TESTS.md, or doing a skeptic pass over the code. Use whenever the user asks to capture a run, score a run, write a verdict, analyze a life, or audit run evidence.
---

# Orrin run analysis — standing rules

Lessons paid for across Runs 1–9. Every one of these exists because skipping
it once produced a wrong or unattributable conclusion. Do them every time,
even when the run "looks clean."

## Before scoring anything

1. **Establish the run's shape first**: boot count (`grep "Run stamp"` across
   `activity_log.txt` + `rotated/`), cycle contiguity in
   `production_loop.jsonl`, birth/death timestamps, death reason per segment.
   Segments change every denominator.
2. **State the LLM mode up front** in the verdict: `mode: symbolic-only` or
   `mode: LLM-assisted` (check for `[ask_llm] Blocked` lines). Memo quality,
   exemplar promotion, and synthesis conclusions are mode-dependent — Run 9's
   first-ever promoted exemplars were offline scrape-stitches because nobody
   noticed the mode.
3. **Name the build commit.** If the life ran on uncommitted code, say so
   loudly in the verdict — Run 9 has no commit hash and can never be
   reproduced. Push for: commit before launch, SHA in the boot Run stamp.
4. **Check the log isn't lying**: `run_orrin.sh` tee output block-buffers
   (looks frozen); trust `brain/data` mtimes, not the log tail. `crash.log`
   cycle numbers can be stale buffered stdout — the `production_loop` cycle
   seam is the only crash-accurate counter.

## Capture (before any reset touches anything)

- `brain/data/`: `outcome_metrics.json`, `effect_ledger.jsonl`,
  `comp_goals.json`, `goals_mem.json`, `action_reward_ema.json`,
  `commitment_signals.json`, `production_loop.jsonl`, `production_funnel.json`,
  `aspiration_scoreboard.json`, `failures.jsonl`, `habituation.json`
- `activity_log.txt` **plus all of `rotated/`** (the life usually spans 6–9
  rotated files)
- The **full `data/goals/` daemon tree** (WAL + state + snapshots +
  artifacts) — verify the copy with `diff -rq`. Run 8 lost this and the
  diagnosis had to mine the live WAL.
- Folder convention: `docs/Behavioral Evaluation & Runtime Diagnostics/
  demo_runs/<date>-run/` with `data/`, `logs/`, `goals_daemon/`, and a
  `DEMO_RUN_<date>.md` verdict. Add the run's row to `DEMO_RUNS.md` and a
  result block in `docs/NEXT_RUN_TESTS.md`.

## Scoring — non-negotiables

- **Score every historical monopoly layer, every run**: ignition source,
  candidate-generator flavor, committed-goal occupancy, value EMA. One
  `uniq -c` each. The monopoly relocated through layers that had stopped
  being scored (Runs 2→8), and ignition saturation (10,278/10,278 ignited,
  `drive_mastery` pinned at 1.00) went unseen because ignition scoring
  stopped after Run 3.
- **Reset-safe totals**: sum `production_loop.jsonl` booleans across the
  whole file; never trust tail cumulative counters (they reset at relaunch).
- **Run the §6 read-side checks** in `docs/NEXT_RUN_TESTS.md` (funnel stages
  beyond `candidate`, material classes, goal-id coverage, cooldown truth,
  speech grounding, writeback pressure, delayed-reward sources).
- **Honest-failure checks** (Run 8/9 lesson): no step `attempts` >
  `max_attempts`; no DONE→FAILED flap; failed goals carry a real
  `last_error`; a "FAILED" goal with artifacts on disk means either the
  runner race or misfiled drive-by intake — distinguish them (check artifact
  topic + provenance vs the goal title).
- **Reuse rows**: verify real `cycle` + `metadata.path`, subject-token
  overlap with the citing goal, and whether the citing goal succeeded (Run 8:
  reuse was time-locked ≤250 ms before failures — always check).

## Standing skeptic questions (ask on every pass, not just gate items)

- Any **gate-blocked or structurally impossible action with a healthy reward
  EMA**? (Run 9: `decide_to_write_code` blocked 369/369, EMA #2 at 0.618 —
  reward pays gesture unless proven otherwise.)
- Any **signal flat at a bound** (0.0 or 1.0) for hundreds of cycles? A
  threshold fed by a saturated signal is a wire, not a gate.
- Any **rule/knowledge hit-count growing faster than ~1×/cycle**? That's loop
  noise wearing a confidence score (Run 9: 66,087 hits on one rule).
- **Does the causal graph have any non-interoceptive edge yet?** (Run 9:
  241/241 self-edges.)
- **Do instruments still measure anything?** Funnel stages nothing reaches,
  unwired stats fns — flag dead instruments; they create fake coverage.
- **Same title, two goal ids?** The dual-store seam manufactures desyncs,
  double-failures, and fake honest-failure violations.

## Ground-truth discipline (read before building any fix off an analysis)

- **Test a fix/check against the REAL artifacts, not your description of them.**
  A claim in a prior verdict — or one you made earlier this session — is a
  hypothesis, not ground truth. `Read`/`grep` the actual files the check will
  run on and confirm the pathology is where you think before writing, then run
  the check against those real files and confirm it fires on the true positive
  and spares the true negatives. (2026-07-18: the exemplar originality veto was
  built to the claim "one exemplar is a pasted abstract"; the first version
  passed all three because the scrape came from a different code path than
  assumed. Only reading the real files revealed the true signal — the artifact's
  own `source:` provenance footer.)
- **Provenance beats heuristics.** Prefer the fact the system already records
  about itself (a `source:`/stamp/ID footer, a WAL field) over any text
  heuristic layered on top. The self-declaration is exact; the heuristic guesses.
- **Confident prose ≠ correct answer.** The bridge between them is running it
  against reality. When a synthetic-only test passes, it has told you the code
  runs, not that it catches the real thing.

## Attribution discipline

- **Prefer a forced-fire harness test over a life observable** whenever the
  code path is reachable in a test (the R9-F7 pattern: the refractory is
  proven by `tests/brain/test_refractory_harness.py`, not by waiting a life).
- When two levers ship together, **pre-register which observable separates
  them** before launch — Run 8 shipped F1+F2 bundled and couldn't attribute
  the win (it was F2; F1 turned out unreachable).
- A signal that pattern-matches a known failure may have a new cause: run the
  second-pass audit (the Run 8 §4b convention) before letting a red stand.

## Verdict framing

- Per-signal scoring against the exact gate text, verbatim thresholds. A miss
  is "**failed fix, not a matter of interpretation**" — never reinterpret the
  gate to pass it; if the gate itself is wrong, rescore it explicitly in a
  dated section (the G2 harness rescoring pattern) rather than silently.
- End every verdict with a numbered next-run fix list with **per-item
  observables** (what number moves, read from which store).
- Update memory (`project_staging_runN_capture`) and the `MEMORY.md` index
  line when the verdict lands.
