"""Report broad exception handlers that silently discard diagnostic evidence."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOTS = ("brain", "backend", "goals", "memory", "reaper", "observability", "main.py")

# Forward-ratchet ceiling for silent broad handlers (STRUCTURAL_DEBT_PLAN §9).
# This is the single source of truth shared by the report (`make audit-exceptions`)
# and the gate (`tests/test_exception_ratchet.py`) so they can never disagree.
# It freezes the count when the ratchet landed; it may only ever be *lowered*, in
# the same commit that reclassifies the handlers (log / narrow / re-raise / annotate)
# that bring the real count down. New silent handlers cannot be added.
CEILING = 54
OBSERVABILITY_CALLS = {
    "record_failure",
    "log_error",
    "log_activity",
    "warning",
    "error",
    "exception",
    "print",
}


def repo_root() -> Path:
    """Repository root (parent of the `brain/` package)."""
    return Path(__file__).resolve().parents[2]


def _python_files(root: Path) -> Iterable[Path]:
    for name in ROOTS:
        path = root / name
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from path.rglob("*.py")


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = getattr(child.func, "id", None) or getattr(child.func, "attr", None)
        if name:
            names.add(str(name))
    return names


def find_silent_broad_handlers(root: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in _python_files(root):
        if "data/_archive" in path.as_posix():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            broad = node.type is None or (
                isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
            )
            if not broad or _call_names(node) & OBSERVABILITY_CALLS:
                continue
            if len(node.body) != 1 or not isinstance(
                node.body[0], (ast.Pass, ast.Continue, ast.Return)
            ):
                continue
            findings.append((path.relative_to(root), node.lineno, ast.unparse(node.body[0])))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=30, help="files to include in summary")
    parser.add_argument("--details", action="store_true", help="print every finding")
    args = parser.parse_args()

    root = repo_root()
    findings = find_silent_broad_handlers(root)
    counts = Counter(str(path) for path, _, _ in findings)
    print(
        f"silent broad handlers: {len(findings)} across {len(counts)} files "
        f"(ratchet ceiling: {CEILING})"
    )
    for path, count in counts.most_common(max(0, args.top)):
        print(f"{count:4}  {path}")
    if args.details:
        for path, line, behavior in findings:
            print(f"{path}:{line}: {behavior}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
