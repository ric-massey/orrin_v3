# UI, Security & Desktop — Consolidated Master Plan

**Date:** 2026-06-16
**Supersedes / consolidates:**
- `UI_AUDIT_REPORT_2026-06-14.md` (findings)
- `UI_AUDIT_REMEDIATION_PLAN_2026-06-14.md` (fix plan)
- `DESKTOP_APP_REMAINING_2026-06-15.md` (packaging tail)
- `UI_LEARNING_VISIBILITY_IDEAS_2026-06-16.md` (forward roadmap)

This is the single source of truth for the UI/security/desktop track. Every status
claim below was **re-verified against the code on 2026-06-16** (file:line cited).
The four source docs are kept for history but should be treated as read-only.

---

## 0. TL;DR — where this track actually stands

| Area | State | Evidence |
|---|---|---|
| **Security audit (H1–H4)** | ✅ **Done** | `app.py` CORS→`trusted_origins()`, `_reject_untrusted_origin`, source denylist, WS token |
| **Reliability audit (H5)** | ✅ **Done** | root + per-panel `ErrorBoundary` (`main.tsx:59`, `Brain.tsx:274`) |
| **Honesty (M1)** | ✅ **Done** | one `useStreamStale` w/ internal tick (`telemetry.ts:304`) |
| **Robustness (M2–M4)** | ✅ **Done** | fetchJSON ct-guard, occurrence dedup, vitals degrade-strip |
| **Polish (L1–L6)** | ✅ **Done** | L1–L6 built; L5 now has global and per-panel reset |
| **Desktop in-repo code** | ✅ **Done** | Groups A–I per git history |
| **Desktop external blockers** | ⛔ **Blocked** | certs / hosting / GUI / tagged-CI — not code |
| **Learning-visibility roadmap** | ✅ **Built + visually checked** | items 1–5 built; static desktop/mobile staging pass completed 2026-06-17 |

**Bottom line:** the security/reliability/honesty work is finished and verified, and the
learning-visibility UI is now built. The remaining work on this track is a short desktop
verification pass that needs a real machine + accounts, plus external signing/update
blockers. See §4.

> 🔎 **Re-traced 2026-06-17 (Claude Code) — claims checked against code, not asserted.**
> Verified present at the cited sites: H1 (CORS→`trusted_origins`, source dotfile/suffix denylist `app.py:319`), H2/H3/H4 (`_reject_untrusted_origin` at `app.py:1490` guards control + `ingest`/`agent_*` + WS `ws_telemetry` `app.py:1952`), H5 (`main.tsx:61`), M1 (`telemetry.ts:304`), B1 (summary tallied *before* the `limit` slice, `app.py:1348-1353`), and learning items 1–4 endpoints (`/behavior-changes`, `/belief-revisions`, `/predictions` trends). **Item 5 was found already built, not pending** — `GET /api/learning` (`app.py:824-939`) returns real `goal_progress` + `rut`, the `GoalProgressCard`/`RutCard` in `pages/Learning.tsx` already consume that exact contract, and it smoke-tests **200 OK against live data** (36 goals, 58/63 milestones; rut `look_around` score 0.5, streak 2). `test_learning_exposes_goal_progress_and_rut` + the other 14 product-endpoint tests pass. **Nothing left to build on this track in-repo;** only the live-browser visual pass (below) and the external desktop blockers (§4) remain.
> Polish applied 2026-06-17: the Goal-progress sort now floats objectives with a real milestone/step bar above ones with no trackable progress (`_goal_sort_key` measurable-rank tiebreak, `app.py`), so the top card is no longer a bar-less `progress=None` row. Active-in-flight still ranks above completed; aggregate milestone count unaffected; 15/15 product-endpoint tests pass.

---

## 1. Architecture (as built — unchanged, still sound)

```
 producers (cognitive loop)                         consumers (browser / native)
 brain/ORRIN_loop.py ── TelemetryBridge ──POST /ingest──►┌──────────┐──WS /ws/telemetry──► useTelemetry()
 brain/behavior/face_bridge.py ◄─ /api/agent/* ──────────│   Hub    │                      (snapshot then deltas)
 React panels ──GET /api/{vitals,life,drives,...}────────►└──────────┘  (reads brain/data/*.json)
```

- **Streaming:** one WebSocket, reducer in `lib/telemetry.ts` (latest-wins merge,
  bounded rings). Snapshot-then-delta.
