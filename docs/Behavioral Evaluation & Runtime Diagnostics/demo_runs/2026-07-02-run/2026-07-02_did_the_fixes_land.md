# Did the fixes land? — P2–P8 + AR1–AR9 intent vs. behaviour

**The fixes under test:** this was the staging run for *two* stacked builds —
Grounding & Surface Phases 2–8 (commit `f1ad35f`; P1 was validated on the 07-01
run) and Audit Remediation AR1–AR9 (commit `db4a139`, "make the making real").
Companion §8-gate verdict in `2026-07-02_run_analysis.md`; this doc is the
per-mechanism read. UI surfaces (P7's panels) are out of scope here by request —
only the runtime side is judged.

**How we know it ran:** clean newborn via `reset_orrin.py` at 07:18 EDT (pre-reset
snapshot archived), single launch, 10,071 cycles, graceful operator stop. Both
commits were in the tree at birth; their fingerprints are all over the data
(`symbolic_artifact` ledger kind, `ltc_aspiration-*` goal ids, `research`-kind
goals, `prediction_metrics.jsonl` — none of which existed before these builds).

---

## Grounding & Surface P2–P8

| Phase | Intent | Observed behaviour | Verdict |
|---|---|---|---|
| P2 — graded signal reaches every learner | selection follows learned value | §8 **S9 moved**: high-EMA `research_topic` (0.614) share 8.7%→15.7% over the last 3k ticks, `generate_intrinsic_goals` dethroned from #1, low-EMA actions falling; reward EMAs span 0.16–0.77 and picks track them | ✅ **landed** (behaviourally; the LM-diet half has no direct runtime meter yet) |
| P3 — produce-and-check loop | machine-verifiable production replaces hollow notes | built, **top** reward EMA (0.7651), 8 conscious picks (avg reward 0.805), 679 daemon-lane `step_exec` executions — but `production_attempt_count` **0** all run: the funnel/handoff counters never saw any of it | 🔴 **built, executed, unmetered** — the S7 lane split; bridging it is next-fix #3 |
| P4 — long-term goals actually drive | a committed long-term thread through planning | `ltc_aspiration-self_understa_1/2` committed most of the run (`committed_goal_present: true` at death); **31 ledger rows attributed to ltc goals** | 🟡 **drives, doesn't credit** — attributions never reached `mark_objective_contribution` (S6 fail, all 4 links broken) |
| P5 — homeostatic decay on appraisal (B3) | drives breathe instead of pinning | curiosity 0.253–0.892 (mean 0.636), motivation 0.50–0.887, confidence 0.45–0.871; hundreds of full sag-and-recover arcs vs 07-01's 0.81–0.84 flatline; "hot and flat" self-report 70×→1× | ✅ **landed — closes B3** (`B3_DECAY_DIAGNOSIS` archived) |
| P6 — veil sealed (substrate → consciousness one-way) | no internal diagnostics leak to the person-facing surface | all 10 chat replies membrane-composed; honest uncertainty ("Don't have a strong view on that yet") instead of substrate dumps; no dotted-path/gate-category goal subjects born (AR7's rejection working) | ✅ **landed**, one blemish: replies quote raw internal goal *titles* verbatim, including the title-dup bug ("Understand beyond Understand my own mind…") |
| P7 — lived surface + ablation panel | telemetry plumbing for the felt state | the 10,065-row telemetry archive this analysis is built on came through the P7 plumbing; UI panels not assessed here | 🟢 runtime side working; UI out of scope |
| P8 — structural tax | risk register, ongoing | not a runtime behaviour; register committed pre-run | n/a |

## Audit Remediation AR1–AR9

| Item | Intent | Observed behaviour | Verdict |
|---|---|---|---|
| AR1 — every durable artifact records an effect (keystone) | ledger sees symbolic making | **116 `symbolic_artifact` rows** (113 causal-edge establishments, 3 crystallization batches) + 3 runner `file_write` rows; rate-cap and dedupe visible (34 rows deduped); **S5 moved to 1.114 because of this** | ✅ **landed — the run's biggest win** |
| AR2 — understand goals become `research` kind with a real handler | extractive memos instead of hollow reads | 3 `research`-kind goals born with handler specs and **scheduled** (search steps ran 3× each) — but all 9 search attempts crashed with `RuntimeError: ctx.web_search hook not provided`, steps went FAILED, goals stuck READY; no memo produced *(corrected 2026-07-02 second pass — originally misread as "never scheduled")* | 🔴 **wired end-to-end except one missing runner hook** — see `2026-07-02_deeper_pass.md` §5 |
| AR3 — LLM-off drafts from the native LM | composed sections come from the organ | no `compose_section` artifact was attempted this run | ⚪ **not exercised** |
| AR4 — making pays per attempt | produce/compose actions earn intake-comparable credit | `produce_and_check` avg reward **0.805**, top EMA 0.7651 — the pay circuit works. Caveat from the second pass: the final 1.7 h were a stuck-step loop executing it ~8×/min, so part of that EMA is a loop paying itself (`deeper_pass.md` §4) | ✅ **landed**, EMA reading needs the lane fix before it's trustworthy |
| AR5 — birth-rate quota (make/connect floor 25%, intake cap 60%) | goal births stop being all-intake | births this run: 2 housekeeping/deps, 3 introspective trace, 3 research-understand; the funnel's candidate stream is still overwhelmingly "Understand X" | 🟡 **inconclusive** — only ~8 tracked births, too thin to judge the rolling-window quota |
| AR6 — prediction errors to capped jsonl, WAL boot replay | long memory stops silting | `prediction_metrics.jsonl` present, 1,870 rows; single-launch run so boot-replay path untested beyond birth | ✅ **landed** (capped-file half verified) |
| AR7 — felt-state notes deliver but never credit; diagnostic strings rejected as subjects | hollow notes stop paying | `note_novel` collapsed 1,680→**31 rows, all significance 0.0**; zero credited; no internal-identifier goal subjects observed | ✅ **landed** |
| AR8 — resource-deficit dynamics; allostatic arming reachable | rise-and-recover, no flatline | drives rise-and-recover all life (see P5) — but `allostatic_load` **0.000 for the entire run**, energy-mode active EMA 0.487, never near the 0.60 arming line | 🟡 **half-landed** — the flatline is gone, the allostasis layer is still inert (standing invariant since 06-29) |
| AR9 — boot write-probe fails loudly; reset targets identity + artifacts | clean births | this run's birth *used* `reset_orrin.py` — clean newborn, archived snapshot, no stale identity | ✅ **landed** (happy path) |

---

## What the scorecard means

**The honesty layer is done.** AR1+AR7 together inverted the ledger: last life it
was 1,680 hollow notes and nothing else; this life it is 116 real symbolic
artifacts and 31 uncredited notes. P5 freed the drives. P2/AR4 made value flow into
selection (S9). Five of the nine AR items landed clean, and nothing regressed —
zero crashes, zero desyncs, clean death.

**The connection layer is not.** The two §8 failures are both *seams between
working parts*: P4 drives long-term goals and attributes effects to them, but the
attribution never becomes aspiration credit (S6); P3+AR4 make produce-and-check the
most-valued and most-executed making action, but the production funnel meters a
different lane and counts 0 (S7). Add AR2's research goals that route and schedule
correctly but crash on a missing `ctx.web_search` runner hook, and the pattern of
this run is: **every organ works, three handoffs are missing.**

**One prediction check for Run 3:** if the S6/S7 seam fixes in `run_analysis.md`
land, S5 and S9 should *hold* without retuning (they depend on AR1/P2, which are
independent of the seams). If S5 regresses when the lanes are bridged, the
significance numbers were partly an artifact of what wasn't being counted.

*Generated 2026-07-02 from runtime data after a clean operator stop. Analysis only;
no code changed by this write.*
