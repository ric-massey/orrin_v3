# Split-Consciousness / Telemetry-Fidelity Audit — 2026-06-19

**Question audited:** "How does Orrin's brain have a split consciousness — the backend
has the numbers, the frontend doesn't?"

**Short answer:** There is no single "Orrin state" that both halves share. There are
**three different representations** of his inner numbers, and the live face/charts watch a
*lossy, re-derived projection* of the real thing — not the real thing. The same quantity
(valence, homeostasis) can legitimately show three different values in three places, and the
value the UI graphs live is, by construction, **not equal** to the number the cognitive loop
actually computed.

---

## 1. The three representations (the actual "split")

| # | Representation | Where it lives | Who reads it | Fidelity |
|---|---------------|----------------|--------------|----------|
| **A** | **Live process state** — `context["affect_state"]` (`valence`∈−1..1, `activation_level`∈−1..1, full `core_signals` vector, `resource_deficit`, `allostatic_load`, drives, reward components) | RAM, inside the cognitive loop | The brain itself, this cycle | **Ground truth.** Ephemeral. |
| **B** | **On-disk JSON** — `affect_state.json`, `goals_mem.json`, `predictions.json`, `health_state.json`, `mood_state.json`, … | `brain/data/*.json` (`affect.py:150` writes A→B) | The REST panels (`/api/self`, `/api/vitals`, `/api/consciousness`, `/api/goals`, …) via polling | Ground truth **but lagged** by each writer's save cadence. |
| **C** | **Live telemetry stream** — the WS `/ws/telemetry` frames | RAM in the hub + `telemetry_history.json` | The Face mood + every Brain *chart* | **Derived/transformed** projection of A. Lossy. |

The "backend has the numbers, the frontend doesn't" feeling is real: **representation A is
never sent anywhere.** The frontend only ever sees B (disk, lagged) and C (a re-derivation).
The brain's actual real-time numbers leave the process only after being either persisted (B)
or transformed (C).

```
        ┌─────────────── A: live affect_state (valence −1..1, core_signals) ────────────┐
        │  (ground truth, RAM, never transmitted as-is)                                 │
        └───────────┬───────────────────────────────────────────┬───────────────────────┘
                    │ affect.py:150 save_json                    │ _emit_affect() TRANSFORM
                    ▼                                            ▼
        B: brain/data/*.json  ──REST poll──► panels      C: WS stream ──► charts + Face mood
           (lagged ground truth)                            (recentered, recomputed, clamped,
                                                             throttled, cached)
```

---

## 2. Where C diverges from A (the transform layer)

All in `brain/ORRIN_loop.py::_emit_affect` (lines ~194–254). This is the single chokepoint
where the brain's real numbers are rewritten before the UI ever sees them.

### F1 — Valence is re-centered, so UI valence ≠ brain valence  *(by design, but undocumented in UI)*
- Brain valence runs **−1..1** (`affect_dynamics.py:239`).
- Emitted as `valence = clamp01(0.5 + 0.5 * valence)` → **0..1** (`ORRIN_loop.py:236`).
- The raw value *is* also shipped as `valence_raw` (`:237`), but the **Face mood and the
  default affect chart read `valence`**, i.e. the recentered one. Anyone reading the chart is
  reading `0.5 + v/2`, not `v`. A truly neutral brain (v=0) and the chart's "neutral" (0.5)
  happen to line up, but every non-zero reading is visually compressed by half.

### F2 — Homeostasis shown is a *different computation* than the brain's homeostasis  *(High)*
- The brain has its own homeostasis/stability notion in `affect_state`.
- `_emit_affect` **ignores it** and recomputes a fresh number from `affect.setpoints`:
  weighted mean deviation of `core_signals` from setpoints, `clamp01(1 - mean_dev*1.6)`
  (`ORRIN_loop.py:211–223`), with `exploration_drive` hand-weighted to 0.15.
- So the "homeostasis" line on the chart is a **UI-only metric invented in the emit helper**.
  It does not exist anywhere in representation A or B. If you asked the brain "what is your
  homeostasis," you would get a different number than the chart shows. The magic constants
  (`1.6`, `0.15`) live only here.

### F3 — Distress / load are rescaled by undocumented divisors  *(Medium)*
- `distress = clamp01(negative_load(a) / 2.5)` (`:230`). The `/2.5` is a display-fit constant
  with no comment justifying it; `negative_load` can exceed 2.5, in which case distress pins
  at 1.0 and **saturation is invisible**.
- `motivation`, `confidence`, `curiosity`, `allostatic_load`, `stability` are each
  `clamp01(...)` of a single `core_signals` field (`:245–250`). Any value the brain pushes
  outside 0..1 is **silently flattened** — the chart cannot distinguish "exactly at the rail"
  from "way past the rail."

