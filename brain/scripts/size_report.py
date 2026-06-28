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
    # 603 lines — consciousness telemetry panel; 3 over after the 4E split. A
    # future presentational sub-panel extraction brings it under (real FE change,
    # out of scope for the enforcement pass).
    "frontend/src/components/brain/AttentionPanel.tsx": "603 lines; 4E split candidate",
    # 608 lines — was ~588 (already near the limit) before §9 added per-site
    # failure recording. Bundles specs + sampling + evaluators + scenario seeding:
    # a genuine decomposition candidate (split the harness from the specs), out of
    # scope for the exception-handling pass.
    "brain/benchmarks/__init__.py": "608 lines; harness/specs split candidate",
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
