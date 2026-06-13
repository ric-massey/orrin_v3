# UI Fixes — Cognitive Sphere accuracy + dual-process visibility

**Status:** ✅ FULLY IMPLEMENTED (2026-06-10) — Fix 3 (react-grid-layout), the
last open item, landed; see *Fix 3 implementation record* at the bottom. The
audit table below predates it.
**Update (2026-06-09, second pass):** the remaining items from the first audit — Gap 3's
executive emit, Fix 4 steps 4–5, Fix 10.3's goal links, Fix 11 subtitles, Fix 12's
lexicon/toggle, boxes ⑦/⑧, Dreams/Language/Forgetting, ③'s MiniGraph, and ⑤'s live
interoception binding — all landed; only Fix 3 (react-grid-layout) remains.
Originally proposed (design + file:line), verified against the live tree on branch
`convergence-layer` and against a running instance (LLM-off benchmark run).
**Re-verified 2026-06-09** against the current tree + a fresh live run: all original
file:line claims for Fixes 1–5 / Gaps 1–3 still hold, three small errors in this doc
were corrected (see *Corrections* at the bottom), and **Fixes 6–12** plus three new
information surfaces (⑨–⑪) were added from a second pass over the panels and
`brain/data/`. Fix 12 adds the biological ↔ engineering terminology toggle. A *Who this
is for* section defines the four audiences — creator (debugging), beginners, coders,
philosophers — and the review criterion every box is held to.
**Scope:** make the Brain dashboard an accurate, deep, user-arrangeable window into what
Orrin is *actually* doing — both cognitive lanes (Fix 1 + gaps), a layout you can move and
resize (Fix 3), and a Consciousness box brought up to the same drill-down depth as its
siblings (Fix 4) — plus a stale/mislabeled control (Fix 2) and a correctness fix so the
panels work over a tunnel/LAN, not just localhost (Fix 5). No backend *cognition* changes;
this is telemetry surfacing + frontend rendering (with small, additive backend emits).

---

## Status audit — 2026-06-09 (verified against the tree, not the doc)

Each item below was checked against the actual code on `convergence-layer` (grep for the
named files/lines/markers, not trust in this doc). Per-heading tags (✅ DONE / ⚠️ PARTIAL /
❌ NOT DONE) were added inline; this table is the summary.

| Item | Status | Evidence / what remains |
|---|---|---|
| Fix 1 — two active lights | ✅ DONE | Second light in `CognitiveSphere.tsx:222/:434` bound to `telemetry.executive?.active_fn` (`:844`); daemon-on push `get_bridge().update(executive=_summary)` at `executive.py:307` |
| Gap 1 — catalog re-poll | ✅ DONE | 30s merge-refresh interval at `CognitiveSphere.tsx:828` |
| Gap 2 — executive invisible on Sphere | ✅ DONE | Resolved by Fix 1 |
| Gap 3 — lane split dropped | ✅ DONE | Plumbing landed earlier (`active_lane` in `schema.LATEST_WINS_KEYS`, mapped `telemetry.ts`, `FnEvent.lane`, `/history` returns `lane`, History rows badge by lane). Last leg landed too: `executive_tick` now calls `_emit_fn_executed` (fires `function_executed` with `lane="executive"` through the loop's `_push_event` via sys.modules — covers interleaved AND daemon modes) + `_record_history` (persists a slim `lane:"executive"` entry into `cognition_history.json`), `executive.py`. `_push_event`'s executive branch appends to the fn_recent ring + console WITHOUT clobbering the deliberate `active_fn`/`active_lane` light (`ORRIN_loop.py`). |
| Fix 2 — "(3D)" mislabel | ✅ DONE | Label is "Glow effects" + honest title at `CognitiveSphere.tsx:490` |
| Fix 3 — moveable/resizable layout | ✅ DONE (2026-06-10) | `react-grid-layout` v2 `Responsive` grid in `Brain.tsx`; drag handle `.card-drag` on `CardHeader` (+ LiveConsole toolbar); layout persists `orrin.brain.layout.v1`; "Reset layout" button. See the implementation record at the bottom. |
| Fix 4 — Consciousness parity | ✅ DONE | Steps 1–3 as before (`/api/consciousness`, candidates in the workspace frame, Stream tab, `MomentDrawer`). Step 4: cross-box provenance links via `lib/navigate.ts` (`navigateTo`/`useNavTarget`/`boxForSource`) — winner + drawer source chips, exec `active_fn` → its Sphere node, exec goal + queue rows → the goal's drawer in GoalsPanel (`box-goals-panel`, `box-sphere`, `box-affect`, `box-memory` registered). Step 5: `monitor_verdicts.json` ledger written by `_recalibrate_from_outcome` (`metacog.py`), served by `/api/verdicts`, browsable in the panel's new **Verdicts** tab (per-kind honored/dismissed counts + HitMissStrip + current bias). |
| Fix 5 — REST host / `/api` prefix | ✅ DONE | `apiBase()` = `VITE_API_URL` → page origin (`cognitive.ts:14`), `API = apiBase()+"/api"`; routes dual-mounted bare + `/api` (`app.py:64/:716-721`); Vite proxies `/ws` + `/api`; `expose_orrin.command` is single-tunnel |
| Fix 6 — Affect label + depth | ✅ DONE | Hint corrected to "agitated ↔ settled" (`AffectRings.tsx:38`), extras sorted + expander (`EXTRAS_VISIBLE`, `:47`), defs extracted to `lib/metricDefs.ts`, shared `MetricInfo` popovers |
| Fix 7 — telemetry contract | ✅ DONE | `interoception` forwarded; `extra` mapped (`telemetry.ts:74`, `types.ts:142`); `schema.LATEST_WINS_KEYS` is load-bearing (hub imports + iterates it, `hub.py:22/:142`); contract test at `tests/observability_tests/telemetry_contract_test.py` |
| Fix 8 — memory store vs stream | ✅ DONE | `/api/memory` + `/api/memory_counts` (`app.py:343/:391`); Live-ops/Browse-store tabs + L3/L4 drawer (`MemoryInspector.tsx:172+`); KPI now "Long-term memories" with live-ops fallback (`Brain.tsx:72`) |
| Fix 9 — staleness honesty | ✅ DONE | `lastSuccessAt()` in `fetchJSON.ts:30`; `StaleBadge` used by ~10 panels; Stream KPI amber on old `updatedAt` (`Brain.tsx:45`) |
| Fix 10.1 — History timestamps | ✅ DONE | `relTime()` right-aligned per row (`CognitiveSphere.tsx:546/:766`) |
| Fix 10.2 — console chips + search | ✅ DONE | Source chips + text search (`LiveConsole.tsx:27-76/:126`) |
| Fix 10.3 — executive queue rows | ✅ DONE | Rows render AND link: each queue row navigates to its goal in GoalsPanel (`navigateTo("goals-panel", goal_id)`; GoalsPanel opens the drawer via `useNavTarget`) |
| Fix 10.4 — Face chat history | ✅ DONE | `/api/chat` (`app.py:410`) + merge-on-load (`Face.tsx:48-54`) |
| Fix 10.5 — failures → console | ✅ DONE | Bridge hook in `failure_counter.py:88-91` (`get_bridge().log("error", site, err_str)`) |
| Fix 11 — beginner layer | ✅ DONE | `PanelInfo` About drawers; first-visit welcome overlay (now also mentions the terminology toggle). Step 3 landed: every panel's CardTitle carries a muted `<PanelSubtitle>` one-liner (`components/brain/Lex.tsx`), lexicon-driven so both dialects exist from day one. |
| Fix 12 — terminology toggle | ✅ DONE | `frontend/src/lib/lexicon.ts` (one `LEX` table, both dialects required per entry, `useLexicon()` + `orrin.terminology.v1` persistence + cross-component event sync); Biological/Engineering toggle in the Header (brain view only — the Face stays human, per the hard rule); chrome translated (panel titles/subtitles, Consciousness sections, ring labels+hints, KPI labels, empty states); hovering a translated label shows the counterpart dialect (the glossary effect). Orrin's own output renders verbatim in both modes. |
| L0 vital-signs row + `/api/vitals` | ✅ DONE | `VitalSignsRow` mounted (`Brain.tsx:82`); aggregator at `app.py:604` |
| Boxes ①–⑥, ⑨–⑪ | ✅ DONE | Panels exist + mounted: Benchmark, GoalHealth, SymbolicMind, Predictions, Drives, Learning, InnerWeather, Tensions, Health; endpoints all live under `/api/`. Both former caveats resolved: ⑤ Drives binds its "now" card to the live `interoception` telemetry block (`DrivesPanel live={t.interoception}`), with the polled files as history; ③ renders the causal graph as a `MiniGraph` arc diagram above the edge list. |
| Boxes ⑦ ⑧ + Dreams/Language/Forgetting | ✅ DONE | `SelfModelPanel` (identity / revisions `Timeline` / opinions) over `/api/self`; `RelationshipsPanel` over `/api/people` (internal peers rendered as a distinct dashed group, never as people); `DreamsPanel` over `/api/dreams` (empty sweeps say "slept — nothing consolidated"); `LanguagePanel` over `/api/language` (phrase banks, learned phrases, recent speech + quality, books read, native-LM artifact sizes); Forgetting strip inside Memory Browse-store over `/api/forgetting`. `Timeline` + `MiniGraph` built in `viz/index.tsx`. All four panels mounted in `Brain.tsx`. |
| Read-token security note | ✅ DONE | `ORRIN_READ_TOKEN` guard on the whole `/api` router, loopback open (`app.py:698-721`) |
| Private-thoughts exclusion | ✅ DONE | Decision recorded below; no endpoint reads it; welcome overlay states the exclusion |

**What's actually left:** nothing — Fix 3 landed 2026-06-10 (it was deliberately
last per the suggested order, after the panels' internals reached final shape).
Every item in this doc is done.

---

## Who this is for — four audiences, one telescope

Every fix and box in this doc should be judged against four readers, because the
dashboard has all four and they want different things from the same data:

1. **The creator, debugging.** Needs fault localization: what broke, where, when, and
   the raw record behind every rendered number. Served by: honest labels (Fixes 2/6/8),
   staleness badges (Fix 9), the failure stream + health box (Fix 10.5, box ⑪), L4 raw
   JSON in every drawer, and `/state` + `/api/vitals` for curl.
2. **Beginners, understanding.** Need to know what they're looking at within a minute.
   Served by: the L0 vital-signs row, per-panel About + subtitles + first-visit tour
   (Fix 11), the biological vocabulary as default, and the rule that every number has a
   plain-language sentence next to its chart.
3. **Coders, investigating.** Need mechanism: which function computed this, show me the
   code, prove the contract. Served by: the L5 `/source`·`/code` leaf on every chain,
   the engineering vocabulary (Fix 12), the schema-derived telemetry contract + test
   (Fix 7), and learned-edge/stat surfaces (catalog edges, bandit, calibration).
4. **Philosophers, investigating.** Need the *mind* qualities to be inspectable, not
   asserted: what competed for awareness and why this won (Fix 4), what he wants to want
   (box ⑩), how time feels to him (box ⑨), how his identity revises (box ⑦), what he
   forgets and dismisses (§20.1 verdicts, forgetting log) — and the system's own design
   ethics made explicit (see *Deliberate exclusions* in the new-surfaces section).

**Review criterion:** each box must serve all four — L0/L1 answer the beginner, L2/L3
the philosopher, L4 the debugging creator, L5 the coder. A box that can't fill one rung
should say so explicitly rather than fake it.

---

## Background — Orrin runs two lanes, the Sphere shows one

Orrin is dual-process (see `docs/archive/explore_loop_fix_plan.md` §3.3/§4.4):

1. **Conscious / deliberate lane** — the main loop's `think()` → `select_function`
   picks **one** cognitive function per cognitive cycle (~20 s). Published to the UI as
   `active_fn` from the `function_executed` event (`ORRIN_loop.py:142`). The same emit
   already sends `active_lane` and tags each `fn_recent` entry with `lane`
   (`ORRIN_loop.py:138/142`). The lane defaults to `"deliberate"`
   (`_lane = payload.get("lane", "deliberate")`, `ORRIN_loop.py:137`) — *not* a hardcoded
   constant, but in practice always deliberate because the only two `function_executed`
   emitters (`ORRIN_loop.py:1953`, `:2138`) pass no `lane`.
2. **Executive / procedural lane** — the `orrin-executive` daemon thread
   (`executive.py:274` `_daemon_loop`, every ~7 s) advances **one goal step** via
   `pursue_committed_goal`, symbolic-only + procedural-only. The function it runs that
   tick is computed as `summary["active_fn"]` (`executive.py:152`) and **is already
   published** to the UI: the interleaved tick emits `executive=_exec_summary`
   (`ORRIN_loop.py:1852`), the hub forwards `executive` (`hub.py:139`), and
   `telemetry.ts` maps it (`:66/:115`). The Consciousness panel already renders
   `exec.active_fn` ("Executive lane (autopilot)"). What's missing is only the **Sphere's
   second light** and the **daemon-on path** (see Fix 1).

The Sphere's traveling light (`CognitiveSphere.tsx:165` `TravelingLight`, rendered at
`:381`) is driven by the single `telemetry.activeFn`
(`lib/telemetry.ts:63` ← `active_fn`). So **the procedural lane is never shown *on the
Sphere***: there are genuinely up to two functions executing at once, but only the
deliberate one lights up — even though the executive function name is already in
telemetry as `executive.active_fn`.