### F4 — `learning` is cached up to 4 s and reads a *fourth* source  *(Medium)*
- `_learning_pulse` (`:259–281`) computes "is his mind growing" from `predictions.json`
  (representation B), caches it for 4 s, and ships it as the affect field `learning`.
- So one of the "affect" signals on the live chart is actually a **4-second-stale derivative
  of a disk file**, sitting next to sub-second live signals on the same axis. They are not the
  same clock.

### F5 — Double clamp + NaN-drop on the hub side  *(Low, compounding)*
- Everything is clamped *again* in `hub.merge` via `clamp01` (`hub.py:224–228`) and any
  non-numeric/NaN metric is dropped (`hub.py:70–78, 237`). Defensible defensively, but it
  means a value can be clipped twice and a frame's metrics can partially vanish without any
  visible marker on the chart.

---

## 3. Where B and C disagree with each other (two clocks, one quantity)

- **Goals** appear in **both** streams: REST `/api/goals` reads `goals_mem.json` (B,
  `app.py:257`) **and** the loop pushes a throttled goal summary over WS every 2 s
  (`_emit_goals`, `ORRIN_loop.py:284–342`, `_GOALS_PUSH_INTERVAL = 2.0`). The
  `GoalsPanel` and the Sphere can therefore show **two versions of the goal set** that are up
  to ~2 s out of sync, derived by two different summarizers (`_summ` vs the REST handler).
- **Affect** appears in **C only**. There is **no REST endpoint that serves the raw
  `affect_state.json`** vector. So the panels' "ground truth" world (B) and the charts'
  transformed world (C) never even cross-check on affect — they can't, because A's affect is
  only ever exposed in transformed form.

---

## 4. Numbers the backend computes but the frontend *never* sees (dark state)

These exist in representation A and are never emitted to C nor exposed via a B endpoint the UI
reads:

- The full **`core_signals` vector** raw (only ~8 hand-picked fields survive `_emit_affect`).
- **Reward decomposition** — the production/intake split, effect-ledger components
  (`ORRIN_PRODUCTION_REWARD_PLAN`) — only the per-fn scalar `reward` rides along in
  `fn_recent` (`ORRIN_loop.py:162`).
- **Pearce-Hall adaptive learning rate** and prediction-error magnitude (the metacognition
  layer) — computed, never charted.
- **Setpoints themselves** — the targets homeostasis is measured against
  (`affect.setpoints`) are used inside the emit transform but never shown, so the chart's
  homeostasis number is uninterpretable from the UI alone.
- Per-signal **deviation weights** used in F2.

A function map / catalog *is* shipped once (`_push_catalog_once`, `:178`) and decision-stats
come via REST `/api/catalog` — those are fine. The gap is specifically the **affective and
reward scalars**.

---

## 5. Failure modes that widen the split

### F6 — Demo fallback can fabricate the entire number stream  *(Medium — guard rail exists)*
- `frontend/src/lib/telemetry.ts::startDemo` (`:176–225`) synthesizes valence/arousal/
  homeostasis from `Math.sin(...)` and random logs. It is **off by default** now
  (`App.tsx`, opt-in via `VITE_TELEMETRY_DEMO_FALLBACK=1`), per the UI memory — good — but if
  ever re-enabled, the charts show **plausible fake numbers indistinguishable from live**,
  which is the worst possible split (frontend has numbers; backend isn't even running).

### F7 — Backpressure silently drops history, charts keep a confident line  *(Low)*
- Logs/memory are bounded rings that shed oldest under load (`telemetry_bridge.py:129–131,
  336–343`) — at least this surfaces a single warn line. But **affect/metrics are
  latest-wins coalesced** (`:316–321`): under lag the intermediate affect frames are
  *discarded*, so the chart silently under-samples his real excursions. The line looks smooth
  because the spikes were dropped, not because they didn't happen.

### F8 — Liveness vs freshness is only loosely coupled  *(Low — partially handled)*
- `useStreamStale` (`:304`) flags a wedged-but-connected socket after 15 s, which is good.
  But within that window the charts present the **last transformed value as current**, with no
  per-metric age. A 14-s-stale homeostasis reads identically to a live one.

---

## 6. What the contract test does and does **not** protect

`tests/observability_tests/telemetry_contract_test.py` is strong but guards a narrower
property than people assume. It proves: *every key emitted via `tb.update(...)` in `brain/`
is handled by the hub and referenced in `telemetry.ts`* — i.e. **no key is silently dropped
in transit.**

It does **not** prove:
- that the emitted value **equals** the brain's internal value (F1–F4 are all "handled keys"
  carrying transformed values — the test is green);
