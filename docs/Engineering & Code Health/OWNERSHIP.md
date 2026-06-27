# Ownership tables

**Created:** 2026-06-23 (CODEBASE_CLEANUP_PLAN Phase 7 — "Define ownership for
architecture, runtime state schemas, packaging, and UI contracts").

This document is the narrative behind `.github/CODEOWNERS`. CODEOWNERS routes the
review request; this table says what *owning* a domain means: where its source of
truth lives, the rule a change must follow, and the automated check that enforces
the rule. "Owner" is the person accountable for that contract staying coherent —
on a single-maintainer repo that is `@ric-massey`, but the *contracts and gates*
below are what actually keep the domains honest, and they outlive any one owner.

## Domains

| Domain | Owner | Source of truth | Change rule | Enforcing check |
| --- | --- | --- | --- | --- |
| **Architecture** | @ric-massey | `brain/ORRIN_loop.py` + `brain/loop/` (the loop spine); the engineering plans/decision records under `docs/Engineering & Code Health/` | New cross-package edges and import cycles are not introduced silently; modules stay under the 600-line soft limit; decisions are recorded as a plan/ADR, not folklore. | `tests/test_package_layering.py` (edge ratchet), `tests/test_import_contract.py` (import-naming ratchet), `tests/test_module_size.py` (size ratchet) — all in `make verify`. |
| **Runtime state schemas** | @ric-massey | `brain/utils/schema_migration.py` (`CURRENT_SCHEMA_VERSION` + `_MIGRATIONS`) | Any change to a persisted-state envelope bumps the global schema version and lands a round-trip migration test (old fixture → migrate → asserted shape). The per-store version is subsumed by the global one (Phase 5.4). | `tests/brain/test_schema_migration_roundtrip.py` — CI-locks `set(_MIGRATIONS) ⊆ tested`. |
| **Packaging** | @ric-massey | `pyproject.toml` (the single dependency model + extras); `requirements*.txt` / `requirements.lock` are generated mirrors; `Dockerfile`/`docker-compose.yml`; `packaging/orrin.spec` (PyInstaller) | Dependencies are declared in `pyproject.toml` and the mirrors regenerated from it — never hand-diverged. Source/editable/Docker/PyInstaller builds resolve from the same model. Vulnerability + outdated reporting runs continuously. | `.github/workflows/build.yml`, `docker.yml`, `dependency-audit.yml`; `make audit-deps`. |
| **UI contracts** | @ric-massey | `backend/server/schema.py` (pydantic — the telemetry single source of truth) | The TS wire types are **generated** from `schema.py`, never hand-authored; both producer (pydantic on emit) and consumer (zod on parse) validate frames at runtime. `frontend/src/lib/telemetry.gen.ts` is generated output — regenerate via `make telemetry-types`, don't edit. | `tests/observability_tests/telemetry_codegen_test.py` (fails CI if `.gen.ts` is stale). |

## v1 / v2 goals + memory ownership

The cross-cutting constraint "the v1/v2 goals and memory systems require explicit
ownership tables before either adapter is simplified" lands here.

- **v1 packages** (`goals/`, `memory/`, `reaper/`) are intentional top-level
  packages and **owned as a frozen seam**, not as evolving code. `brain.*` reaches
  them only through the documented adapter files enumerated in
  `tests/test_package_layering.py::ADAPTER_FILES`; any other `brain.* → v1` import
  fails the build (`test_brain_does_not_import_top_level_outside_adapters`).
- **v2 systems** are the `brain.cognition.planning.*` goal stack and
  `brain.cog_memory.*` memory stack.
- **Rule:** neither adapter is simplified or removed until its seam is retired
  from `ADAPTER_FILES` in a dedicated commit that explains the migration. The
  ratchet is the enforcement: shrinking `ADAPTER_FILES` is the only way to narrow
  the coupling, and it is a deliberate, reviewed act.

## Maintenance

- When a source-of-truth file moves, update both `.github/CODEOWNERS` and this
  table in the same commit.
- New enforcing checks (Phase 7 ratchets) should be linked from the relevant row
  so the "how it's kept honest" column stays complete.