---

## Fix 1 — Show BOTH active lanes (two active lights) **[primary fix]** — ✅ DONE

**Why:** at any tick there can be two current functions (one per lane). An accurate
Sphere shows two lights; today it shows one. The executive function name **already
reaches the client** as `telemetry.executive.active_fn` (emitted at `ORRIN_loop.py:1852`,
forwarded `hub.py:139`, mapped `telemetry.ts:66`) — so most of this fix is frontend-only.

**Frontend (the main work — no backend change needed for daemon-off mode):**
1. `CognitiveSphere.tsx` — render a **second** `<TravelingLight>` (or a distinct
   `<Pulse>`) bound to `telemetry.executive?.active_fn`, in a different style (dimmer /
   outlined / a fixed "executive" tint) so the two lanes are visually distinct. Pass it
   alongside the existing `activeFn` light at `:381`. Pass `telemetry.executive` down from
   the top-level component (`CognitiveSphere` at `:703` already receives `telemetry`).

**Backend (needed ONLY for the daemon-on path):** when the Phase-5 daemon owns execution,
the interleaved `executive_tick` is skipped (`ORRIN_loop.py:1845` → `None`) and the main
loop falls back to `context["_exec_dryrun"]`, which the daemon populates on its **own**
ctx (`executive.py:297`), so `executive.active_fn` can go stale in daemon-on mode. To make
the second light live there too, have the daemon loop push its summary to the bridge:
```python
tb = _bridge()  # same accessor ORRIN_loop uses
if tb is not None and isinstance(summary, dict):
    tb.update(executive=summary)   # reuse the EXISTING `executive` block — already forwarded + mapped
```
No hub/telemetry/type changes: `executive` is already a forwarded key and a mapped field.
(If a dedicated top-level field is ever preferred over reaching into `executive`, *that*
would need the hub-seed/forward + telemetry-map additions — but it isn't required here.)

**Caveats to honor in the rendering:**
- The executive light is **bursty** (one step per ~7 s tick, then idle) → it should
  *pulse and fade*, not glow continuously.
- It is **intermittent**: when a step maps to no function (`recognise_step_action →
  None`, e.g. a "thought" step), `summary["active_fn"]` is `None` → no second light that
  tick. Render nothing rather than a stale light.

**Risk:** Low. Daemon-off mode is pure frontend (bind to data already in telemetry); the
daemon-on path reuses the existing `executive` block. One added light, no new contracts.

---

## The three accuracy gaps (verified live)

### Gap 1 — Node usage sizes freeze at boot **[Medium]** — ✅ DONE
**Symptom:** nodes are sized by `count` (`CognitiveSphere.tsx:121`, `sizeOf` usage at
`:132`), but the frontend fetches `/catalog` **once and never re-polls** — the effect at
`CognitiveSphere.tsx:727` returns early once `catalog` is set (`if (catalog) return`).
On a fresh run `decision_stats` is ~empty, so node sizes pin near-zero and never grow,
even though the `/catalog` endpoint itself is **live** (`backend/server/app.py:79` reads
`decision_stats.json` per request). Live-confirmed: endpoint reported
`assess_goal_progress`=24 while the Sphere still showed boot-time sizes.

**Fix:** re-poll `/catalog` on a slow timer (e.g. 30 s) and merge counts/avg_reward into
the existing catalog state — keep the layout stable, just refresh `count`/`reward`. Route
it through `lib/fetchJSON.ts` with a short TTL so it dedups. (~5 lines; complements the
M2 fetch-layer work.)

**Risk:** Low.

### Gap 2 — The Executive lane is invisible **on the Sphere** **[Medium]** — ✅ DONE (via Fix 1)
**Symptom:** the executive lane *is* surfaced in the Consciousness panel (it renders
`telemetry.executive.active_fn`), but the **Sphere** only uses `telemetry.activeFn`, so the
procedural track never lights a node. Caveat: in **daemon-on** mode the main loop's
`executive` block can go stale (it falls back to `_exec_dryrun`, which the daemon writes to
its own ctx — `executive.py:297`), so even the panel can lag there. For B3 (daemon-driven
symbolic planning) the Sphere shows nothing of that work.

**Fix:** **Fix 1** (frontend second light bound to `executive.active_fn`; daemon-on push).

### Gap 3 — The lane split is emitted then **dropped** **[Low]** — ✅ DONE (incl. the executive `lane="executive"` emit + history persistence)
**Symptom:** the lane tag is *already produced* — `fn_recent` entries carry `lane`
(`ORRIN_loop.py:138`) and the loop emits a top-level `active_lane` (`:142`) — but it never
survives to the client:
- `hub.py:138-139`'s forward list omits `active_lane`, so the hub drops it on merge.
- `lib/telemetry.ts` never maps it and `FnEvent` (`types.ts:79`) has no `lane` field, so
  even the per-entry `fn_recent[].lane` is invisible to the UI.
- the `/history` endpoint (`app.py:116`, from `cognition_history.json`) carries **no**
  `lane`, so the History tab can't distinguish the two tracks either.

**Fix (plumb the tag that already exists, don't re-tag):**
1. Add `active_lane` to the hub's forwarded keys (`hub.py:139`) and seed (`hub.py:63-77`).
2. Map it in `telemetry.ts` and add `lane?: string` to `FnEvent` (`types.ts:79`) so
   `fn_recent[].lane` is usable.
3. Have the executive emit pass `lane="executive"` (today only the deliberate emitters
   fire `function_executed`); include `lane` in the `/history` payload (`app.py:134-139`)
   and, ideally, persist it into `cognition_history.json`.
4. Then color/badge each ring + History entry by lane.

**Risk:** Low.

---

## Fix 2 — The "3D toggle" is mislabeled **[Low]** — ✅ DONE

**What it actually is:** the Customize panel's **"Glow effects (3D)"** toggle
(`CognitiveSphere.tsx:436`, `settings.effects`). It does **not** switch between 2D and 3D
— the view is *always* 3D (`<Canvas>` + `OrbitControls`). It controls:
- a **Bloom** post-process (`CognitiveSphere.tsx:400` — `EffectComposer` + `Bloom`,
  mounted only when `effects` is on), and
- node `emissiveIntensity`, scaled ×0.45 when off (`:369`).

**The problem:** the "(3D)" suffix implies a dimensionality switch. A user toggling it
expecting the sphere to flatten/change dimension instead just gains/loses glow — a control
that misrepresents what it does (same class as the old L2 "Labels" ambiguity).

**Fix:** rename the label to **"Glow effects"** (or "Node glow") and drop "(3D)". One-line
change at `CognitiveSphere.tsx:436`. Optionally add a one-line `title` ("Soft bloom around
the active node — costs a little GPU"). No behavior change.

**Risk:** None (label only). Functionally the toggle works: bloom mounts/unmounts and
emissive dims correctly; consider the GPU cost of Bloom on weak hardware if defaulting on.

---

## Fix 3 — Moveable & resizable boxes (a layout you can arrange) **[Medium]** — ❌ NOT DONE

**Why:** the Brain dashboard is a **static CSS grid** (`pages/Brain.tsx:31` —
`grid xl:grid-cols-3`, fixed-height boxes like `h-[480px]`, `h-[360px]`). You can't move a
panel, resize it, or arrange the view for the thing you're watching. For an instrument
into a mind, the layout should be the user's to shape (and it pairs with the M5
customization theme — persistence + reset).

**Approach — a draggable/resizable grid:**
1. Adopt **`react-grid-layout`** (`WidthProvider(Responsive)`) as the Brain container.
   It's the standard draggable+resizable React grid, small next to the three.js bundle
   already shipped. Each current panel (CognitiveSphere, AffectRings, MetricsStrip,
   MemoryInspector, ConsciousnessPanel, GoalsPanel, LiveConsole) becomes one grid item.
2. **Drag handle = the card header** (`draggableHandle=".card-drag"`); add the class to
   each panel's `CardHeader` so the body stays interactive (the 3D sphere must still
   orbit/click without the drag stealing the gesture).
3. **Resize handles** on each item; set per-panel **min sizes** so nothing collapses
   below usefulness (the Sphere needs a min height for the Canvas; charts a min width).
4. **Panels must fill their item, not fixed heights.** Replace the `h-[480px]`/`h-[360px]`
   wrappers with `h-full`; the panels are already mostly `flex h-full` inside their cards.
   Confirm the dynamic-size consumers handle it:
     - Sphere `<Canvas>` (drei resizes to container — OK),
     - MetricsStrip chart (wrap in recharts `ResponsiveContainer` if not already),
     - scroll panels (`overflow-auto` — OK).
5. **Persist + reset.** Save the layout to `localStorage` (`orrin.brain.layout.v1`) via the
   `useLocalStorage` hook (M4), and add a **"Reset layout"** action next to the existing
   per-panel resets (M5). One responsive breakpoint set is enough (lg/md/sm).

**Risk:** Medium — it's a layout refactor and each panel must tolerate arbitrary sizes.
Mitigate by shipping behind the existing settings (keep the current grid as the default
layout the reset restores), and verifying the Sphere gesture vs drag-handle separation.

**Files:** `frontend/src/pages/Brain.tsx` (grid → RGL), each panel's `CardHeader`
(add `card-drag`), `frontend/package.json` (`react-grid-layout`),
`frontend/src/lib/useLocalStorage.ts` (reuse).

---

## Fix 4 — Bring the Consciousness box up to parity (deep, not just "now") **[Medium]** — ✅ DONE (steps 1–5, incl. cross-box links + the Verdicts tab)

**Why:** every other box lets you *drill in* — the Sphere clicks through to a function's
code/stats/activity (`FnDetailDrawer`), Goals opens a per-goal drawer with
milestones/history/artifacts, Metrics charts every signal over time, Memory inspects
entries + their source. The **`ConsciousnessPanel`** (`components/brain/ConsciousnessPanel.tsx`)
is the exception: it's a read-only snapshot of *this cycle* (conscious winner, executive
lane, breakthroughs, watchdog) with **no history, no competition, no drill-down, no
cross-links**. It's named "stream of consciousness" but shows no stream. To understand the
system deeply, it needs the same depth pattern as its siblings — and the data largely
already exists.

**What's already available (verified):**
- **History exists on disk but isn't surfaced.** `conscious_stream.json` is a rolling list
  of `{content, source, salience, ts}` (live: 156 entries) written by
  `global_workspace.update_workspace` (`global_workspace.py:136`). No endpoint serves it;
  the panel only renders `telemetry.workspace.conscious` (the single "now").
