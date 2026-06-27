# Pre-Run Note — 2026-06-24

**Purpose:** state, before the run, exactly what changed since the last run and
what each change is supposed to do — so the post-run analysis can check behaviour
against intent instead of guessing.
**Baseline (last run):** `2026-06-19-run`.
**Code state:** branch `goals-master-plan` (GOALS_MASTER_PLAN Parts I & II committed;
PRODUCTION_LOOP_CLOSURE + structural-debt §9 already on `main` since 06-19).
**Boot/health check:** full app boot + one cycle (`ORRIN_ONCE`) exits 0, no
tracebacks; 640 tests pass (2 pre-existing unrelated failures, present on `main` too).

---

## TL;DR — what this run is testing

Three bodies of work landed since 2026-06-19. In order of how new / how much
behaviour they change:

1. **Goal architecture (NEW today)** — a survival/homeostatic goal layer, and an
   inversion of where the committed goal comes from (v1 cognitive tree is now the
   source of truth, v2 just executes). **Highest-risk, least-proven.**
2. **Production-loop closure (06-20)** — reward now credits real output/artifacts,
   so "make things" should stop collapsing into busywork.
3. **Silent-handler cleanup (06-19→)** — ~360 swallowed exceptions reclassified.
   Mostly hygiene, but it can *surface* errors that used to be silent.

The single most important question this run answers: **does the new v1-authoritative
goal pipeline keep Orrin committing to, pursuing, and CLOSING goals over many cycles
without starving, thrashing, or leaking?**

---

## 1. Goal architecture — GOALS_MASTER_PLAN Parts I & II (NEW, 2026-06-24)

### Part I — survival / homeostatic goal layer
The autonomic→cortical bridge that was previously built-but-unwired.

| What now happens | Watch for (good) | Watch for (bad) |
|---|---|---|
| **Acute preempt** — a *critical* vital signal interrupts the committed goal for the cycle (2-cycle hysteresis), then resumes. | When a vital signal goes critical, pursuit yields that cycle (`reason="survival_preempt"`) and resumes after. | Per-cycle flip-flop (slot thrash) between a goal and the preempt — hysteresis should prevent this. |
| **Chronic recruit** — a deficit neglected ≥5 cycles becomes a real `tier="survival"` restoration goal whose first step is the alert's `suggested_fn`. | A "Restore: …" goal appears only after sustained neglect; deduped (one per deficit). | Survival goals spamming/duplicating; recruiting with no real deficit. |
| **Survival rules** — survival goals are non-disengageable and go **dormant** (not completed) when satisfied, re-firing after ≥30 min. | A satisfied survival goal goes dormant, returns later. | A survival goal getting Wrosch-abandoned; or re-firing instantly (no cooldown). |
| **Tier closure** — core goals close on *satiety*, not just plan-completion (`ORRIN_TIER_CLOSURE` on). | Goals close when the need is met, not stuck waiting for an empty plan. | Premature closure (cycle-1 / hollow) — guards should block this. |

### Part II — v1/v2 goal storage collapse (Option D)
- **Field ownership:** `tier`/origin now survive the v2 round-trip via the spec
  projection. **Check:** a recruited survival goal stays `tier="survival"` end-to-end
  (previously it silently became `"generic"`).
- **Lifecycle inversion (all-in, no flag):** the committed goal is chosen from the
  **v1 cognitive tree**; v2 is the execution projection only.
- **Workspace binding (D3):** the goal Orrin is *aware of* carries the committed
  goal's id — awareness and pursuit are bound to one object.

### ⚠️ #1 thing to watch this run
A goal that **originates in v1**, gets projected to v2, and finishes executing may
**not close in v1** — the v2 id isn't written back onto the v1 node yet, so the
completion/failed event can't reconcile. **Symptom:** an executable goal (coding /
research) "runs, produces, but never closes" in the v1 tree, or re-commits forever.
If seen → targeted fix-forward (write the v2 id back at projection time).

Secondary goal watch-items:
- **Starvation:** does Orrin always have a committed goal, or does the v1-tree
  selector ever return empty when it shouldn't?
- **Duplication:** the v2→v1 reconcile (`_reconcile_open_v2_into_v1`) should absorb
  each open v2 goal exactly once — watch for duplicate nodes.
- **Rut regression:** the 2026-06-17 "goal-rotation rut" (cycle internal goals, never
  reach external work) — did survival/recruit/tier-closure + v1 selection improve it?

---

## 2. Production-loop closure (2026-06-20, already on main)

Reward was previously denominated in internal events (intake paid the same as
production), so Orrin made little. Now: an effect ledger + reward split + fail-able
artifact goals + tier-3 artifact re-use credit + hardened `leave_note` provenance +
persisted production telemetry.

- **Watch (good):** Orrin actually produces artifacts (notes/syntheses/code) and is
  rewarded for *output*, not for going-through-the-motions; `output_producing` /
  `genuine_contact` goals get committed and completed.
- **Watch (bad):** production goals failing on the artifact gate without ever
  producing; reward still flat regardless of output.
- This run also serves as PRODUCTION_LOOP_CLOSURE's pending runtime demos (5.2/5.3).

---

## 3. Silent-handler cleanup (2026-06-19 onward, on main)

~360 silently-swallowed `except` blocks reclassified down to a permanent floor of 3.
Purely structural, but consequential for a run: **errors that used to be swallowed
may now log or raise.**

- **Watch (good):** clean logs; any genuine error is now visible instead of hidden.
- **Watch (bad):** a previously-masked bug now surfaces as a logged failure or a
  louder error path. This is *desirable* (we want to see them) but may look like a
  regression — judge by whether the underlying behaviour is actually worse.

---

## Known non-blockers / caveats (don't mistake these for regressions)

- **Dashboard valence is misleading.** A known observability remap compresses
  distress into a flat ~0.6 (see `DEMO_RUN_FIXES_2026-06-17`). **Read raw
  `brain/data/affect_state.json`** (`valence`, `mood`, `core_signals.impasse_signal`)
  for true affect, not the dashboard number.
- **Restart gotcha.** If using `run_orrin.sh`, its auto-restart can wedge unless the
  Vite frontend process group is also killed.
- **Unwired telemetry.** Some stats (e.g. `gate_report`) aren't surfaced in the UI
  yet (UNWIRED_TELEMETRY_UI_PLAN, proposed) — absence in the UI ≠ broken.

---

## What to capture for the post-run analysis

- `brain/data/affect_state.json`, `telemetry_history.json`, `goals_mem.json` (v1
  tree), `data/goals/` (v2), `brain/logs/orrin_runtime.log`.
- Goal lifecycle trace: did goals commit → pursue → **close** (not just rotate)?
- Any survival preempt/recruit events, and whether they were warranted.
- Whether any executable goal finished but failed to close in v1 (the #1 watch).
- What he actually **made** (artifacts), and whether reward tracked output.

---

## Success criteria for this run

1. Boots and sustains many cycles with no crash / no new error storm.
2. Goals commit, pursue, and **close** — no permanent rotation rut, no starvation.
3. Survival layer behaves only when warranted (no thrash, no spam).
4. At least one real artifact produced and rewarded as output.
5. No executable goal stuck "done but never closing" in v1 (or, if seen, it's the
   known v2-id-writeback gap — log it for fix-forward).
