"""Ratcheted line-coverage gate (CODEBASE_CLEANUP_PLAN Phase 7).

The plan calls for "changed-lines or ratcheted coverage instead of an arbitrary
global target." This is the ratchet: a recorded floor in ``.coverage-floor`` that
the build may never drop below, and a ``--update`` mode that raises the floor as
coverage improves. There is no hand-picked global target — the floor *is* the
current measured coverage, and it only moves up.

Typical use (also what ``make coverage`` runs):

    coverage run -m pytest -q
    coverage json -o coverage.json
    python -m brain.scripts.coverage_ratchet            # gate: fail if below floor
    python -m brain.scripts.coverage_ratchet --update   # raise the floor after gains

The small ``--tolerance`` (default 0.5 pt) absorbs the coverage jitter that comes
from which optional dependencies happen to be installed (some branches only run
when e.g. spaCy / an LLM SDK is present), so the gate fails on real regressions,
not environment noise.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLOOR_FILE = REPO / ".coverage-floor"
DEFAULT_JSON = REPO / "coverage.json"


def read_floor() -> float:
    if not FLOOR_FILE.exists():
        return 0.0
    return float(FLOOR_FILE.read_text(encoding="utf-8").strip())


def write_floor(value: float) -> None:
    FLOOR_FILE.write_text(f"{value:.1f}\n", encoding="utf-8")


def measured_percent(json_path: Path) -> float:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return float(data["totals"]["percent_covered"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON,
                        help="coverage.json path (default: ./coverage.json)")
    parser.add_argument("--tolerance", type=float, default=0.5,
                        help="points below the floor tolerated before failing")
    parser.add_argument("--update", action="store_true",
                        help="raise the floor to the measured coverage (after gains)")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"coverage-ratchet: no coverage data at {args.json} "
              "(run `coverage run -m pytest && coverage json` first)")
        return 2

    current = measured_percent(args.json)
    floor = read_floor()
    print(f"coverage-ratchet: measured {current:.1f}%  floor {floor:.1f}%  "
          f"(tolerance {args.tolerance:.1f})")

    if args.update:
        if current > floor:
            write_floor(current)
            print(f"coverage-ratchet: floor raised {floor:.1f}% -> {current:.1f}%")
        else:
            print("coverage-ratchet: no gain; floor unchanged")
        return 0

    if current + args.tolerance < floor:
        print(f"::error::coverage {current:.1f}% dropped below floor {floor:.1f}% "
              f"(tolerance {args.tolerance:.1f}). Add tests, or if the drop is "
              "intentional lower .coverage-floor in the same commit with a reason.")
        return 1

    if current > floor + args.tolerance:
        print(f"coverage-ratchet: coverage is {current - floor:.1f} pt above the "
              "floor — run `make coverage-update` to ratchet it up.")
    print("coverage-ratchet: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