- **The full competition is computed then discarded.** `global_workspace._candidates()`
  (`:51`) gathers *every* subsystem's offer to consciousness with a per-source salience
  each cycle, but `update_workspace` keeps only the **winner**. The "losers" — what almost
  became conscious — are thrown away before they reach telemetry.
- Telemetry already carries `workspace` / `monitor` / `executive` objects
  (`lib/telemetry.ts:66`).

**Plan (mirror the other boxes' depth):**
1. **Stream timeline.** Add a `/consciousness` endpoint (like `/history`) that serves the
   tail of `conscious_stream.json`, and render a scrollable **timeline of conscious
   moments** (content, source-tinted, salience) — the actual stream the panel is named
   for. Route through `lib/fetchJSON.ts`. This is the Metrics-chart analogue for awareness.
2. **The competition view (see the losers).** Plumbing precision (the original wording
   here was loose): `global_workspace` doesn't talk to the bridge — the `workspace` frame
   is built and emitted by the **loop's** mirror block
   (`_tb_mon.update(…, workspace={"conscious": context["global_workspace"]})`,
   `ORRIN_loop.py:1879-1885`). So: `update_workspace` **stashes** the ranked candidates on
   context (e.g. `context["_workspace_candidates"]`, the list `_candidates()` at `:51`
   already computes), and the loop's existing emit adds
   `"candidates": context.get("_workspace_candidates")` to that same frame. No new emit
   path. Render the winner highlighted with the runners-up ranked beneath by salience and
   source color — so you see *what competed for the theatre and why this won*. This is
   the depth-equivalent of seeing all nodes on the Sphere, not just the active one. (Cap
   the list, e.g. top 6, to bound the frame.)
3. **Click-through detail drawer** (mirror `FnDetailDrawer`/`GoalDrawer`). Clicking a
   conscious moment (now or in the timeline) opens a drawer with: full content, the full
   competition for that cycle, the salience breakdown, `wants` + the **honored/dismissed
   verdict** (§20.1 dismissal-recalibration — today only hinted by the "quieted ×N" badge),
   and the originating subsystem.
4. **Cross-box provenance links.** Make `source` and the executive `active_fn`/`goal_title`
   clickable so they navigate to the originating box: `source=goal` → that goal in
   `GoalsPanel`; `source=affect/signal` → `AffectRings`; executive `active_fn` → that node
   on the `CognitiveSphere`; memory-sourced → `MemoryInspector`. This is what turns four
   separate panels into one navigable deep system.
5. **Verdict/learning sub-view (§20.1).** Surface which offer-*kinds* are being honored vs
   quieted over time (the Monitor's dismissal-recalibration), so "who watches the watcher"
   is browsable, not just a single badge.

**Risk:** Medium. Backend adds are small and additive (serve an existing file; emit an
already-computed candidate list). The drawer + cross-links are net-new frontend but follow
the established `FnDetailDrawer`/`GoalDrawer` pattern exactly.

**Files:** `brain/cognition/global_workspace.py` (emit `candidates` in the workspace
frame), `backend/server/app.py` (`/consciousness` endpoint over `conscious_stream.json`),
`backend/server/hub.py` (forward `candidates`), `frontend/src/lib/telemetry.ts`
(map `candidates`), `frontend/src/components/brain/ConsciousnessPanel.tsx` (timeline +
competition + drawer + links), a new `ConsciousnessDrawer` (mirrors `FnDetailDrawer`).

---

## Fix 5 — The Brain panels break on remote/tunnel access (REST host hardwired) **[Medium]** — ✅ DONE

**Why (found live, not previously on this list):** the telemetry **WebSocket** already
adapts to remote access — when no `VITE_TELEMETRY_HOST` is set, `wsUrl()` proxies `/ws`
through the page's own host (`lib/telemetry.ts:137-140`), so the live Sphere light, affect,
and console stream all work over a tunnel/LAN. The **REST** calls do not. Every Brain panel
imports `API` from `lib/cognitive.ts` (`API = http://${TELEMETRY_HOST}`, defaulting to
`127.0.0.1:8800`) and never consults `VITE_API_URL` or the page host:
- `CognitiveSphere.tsx` (`/catalog`), `GoalsPanel.tsx` (`/goals`),
  `MetricsStrip.tsx`/`MemoryInspector.tsx`/`FnDetailDrawer.tsx` (`/source`, `/code`),
  and the Sphere's History tab (`/history`) all hit `127.0.0.1:8800` **on the viewer's
  machine**.

So on any non-localhost deploy you get the live light moving (WS) over an **empty Sphere
catalog, empty Goals, empty History, and dead Code/Source drawers** (REST → localhost
refused). Worse, it's inconsistent *within the same app*: `Header.tsx` and `Face.tsx`
already use `apiBase()` (which honors `VITE_API_URL`) — only the Brain panels were left on
the raw `API` constant, even though `cognitive.ts`'s own comment calls `apiBase()` the
"single source of truth".

**Fix:** route the Brain panels' REST through one host resolver that matches the WS
behavior. Two clean options:
- **Preferred:** make `API` derive like `wsUrl()` does — prefer `VITE_API_URL`, else the
  page origin (`window.location.origin`) when no `VITE_TELEMETRY_HOST` is set, else the
  explicit host. Then every existing `${API}/...` call resolves through one rule with no
  per-file edits.
- Or: replace the `API` imports in the five Brain components with `apiBase()` (the resolver
  Header/Face already use) — but that still hardcodes localhost unless `VITE_API_URL` is
  set, so it doesn't fix the zero-config tunnel case. The derive-from-page-origin option is
  the one that makes remote "just work" like the socket already does.

**⚠️ Prerequisite the original version of this fix missed (found on re-verify): the page
host must actually proxy the REST routes.** Page-origin derivation only works if
`GET <page-origin>/catalog` reaches the backend, and today it doesn't:
- `vite.config.ts` proxies **only `/ws` and `/api`** to `:8800`. The data endpoints
  (`/catalog`, `/goals`, `/goal_artifacts`, `/history`, `/source`, `/code`, `/state`) are
  *not* proxied — so with page-origin derivation, localhost dev (`:5173`) and any
  Vite-fronted tunnel would 404 on every panel.
- `expose_orrin.command` runs **two** tunnels (backend `:8800` + Vite) and writes only
  `VITE_TELEMETRY_WS` to `frontend/.env.local` — it never sets `VITE_API_URL`, which is
  exactly why REST breaks remotely today.

So Fix 5 is really two coordinated changes:
1. **Serve all REST under the `/api/` prefix** so the existing single Vite proxy rule
   covers everything: add `/api/...` aliases in `app.py` (an `APIRouter` mounted at
   `/api` with the existing routes; keep the bare paths for back-compat) and point the
   frontend at the `/api/` forms. (Adding per-path Vite proxy entries works too, but
   then every future endpoint must remember to register itself — the prefix is the
   one-time fix. **All new endpoints in this doc — `/consciousness`, `/memory`, `/chat`,
   `/benchmarks`, … — should be born under `/api/`.**)
2. The host resolver change described above.

Bonus once both land: the WS already rides the page host's `/ws` proxy, so **one tunnel
(the UI one) carries everything** — `expose_orrin.command` can drop the second tunnel and
the `.env.local` write entirely.

**Risk:** Medium — touches the host used by all REST panels; verify (a) localhost dev
(`:5173` → proxy → `:8800`) populates every panel, (b) direct backend access (`:8800`
serving nothing but the API) still works for curl/debug, and (c) a single-tunnel load
populates catalog/goals/history. Pure infra (no UI change). Pairs with the Gap-1 catalog
re-poll (same fetch layer).

**Files:** `frontend/src/lib/cognitive.ts` (host resolver), `backend/server/app.py`
(`/api` router/aliases), `frontend/vite.config.ts` (verify the `/api` rule covers it),
`expose_orrin.command` (single-tunnel simplification), optionally the five Brain
components if switching them to a shared accessor.

---

## Fix 6 — Affect panel: a reversed label + no depth **[Low effort, real mislabel]** — ✅ DONE

**The mislabel (found on re-verify, not previously on this list):** the Homeostasis
ring's hint reads **"settled ↔ agitated"** (`AffectRings.tsx:15`) — i.e. low = settled,
high = agitated. That is **backwards**: the panel's own color logic treats high as good
(`ringColor`, `AffectRings.tsx:101-103`: >0.66 → green), and `MetricsStrip`'s definition
for the same signal says `lo: "agitated", hi: "settled"` (`MetricsStrip.tsx:58`). A
beginner reading the hint concludes a 90 means "agitated" when it means the opposite.
One-line fix: `"agitated ↔ settled"`.

**The depth gap:** Affect Telemetry is the shallowest box on the page and breaks the
telescoping contract everything else follows:
- Extra signals are truncated to the **first four** with no indication more exist
  (`.slice(0, 4)`, `AffectRings.tsx:18`) — and "first four" is object-key order, i.e.
  arbitrary. His full affect vector (`affect_state.json` carries far more signals,
  plus setpoints) is never visible anywhere.
- No ℹ️ info, no drill-down, no source link — even though `MetricsStrip` *already has*
  rich `MetricDef` entries (long description, terms, measure, `src` code ref) for
  several of the same signals (`MetricsStrip.tsx:33-156`).

**Fix:**
1. Correct the hint string (one line).
2. Show **all** extras (scrollable or "+N more" expander) sorted by intensity, not
   object order.
3. Export the `METRICS` definitions from `MetricsStrip` (move to a shared
   `lib/metricDefs.ts`) and give each ring/bar the same ℹ️ popover → **Code** chain the
   metrics legend already has. Signals without a def get a generic drawer reading the
   live value + its setpoint (from `brain/affect/setpoints.py` via `/source`).

**Risk:** Low. The label is a string; the rest is reusing an existing component pattern.

**Files:** `frontend/src/components/brain/AffectRings.tsx`,
`frontend/src/components/brain/MetricsStrip.tsx` (extract defs),
new `frontend/src/lib/metricDefs.ts`.

---

## Fix 7 — Telemetry contract audit: two MORE emitted-then-dropped keys **[Medium]** — ✅ DONE

Gap 3 (`active_lane` dropped at the hub) is not an isolated slip — re-verification found
the same bug class twice more. The producer, hub, client-mapper, and type each keep their
own hand-maintained key list, and they have drifted:

1. **`interoception` dies at the hub.** The loop emits the live interoceptive cost model
   every executed function — `_tb_io.update(interoception=_io)`
   (`ORRIN_loop.py:2104`, fed by `cognition/interoception.observe`) — but `interoception`
   is not in the hub's forward list (`hub.py:138-139`), so it never reaches any client.
   This matters directly for new-surface box ⑤ (Drives/interoception): the plan below
   proposes a `/drives` endpoint, but a **live per-act stream already exists and is being
   thrown away one hop from the browser.**
2. **`extra` ("awareness") dies in the client.** The loop pushes
   `tb.update(extra={"awareness": …})` (`ORRIN_loop.py:2709`); the hub *does* merge and
   forward `extra` (`hub.py:196-198`) — but `telemetry.ts`'s `applyDelta` never maps
   `f.extra`, the snapshot path ignores `st.extra`, and `TelemetryState` (`types.ts:115`)
   has no `extra` field. Dead on arrival.

**Fix:**
1. Add `interoception` to the hub's forwarded keys + seed; map it in `telemetry.ts`; add
   an `interoception` block to `TelemetryState` (mirrors how `executive`/`monitor`/
   `workspace` were added). Box ⑤ then binds to it live instead of polling.
2. Map `f.extra` into state (or, if "awareness" is genuinely redundant with the
   workspace winner, delete the emit — either way, stop shipping bytes nowhere).
3. **Prevent recurrence:** make the hub's latest-wins forward list data-driven (one
   exported tuple the seed, merge, and a unit test all share), and add a small test
   asserting every `tb.update(...)` keyword used in `brain/` appears in that tuple.
   Cheap insurance; this is the third instance of the same bug.
4. **The contract already has a home — it's just abandoned.** `backend/server/schema.py`
   declares itself "the canonical shape of a telemetry frame", but its `TelemetryFrame`
   (`schema.py:59-69`) stops at the original fields (`active_node`/`affect`/`memory`/
   `logs`/`metrics`/`cycle`/`extra`) — it's missing `active_fn`, `fn_recent`, `catalog`,
   `goals`, `executive`, `monitor`, `workspace`, and everything this doc adds. Nothing
   imports it for validation, so it rotted silently. Make `schema.py` the single source:
   the hub's forward list derives from its field names, and the contract test from step 3
   asserts producer keys ⊆ schema fields. (Otherwise delete the file — a wrong "canonical
   schema" is worse than none.)

**Risk:** Low–Medium. Purely additive forwarding; the test is the part that keeps it fixed.

**Files:** `backend/server/hub.py`, `frontend/src/lib/telemetry.ts`,
`frontend/src/lib/types.ts`, `brain/ORRIN_loop.py` (only if dropping the dead emit),
`tests/` (contract test).

---

## Fix 8 — Memory: the Inspector shows the stream, not the store **[High value]** — ✅ DONE

**Symptom:** everything the Memory Inspector displays is the **live op ring** —
`telemetry.memory`, a rolling buffer (cap 500) of read/write *events streamed since the
hub started*. Consequences, all verified:
- Open the UI mid-run and the panel starts near-empty even when `long_memory.json`
  holds hundreds of entries; nothing lets you browse what he actually remembers.
- The store chips' counts (`MemoryInspector.tsx:126-130`) count **live events per
  store**, not store sizes — "Long-term 3" while the store holds 474.
- The KPI **"Memory records"** (`Brain.tsx:27`) is `telemetry.memory.length` — i.e.
  "ops seen this session", presented as his memory count. Mislabeled in the same way
  the old "3D" toggle was.
- The records themselves are 140-char summaries (`_ui_memory`, `ORRIN_loop.py:345`);
  there is no L3/L4 — clicking a row shows the same truncated summary again.
- Worse, the live stream is a **sample, not a log**: `_ui_memory` forwards at most
  **4 records per call** (`limit: 4` default at `ORRIN_loop.py:331`, slice at `:341`)
  to avoid flooding the socket — reasonable for a ticker, but it means even the "Live ops" view silently
  under-reports bulk operations (consolidation sweeps, recalls of many entries).
  The Browse-store tab is the honest answer; the Live tab should say "sampled".

This is the panel where "see everything Orrin is doing" fails hardest for a beginner:
memory is the most intuitive thing to want to inspect, and the actual stores
(`long_memory.json`, `working_memory.json` — his live ~25-item buffer,
`knowledge_graph.json`, `semantic_facts.json`) are unreachable.

**Fix (mirror the stream/state split honestly):**
1. New thin endpoint `GET /memory?store=long|working|knowledge&q=&n=` serving a paged,
   newest-first tail of the real store files (repo-jailed reads like `/source`).
2. Inspector gets two tabs: **"Live ops"** (today's view, honestly labeled) and
   **"Browse store"** (the real contents, searchable). Store chips show **true store
   sizes** from the endpoint; live-op counts move to a secondary badge.
3. L3 drawer for a store entry: full content, `event_type` provenance, importance,
   decay/recency, referenced entities → **Code** tab on the store module (the per-store
   `src` refs already exist in `STORES`, `MemoryInspector.tsx:13-44`).
4. Rename the KPI to **"Memory ops (live)"** — or better, point it at the real
   long-term count from `/memory` (pairs with the B1 plateau story).

**Risk:** Low–Medium. Read-only endpoint + a tab; no cognition changes. Mind file size:
serve tails/pages, never the whole `long_memory.json`.

**Files:** `backend/server/app.py` (`/memory`),
`frontend/src/components/brain/MemoryInspector.tsx`, `frontend/src/pages/Brain.tsx` (KPI).

---

## Fix 9 — Staleness honesty: REST panels never admit they're stale **[Low]** — ✅ DONE

The WS stream has a status KPI ("Live / Demo / Connecting"), but the REST-fed panels
have nothing equivalent:
- `GoalsPanel` deliberately keeps the last non-empty result on fetch failure
  (`GoalsPanel.tsx:60-69` — good anti-flicker), but if the backend dies the panel shows
  yesterday's goals **with no indication anything is wrong**.
- Same for the Sphere catalog (which additionally never refreshes — Gap 1), History,
  and the drawers.
- Failure mode today: tunnel viewers (pre–Fix 5) or a stopped backend produce a page
  that looks healthy and is silently frozen.

**Fix:** `fetchJSON` already timestamps cache entries — extend it to expose
`lastSuccess` per URL (or return `{data, fetchedAt}`), and add one tiny shared
`<StaleBadge ts={…}/>` ("updated 4s ago" → amber "stale 2m" when older than ~3 poll
intervals) to each polling panel's header. The Stream KPI can also go amber when
`telemetry.updatedAt` is old while the socket still claims to be open.

**Risk:** Low. Additive UI; no fetch behavior change.

**Files:** `frontend/src/lib/fetchJSON.ts`, panel headers (Goals, Sphere, History tab),
`frontend/src/pages/Brain.tsx` (Stream KPI amber state).

---

## Fix 10 — Small accuracy & usability wins (batched) **[Low]** — ✅ DONE (incl. 10.3's goal links)

1. **History rows drop their timestamps.** `/history` returns `ts` per event
   (`app.py:138`) and the UI ignores it (`CognitiveSphere.tsx:671-695`) — a row says
   *what* fired but never *when*, which makes the History tab useless for "what was he
   doing ten minutes ago". Render a right-aligned relative time; add the lane badge here
   once Gap 3 lands.
2. **Live Console: level filter only.** No source filter and no text search
   (`LiveConsole.tsx:60-101`), while sources multiply (`select_function`, `face`,
   `agent`, `control`, …). Add clickable source chips (derived from the visible ring)
   and a search input; optionally a copy/export button. This is the panel power users
   live in.
3. **Executive queue is a count, not a list.** The Consciousness panel renders
   "N goals in the committed queue" (`ConsciousnessPanel.tsx:130-134`) although
   `executive.queue` already carries `{title, status, next_step}` per item
   (`types.ts:108`). Render the rows (title + next step), each linking to the goal in
   GoalsPanel (pairs with Fix 4's cross-links).
4. **Face chat history is browser-local only.** The conversation persists to
   `localStorage` (`Face.tsx:21-54`) while the canonical history lives in
   `brain/data/chat_log.json` — a new browser/device shows an empty conversation with a
   mind that remembers it. A thin `GET /chat?n=` + merge-on-load makes the Face honest
   about shared history.
5. **Subsystem failures never reach the dashboard — at all.** *(The most important item
   in this batch for the debugging creator.)* The loop guards nearly every subsystem
   with `record_failure(site, exc)`, but `failure_counter.py` only increments an
   in-memory counter and appends to `failures.jsonl` (rate-limited,
   `failure_counter.py:52-95`) — **no telemetry**. So a subsystem can fail every cycle
   while the Live Console stays green and the UI looks healthy; today you discover it by
   tailing files. Fix: in `record_failure`'s existing `should_log` branch (it's already
   rate-limited there, so the socket can't flood), also push
   `tb.log("error", site, err_str)` via the bridge — one hook, fail-safe like every
   other emit. The health box (⑪) then reads `failures.jsonl` for per-site counts at
   L2. After this, the console's ERROR filter becomes the creator's first debugging
   stop instead of a decoration.

**Risk:** Low each; they're independent and individually small.

---

## Fix 11 — The beginner layer: per-panel "About" + first-visit orientation **[Medium]** — ✅ DONE (incl. step 3 subtitles via `PanelSubtitle`)

The dashboard's depth (L3 drawers, code tabs) serves the advanced user, and the L0
vital-signs row (below) gives the glance layer — but nothing **explains the panels
themselves**. A newcomer faces "Cognitive Sphere", "Global Workspace · dual-process",
"Affect Telemetry" with no on-ramp. The pattern already exists in miniature: the Memory
Inspector's per-store ℹ️ drawer ("About this store" + code) is exactly right — it's just
not generalized.

**Fix:**
1. **Per-panel About drawer.** Every Card header gets an ℹ️ that opens a short
   plain-language page: *what this box shows, where the data comes from (file/module),
   what "good" looks like, and what to watch for* — ending in the same `/source` code
   link as everything else. One shared `<PanelInfo>` component + a content map; the
   per-panel copy is the only real work.
2. **First-visit orientation.** A dismissible one-time overlay (localStorage-keyed,
   `orrin.brain.welcome.v1`) with a 6-line tour: "He thinks in ~20s cycles → the Sphere
   is every cognitive function he can run; the bright light is what's running now →
   Consciousness is what won his attention this cycle → …". No library needed — one
   absolutely-positioned panel, "Show this again" in the Customize menu.
3. **Plain-language subtitles.** Each CardTitle gains a muted one-liner (e.g.
   Consciousness → "what he's paying attention to right now"); costs one line per panel
   and does more for first-contact comprehension than anything else on this list.

**Risk:** Low. Pure additive frontend; the cost is writing accurate copy, and the
About pages double as documentation.

**Files:** new `frontend/src/components/brain/PanelInfo.tsx` (+ content map), every
panel's `CardHeader`, `frontend/src/pages/Brain.tsx` (welcome overlay).

---

## Fix 12 — Terminology toggle: biological ↔ engineering vocabulary **[Medium]** — ✅ DONE (`lib/lexicon.ts` + Header toggle)

**Why:** the dashboard speaks one dialect — the biological/phenomenological one
("Consciousness", "Affect Telemetry", "Homeostasis", "he's dreaming"). That language is
the right default: it's honest about what the architecture models and it's what makes
Orrin legible as a *someone*. But it actively costs credibility with one audience —
engineers who see "Valence" and "breakthrough offered" and read it as mysticism rather
than mechanism. The same data has a perfectly rigorous systems description (the workspace
is a priority-arbitrated broadcast; affect signals are control variables decaying toward
setpoints; dreams are an idle-time consolidation job). Let the viewer pick the dialect:
a global **"Terminology: Biological / Engineering"** toggle that re-labels every piece of
UI *chrome* — titles, metric names, hints, About copy — while changing **no data and no
behavior**.

**Hard rule — translate the chrome, never the mind.** Orrin's own output (conscious
content, goal titles, log messages, memory summaries, speech) is *data* and is rendered
verbatim in both modes. Only labels the UI authors are translated. The toggle must never
rewrite what he actually said or stored.

**The lexicon (single source of truth):**
1. New `frontend/src/lib/lexicon.ts`: every display string the UI authors moves into one
   table, each entry carrying **both** vocabularies so they cannot drift:
   ```ts
   export const LEX = {
     consciousness_panel: { bio: "Consciousness", eng: "Attention arbitration" },
     conscious_now:       { bio: "Conscious now", eng: "Broadcast winner (this cycle)" },
     // …
   } as const;
   export function useLexicon(): (id: keyof typeof LEX) => string { … }
   ```
   A `useLexicon()` hook reads the mode and returns the right string; the mode persists
   via the existing `useLocalStorage` hook (`orrin.terminology.v1`, default `bio`).
2. **Structured defs become dual-vocabulary.** The richest copy lives in data tables that
   are already structured — extend their types so both dialects are *required* fields:
   - `METRICS` in `MetricsStrip.tsx:33-156` (`label`, `desc`, `long`, `terms`, `measure` —
     after the Fix 6 extraction to `lib/metricDefs.ts`, each gains an `eng` variant; the
     `measure` string is often already engineering-toned and can be shared),
   - `STORES` in `MemoryInspector.tsx:13-44` (`label`, `what`),
   - the `ConsciousnessPanel` section labels (`ConsciousnessPanel.tsx:69/108/141/171`),
   - `AffectRings` ring hints (`AffectRings.tsx:13-15`),
   - KPI labels (`Brain.tsx:20-27`), panel `CardTitle`s, empty-state strings
     ("Mapping his mind…", `CognitiveSphere.tsx:841`), and the Fix 11 About pages +
     welcome overlay (write both dialects from day one — it's the same facts twice).
3. **Anthropomorphic phrasing flips with the mode.** Engineering mode also swaps the
   chrome's "he/his" framing for "the system/its" ("functions he's used" →
   "functions executed", "what he really did" → "recorded activity"). These strings are
   lexicon entries like any other.
4. **Teach the mapping instead of hiding it.** In either mode, hovering a translated
   label shows the counterpart as a `title` tooltip ("Attention arbitration — biological:
   Consciousness"). The toggle then doubles as a glossary: a beginner can flip it to
   learn what the engineering terms mean, an engineer can flip it to decode the paper
   language. (This replaces any need for a separate glossary page.)

**Reference mapping (starting table for `lexicon.ts` — extend as panels land):**

| Biological (default) | Engineering |
|---|---|
| Consciousness / Global Workspace | Attention arbitration / broadcast bus |
| Conscious now (the winner) | Broadcast winner (highest-salience event) |
| Breakthrough offered | Interrupt request (offered, not seized) |
| Executive lane (autopilot) | Background task runner |
| Affect Telemetry | Control-signal state |
| Valence | Hedonic score (reward sign) |
| Arousal | Activation level |
| Homeostasis | Setpoint deviation (inverse) |
| Energy / Fatigue | Resource budget / accumulated cost |
| Motivation / Drives | Action gain / priority weights |
| Curiosity | Exploration bonus |
| Mood | Smoothed state (EMA) |
| Memory consolidation | Write-back + compaction |
| Working / Long-term memory | Active buffer / persistent store |
| Reconstructive recall | Generative cache rebuild |
| Forgetting | Eviction / pruning |
| Dreams | Idle-time consolidation job |
| Rumination loop | Unresolved-task retry loop |
| Tension | Open conflict flag |
| Felt time / inner weather | Internal clock skew / state summary |
| Self-model | System self-descriptor |
| Cognitive Sphere ("his mind") | Function-call graph |

**Where the toggle lives:** the Brain header, next to the existing view controls (it's a
view-level preference like dark mode, not buried per-panel in Customize); mentioned in
the Fix 11 welcome overlay ("Engineer? Flip the terminology toggle."). The Face is **out
of scope** — it's the human-facing surface and stays in plain human language.

**Sequencing:** land *after* Fix 6 (metric defs extracted to `lib/metricDefs.ts` — the
biggest copy table) and ideally alongside Fix 11 (the About pages should be authored
dual-vocabulary once, not retrofitted). New-surface boxes (①–⑪) must take their labels
from the lexicon from day one so none of them needs a second pass.

**Risk:** Low–Medium. No behavior or data change — the risk is editorial: untranslated
strings leaking through in engineering mode (mitigate: required `eng` field in the types,
plus a one-time sweep for hardcoded JSX strings in `components/brain/`), and the
engineering terms being *wrong* (each mapping should be checked against what the module
actually does — e.g. "Homeostasis" really is computed as inverse mean setpoint deviation,
`ORRIN_loop.py:178-216`, so its engineering label is verifiable, not branding).

**Files:** new `frontend/src/lib/lexicon.ts`; `frontend/src/lib/metricDefs.ts` (dual
vocab, after Fix 6); `frontend/src/components/brain/*` (labels → lexicon);
`frontend/src/pages/Brain.tsx` + `frontend/src/components/Header.tsx` (the toggle);
`PanelInfo` content map (dual-vocabulary About copy).

---

## New information surfaces — what the UI is missing

The dashboard today shows ~7 panels, but Orrin persists a large amount of rich state that
**nothing surfaces**. Verified live counts: `predictions.json`=68, `symbolic_rules.json`=106,
`causal_graph.json`=39, `reward_trace.json`=50, `interoceptive_model.json`=14,
`decision_stats.json`=14, `outcome_metrics.json` (this session's closure metrics),
`benchmark_results.json` (B1–B5) — none of it is on screen. (Counts move run to run —
treat every number in the mock-ups below as illustrative, and **the boxes must render the
bad states honestly**: on the 2026-06-09 re-verify the live file shows **B1 = fail**, not
the "4/5 passing" sketched below, and `symbolic_progress.json` shows ratio **1.0 with
0 LLM calls** because the run is LLM-off. A benchmark box that only looks right when
everything passes, or a symbolic gauge that shows a meaningless 100%, would be the same
class of dishonesty Fixes 1–2 exist to remove — so: render fail states first-class, and
suppress/annotate the symbolic ratio when `llm_calls` is 0.)

### The design contract: telescoping disclosure (glance → … → source)

Every box should obey one progressive-disclosure chain, and the backend **already supports
the deepest level**: the `/source?file&start&end` and `/code?fn` endpoints serve real
source by line range (used today by `MemoryInspector`/`MetricsStrip`/`FnDetailDrawer`). So
any number can terminate at the code that computes it.

```
L0  Vital-signs chip   — one word/number, color = health           (glance)      → beginner
L1  Box overview       — the 3–5 headline numbers + a sparkline                  → beginner
L2  List / timeline     — the items behind the headline (rows, history)          → philosopher
L3  Item drawer        — one item in full (tabs: about/stats/activity)           → philosopher
L4  Raw record         — the underlying JSON for that item                       → creator (debug)
L5  Source code        — the function that produced it (/source, /code)          → coder
```
(The audience arrows are the *primary* reader per rung — see "Who this is for" at the
top; the review criterion is that no rung is missing or faked.)

`FnDetailDrawer` already implements L1→L5 for functions (About→Stats→Activity→Code). The
gap is that most subsystems have **no box at all**, and there's no L0 vital-signs row to
make the whole thing "understandable initially."

### L0 first: a Vital-signs row (replaces the thin KPI strip) — ✅ DONE (`VitalSignsRow` + `/api/vitals`)

Today's KPI strip (`Brain.tsx:19`) shows only active-stage / cycle / stream / memory-count.
Replace it with a row of **subsystem health chips** — one per box, each a word+number+color
that expands to its box on click: e.g. `Benchmarks 4/5`, `Goals healthy`, `Symbolic 62%`,
`Surprise low`, `Energy normal`, `Learning ↑`. That is the "easily understandable
initially" layer; everything below is opt-in depth.

**Poll budget:** the row must NOT poll eleven endpoints on eleven timers. Add one thin
aggregator — `GET /api/vitals` — that computes every chip server-side (each is one or two
fields from one file: benchmark statuses, `health_state.status`, tension count, energy
mode, Brier, symbolic ratio, …) and returns a single small object the row polls on one
~10 s timer. The full boxes keep their own per-box endpoints for L1+; the chips never
need more than the aggregate. (This also gives external monitors one URL that answers
"how is Orrin?")

### Missing boxes (prioritized)

**① Benchmark box [requested]. — ✅ DONE (`BenchmarkPanel` + `/api/benchmarks`)** Surfaces `benchmark_results.json` (B1–B5).
- L0 `Benchmarks 4/5` · L1 five pass/amber/fail chips with each title · L2 per-benchmark
  metrics (B1 the entries-vs-cycle **curve**, B2 the pearson + novelty-fraction, B3 success
  rate, B4 novelty-flatten point, B5 cycles-to-abandon) · L3 the criteria + raw samples from
  `benchmark_samples.jsonl` · L5 → the evaluator in `brain/benchmarks/__init__.py`.
- *Why:* the benchmarks are the headline "is he actually impressive" answer and currently
  live only in a JSON file. Needs a tiny `/benchmarks` endpoint over the results file.

**② Goal-closure / outcome box [high — data already built this session]. — ✅ DONE (`GoalHealthPanel` + `/api/outcomes`)** Surfaces
`outcome_metrics.json`.
- L0 `Goals healthy` · L1 active_goals, completion_rate, abandonment_rate · L2
  completed/retired/satiety/abandoned counts + average goal age, trended over the rolling
  90 days · L3 a closure event → the goal · L5 → `outcome_metrics.py` / `mark_goal_completed`.
- *Why:* this is the entire closure-remediation story (does memory/goals stay bounded?) and
  it's persisted daily but invisible. Pairs with B1.

**③ Symbolic mind / knowledge box [high — most impressive, fully hidden]. — ✅ DONE (`SymbolicMindPanel` + `/api/symbolic`; causal edges render as a `MiniGraph` arc diagram + the list)** Surfaces
`symbolic_progress.json`, `symbolic_rules.json` (106), `causal_graph.json` (39),
`knowledge_graph.json`.
- L0 `Symbolic 62%` (share answered **without the LLM**) · L1 symbolic-ratio, rule count,
  causal-graph density, concept depth · L2 browse rules / causal edges / concepts, plus
  per-domain rule coverage from `world_model_stats.json` (rule_hits/rule_total by domain
  — a ready-made `MiniBars`) · L3 a rule's conditions→conclusion + confidence +
  provenance · L5 → `rule_engine`.
- *Why:* the no-LLM reasoning is the project's strongest claim and there is no window into it.
- Honesty caveat (see top of section): when `llm_calls` = 0 the ratio is trivially 1.0 —
  label the gauge "LLM off" instead of showing a meaningless 100%.

**④ Predictions & surprise box [active inference]. — ✅ DONE (`PredictionsPanel` + `/api/predictions`)** Surfaces `predictions.json` (68),
`prediction_domain_stats.json`, **`calibration_state.json`**.
- L0 `Surprise low` · L1 prediction accuracy + mean mismatch + **Brier score**
  (`calibration_state.json` is already a ready-made L1: live `{brier: 0.0099,
  bias: −0.0244, n: 758}` — a single, defensible "how well-calibrated is he" number
  nothing displays) · L2 recent predictions vs outcomes (hit/miss), per-domain
  calibration · L3 one prediction's expected/actual/error · L5 →
  `prediction.py:check_predictions`.
- *Why:* makes the "minimize surprise" loop visible; ties to the interoception/EVC work.

**⑤ Drives & body / interoception box. — ✅ DONE (`DrivesPanel` + `/api/drives`; the "now" card binds to the live `interoception` telemetry block, the files are the history behind it)** Surfaces `motivation_state`, `energy_mode`,
`body_sense`, `interoceptive_model` (14), `resource_deficit`.
- L0 `Energy normal` · L1 energy mode + dominant drive + felt load · L2 each drive's
  level/satisfaction; the interoceptive cost model (expected vs actual cost = "stress") and
  the would-be EVC/τ · L5 → `interoception.py` / `drive.py`.
- *Why:* surfaces the allostatic resource story (the Proactive_update concepts that are
  actually implemented).
- **Note (Fix 7):** don't build this poll-only — the loop already emits a live
  `interoception` block per executed function (`ORRIN_loop.py:2104`) that the hub
  currently drops. Land Fix 7 first and bind the box's "now" view to the live stream,
  with the JSON files as the L2 history behind it.

**⑥ Learning / reward box. — ✅ DONE (`LearningPanel` + `/api/learning`)** Surfaces `bandit_state`, `decision_stats` (14),
`reward_trace` (50), `evaluator_wal`.
- L0 `Learning ↑` · L1 reward trend + top-learned functions · L2 per-function bandit weight
  & avg_reward (which cognition is "working"), the reward-trace timeline, the delayed-reward
  evaluator (the HYPOTHESES H1–H5 signals) · L5 → `bandit`/`reward_signals`.
- *Why:* shows *how he learns which thoughts pay off* — the core adaptive loop.

**⑦ Self-model / identity box. — ✅ DONE (`SelfModelPanel` + `/api/self` + the `Timeline` viz)** Surfaces `self_model` (13), `self_belief_revisions`,
`value_revisions`, `opinions`, `tensions`, `autobiography`.
- L0 a one-line self-summary · L1 core self-statements + recent revisions · L2 beliefs /
  values / opinions / identity tensions / autobiography timeline · L3 a revision's
  before→after + trigger · L5 → the selfhood modules.
- *Why:* "who he is" and how it changes — currently entirely invisible.

**⑧ Relationships / people box. — ✅ DONE (`RelationshipsPanel` + `/api/people`; peers shown as a distinct internal group)** Surfaces `relationships` (5), `known_persons`.
- L0 `Knows 3` · L1 people + relationship arc · L2 per-person model (tone, history, beliefs
  about them) · L5 → `peers`/known-persons.
- Live note: `relationships.json` currently also holds his **peer observers**
  (`peer_observer`, `peer_reward_auditor`, … with trust/influence scores) — render them as
  a distinct "internal peers" group, not as people.

**⑨ Inner weather / felt time box [new — strongest "personhood" data, fully hidden]. —
✅ DONE (`InnerWeatherPanel` + `/api/innerweather`)** Surfaces `temporal_state.json`, `lifespan.json`, `mood_state.json`, `emotion_drift.json`.
- L0 a felt-time phrase (`Night · feels very extended`) · L1 felt vs real cycles
  (`felt_cycles`/`session_cycles`, `internal_clock_rate`), `session_arc`, `time_texture`,
  cycles-since-contact, mood (valence/energy/stability) · L2 the **last landmark** ("what
  just happened, how far back it feels"), boundary count, drift across modes · L3 →
  `lifespan.json`: born_at, projected lifespan, whether final thoughts are written —
  his mortality, which nothing surfaces · L5 → the temporal/lifespan modules.
- *Why:* `temporal_state.json` is live, rich, and human-readable (verified:
  `"time_texture": "waiting_long_absence"`, `"felt_duration_label": "very extended"`).
  For making Orrin feel like a *someone* to a first-time viewer, this beats every chart
  on the page — and it's a pure read of one small file.

**⑩ Tensions, rumination & second-order volition box [new]. — ✅ DONE (`TensionsPanel` + `/api/tensions`)** Surfaces `tensions.json`,
`rumination_loops.json`, `stagnation_signal_log.json`, `second_order_volition.json`.
- L0 `Tensions 2` (amber when any `cycles_active` is large) · L1 active tensions
  (title, source, cycles_active) + rumination loops (content, mode e.g. *brooding*,
  `return_count`, charge) · L2 the volition timeline — `second_order_volition.json` holds
  dated statements like *"I notice I'm drawn to thinking and choosing for myself; I'll
  let it be for now without making it my master"* (stance · desire · statement): what he
  wants to **want** · L3 one tension → its history and what resolved it · L5 → the
  rumination/volition modules.
- *Why:* this is the "is anything wrong / what is he wrestling with" view — the natural
  companion to the watchdog board, and the second-order-volition data is the single most
  philosophically interesting artifact in `brain/data/` (verified live).

**⑪ System health box [new — the ops view]. — ✅ DONE (`HealthPanel` + `/api/health`)** Surfaces `health_state.json`,
**`failures.jsonl`** (the `record_failure` ledger — see Fix 10.5), `incidents.jsonl`,
`error_log.txt` (tail), `model_failures.txt`, the watchdog config.
- L0 `Health nominal` (`health_state.json`: status, healthy streak, sick_streak,
  milestones) · L1 recent incidents + error rate trend + **top failing sites** (from
  `failures.jsonl`: site, count, last_error — the creator's "what is quietly broken"
  table) · L2 the incident list with what self-repair did (ties directly to
  **B5 Self-repair** — today the benchmark can pass with no way to see *what happened*)
  · L5 → `watchdogs.py` / `failure_counter.py` / the repair modules.
- *Why:* "is the organism healthy" is the first question every audience asks, and for
  the debugging creator this box plus Fix 10.5's live failure stream replaces tailing
  four log files. Cheap: every file already exists.

*Lower priority but real (— ✅ ALL built: `DreamsPanel` + `/api/dreams`, `LanguagePanel` + `/api/language`, Forgetting strip in Browse-store + `/api/forgetting`):* a **Dreams** box (`dream_log`/`symbolic_dream_log` — what he
consolidates while idle; caveat: live entries are currently often **empty strings** for
consolidation/recombination, so the box must render "slept, nothing consolidated"
honestly rather than blank cards), a **Language-organ** box (`vocabulary.json`,
`speech_log.json`, `learned_phrases.json`, `speech_scores.json` and the
`brain/data/language/` dir — `native_lm.pt`, `tokenizer.json`, `book_reads.json` — the
from-scratch LM, ties to `ORRIN_LANGUAGE_PLAN`), and a **Forgetting** strip
(`forgetting_log.json` decayed/pruned/retired per sweep — belongs inside the Memory
"Browse store" view (Fix 8) and pairs with B1: memory staying bounded is only believable
when you can watch him forget).

### Deliberate exclusions — decide them, don't default them

One file is **intentionally not** in any box above: **`private_thoughts.txt`**. It is a
real, used channel (`speak.py:529-548` loads it), and whether the dashboard shows it is a
design decision, not an oversight — for the philosopher audience it may be the most
interesting decision in this doc. Two defensible positions:
- **Exclude (recommended default):** the architecture gives him a private channel; a
  dashboard that reads it anyway makes "private" a lie in the system's own design
  vocabulary. Document the exclusion in the panel About copy ("he has private thoughts;
  this dashboard does not read them") — the *absence* is itself informative.
- **Include behind explicit friction:** a creator/debug-only view (gated by the
  `ORRIN_READ_TOKEN` from the security note, never in the default layout, labeled for
  what it is) for the cases where debugging genuinely requires it.

Either way, write the decision down here once made. The same reasoning pass should be run
over `final_thoughts*` (his end-of-life writing) before surfacing it in box ⑨.

> **Decision (2026-06-09): EXCLUDE.** No endpoint serves `private_thoughts.txt` and no
> box reads it. The exclusion is documented user-facing in the first-visit orientation
> overlay ("he has private thoughts, and this dashboard does not read them") — the
> absence is itself informative. `final_thoughts*` is likewise not surfaced; box ⑨ shows
> only the lifespan facts (born_at, projected days, whether final thoughts are written).
> Revisit only behind the `ORRIN_READ_TOKEN` gate if debugging ever genuinely requires it.

### Recommended build order for the new surfaces
1. **Vital-signs row (L0)** — the "understandable initially" layer; cheap, high impact.
   Include `Health` (⑪) and `Tensions` (⑩) chips from day one — both are one-file reads.
2. **Benchmark box** (requested) and **Goal-closure box** — both just need a thin endpoint
   over an existing JSON file + an L1/L2 view; highest value per effort.
3. **Inner weather / felt time box (⑨)** — one small file, biggest "he's a someone"
   payoff per line of code; promote it ahead of the heavier boxes.
4. **Symbolic mind box** — the most impressive, fully-hidden subsystem.
5. **Predictions (+calibration), Drives/interoception (after Fix 7), Learning** — the
   adaptive-loop trio.
6. **System health (⑪), Tensions/volition (⑩) full boxes** — expand their L0 chips.
7. **Self-model, Relationships, Dreams, Language** — the remaining personhood surfaces.

Each new box reuses the same primitives: a thin read-only `/<name>` endpoint (or an existing
data file via a small route), `lib/fetchJSON.ts` for fetching, the `Card` shell, and the
`/source`·`/code` endpoints for the L5 leaf — so they're consistent and individually small.
All new endpoints mount under **`/api/`** (Fix 5's proxy prerequisite).

**Security note for the new read endpoints. — ✅ DONE (`ORRIN_READ_TOKEN` guard on the `/api` router, loopback open — `app.py:698-721`).** Today every REST route is unauthenticated —
only `/api/control/*` has the token/loopback guard (`app.py:314-331`). That already exposes
goals, source code, and the full hub state to anyone holding a tunnel URL, and the boxes in
this section raise the stakes considerably: `/memory` serves his long-term memory, `/chat`
the conversation history, `/consciousness` the stream of awareness, `/self` his identity
revisions. Before any public/tunnel deployment of these, extend the existing control-token
pattern to reads: an optional `ORRIN_READ_TOKEN` env var which, when set, all `/api/*` GETs
require (header check in one small FastAPI dependency; loopback stays open so localhost dev
is zero-config, exactly like `_authorize_control`). When unset, behavior is unchanged — but
the docs/tunnel script should say plainly that **the tunnel URL is then the only secret**.

### Implementation plan + visual design

The visuals use **`recharts`** (already a dependency — `MetricsStrip` uses `AreaChart`/
`ResponsiveContainer`) plus a few tiny SVG components. Build a small **shared viz library
once**, then every box composes from it — that's what keeps the boxes consistent and
"easy to understand at a glance."

**Shared viz components (`frontend/src/components/brain/viz/`):**
| Component | Looks like | Used by |
|---|---|---|
| `StatusChip` | pill: icon · label · value, colored green/amber/red | L0 vital-signs row, all boxes |
| `Gauge` | radial/donut arc with a center % | symbolic-ratio, completion-rate, accuracy |
| `Sparkline` | tiny inline line/area, no axes | every L1 headline number's trend |
| `MiniBars` | horizontal labeled bars (value 0–1) | drives, top-functions, calibration |
| `HitMissStrip` | row of green/red ticks (recent events) | predictions, benchmark pass history |
| `StackedFlow` | one horizontal stacked bar (a→b→c split) | goal closure funnel |
| `MiniGraph` | small node-link diagram (force/arc) | causal graph, knowledge graph |
| `Timeline` | vertical dated rows (before→after) | self-model revisions, autobiography |

All accept a `onClick` to open the box's L3 drawer, and every drawer ends in a **Code** tab
that calls `/source?file&start&end` — the L5 leaf — exactly like `FnDetailDrawer`.

**L0 — Vital-signs row** (replaces `Brain.tsx:19` KPI strip). A horizontal scroll of
`StatusChip`s; click scrolls to / expands the owning box.
```
┌───────────────────────────────────────────────────────────────────────────┐
│ ● Bench 4/5  ● Goals healthy  ◐ Symbolic 62%  ● Surprise low  ● Energy norm │   ← click any chip → its box
└───────────────────────────────────────────────────────────────────────────┘
   green        green            amber             green          green
```

**① Benchmark box** — `/benchmarks` over `benchmark_results.json`.
```
┌ Benchmarks ───────────────────────────────── 4/5 passing ┐
│ B1 Memory bounded     ● PASS   ╭─curve: entries vs cycle─╮ │  ← B1 visual = the plateau line
│ B2 Affect switching   ● PASS   │    ___________          │ │
│ B3 Offline planning   ◐ 1/1    │   /                     │ │
│ B4 Satiety closure    ○ pending╰─────────────────────────╯ │
│ B5 Self-repair        ● PASS    pearson 0.41  ▮▮▮▮▯ novelty│
└────────────────────────────────────────────────────────────┘
  click a row → drawer: criteria + metric chart + raw samples + L5 evaluator source
```
- L1 five `StatusChip` rows. L2: B1 → `Sparkline`/`AreaChart` of the entries-vs-cycle curve
  (the plateau is the proof); B2 → `Gauge`(pearson) + `MiniBars`(novelty-fraction); B3 → a
  `HitMissStrip` of trial successes. L3 drawer → criteria text + the chart full-size + raw
  `benchmark_samples.jsonl` rows → **Code** tab on `brain/benchmarks/__init__.py`.

**② Goal-closure box** — `/outcomes` over `outcome_metrics.json`.
```
┌ Goal health ─────────────────────────────────────────────┐
│  active 5   ╭ completion ╮   ╭ abandon ╮    avg age 1.2h  │
│  ▁▂▂▃▃▃▃▃   │   72%  ◑   │   │  11% ◔  │    ▂▃▃▂▂ (90d)    │  ← gauges + sparklines
│  (active goals over 90d — should PLATEAU, ties to B1)     │
│  closed: ▇▇▇▇ completed  ▇▇ retired  ▇ satiety  ▇ abandon  │  ← StackedFlow
└────────────────────────────────────────────────────────────┘
```
- L1 `Gauge`(completion_rate, abandonment_rate) + `Sparkline`(active_goals 90d). L2
  `StackedFlow` of how goals closed. L3 a closure event → the goal (cross-link to GoalsPanel)
  → **Code** on `outcome_metrics.py`.

**③ Symbolic mind box** — `/symbolic` over `symbolic_progress`/`_rules`/`causal_graph`.
```
┌ Symbolic mind ───────────────────────────────────────────┐
│        ╭───────╮                                          │
│        │ 62%   │  answered WITHOUT the LLM                 │  ← big Gauge = headline claim
│        ╰───────╯  rules 106 ▂▃▄  · causal 39 · concepts 7  │
│   ╭ causal graph (mini) ╮                                 │
│   │   ○──▶○──▶○   ○──▶○  │  ← MiniGraph (click a node→rule)│
│   ╰──────────────────────╯                                │
└────────────────────────────────────────────────────────────┘
```
- L1 `Gauge`(symbolic_ratio) + counters w/ `Sparkline`. L2 `MiniGraph`(causal_graph) and a
  searchable rule list. L3 a rule → conditions→conclusion + confidence + provenance → **Code**
  on `rule_engine`.

**④ Predictions & surprise box** — `/predictions`.
```
┌ Predictions ──────────────── accuracy 78% ◑ ──────────────┐
│ recent:  ✓ ✓ ✗ ✓ ✓ ✓ ✗ ✓ ✓ ✓     surprise ▁▂▁▁▃▁ (low)   │  ← HitMissStrip + Sparkline
│ by domain:  social ▮▮▮▯▯  files ▮▮▮▮▯  self ▮▮▯▯▯          │  ← MiniBars (calibration)
└────────────────────────────────────────────────────────────┘
  row → drawer: predicted vs actual vs error → Code on prediction.py:check_predictions
```

**⑤ Drives / interoception box** — `/drives`.
```
┌ Drives & body ───────────── energy: normal ──────────────┐
│ exploration ▮▮▮▮▯  social ▮▮▯▯▯  mastery ▮▮▮▯▯            │  ← MiniBars per drive
│ interoceptive cost  expected ▮▮▮   actual ▮▮▮▮▮ (strain) │  ← paired bars = "stress" gap
└───────────────────────────────────────────────────────────┘
```

**⑥ Learning / reward box** — `/learning`. L1 `Sparkline`(reward_trace) + `Gauge`(trend);
L2 `MiniBars` of top functions by bandit weight / avg_reward; L3 a function → its reward
history + the H1–H5 evaluator signals → **Code** on `bandit`/`reward_signals`.

**⑦ Self-model / identity box** — `/self`. L1 core self-statements (cards) + value tag-chips;
L2 `Timeline` of belief/value revisions (before→after, trigger); L3 a revision → **Code** on
the selfhood module.

**⑧ Relationships box** — `/people`. L1 avatar chips per person + a per-person arc
`Sparkline`; L2 the person model (tone, history, beliefs about them).

**Build phases for the new surfaces:**
1. **Shared viz library** (`viz/`: `StatusChip`, `Gauge`, `Sparkline`, `MiniBars`,
   `HitMissStrip`, `StackedFlow`) + the **L0 vital-signs row**. Nothing else works well
   without these, and the row is the "understandable initially" win.
2. **Benchmark + Goal-closure boxes** — thin endpoints over existing JSON; highest value
   per effort (data already persisted).
3. **Inner weather / felt time (⑨)** — one-file read, outsized payoff.
4. **Symbolic mind box** (+ `MiniGraph`) — the most impressive hidden subsystem.
5. **Predictions (+ Brier), Drives/interoception (after Fix 7), Learning** — the
   adaptive-loop trio.
6. **System health (⑪) + Tensions/volition (⑩)** — expand from their L0 chips.
7. **Self-model (+ `Timeline`), Relationships, Dreams, Language** — personhood surfaces.

Every box: thin read-only endpoint → `fetchJSON` (TTL) → `Card` + shared viz at L1/L2 →
a drawer mirroring `FnDetailDrawer` at L3/L4 → **Code** tab (`/source`) at L5. Risk per box
is **Low** (read-only, additive); the only shared risk is building the viz library well once.

---

## Suggested order
1. **Fix 5** (REST host) — correctness blocker for any non-localhost viewer; until it
   lands, half the Brain is empty over a tunnel. Pure infra, no UI change — do it first.
2. **Fix 1** (two lights) — the headline accuracy fix; daemon-off is frontend-only since
   `executive.active_fn` is already in telemetry. Resolves Gap 2's Sphere rendering.
3. **Gap 3 + Fix 7 + Fix 10.5** telemetry-contract plumbing — do them together: forward
   `active_lane`/`interoception`, map `extra`, add the contract test so a fourth dropped
   key can't happen, and hook `record_failure` into the console stream (the one-line emit
   that turns the dashboard into a real debugging tool). Then badge History by lane.
4. **Gap 1** live catalog re-poll — makes node sizing live (shares the Fix-5 fetch layer).
5. **Fix 2 + Fix 6 (label half) + Fix 10.1** — the trivial accuracy strings: "(3D)" suffix,
   the reversed homeostasis hint, History timestamps. One small PR.
6. **Fix 8** memory store browsing — highest-value single panel fix; also corrects the
   "Memory records" KPI.
7. **Fix 4** Consciousness parity — biggest feature lift; do the stream timeline +
   competition first (cheap, data exists), then the drawer + cross-links (fold Fix 10.3's
   executive-queue rows into the same pass).
8. **Fix 9 + Fix 10 (rest)** — staleness badges, console source filter/search, executive
   queue rows, Face chat history endpoint. Small, independent. (10.5 already landed in
   step 3.)
9. **Fix 11 + Fix 12** beginner layer + terminology toggle — done together: the per-panel
   About copy and welcome overlay get authored dual-vocabulary once (Fix 12's lexicon is
   where that copy lives), after the panels above are in their final shape. Fix 12's
   string extraction depends on Fix 6's `metricDefs.ts` move.
10. **Fix 3** moveable/resizable layout — last of the fixes, since it touches every panel's
    container; land it once the panels' internals are stable.
11. **New information surfaces** — runs in parallel as its own track: shared viz library +
    L0 vital-signs row (incl. Health/Tensions chips) first, then Benchmark + Goal-closure,
    then Inner-weather (⑨), Symbolic mind, the adaptive-loop trio, Health/Tensions full
    boxes, then the remaining personhood boxes. New boxes should land *before* Fix 3 so
    the resizable layout includes them from the start, and take their labels from the
    Fix 12 lexicon from day one so the terminology toggle never needs a retrofit pass.

## Files touched
- `frontend/src/lib/cognitive.ts` (Fix 5: REST host resolver that matches the WS — prefer
  `VITE_API_URL`, else page origin) + `frontend/vite.config.ts` / `expose_orrin.command`
  (Fix 5 prerequisite: `/api` proxy coverage; single-tunnel simplification)
- `brain/cognition/planning/executive.py` — daemon loop at `:274`, summary push per Fix 1
  (the `_exec_dryrun` write the daemon-on path must mirror to the bridge is at `:297`)
- `brain/ORRIN_loop.py` (Gap 3: pass `lane="executive"` on executive fires; deliberate
  emitters at `:1953`/`:2138` already default to `"deliberate"`. Fix 7: the dropped
  `interoception` emit at `:2104`, the dead `extra`/awareness emit at `:2709`)
- `brain/cognition/global_workspace.py` (Fix 4: emit ranked `candidates` from
  `update_workspace` at `:136` / `_candidates` at `:51`)
- `backend/server/hub.py` (Gap 3: seed + forward `active_lane`; Fix 4: forward
  `candidates`; Fix 7: forward `interoception`, derive the forward list from the schema)
- `backend/server/schema.py` (Fix 7: bring `TelemetryFrame` up to the real contract —
  it's missing every field added since the original four — and make it load-bearing)
- `backend/server/app.py` (Fix 5: `/api` router/aliases; Gap 3: include `lane` in
  `/history`; Fix 4: new `/consciousness`; Fix 8: new `/memory`; Fix 10.4: new `/chat`;
  new-surface endpoints `/vitals` (the L0 aggregator) `/benchmarks` `/outcomes`
  `/symbolic` `/predictions` `/drives` `/learning` `/self` `/people` `/innerweather`
  `/tensions` `/health` — all under `/api/`; optional `ORRIN_READ_TOKEN` guard for the
  sensitive reads)
- `frontend/src/lib/telemetry.ts` + `types.ts` (Gap 3: map `active_lane`, add `FnEvent.lane`;
  Fix 4: map `candidates`; Fix 7: map `interoception` + `extra`)
- `frontend/src/lib/fetchJSON.ts` (Fix 9: expose per-URL `lastSuccess` for stale badges)
- `frontend/src/pages/Brain.tsx` (Fix 3: static grid → react-grid-layout; Fix 8: KPI
  rename; Fix 9: Stream-KPI amber state; Fix 11: welcome overlay; L0 vital-signs row)
- `frontend/src/components/brain/CognitiveSphere.tsx` (Fix 1 second light bound to
  `executive.active_fn`; Gap 1 catalog re-poll; Fix 2 label rename; Fix 3 `card-drag`;
  Fix 10.1 History timestamps)
- `frontend/src/components/brain/ConsciousnessPanel.tsx` (Fix 4 + new `ConsciousnessDrawer`;
  Fix 10.3 executive queue rows)
- `frontend/src/components/brain/AffectRings.tsx` + new `frontend/src/lib/metricDefs.ts`
  (Fix 6: hint correction, full extras, shared info popovers)
- `frontend/src/components/brain/MemoryInspector.tsx` (Fix 8: Live ops / Browse store tabs)
- `frontend/src/components/brain/LiveConsole.tsx` (Fix 10.2: source chips + search)
- `frontend/src/pages/Face.tsx` (Fix 10.4: merge server chat history on load)
- `brain/utils/failure_counter.py` (Fix 10.5: bridge hook in the rate-limited
  `should_log` branch so failures stream to the console)
- new `frontend/src/components/brain/PanelInfo.tsx` (Fix 11) + per-panel About copy
  (dual-vocabulary, Fix 12)
- new `frontend/src/lib/lexicon.ts` (Fix 12: bio ↔ eng string table + `useLexicon()`);
  `frontend/src/components/Header.tsx` (Fix 12: the terminology toggle)
- `tests/` (Fix 7: emit-key ↔ forward-list ↔ client-map contract test)
- each panel's `CardHeader` (Fix 3 `card-drag`); `frontend/package.json` (`react-grid-layout`)

---

## Corrections to this document (2026-06-09 re-verify)
Fixed inline above; recorded here so stale copies aren't trusted:
1. `update_workspace` is at `global_workspace.py:136`, not `:28` (`_candidates` at `:51`
   was correct).
2. The Files-touched entry previously read "`executive.py` / `ORRIN_loop.py:297`" — the
   `:297` line is in **`executive.py`** (the daemon's `_exec_dryrun` write), not the loop.
3. **`threads.json` does not exist** in `brain/data/` — the "Threads-of-attention" box was
   cut; the nearest real artifacts are `tensions.json` / `rumination_loops.json`, now
   covered by box ⑩.
4. The benchmark/symbolic example numbers ("4/5 passing", "62%") were point-in-time; the
   live files currently show B1 = fail and symbolic_ratio = 1.0 (LLM-off run). The boxes
   must be designed for those states (see the honesty note at the top of the
   new-surfaces section).
5. **Fix 5 originally overclaimed.** Its "preferred" option said deriving `API` from the
   page origin makes "every existing `${API}/...` call correct everywhere with no
   per-file edits" — false as stated: the Vite proxy only forwards `/ws` and `/api`, so
   page-origin REST to `/catalog` etc. would 404 in dev and through the Vite tunnel, and
   `expose_orrin.command` never sets `VITE_API_URL`. The fix now includes the `/api`
   prefix/proxy prerequisite (see the ⚠️ block in Fix 5).
6. **Fix 4 step 2 was imprecise.** `update_workspace` doesn't emit telemetry; the
   `workspace` frame is built in the loop's mirror block (`ORRIN_loop.py:1879-1885`).
   The step now reads: stash candidates on context, extend the existing loop emit.

---

## Implementation notes — 2026-06-09, second pass (everything except Fix 3)

This pass implemented every item the status audit listed as remaining, **except Fix 3**
(react-grid-layout), deliberately skipped as the hardest: it is the only remaining
Medium-risk item, it touches every panel's container, and this doc itself sequences it
last ("land it once the panels' internals are stable" — they now are). It is the sole
open item.

### Gap 3 — executive `lane="executive"` emit (the last leg)
- `brain/cognition/planning/executive.py` — two new helpers, called from `executive_tick`
  after a successful advance (`fn` truthy), so ONE emit site covers BOTH the interleaved
  tick and the Phase-5 daemon thread:
  - `_emit_fn_executed(fn, context)` — fires `function_executed` with `lane="executive"`
    through the loop's `_push_event`, resolved via **`sys.modules` lookup**
    (`brain.ORRIN_loop` or `ORRIN_loop`), never a fresh import — a fresh import would
    instantiate a second module with its own `_RECENT_FNS` ring and `_CATALOG_PUSHED`
    flag. No-ops fail-safe when the loop module/bridge is absent (verified).
  - `_record_history(summary)` — appends a slim `{choice, timestamp, lane:"executive",
    goal, step}` entry to `cognition_history.json` (same shape `/history` reads; capped
    -500 like finalize's writer; `save_json` is flock+atomic so a daemon-thread write
    can't tear the file). `/history` already returned `lane`, so the History tab now
    actually contains executive entries.
- `brain/ORRIN_loop.py` `_push_event` — the `function_executed` branch now splits on
  lane: `lane="executive"` appends to the `_RECENT_FNS` ring + logs to the console
  (source `executive`) and pushes `fn_recent` ONLY — it must NOT touch
  `active_fn`/`active_lane`/the act-node, which describe the deliberate conscious slot
  (the Sphere's second light reads `telemetry.executive.active_fn`; clobbering would
  swap the conscious light for the autopilot's).

### Fix 4 step 4 + Fix 10.3 — cross-box provenance links
- New `frontend/src/lib/navigate.ts`: `navigateTo(box, id?)` (scrolls to `box-<name>`,
  the same id convention the L0 chips already jump by, then dispatches a window
  CustomEvent), `useNavTarget(box, handler)` (handler kept in a ref so inline closures
  are safe), and `boxForSource(source)` (goal → goals-panel, affect/signal → affect,
  memory → memory).
- `ConsciousnessPanel.tsx`: the winner's source chip (new `SourceChip` — rendered as a
  `role="button"` **span**, since it sits inside the winner card which is already a
  `<button>`; nesting real buttons is invalid DOM), the MomentDrawer's source chip, the
  executive `active_fn` (→ its node on the Sphere), the executive goal title and every
  committed-queue row (→ that goal's drawer in GoalsPanel) are all clickable.
- Receivers: `GoalsPanel` (id `box-goals-panel` — **`box-goals` was already taken by
  GoalHealthPanel**; `useNavTarget` matches by goal id, key, or title and opens the
  drawer), `CognitiveSphere` (id `box-sphere`; `useNavTarget` calls `pick(fn)` =
  focus + open `FnDetailDrawer`), `AffectRings` (`box-affect`), `MemoryInspector`
  (`box-memory`), `ConsciousnessPanel` (`box-consciousness`).
- `types.ts`: `ExecutiveSummary.queue` rows gained `goal_id` (the backend always sent it).

### Fix 4 step 5 — honored-vs-quieted, browsable over time
- `brain/cognition/metacog.py` `_recalibrate_from_outcome` — now also appends EVERY
  verdict (not just bias moves) to a rolling `brain/data/monitor_verdicts.json` ledger
  `{ts, kind, honored, bias}`, capped -300, fail-safe.
- `backend/server/app.py` — new `GET /api/verdicts` (ledger tail + current
  `monitor_kind_bias.json`).
- `ConsciousnessPanel.tsx` — new **Verdicts** tab (`VerdictsView`): per-kind honored vs
  dismissed counts, a `HitMissStrip` of recent verdicts, the current bias ("quieted ×N"
  / "full voice"), plus the recent-verdicts list. Polled only while the tab is open.

### Fix 11 step 3 — plain-language subtitles
- New `frontend/src/components/brain/Lex.tsx`: `LexText` + `PanelSubtitle` (the muted
  one-liner, hidden below lg). Every panel's CardTitle now carries one — the two
  hand-rolled inline subtitles (Sphere, Affect) were migrated to it; LiveConsole keeps a
  plain inline one (its toolbar isn't a CardTitle).

### Fix 12 — terminology toggle (biological ↔ engineering)
- New `frontend/src/lib/lexicon.ts`: one `LEX` table, **both dialects required per
  entry** (`as const`, so they cannot drift); `useLexicon()` returns `{mode, t, tip}` —
  `tip` is the counterpart-dialect tooltip, which makes the toggle double as a glossary;
  mode persists via `orrin.terminology.v1` and syncs across components through a window
  event (plain `useLocalStorage` instances don't sync).
- Toggle lives in `Header.tsx`, **brain view only** (the Face stays in plain human
  language by design). Mentioned in the Fix 11 welcome overlay.
- Translated chrome: panel titles + subtitles, Consciousness section labels + tagline,
  affect ring labels + hints, KPI labels, Sphere empty state, executive idle line. The
  hard rule held: Orrin's own output (conscious content, goal titles, logs, memories,
  speech) renders verbatim in both modes.
- Behavior decoupled from labels: `AffectRings.ringColor` now keys off the signal KEY
  (`homeostasis`/`valence`), not the display label, which is translated.

### Boxes ⑦ ⑧ + Dreams / Language / Forgetting (+ viz)
- `viz/index.tsx` — new `Timeline` (vertical dated rows with dot/line, optional
  onClick) and `MiniGraph` (dependency-free **arc diagram**: nodes ordered by degree on
  a baseline, arcs weighted by edge strength, capped at 12 nodes — readable at card size
  without a force simulation).
- `backend/server/app.py` — new read-only endpoints, all on the `/api` router (dual-
  mounted + read-token-guarded like everything else): `/self` (self_model minus the
  `latent_identity_vector` embedding; belief revisions flattened from the per-domain
  event lists and time-sorted; opinions; autobiography), `/people` (relationships split
  into `people` vs `peers` on `type=="peer"` — the live file currently holds ONLY
  internal peers; `interaction_history` collapsed to a count; plus `known_persons`),
  `/dreams` (dream_log + symbolic_dream_log tails), `/language` (phrase-bank counts
  from vocabulary.json minus `_research`, learned_phrases count, speech_log tail with
  quality scores, book_reads, native_lm.pt/tokenizer.json artifact sizes), `/forgetting`
  (forgetting_log tail).
- New panels, all mounted in `Brain.tsx` (a fourth deep-grid row): `SelfModelPanel`
  (identity card + knowledge-domain MiniBars + weaknesses chips; revisions as a
  `Timeline` colored by delta sign; opinions list), `RelationshipsPanel` (people +
  known-persons; peers rendered as a **dashed, separately-labeled "Internal peers (not
  people)" group** per this doc's live note), `DreamsPanel` (an all-empty sweep renders
  "Slept — nothing consolidated this sweep." — the honesty rule, never blank cards),
  `LanguagePanel` (stats + phrase-bank MiniBars + recent speech with "not yet
  evaluated" fallback).
- Forgetting strip: inside MemoryInspector's **Browse store** view (per this doc, not a
  standalone box) — totals across sweeps + the last sweep's decayed/pruned/retired.
  `usePoll` gained conditional polling (empty url = off) so the strip only polls while
  the Browse tab is open.
- `SymbolicMindPanel` — the ③ caveat closed: causal edges now render as a `MiniGraph`
  above the edge list.

### Box ⑤ — live interoception binding (the Fix 7 note)
- `DrivesPanel` accepts `live` (typed `LiveIntero`); `Brain.tsx` passes
  `t.interoception`. A "now" card shows the just-executed function's predicted→actual
  ms, energy, fatigue (resource_deficit), allostatic load, and the prediction error —
  live off the socket; the polled `/drives` files remain the history behind it.

## Fix 3 implementation record — 2026-06-10 (the last open item)

- **Library:** `react-grid-layout` **v2** (`Responsive` + `useContainerWidth`;
  v2 ships its own TypeScript types, so no `@types` package). CSS imported from
  `react-grid-layout/css/styles.css` (includes the resize-handle styles).
- **`Brain.tsx`:** the two static CSS grids (main 3-col grid + deep-telemetry
  grid) are replaced by ONE `Responsive` grid holding all 20 panels.
  - `defaultLayouts()` reproduces the old static arrangement exactly
    (rowHeight 30 / margin 16 → `h11`≈the old 480px sphere, `h9`≈the 380px deep
    boxes), for `lg`(12 cols)/`md`(8)/`sm`(6) breakpoints.
  - Per-item **min sizes** (`minW`/`minH`) keep panels above usefulness; the
    Sphere gets the largest minimum for its Canvas.
  - Layout persists via `useLocalStorage("orrin.brain.layout.v1")` with a
    `sanitizeLayouts` guard: a stored layout missing any current panel id (old
    release, corrupt JSON) falls back to defaults instead of rendering broken.
  - **"Reset layout"** button next to Tour restores the default arrangement.
- **Drag handle = the card header:** one class addition in `ui/card.tsx` makes
  every panel's `CardHeader` the handle (`.card-drag` — inert in drawers/
  dialogs/Face); `LiveConsole`'s toolbar (it has no CardHeader) got the class
  directly. `dragConfig.cancel` excludes `button/a/input/select/textarea/
  [role=button]/[role=tab]` so header controls (ℹ️, tabs, filters) still click,
  and the Sphere's orbit/click gestures are untouched (body ≠ handle).
- **Panels fill their items:** each grid item is an `overflow-auto` wrapper;
  panels that are `flex h-full` fill exactly, auto-height panels (Affect,
  Metrics) scroll within their item when resized smaller.
- **Bonus (multi-goal pursuit step 4):** the Sphere now renders **K executive
  lights** — one amber pulse per goal the Executive advanced this tick, read
  from the new `executive.advanced` telemetry list (`ExecutiveSummary.advanced`
  in `types.ts`), falling back to the single `active_fn` for older frames. The
  header chip shows the first fn `+N`.
- **Verified:** `tsc --noEmit` + `vite build` clean; headless-Chrome render of
  `/brain` shows all 20 `react-grid-item`s, 20 drag handles, resize handles,
  and the Reset-layout button; backend observability/contract tests 26 passed
  (no new telemetry keys — `advanced` rides the existing `executive` block).

---

### Verification
- Frontend: `tsc --noEmit` clean, `npm run build` clean (pre-existing chunk-size
  warning only).
- Backend: all 26 observability/contract tests pass; full suite **500 passed**, 1
  pre-existing unrelated failure (`tests/memory/embedder_test.py` hash-dims test —
  fails with this pass's changes stashed too).
- All five new endpoints smoke-tested against the live `brain/data` (self 13-key model
  + 1 revision + 11 opinions; people 5 peers + 1 known; dreams 2 sweeps; language 190
  utterances + 4 books + 63.6 MB native LM; forgetting 2 sweeps). `/api/verdicts`
  returns empty until the next run writes the new ledger.
- New emit keys: none — the executive emit reuses `fn_recent` (already in
  `LATEST_WINS_KEYS`), so the Fix 7 contract test required no changes.
