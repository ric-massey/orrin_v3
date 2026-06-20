# Production Loop Closure — Fix Proposal

**Date:** 2026-06-20
**Status:** PROPOSED
**Triggered by:** `docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-06-19-run/` (first life under the binding / goal-lens / comprehension / production machinery — 11,633 cycles, clean death)
**Scope:** `brain/think/think_utils/select_function.py` (or executive/drive routing), `brain/cognition/goal_lens.py`, `brain/cognition/leave_note.py`, `brain/ORRIN_loop.py` (committed-goal lifecycle)
**Related:** [[GOALS_AND_UNDERSTANDING_FIX_PROPOSAL_2026-06-20]] (implemented G1–G7; this is the G8 verification turning up a gap), `project_reward_denominator`, `project_binding_workspace`, `project_explore_exploit_value`

---

## 0. One-line statement

The comprehension→production loop was **built, wired, and proven safe** in the 2026-06-19 life, but it **never fired once**: `compose_section` (the real production capability) was selected **0 times in 11,633 cycles**, the `tracked_work/` directory was never created, and all 146 "production" events came from `leave_note` scraping filesystem noise. Result: **146/146 effects scored novelty 0.0 / significance 0.0, all four aspirations stayed at 0 % all life**, and felt-cost (distress, allostatic load) climbed monotonically with no relief. The two halves — comprehension and production — are each wired to the loop but **not to each other through the action that actually fires.** This proposal connects them.

---

## 1. What the run proved

The prior proposal ([[GOALS_AND_UNDERSTANDING_FIX_PROPOSAL_2026-06-20]]) added the goal **lens**, **comprehension**, and a **production capability** (`compose_section`), on top of the already-correct effect-ledger gate. The 2026-06-19 life was its first live test. Two clean results:

- **The machinery is safe.** `binding.py` + `goal_lens.py` ran every cycle for ~14 h with **zero exceptions**, and the process died cleanly. The fail-closed invariants held.
- **The scorer is honest.** 146 effect-ledger notes, every one `novelty 0.0 / significance 0.0`; all four aspirations `0 (0 %)`. Last life one aspiration falsely read 100 % (uncredited Wikipedia intake mistaken for progress); this life the tightened gate correctly reports **nothing was produced.**

The honest meter is the achievement. **The gap it exposes is the subject of this proposal:** the apparatus that is supposed to *produce* something worth crediting never engaged.

---

## 2. The defect, with evidence

### The smoking gun — `compose_section` was never selected

Full-life decision stats (`brain/data/_archive/snapshot_20260619_081225_pre_reset/decision_stats.json`):

```
 3768  generate_intrinsic_goals     ← #1, the drift spawn action
 1499  look_around
 1308  look_outward
  943  assess_goal_progress
  829  search_own_files             ┐
  488  search_files                 ├─ 1,712 filesystem-search picks → the junk note source
  395  grep_files                   ┘
  540  research_topic
  348  wikipedia_search
   19  leave_note
    —  compose_section              ← ABSENT. Selected zero times.
```

`brain/data/tracked_work/` **does not exist** — the production capability never wrote a single file. Every credited-as-zero effect came from `leave_note`, not from the capability built to satisfy production goals.

### Three root causes feed it

**R1 — `compose_section` is structurally unreachable in practice.**
The only thing that pushes the loop toward `compose_section` is `goal_lens.action_prior` (`goal_lens.py:34`): `+0.18` if the lens carries `tracked_work`, `+0.10` if `requires_artifact`, capped at `+0.36`. That nudge requires *all* of: (a) a non-null `committed_goal`, (b) `lens.active`, (c) the goal carrying `tracked_work`/`requires_artifact`. Against a drive baseline where `generate_intrinsic_goals` is picked **3,768×**, a one-time `+0.18` prior cannot win. And `compose_section` itself early-returns `{"success": False, "error": "No committed goal"}` (`compose_section.py:55`) without a committed goal — so it is a no-op exactly when the lens is also dark. **There is no ignition path for production, only a weak bias it can't cash.**

**R2 — The goal is committed too rarely, so the lens is dark most of the life.**
`apply_goal_lens` (`goal_lens.py:52`) activates *only* on `context["committed_goal"]`; with no committed goal it pops the lens and returns. The run's final conscious stream reads **"No committed goal right now,"** and the analysis confirms he was "frequently un-goaled" despite 9 live goals (5 dormant, 4 in-progress). Selection is **drive-first** (prior proposal §1.1): with no committed goal, the lens contributes nothing to *either* signal routing *or* the production prior, and the drives win by default → wandering + cheap `leave_note`. The comprehension layer correctly enriched goals with `grounded_parts` / `definition_of_done` (`goal_comprehension.py`), but that content is only consumed *through the lens*, which was off.

**R3 — The note path that *does* fire ignores the comprehended target and seeds from noise.**
`leave_note.py:42–58`: absent a degraded-goal topic, it scans the last 25 long-memory entries for `"from searching"` / `"finding was written"` / `"[world_perception]"` and seeds the note body with that payload. Those entries are the outputs of `search_own_files` / `grep_files` / `search_files` (1,712 picks) — i.e. `.lock` / `data` filename fragments from his own data directory. Hence the actual note bodies:

