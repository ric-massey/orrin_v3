"""Module size/complexity report (CODEBASE_CLEANUP_PLAN Phase 7).

Reports hand-maintained source modules by line count, flags those over the
600-line soft limit, and warns on modules *approaching* it. This is the
human-readable companion to ``tests/test_module_size.py`` (the ratchet that
fails CI when a *new* module crosses the limit): the test imports the scan
policy from here so the two never drift.

    make size-report                 # full report
    python -m brain.scripts.size_report --warn-only   # only flagged modules
    python -m brain.scripts.size_report --top 20      # largest 20

Soft limit and exemptions are the single source of truth in this module:
``SOFT_LIMIT``, ``WARN_LIMIT``, ``EXEMPT``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SOFT_LIMIT = 600
# Modules within this many lines of the limit are "approaching" (warned, not failed).
WARN_LIMIT = 540

# Source roots scanned. Tests, generated code, vendored deps, and build output
# are excluded — the limit is about hand-maintained source readability.
SOURCE_GLOBS = (
    "brain/**/*.py",
    "backend/**/*.py",
    "goals/**/*.py",
    "memory/**/*.py",
    "supervisor/**/*.py",
    "runtime/**/*.py",
    "observability/**/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
    "main.py",
    "watchdogs.py",
    "reset_orrin.py",
)

EXCLUDE_FRAGMENTS = (
    "/__pycache__/",
    "/node_modules/",
    "/dist/",
    "/tests/",
    "_test.py",
    "_tests/",
    ".test.ts",
    ".test.tsx",
    ".spec.ts",
    ".spec.tsx",
    ".gen.ts",
)

# Files already over the soft limit when the Phase-7 ratchet landed (2026-06-23).
# Frozen with a reason; expected to trend down. ``test_module_size.py`` fails if
# one is deleted or drops under the limit (so the exemption can't go stale).
EXEMPT: dict[str, str] = {
    # 604 lines — was 595 (already at the limit) before RUN4 B4.1 added the
    # make-shaped credit guard to _evidenced_aspiration (a research/intake memo can
    # no longer wear the making hat). Bundles aspiration bootstrapping + crediting +
    # the learned drive→aspiration EMA + partial-credit scoring: a genuine
    # decomposition candidate (split the crediting core from the learning ledger),
    # out of scope for this behavioural-fix pass.
    "brain/cognition/intrinsic_objectives.py": "604 lines; crediting/learning split candidate (RUN4 B4)",
    # 603 lines — consciousness telemetry panel; 3 over after the 4E split. A
    # future presentational sub-panel extraction brings it under (real FE change,
    # out of scope for the enforcement pass).
    "frontend/src/components/brain/AttentionPanel.tsx": "603 lines; 4E split candidate",
    # 608 lines — was ~588 (already near the limit) before §9 added per-site
    # failure recording. Bundles specs + sampling + evaluators + scenario seeding:
    # a genuine decomposition candidate (split the harness from the specs), out of
    # scope for the exception-handling pass.
    "brain/benchmarks/__init__.py": "608 lines; harness/specs split candidate",
    # 640 lines — was 575 (under the limit) before the grounding-plan P2b/P3 work
    # added cohesive ledger ops: tool_run_effect significance + has_effect_kind (P3
    # check-pass gate) and mark_corrected/correction_count (P2b, the write-down mirror
    # of mark_reused). These belong with the ledger; a future split of the
    # significance/novelty scoring helpers from the persistence core brings it under.
    "brain/agency/effect_ledger.py": "640 lines; scoring/persistence split candidate (P2b/P3)",
    # 679 lines — was 648 (already over) before P2a added the reward-weighted diet
    # (block weighting + reward channel). The training/consolidation passes belong
    # together; a future split of the corpus-assembly helpers (sources → weighted
    # blocks) from the bout runner brings it under.
    "brain/cognition/language/acquisition.py": "679 lines; corpus-assembly split candidate (P2a)",
    # 638 lines — was exactly 600 at the ratchet baseline; the grounded-cognition
    # appraisal work plus P5's time-at-ceiling accelerator on the per-call
    # restoring pull crossed it. The decay/ceiling/velocity passes are one
    # pipeline; the standing decomposition candidate is extracting the per-call
    # restoring-force block into signal_dynamics (where its siblings live).
    "brain/control_signals/update_signal_state.py": "638 lines; restoring-force extraction candidate (P5)",
    # 619 lines — was 585 before the grounding-plan symbolic goal generators grew
    # (frontier/introspective reframe). Generator-per-drive is cohesive; a future
    # split into a package (one module per generator family) brings it under.
    "brain/cognition/intrinsic_generators.py": "619 lines; generator-family split candidate",
    # 675 lines — was 600 (exactly at the limit) before the R9-F1/F2/F4 race
    # fixes (in-flight set, fresh step re-read, zombie/terminal-goal guard,
    # attempts cap, failed-step error attribution). The concurrency guards
    # belong at the execution seam they protect; the standing decomposition
    # candidate is splitting finalization (_maybe_finalize_goal + effects
    # recording) from the worker loop.
    "goals/runner.py": "675 lines; execution/finalization split candidate (R9-F1..F4)",
    # 607 lines — was 594 before the R9 watchdog wiring (cycle_stall_guard in
    # the start_watchdogs unpack + the loud DEGRADED fallback replacing the
    # silent TypeError that had been eating every resource provider). main.py
    # decomposition is the ongoing Phase-4 extraction track.
    "main.py": "607 lines; boot decomposition ongoing (Phase 4)",
}


def _is_excluded(rel_path: str) -> bool:
    return any(frag in rel_path for frag in EXCLUDE_FRAGMENTS)


def _line_count(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def module_sizes() -> list[tuple[str, int]]:
    """Return [(rel_path, line_count)] for every scanned source module, largest first."""
    seen: dict[str, int] = {}
    for glob in SOURCE_GLOBS:
        for path in REPO.glob(glob):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO).as_posix()
            if _is_excluded(rel) or rel in seen:
                continue
            seen[rel] = _line_count(path)
    return sorted(seen.items(), key=lambda kv: -kv[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=0,
                        help="show only the N largest modules (0 = all)")
    parser.add_argument("--warn-only", action="store_true",
                        help="show only modules at/over the warn threshold")
    args = parser.parse_args()

    sizes = module_sizes()
    over = [(r, n) for r, n in sizes if n > SOFT_LIMIT and r not in EXEMPT]
    warn = [(r, n) for r, n in sizes if WARN_LIMIT <= n <= SOFT_LIMIT and r not in EXEMPT]
    exempt = [(r, n) for r, n in sizes if r in EXEMPT]

    print(f"scanned {len(sizes)} source modules  (soft limit {SOFT_LIMIT}, "
          f"warn ≥ {WARN_LIMIT})")
    print(f"  over limit: {len(over)}   approaching: {len(warn)}   exempt: {len(exempt)}")
    print()

    rows = sizes
    if args.warn_only:
        rows = [(r, n) for r, n in sizes if n >= WARN_LIMIT or r in EXEMPT]
    if args.top > 0:
        rows = rows[: args.top]

    for rel, lines in rows:
        if rel in EXEMPT:
            tag = "EXEMPT  "
        elif lines > SOFT_LIMIT:
            tag = "OVER    "
        elif lines >= WARN_LIMIT:
            tag = "approach"
        else:
            tag = "        "
        print(f"  {lines:5}  {tag}  {rel}")

    # Non-zero exit if an un-exempt module is over the limit (mirrors the ratchet),
    # so the script is usable as a standalone check too.
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