- **REST:** independent pollers via `lib/fetchJSON.ts` (in-flight dedup + TTL cache),
  each panel paired with a `StaleBadge`. The `api` router is mounted twice — bare and
  under `/api` (`app.py:1171-1172`) — so every `/api/*` call the frontend makes resolves.
- **Pages now shipped:** Watch, Face, Cognition, Life, Memory, Timeline, Brain,
  Settings (`main.tsx`). The 2026-06-14 audit only covered Face + Brain + the bridge;
  the other six pages post-date it (see §3 for their review).

The contract is still test-enforced (`telemetry_contract_test.py`). No schema changes
were needed for any of the audit fixes — all were additive guards / render wiring.

---

## 2. Security & reliability — CLOSED (verification record)

All HIGH/MEDIUM findings from the audit are fixed. Recorded here so we don't re-litigate.

### H1 — secret exfiltration via `/api/source` — ✅
- CORS shrunk from `*` to `trusted_origins()` (`app.py:69-70`, `config.py:75`).
- `source()` rejects dotfiles and non-source suffixes (`app.py:319-322`), allowlist at
  `app.py:116`. `GET /api/source?file=.env` → 403.

### H2 — CSRF shutdown from any browser tab — ✅
- `_reject_untrusted_origin` runs *before* the loopback/token logic in
  `_authorize_control` (`app.py:1197-1206`); hostile `Origin` → 403, no-Origin
  native callers still pass on loopback.

### H3 — unauthenticated `/ingest` + `/api/agent/*` — ✅
- All four (`ingest`, `agent_input`, `agent_inputs`, `agent_respond`) now take a
  `request: Request` and call `_reject_untrusted_origin` (`app.py:1556-1616`).

### H4 — unauthenticated WebSocket — ✅
- `ws_telemetry` applies the read-token with the loopback exemption matching
  `_authorize_read` (`app.py:1648-1654`).

### H5 — one bad panel white-screens the dashboard — ✅
- Root boundary around `<RouterProvider>` (`main.tsx:59`) + per-grid-item
  `<ErrorBoundary fallback={<PanelError id>}>` (`Brain.tsx:274`).

### M1–M4 — ✅
- **M1** single liveness verdict: `useStreamStale` with its own 5s tick
  (`telemetry.ts:304-311`); Header consumes it (`Header.tsx:44-49`).
- **M2** fetchJSON branches on content-type, throws a typed "backend unreachable"
  instead of an opaque JSON parse error (`fetchJSON.ts:78-80`).
- **M3** chat dedup is now **occurrence-based**, not `role|text` (`Face.tsx:67-85`).
- **M4** vitals row renders a "Vital signs unavailable" strip + StaleBadge instead of
  vanishing (`VitalSignsRow.tsx:30-36`).

### L-items — done
- **L2** ✅ chat-timeout copy now says "reached my core loop … still being processed"
  not "gave up" (`Face.tsx:270`).
- **L3** ✅ `_to_float` guards every metric coercion in `hub.merge` (`hub.py:51-57,217`).
- **L4** ✅ `_wait_for_port` polls `:5173` before `webbrowser.open` (`main.py:533,552`).
- **L6** ✅ `_DATA_PARSE_ERRORS` distinguishes corrupt-vs-empty, surfaced as a /vitals
  "Data" chip (`app.py:483-501,1138`).
- **L1** ✅ reconnect attempt count is surfaced in Header and Brain.
- **L5** ✅ global reset remains available, and every desktop/tablet panel now exposes
  a hover/focus reset control that restores only that panel's default position and size.

---

## 3. Post-audit pages — review (new, were never audited)

I read all six pages added after the audit. They follow the same defensive idioms
(honest empty states, `?? fallback`, `isFinite`/clamp guards, no unguarded `.map`).
**No HIGH/MEDIUM issues found.** One confirmed low-severity bug (see §6 B1).

| Page | Source feeds | Verdict |
|---|---|---|
| Watch (`Watch.tsx`) | telemetry only | clean — orb/trail dedup correct |
| Face (`Face.tsx`) | `/api/chat`, `/api/agent/*` | clean — occurrence dedup, 30s wait honest |
| Cognition (`Cognition.tsx`) | `/api/drives,symbolic,people` | clean — all feeds fall back |
| Life (`Life.tsx`) | `/api/life` | clean — felt-vs-true mortality labelled |
| Timeline (`Timeline.tsx`) | `/api/activity` | **B1: summary undercount** (§6) |
| Memory (`Memory.tsx`) | `/api/memory*` | clean (light read) |

---

