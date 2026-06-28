# Unwired Telemetry → UI Plan

**Created:** 2026-06-23
**Status:** DONE 2026-06-28 — 3A (`gate_report` → `GET /api/intelligence` +
`IntelligenceGrowthPanel` on the Learning page) and 3B (`core_values` chips in
`SelfModelPanel`) both implemented and tested. The only unaddressed item is the
explicitly **optional** `get_human_model()` badge (3C); `record_exception()` was
excluded by design (error logger, not a UI feed). Archived as complete.
**Scope:** surface the "built-but-never-wired" stats/report feeds the Phase-6
dead-code triage found — the ones that are *intended dashboard data*, not actual
cruft. This is the "implement, don't delete" half of the Phase-6 dead-API owner
decision (see `Engineering & Code Health/archive/CODEBASE_CLEANUP_PLAN_2026-06-18.md`).

---

## 1. Why

The Phase-6 dead-code pass flagged a cluster of zero-caller functions that are
**not** cruft — they compute live operational data that was never given an
endpoint or a panel. The correct move for these is to *wire them up*, not sweep
them. Two were already done (`cache_stats` + `gate_stats` → the Cognition
"Thinking cost" card, 2026-06-23). This plan covers the rest.

## 2. UI audit (2026-06-23) — what's surfaced vs not

| Feed | Source | In UI? | Verdict |
| --- | --- | --- | --- |
| `cache_stats()` | `brain/utils/llm_router.py` | ✅ Cognition "Thinking cost" card | done |
| `gate_stats()` | `brain/symbolic/llm_gate.py` | ✅ same card | done |
| `gate_report(days)` | `brain/symbolic/llm_gate.py` | ❌ no endpoint, no consumer, 0 callers | **UI gap — primary target** |
| `core_values` CRUD | `brain/utils/self_model.py` | ⚠️ data read by `SelfModelPanel` via `/api/self`; CRUD API unused | render-only gap |
| `get_human_model()` | `brain/utils/core_utils.py` | ❌ 0 callers | minor / optional |
| `record_exception()` | `brain/utils/error.py` | ❌ 0 callers | **NOT UI-shaped** — it's an error logger; excluded (keep-or-delete decision belongs in cleanup, not here) |

## 3. The work

### 3A. `gate_report` → an "Intelligence Growth" panel (primary)

`gate_report(days)` returns a multi-day growth report (symbolic-vs-LLM trend,
learned-rule count/depth, conflicts, exploration scores; it flushes the session
into `progress_tracker` first). This is the **multi-day trend** complement to the
live, session-instantaneous "Thinking cost" card.

- **Backend:** add a REST endpoint (e.g. `GET /api/intelligence?days=7`) in a
  diagnostics/cognition router under `backend/server/` that calls `gate_report`.
  REST (not the per-frame telemetry socket) is correct here — it's a heavier,
  on-demand, multi-day aggregate, not a per-cycle tick.
- **Frontend:** a panel on the **Learning** page (`frontend/src/pages/Learning.tsx`
  / a new `IntelligenceGrowthPanel.tsx`) that polls the endpoint (reuse
  `usePolledJSON`, like the other REST-fed panels) and renders: symbolic-ratio
  trend line, rule-count growth, and the top exploration/conflict figures. Honest
  empty-state when the report is sparse (early life), matching the house rule.
- **Why a panel, not the socket:** the live card already answers "right now";
  this answers "is his mind growing over days" — a different question with a
  different cadence.

### 3B. `core_values` → render in the Self-Model panel (render-only)

The data path exists (`/api/self` → `self_model.json` carries `core_values`;
`SelfModelPanel.tsx` already types it as `core_values?: unknown[]`) but it isn't
rendered as values. Small change: render the list properly in `SelfModelPanel`.
The concurrency-safe CRUD API in `self_model.py` stays a separate keep/delete
call (it's write-side; the *read* is what the UI needs).

### 3C. `get_human_model` → optional active-model indicator

Low priority: if useful, show which finetune-managed human-model role is active
(a small badge in a diagnostics/settings surface). Defer unless wanted — it's not
a data feed users have asked to see.

### Out of scope
- `record_exception` — an error-recording utility, not a UI feed. Its fate
  (keep as observability API vs delete) is a cleanup decision, recorded in the
  cleanup plan, not implemented here.

## 4. Reasoning

- The split mirrors the data's cadence: **live socket** for per-cycle state
  (cache/gate stats, done) vs **REST poll** for multi-day aggregates
  (`gate_report`). Don't force a heavy multi-day report through the per-frame
  telemetry contract.
- `gate_report` directly serves the offline/native-LM goal — it's the metric for
  "how much of Orrin's thinking now runs symbolically/cheaply, and is that share
  growing." Worth seeing.
- "Implement, don't delete" is the right call *only* for the genuinely
  UI-/data-shaped feeds; `record_exception` is correctly excluded.

## 5. Exit criteria

- `GET /api/intelligence` returns `gate_report` output; a Learning-page panel
  renders the multi-day trend with an honest empty-state; codegen/contract tests
  (if the shape touches the telemetry contract) stay green.
- `SelfModelPanel` renders `core_values` as a readable list.
- `make verify` + frontend typecheck/lint/build green.
- A follow-up audit (vulture + zero-ref trace) confirms no *other* intended
  data-feed function is still unwired, or lists any that remain with a verdict.
