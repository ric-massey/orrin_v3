# Did the fixes land? — the 2026-07-02 fix round, intent vs. behaviour

**The fixes under test:** the 12-item root-cause round from
`../2026-07-02-run/2026-07-02_fix_round_record.md` (commit `dc0bce4`,
"Post-run fix round 2026-07-02: unblock S6/S7"), which implemented every fix
from `2026-07-02_why_every_problem.md`. The fix-round record ends with a
7-point "What Run 3 should show if these landed" checklist — this doc grades
each fix against the run, then the checklist.

**How we know it ran:** clean newborn via `reset_orrin.py` at 21:55 EDT
(snapshot archived), boot 22:04 EDT, single launch, 11,333 cycles, graceful
operator stop at 12:15 EDT. The fixes' fingerprints are all over the data
(`failures.jsonl` rows, `goal_web_hooks` search steps, ledger `goal_id`
everywhere — none of which existed before the round).

---

## The twelve fixes

| # | Fix | Intent | Observed behaviour | Verdict |
|---|---|---|---|---|
| 1 | Rest-drive leak + `consolidat` keyword + dream-launch `satisfy` | rest can never saturate; discharge exists | `drive_rest` **0.599 at death** (design equilibrium ≈0.67), **zero** `drive_rest@` ignitions all run (Run 2: ~7,420), 5 dream cycles on a clean 3-h cadence each firing `satisfy("rest", 0.6)` | ✅ **landed — the horn is unjammed** (but see the new jam, `deeper_pass.md` §1) |
| 2 | AR2 unblocked: `goal_web_hooks` (search + fetch) into GoalsDaemon ctx | research goals reach `synthesize` | **11 `research_memo.md` files written** (cycles 1,383→11,132 — first real research memos of any life); 9 research goals DONE; 3 FAILED honestly (34 `no URLs to fetch` + `step_failed`, all machine-recorded); 0 stuck-READY research goals; zero `ctx.web_search hook not provided` errors | ✅ **landed — the run's biggest win** |
| 3 | Ledger attribution (bound-goal mirror + persisted cycle fallback) | no more anonymous, time-blind effects | `goal_id: null` **0 of 171 rows** (Run 2: 116/150); `cycle: 0` **2 of 171** (Run 2: 119/150 — the 2 are boot-second housekeeping writes); attribution spans 15 distinct goal ids incl. all four `ltc_aspiration-*` families | ✅ **landed** |
| 4 | S7 funnel drains the ledger (`drain_recent_rows` → `production_telemetry`) | attempts counted from every lane | `production_attempt_count` **163** (Run 2: 0 across 10,071 cycles), successes **102** (= exactly the 102 nonzero-significance ledger rows), rejections classified (33 duplicate, 28 low_significance); attempts spread across all 12 thousand-cycle buckets | ✅ **landed** — handoffs still 0 (conscious lane never stages production; that's a missing behaviour, not a metering gap) |
| 5 | S6 crediting receives (`serves`/`driven_by` stamps, archived-skip, ledger partial credit) | aspirations come off 0% | **all four aspirations credited**: contact 5 / making 2 / self-understanding 5 / world 2, progress 0.26/0.10/0.25/0.10; every `comp_goals` entry carries `serves` + `driven_by`; scoreboard funnel 162 generated → 14 attempted → 14 completed (Run 2: 87→2→0) | ✅ **landed — S6 passes** (credit-quality caveat: the 2 "making" credits are research goals, `deeper_pass.md` §5) |
| 6 | Title-dup fixed at the source (`_bare_topic`) | no "Understand Understand…" | **0 occurrences** in logs, comp_goals, goals_mem, chat | ✅ **landed** |
| 7 | v2 runner status honesty (started_at, failure cascade, machine records) | failed keystone ⇒ FAILED goal | 3 research goals whose search steps died went **FAILED** (Run 2's identical failure left them stuck-READY); goal-level failure records written | ✅ **landed** — separate gap: 2 *generic*-kind goals sat READY unscheduled all run (scheduling coverage, not status honesty) |
| 8 | Person model writes on interaction | sessions/messages accumulate | `known_persons.json`: `session_count` **2**, `messages_received` **12**, `last_seen` 16:11:14Z — **4 minutes before death** (Run 2: everything frozen at birth) | ✅ **landed** |
| 9 | Machine-readable failure telemetry | `failures.jsonl` non-empty when things fail | **94 rows** with ts/site/goal_id/title/reason, spanning 02:21Z→16:04Z (Run 2: 0 bytes across 9 failures) | ✅ **landed** |
| 10 | Stuck-loop economics (decaying make-bonus + watchdog un-blinding) | a loop can't pay itself into top EMA | `produce_and_check` has **no conscious EMA row at all** this run (0 conscious picks; Run 2's 0.7651 top-EMA is gone) — the pay exploit is closed. But `step_exec` still matched it **5,758×** at sim=0.35 on four "Establish …" step names, and the monitor filed **300 `stuck_step` verdicts (127 honored)** — the *loop* persists, unpaid and now metered | 🟡 **economics landed, behaviour remains** |
| 11 | Small plumbing (5 items) | — | `health_state.cycle` **11,330** real ✅ · habituation capped at **5,047 keys** (Run 2: 15,469) ✅ · identity string now routes through `explain_analogy` prose 🟡 (see `who_is_he.md` — still tag salad) · social-pressure `_ever_spoke` guard ❓ (pressure gating can't stop the *presence-signal* ignitions — see the new jam) · `final_thoughts_written` **still `False` at death** 🔴 (the one small fix that did not land) | 🟡 **3 of 5 clean** |
| 12 | Module-size + guardrail housekeeping | — | suite green (45 §3 tests; full-suite green recorded at fix time: 1,335) | ✅ |

## The "What Run 3 should show" checklist (fix-round record §end)

1. *"drive_rest cruising ~0.67, ignition diet diverse past hour 2, integrative
   organs writing all day"* — **first two-thirds: no.** Rest cruises (0.599 ✅,
   zero rest ignitions ✅) but the diet is NOT diverse: `social_presence` took
   84% of all ignitions (~90% past hour one), and the integrative organs went
   dark by ~01:11 EDT again (1 crystallized skill, 12 rule firings,
   `world_model_stats` last write 00:35). **The monopoly relocated.** 🟡
2. *"Research goals reaching synthesize with real memos, or failing honestly"* —
   **yes, both.** 11 memos + 3 honest FAILEDs. ✅
3. *"production_attempt_count > 0 tracking ledger activity; rows carry real
   cycle and goal_id"* — **yes.** 163/102, 0 null goal_ids, 2 zero-cycles. ✅
4. *"At least one aspiration off 0%"* — **all four.** ✅
5. *"No 'Understand Understand…' titles; identity story in prose"* — titles ✅;
   identity story half — prose-shaped but still bracket-tagged and truncated. 🟡
6. *"known_persons moving; failures.jsonl non-empty"* — **both.** ✅
7. *"S5 and S9 must hold"* — **S5 held (1.197 ≥ 1.114)** — Run 2's significance
   was real, not a metering artifact. **S9 did not clearly hold** — with the
   loop's self-payment removed, no EMA↔share coupling is visible (corr ≈ −0.15);
   the EMA is one minority term in the multi-factor ranker. ✅/❌

## What the scorecard means

**Ten of twelve fixes verified in the wild, and the two §8 signals they
targeted both moved.** This run inverts Run 2's diagnosis: then, "every organ
works, three handoffs are missing"; now the handoffs carry — attribution flows,
credit lands, memos exist, failures are recorded, the person persists. What
Run 2 could not see (because nothing completed, nothing was attributed, and
nothing was metered) is now measurable — and measurement immediately exposed
the next layer: a v1/v2 resurrection leak under completed goals (S8), a reuse
channel with no callers (S7's other half), an EMA with no real authority (S9),
and an ignition system whose monopoly simply moved from `rest` to
`social_presence`. That is what progress looks like in this codebase: each
fixed seam makes a deeper seam observable.

*Generated 2026-07-03 from runtime data after a clean operator stop. Analysis
only; no code changed by this write.*