## 4. Desktop packaging — what's genuinely left (all external)

The in-repo desktop code (native shell, transport/bridge, per-user data dir, keychain
+ Settings, existence/sleep/death model, schema spine, opt-in auto-update layer,
packaging scripts) is **done** per git history (`196bd7e`…`a759550`). What remains
**cannot be done in-repo** — it needs accounts, certs, hosting, or real hardware:

1. **macOS signing + notarization (I4)** — needs an Apple Developer account.
   Entitlements + Info.plist usage strings already written
   (`packaging/entitlements.plist`, `packaging/orrin.spec`); apply at sign time.
2. **Windows code-signing** — installer builds (`packaging/windows/orrin.iss`) but is
   unsigned → SmartScreen warning. Needs a Windows cert.
3. **Auto-update binary swap + hosting (I7)** — in-repo layer done & tested; still need
   Sparkle / Squirrel-MSIX / zsync platform integration **and** a host for the
   appcast/releases. Must run *after* `prepare_update()` exports the mind, hand off via
   graceful shutdown, and let the next launch's migration spine carry the mind forward.
4. **Tray GUI verification (F1)** — `backend/server/tray.py` (pystray) + close→hide
   wiring implemented best-effort; needs a real desktop to exercise Show/Hide/Quit on
   macOS (NSStatusBar + `run_detached()` Cocoa loop), Windows, Linux.
5. **Tagged-build CI (I1/I5/I6)** — embedded CPython staging, Windows installer,
   Linux AppImage only run on a release tag (`.github/workflows/build.yml`). Cut a
   `vX.Y.Z` tag and confirm a clean run; set `ORRIN_REQUIRE_EMBEDDED=1` to make
   embedded-Python staging failures fatal during release.

**Env note (not a bug):** `tests/conftest.py` reports a false "mutated live Orrin state"
error when a live instance is running locally; CI is clean. Stop the instance for a
clean local run.

---

## 5. Learning-visibility roadmap — built, staging check owed

The dashboard was strong at **stocks** (counts that exist now) and weak at **flows**
(what *changed* and *why*). The test for each item:
**does it render `before → after → because`?** Several engines already compute the data
(`behavioral_adaptation.py`, `exploration_value.py`, `habituation.py`) — they're just
not surfaced. Build in this order:

1. **Behavior-change log (A) — highest value. ✅ BUILT 2026-06-17.** Capture policy edits
   as `{situation, old_action, new_action, reason, evidence, when}` and render the diff.
   - **Write path:** `apply_behavioral_adaptations()` now records every self-edit to a
     bounded `brain/data/behavior_changes.json` (cap 250) via `_persist_changes()`
     (`behavioral_adaptation.py:62-104,210-228`). Each record captures the before/after
     posture (`_describe_state`) and a plain-language "because".
   - **API:** `GET /api/behavior-changes?n=` returns newest-first changes + per-pattern
     tallies (`app.py` after `/predictions`).
   - **Panel:** new **Learning** room (`/learning`, `pages/Learning.tsx`, nav in
     `Header.tsx`, lexicon `nav_learning`) renders each edit as before → after → because.
   - This is the home for the rest of §5 (items 2–5 become panels in the same room).
2. **Unified belief-revision feed (B+C) — ✅ BUILT 2026-06-17.** One chronological "what beliefs moved" feed
   across self-beliefs + opinions + symbolic rules, with old→new confidence + evidence
   count + three churn counters per class. **Mostly consolidation of data already
   computed** (previously split across SelfModel/opinions/Symbolic panels).
   - **API:** `GET /api/belief-revisions?n=` merges `self_belief_revisions.json`,
     `opinions.json`, `rule_revisions.json`, and `symbolic_rules.json` into newest-first
     rows, reconstructing old→new confidence when available and returning churn counters
     per class.
   - **Panel:** the **Learning** room now includes a "What beliefs moved" section with
     class counters, confidence movement, evidence count, and compact summaries.
   - **Test:** `test_belief_revisions_unifies_self_opinion_and_symbolic` covers the
     unified feed and churn counters with isolated fixture data.
3. **Perspective labelling (the three layers) — ✅ BUILT 2026-06-17.** Tag every dashboard metric as
   *dev-only* / *agent-accessible* / *in-attention*. Not a new panel — a classification
   + a small badge. Changes how the whole UI reads (stops layer-c looking like layer-a).
   - **Shared badge:** `PerspectiveBadge` renders the three layer labels with tooltips.
   - **Panel layer:** every Brain-panel `PanelInfo` now declares a perspective, and the
     badge appears beside the info icon and inside the About popover.
   - **Metric layer:** `MetricDef` carries a `perspective`, so metric popovers label raw
     affect/system signals consistently.