```
90 × "something present but hard to name / something pulling for attention"   (affect fallback)
 3 × "something I actually found out: .lock, .lock, , , .lock"
 1 × "something I actually found out: data , .lock, .lock, .lock,"
```

These fail `_unique_token_ratio < 0.25` and `MIN_ARTIFACT_CHARS = 120` (`effect_ledger.py:53,163`) → novelty 0.0, every time. **Critically, `leave_note` never consults `committed_goal.grounded_parts` / `definition_of_done`** even when they exist — the comprehended target and the firing action are not connected.

### The downstream cost

Because production-gated completion only relieves an aspiration's recruitment pressure on a *real effect-backed* contribution (`goals.py:602–608`), and nothing produced a real effect, **every aspiration stayed at 0 % all life** and the unmet-production pressure never discharged: distress climbed 0.15 → 0.25 across the back half, `allostatic_load` ended **pegged at 1.0**. Closing the loop is not only a productivity fix — it is the only thing that relieves the felt-cost channel.

---

## 3. The fix — connect the two halves through the action that fires

Three coordinated changes. F1 is the keystone; F2 and F3 keep it from starving and stop the junk path in the meantime.

### F1 — Give production an ignition path, not just a weak prior *(keystone)*

Mirror how dysregulated cycles already route a dominant drive straight to a function (`impasse_signal → reflection`, `stagnation_signal → seek_novelty`). When there is a committed goal with `requires_artifact`/`tracked_work` **and** a pending production step in its plan, route directly to `compose_section` rather than relying on `action_prior` to out-compete 3,768 spawn picks. Concretely, in the executive/drive routing (`select_function.py`), add a high-priority rule: *committed artifact goal + pending section ⇒ `compose_section`*. This is the prior proposal's own thesis applied — "a goal is one input to selection, not the ignition" (§1.1); production needs its own ignition.

**Acceptance:** `compose_section` appears in `decision_stats` with a non-trivial count; `brain/data/tracked_work/*.md` exists and grows.

### F2 — Keep a goal committed so the lens isn't dark

Diagnose and fix why `committed_goal` is frequently `None` despite 9 live goals. Two options (pick by what the commit lifecycle in `ORRIN_loop.py:1428–1431` reveals):
- **Commit stickiness** — once committed, hold the commitment across cycles until completed/failed/explicitly dropped, instead of re-deriving it (and frequently getting nothing) each cycle.
- **Lens fallback** — if `committed_goal` is null, let `apply_goal_lens` fall back to the highest-priority `in_progress` goal so the lens (and the F1 routing) still engage.

**Acceptance:** `_goal_lens_telemetry.active_cycles` covers a large majority of cycles; "No committed goal right now" becomes rare.

### F3 — Stop the junk note source; seed from the comprehended target

In `leave_note.py`, **prefer the comprehended goal** as the seed: when `committed_goal` carries `grounded_parts` / `definition_of_done`, build the motive from *those* (what "done" looks like for this goal), not from a scraped finding. Only fall back to the long-memory finding scrape when there is no comprehended goal — and **exclude `search_own_files`/`grep_files`/`search_files` filename outputs** from the seed candidates so `.lock` / `data` fragments can never seed a note. This makes even the cheap path carry goal-relevant signal instead of filesystem lint.

**Acceptance:** no effect whose content is a filename fragment; at least some `note_novel` effects score novelty > 0.

---

## 4. Verification (the next demo run's pass/fail)

The run is a success when the effect ledger shows **its first non-zero row** and an aspiration moves off 0 %:

```bash
# At least one credited effect this life
python3 - <<'PY'
import json
credited=sum(1 for l in open('brain/data/effect_ledger.jsonl')
             if l.strip() and (json.loads(l).get('novelty') or 0) > 0)
print('credited effects:', credited)        # target: >= 1
PY

# The production capability actually fired
ls brain/data/tracked_work/                  # target: >= 1 manuscript file
grep -c compose_section brain/data/decision_stats.json   # target: > 0

# The lens was live, not dark
grep -oE "active_cycles[^,]*" brain/data/*goal_lens* 2>/dev/null  # target: majority of cycles

# An aspiration moved off honest-zero
grep -oE "\[aspirations\].*" brain/data/activity_log.txt | tail -1
```

---

## 5. Why this and not more

The temptation is to keep enriching comprehension or strengthening the lens. The run says that is not where the break is: comprehension *ran* and produced grounded parts; the lens *ran* with zero exceptions. The break is purely **connective** — the comprehended target, the lens, and the production capability are three correct components that the firing action never strings together. F1–F3 are the minimal wiring that closes the loop. Everything downstream (aspiration credit, felt-cost relief, the autobiography advancing on a real life-event) is gated on that first non-zero effect.

---

*Generated 2026-06-20 from the 2026-06-19 run forensics + source inspection. No Orrin code or runtime state edited.*