- that affect goes through `.affect()` rather than `.update()` (the affect path bypasses the
  keyword scan entirely — it's a positional `AffectFrame`);
- that B (disk/REST) and C (WS) **agree** on shared quantities like goals (§3).

So the contract test secures the *plumbing*, not the *semantics*. The split lives in the
semantics it doesn't cover.

---

## 7. Recommendations (ordered by leverage)

1. **Make C carry A unmodified; do display math in the client.** Ship `valence` as raw −1..1
   and let the chart map it, instead of pre-centering in `_emit_affect`. Removes F1 and makes
   `valence_raw` redundant. (Low risk; the chart already has `metricDefs`.)
2. **Stop inventing homeostasis in the emit helper (F2).** Either emit the brain's real
   homeostasis from `affect_state`, or move the setpoint-deviation computation *into the
   affect module* so A and C share one definition, and emit that. Today the only place this
   number exists is a telemetry helper — that's the literal "frontend has a number the
   backend doesn't."
3. **Expose A's affect vector via REST** (`/api/affect` reading `affect_state.json`) so the
   panels can cross-check the charts, and so there's a ground-truth answer to "what does Orrin
   actually feel right now" that isn't the transformed stream.
4. **Pick one goal source.** Either drop the WS goal push and let `/api/goals` own it, or have
   both call the *same* summarizer. Eliminates the 2 s two-version skew (§3).
5. **Add a fidelity/semantics test** alongside the plumbing test: assert that for the shared
   keys, the value the loop holds round-trips to the hub state unchanged (catches a future
   F2-style invented metric).
6. **Annotate the divisors** (`/2.5`, `*1.6`, `0.15`, `*0.5+0.5`) with their provenance, or
   replace them with named, shared constants. Right now the UI's numeric reality is governed
   by undocumented magic constants in one helper.
7. **Per-metric freshness** on charts (greyed/aged when `now − point.t` exceeds a cycle), so
   F7/F8 staleness is visible rather than presented as live.

---

## 8. One-line characterization

Orrin's "consciousness" isn't split between backend and frontend so much as the **frontend
watches a translation, not the original** — and a few of the numbers on that translation
(homeostasis above all) **only exist in the translator.** The plumbing is well-guarded; the
*meaning* of the numbers is where backend and frontend quietly disagree.

---

## 9. Remediation status (2026-06-20) — substantive findings RESOLVED

| Rec | Finding | Status |
|----|---------|--------|
| #2 | Homeostasis invented in the emit helper (F2, **High**) | ✅ **Fixed.** Computation moved to the single authority `affect.homeostasis.homeostasis_index`; written onto `affect_state` every cycle (`update_affect_state.py`); `_emit_affect` now only *reads* it. A, B and C share one definition. |
| #3 | No REST endpoint for the raw affect vector | ✅ **Fixed.** New `GET /api/affect` serves raw −1..1 valence, the brain's homeostasis index, and the full `core_signals` vector from `affect_state.json` (`backend/server/app.py`). |
| #1 | Valence re-centered, UI ≠ brain (F1) | ✅ **Resolved (by design + documented).** Raw value already ships as `valence_raw` (dev-only chart) and now via `/api/affect`, so no number is hidden; the 0.5+0.5·v centering is an explicit presentation mapping via named constants (`_VALENCE_UI_CENTER`/`_VALENCE_UI_SCALE`), not a silent divergence. |
| #4 | Two goal summarizers (§3) | ✅ **Fixed** (separately, via the goals work): WS push and `/api/goals` both call `goal_io.summarize_goal_tree`. |
| #5 | No fidelity/semantics test | ✅ **Added.** `tests/observability_tests/affect_fidelity_test.py` pins that charted homeostasis == the brain's stored number and that centered valence round-trips to raw. |
| #6 | Undocumented magic divisors (`/2.5`, `*1.6`, `0.15`, `0.5+0.5`) | ✅ **Fixed.** Replaced with named, commented constants in `ORRIN_loop.py` and `affect/homeostasis.py`. |
| #7 | Per-metric chart freshness (F7/F8, **Low**) | ⏳ **Residual.** Frontend-only rendering polish (grey/age a metric when `now − point.t` exceeds a cycle); deferred — not a backend semantics issue. |

The audit's load-bearing complaint — *"a number that only exists in the
translator"* — is closed: homeostasis now has one owner the brain itself reads.
The single residual (#7) is a Low-severity client rendering nicety. Archived.

---
*Evidence: `brain/ORRIN_loop.py:194–342`, `backend/telemetry_bridge.py:218–344`,
`backend/server/hub.py:189–291`, `backend/server/schema.py:59–97`,
`backend/server/app.py:82,108,257,1361`, `frontend/src/lib/telemetry.ts:46–225`,
`brain/affect/affect.py:150`, `brain/affect/affect_dynamics.py:212–346`,
`tests/observability_tests/telemetry_contract_test.py`.*