4. **Two cheap trend lines — ✅ BUILT 2026-06-17.** Calibration-over-time (H,
   periodic Brier snapshot → sparkline) and a novelty/exploit gauge (J, aggregate
   `exploration_value` into one ratio).
   - **API:** `/api/predictions` now includes `calibration_trend` reconstructed from
     resolved predictions and `exploration` from recent `trace.jsonl` function choices.
   - **Panel:** Predictions renders a rolling Brier sparkline and a recent
     explore-vs-exploit sparkline/ratio.
   - **Test:** `test_predictions_exposes_calibration_and_exploration_trends` covers both
     trend fields with isolated fixture data.
5. **Top-level goal progress (E) + rut readout (I) — ✅ BUILT 2026-06-17.** Met-milestones ÷ total, top objectives only, plus
   **rut readout (I)** (consecutive-use count + rut score). Focused views over existing
   data; together they show persistence and stuckness.
   - **API:** `/api/learning` now returns `goal_progress` from goal stores and `rut`
     from `cognition_state.json`.
   - **Panel:** the **Learning** room renders milestone progress for top goals and the
     current repeated-function pressure/streak.
   - **Test:** `test_learning_exposes_goal_progress_and_rut` covers both fields with
     isolated fixture data.

**Defer (good ideas, real new tracking):** recovery funnel (K), strategy diversity (L),
knowledge reuse (M), memory impact (N), provenance stitching (D), survival histogram
(F). **Already covered:** compression (O — SymbolicMindPanel; at most add an explicit
observations÷rules ratio label).

Guiding principle: **stop adding stocks, start showing changes and their causes.**

---

## 6. Bugs found during this consolidation (verified)

I only list things I traced in the code and confirmed. The audit's HIGH/MEDIUM
findings are all fixed (§2), so these are the *residual* items.

### B1 — Timeline "while you were away" summary undercounts on busy periods — **FIXED 2026-06-17**
`backend/server/app.py` `/api/activity`. Was: sort events, **truncate to `limit`**, *then*
compute `summary` — so a >200-event absence undercounted the headline tallies. **Fixed:**
`summary` is now computed from the full event list *before* the `events` array is sliced
to `limit`. The truncation still bounds the returned event list; only the tally moved
ahead of it.

### B2 — L1 reconnect count not surfaced — **CLOSED 2026-06-17 (already done in code)**
Re-checked: the count *is* surfaced. `Header.tsx:55` renders `Reconnecting (${retries})`
and `Brain.tsx:205` does the same. The master plan's earlier "flat Reconnecting" note was
stale. L1 is closed — no work needed.

### B3 — L5 per-panel layout reset — **FIXED 2026-06-17**
Brain keeps the global reset and now gives every desktop/tablet panel an individual
reset control. Mobile remains fixed single-column, so a panel reset is unnecessary there.

**Not bugs (checked and cleared):** `useStreamStale` *does* self-tick (won't get stuck
on a frozen stream); Face server-history merge is reload-safe (occurrence dedup over
persisted history); all six post-audit pages have honest empty/fallback states; every
`/api/*` the frontend calls maps to a registered route.

---

## 7. Recommended next actions

1. ~~Ship B1~~ — ✅ done 2026-06-17 (summary counted before slice).
2. ~~Decide L1/L5~~ — ✅ both closed; reconnect count and per-panel reset are surfaced.
3. ~~Start the learning-visibility track at item 1 (behavior-change log)~~ — ✅ done
   2026-06-17 (write path + `/api/behavior-changes` + new **Learning** room, §5.1).
4. ~~Continue the learning-visibility track~~ — ✅ items 1–5 are now built.
5. **Cut a `vX.Y.Z` tag** to exercise the desktop CI (I1/I5/I6) and get a clean
   artifact set; then do the F1 tray pass on a real desktop.
6. External blockers (signing certs, update hosting) are procurement, not engineering —
   track them separately; they don't block the above.

**Visual verification:** a static-browser staging pass with representative API and
telemetry fixtures checked Learning and Brain at 1440px and 390px. The pass found and
fixed narrow-header overflow in Memory, Consciousness, Goals, and Live Console; the
second pass reported no panel overflow. `docs/images/orrin_learning_ui.png` is the
resulting README capture. A live-data pass was intentionally not run.
