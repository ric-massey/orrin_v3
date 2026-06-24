# Structural Debt Plan — the audit's two un-remediated findings

**Created:** 2026-06-23
**Status:** proposed (no code changed yet)
**Supersedes the open-items tracking of:**
`archive/ENGINEERING_STRUCTURE_AUDIT_2026-06-18.md` (now archived — all its other
findings are remediated; these two are what remained).

The 2026-06-18 engineering structure audit had two findings the cleanup plan's
phases never closed (they were its "Milestones C–F, NOT STARTED"):

- **§9 — broad silent exception handlers** (the real debt).
- **§4 — ambiguous same-name modules** (lower value now; mostly a decision).

Everything else in the audit (§1 oversized functions, §2 import-time startup,
§3 copied daemon, §5 v1/v2 — now decided Option D, §6/§7/§8 dead/duplicate) is
done. This plan covers the remaining two.

---

## §9 — Broad silent exception handlers (primary)

### The problem

`make audit-exceptions` (`brain/scripts/audit_exception_handlers.py`) reports
**603 silent broad handlers across 247 files** (2026-06-23) — `except Exception:`
blocks whose only body is `pass`/`continue`/`return` with no logging. The audit's
point (finding §9): these make *dead paths and partial failures look healthy* —
a swallowed I/O error or schema mismatch is indistinguishable from success.

Worst files (the tool ranks them): `language/acquisition.py` (14),
`benchmarks/__init__.py` (13), `utils/resource_ceilings.py` (12),
`loop/telemetry.py` (11), `routers/telemetry.py` (11), `cognition/will.py` (9),
`utils/log.py` (9), … a long tail.

### The five categories (from the cleanup plan's cross-cutting constraint)

Every broad handler should be classifiable as exactly one of:

| Category | Right treatment |
| --- | --- |
| **Optional capability** (an optional dep / feature absent) | Keep silent, but **narrow** the except to the real exception and **comment** the intent. |
| **External I/O** (file/network/subprocess) | **Log** via `record_failure` / `get_logger` — never swallow silently. |
| **Data / schema failure** (malformed JSON, missing key) | **Log**, and fail-closed where a bad value would corrupt state. |
| **Programmer error** (AttributeError/KeyError from a bug) | **Do not** catch broadly — narrow or re-raise; a bug must surface. |
| **Shutdown / cleanup** (teardown best-effort) | Keep, but **comment** "best-effort teardown". |

### Approach — ratchet first, then reclassify worst-first

Big-bang reclassification of 603 sites is unsafe and unreviewable. Mirror the
Phase-7 forward-ratchet pattern (`test_package_layering`, `test_module_size`):

1. **Stop the bleed (one commit).** Add `tests/test_exception_ratchet.py` that
   runs the audit tool's counter and **fails if the silent-handler count exceeds a
   frozen ceiling** (603). New silent handlers can no longer be added; the number
   can only go down. Wire into `make verify`.
2. **Reclassify worst-file-first, one file/small-batch per commit.** For each
   silent handler in the file: narrow the exception type, add a `record_failure`/
   log call, or re-raise — per the table above; genuinely-intentional silent ones
   get a one-line `# intentional: <category>` comment so they read as deliberate.
   Drop the ratchet ceiling to the new count after each pass.
3. **Converge.** Repeat until only commented, genuinely-intentional silent
   handlers remain. The ceiling at that point is the permanent floor.

### Why this shape

- The ratchet delivers most of the value immediately (no *new* silent failures)
  for near-zero cost, before the slow reclassification.
- Worst-first puts effort where the most failures hide.
- Per-file commits keep each change reviewable and revertible — the same
  discipline the decomposition phases used.

### Exit criteria (§9)

- `make verify` fails if the silent-handler count rises above the frozen ceiling.
- The count trends monotonically down; each reduction is a behavior-preserving
  reclassification (log/narrow/re-raise/comment), verified by `make verify`.
- Remaining silent handlers are each annotated with their category.

### Status — CONVERGED (2026-06-23)

The ratchet has been driven from the frozen ceiling of **603** down to its
permanent floor of **3** (`CEILING = 3` in `brain/scripts/audit_exception_handlers.py`).
Each reduction was a behavior-preserving reclassification per the category table —
narrow-the-exception-type + `# intentional:` comment for optional-capability /
data / parse cases, `record_failure` / `_log.warning` for I/O and compute failures
that should surface, and `# best-effort` annotations for teardown / telemetry
enrichment — committed worst-first in reviewable per-batch commits, lowering the
ceiling in lockstep.

The 3 remaining handlers are the genuine floor: deliberately-broad catch-alls that
already surface every failure, now annotated `# intentional floor:`:

- `brain/utils/error_router.py` — the central error-router decorator; `route_exception`
  logs and normalizes every failure it catches.
- `brain/utils/llm_providers/base.py` — provider connection test; surfaces any vendor
  failure verbatim to the UI (`# noqa: BLE001`).
- `goals/handlers/generic.py` — LLM goal handler; any failure surfaces as an
  `[llm_unavailable: …]` marker to the runner.

`CEILING = 3` is now the permanent floor; `make verify` keeps it from rising.

---

## §4 — Ambiguous same-name modules (secondary, mostly a decision)

### The finding

Seven module names exist in 2+ packages: `world_model` ×2, `sandbox` ×2,
`llm_gate` ×2, `events` ×3, `embedder` ×2, `introspection` ×2, `paths` ×2.
The audit's concern: the bare names "conceal which layer owns what."

### Why this is now lower-value

Phase 3 normalized every import onto the canonical `brain.*` namespace, so the
collisions are **already disambiguated by full path**:
`brain.cognition.world_model` vs `brain.embodiment.world_model` is unambiguous at
every call site, and `tests/test_import_contract.py` forbids the bare spellings
that caused the original confusion. The names only collide when read in isolation,
not in code.

### Recommendation — decide per pair, default KEEP

| Pair | Verdict |
| --- | --- |
| `paths` (brain/ vs brain/utils) | **KEEP** — imported across hundreds of sites; rename blast radius is huge, payoff small. |
| `embedder` (brain/utils vs memory) | **KEEP** — two real embedding impls, both clearly namespaced; rename not worth the churn. |
| `events` (brain, brain/utils, goals) | **KEEP** — three distinct event systems, each namespaced. |
| `world_model`, `sandbox`, `llm_gate`, `introspection` | **KEEP unless a specific collision causes a real bug** — then rename the *narrower-blast-radius* side only. |

The standing rule: **rename only when a name collision actively causes a bug**
(as the `resource_deficit` collision did in the embedding audit — it was renamed
to `function_usage_fatigue`). Absent that, namespacing is sufficient and the
churn isn't justified. Treat §4 as **won't-do / mitigated by namespacing**,
revisited only on a concrete collision.

### Safe rename procedure (if a pair is ever promoted to "do")

1. Rename the file; update all importers including dynamic ones
   (`importlib`/`__import__`/registry walks/`patch("…")` strings in tests).
2. Update the PyInstaller spec hidden imports and any JSON catalogs.
3. `test_import_contract.py` catches missed/bare references; `make verify` green.

### Exit criteria (§4)

- A per-pair decision is recorded (above); the default-KEEP rationale stands until
  a concrete collision bug promotes a specific pair to "rename."

---

## Sequencing

§9 is the real debt — do its **ratchet (step 1) first** (cheap, stops the bleed),
then chip the worst files down over time. §4 needs no code unless a collision bug
appears; the decision above is the deliverable.
