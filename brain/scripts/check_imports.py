#!/usr/bin/env python3
"""
Import boundary checker — reports upward-layer violations and circular cycles.

Run from brain/: python3 scripts/check_imports.py [--cycles] [--violations]

This version (2026-06-07) classifies every edge by SCOPE so deferred/guarded
imports — which are load-safe and cannot cause a circular ImportError — no longer
masquerade as the same severity as bare top-level imports:

  top       module-level, unguarded import  → real load-time coupling
  guarded   module-level inside try/except (ImportError/Exception/bare) → load-safe
  deferred  inside a function/lambda body    → load-safe

The headline number to act on is **HARD violations** = top-level, unguarded edges
that are not in ALLOWED_EDGES. Two cycle passes are reported: the full package
graph (any scope) and the load-time graph (top-level-unguarded edges only) — only
the latter can actually fail at import time.
"""
from __future__ import annotations
import ast
import sys
from collections import defaultdict
from pathlib import Path

BRAIN = Path(__file__).resolve().parent.parent

# Layer model. `registry` is L2 infra: it statically imports only L0/L1 and is
# consulted (downward) by higher layers; its single cognition import is deferred.
LAYER: dict[str, int] = {
    "core":       0,
    "paths":      1,
    "utils":      1,
    "cog_memory": 2,
    "symbolic":   2,
    "registry":   2,
    "affect":     3,
    "cognition":  3,
    "embodiment": 3,
    "motivation": 3,
    "think":      4,
    "behavior":   5,
    "agency":     5,
    "eval":       6,
    "peers":      6,
}

# Intentional cross-layer edges that are architecture, not debt. `think` is the
# orchestrator and necessarily drives `behavior`; this is the one direction that
# is sanctioned (the `behavior → think` back-edges are deliberately NOT here so
# the genuine peer-cycle residual stays visible).
ALLOWED_EDGES: set[tuple[str, str]] = {
    ("think", "behavior"),
}

_GUARD_EXC = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _pkg(path: Path) -> str:
    parts = path.relative_to(BRAIN).parts
    return parts[0] if parts else ""


def _try_guards_import(try_node: ast.Try) -> bool:
    """True if any handler catches ImportError/Exception/BaseException or is bare."""
    for h in try_node.handlers:
        t = h.type
        if t is None:                                  # bare `except:`
            return True
        names: list[str] = []
        if isinstance(t, ast.Tuple):
            names = [e.attr if isinstance(e, ast.Attribute) else getattr(e, "id", "")
                     for e in t.elts]
        elif isinstance(t, ast.Attribute):
            names = [t.attr]
        elif isinstance(t, ast.Name):
            names = [t.id]
        if any(n in _GUARD_EXC for n in names):
            return True
    return False


def _classify_imports(tree: ast.AST) -> list[tuple[str, str]]:
    """Return (top_level_module, scope) for every import in the file.

    Processes each node first (recording it if it is an import), then recurses
    into its children with the appropriate function/guard context.
    """
    out: list[tuple[str, str]] = []

    def walk(node: ast.AST, in_func: bool, in_guard: bool) -> None:
        # 1) record THIS node if it is an import
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                mods = [node.module.split(".")[0]] if node.module else []
            else:
                mods = [a.name.split(".")[0] for a in node.names]
            scope = "deferred" if in_func else ("guarded" if in_guard else "top")
            out.extend((m, scope) for m in mods)
            return  # imports carry no relevant children

        # 2) entering a function body makes everything below it deferred
        child_in_func = in_func or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))

        # 3) a try whose handlers catch ImportError/Exception guards its BODY only
        if isinstance(node, ast.Try):
            guarded = in_guard or _try_guards_import(node)
            for stmt in node.body:
                walk(stmt, child_in_func, guarded)
            for h in node.handlers:        # fallback imports use the outer guard ctx
                walk(h, child_in_func, in_guard)
            for stmt in node.orelse:
                walk(stmt, child_in_func, in_guard)
            for stmt in node.finalbody:
                walk(stmt, child_in_func, in_guard)
            return

        for child in ast.iter_child_nodes(node):
            walk(child, child_in_func, in_guard)

    walk(tree, False, False)
    return out


def _collect():
    # violations: (path, src_pkg, src_layer, dst_pkg, dst_layer, scope)
    violations: list[tuple] = []
    pkg_deps: dict[str, set[str]] = defaultdict(set)        # full graph (any scope)
    load_deps: dict[str, set[str]] = defaultdict(set)       # top-level-unguarded only

    for py in sorted(BRAIN.rglob("*.py")):
        if "__pycache__" in py.parts or "scripts" in py.parts:
            continue
        src_pkg = _pkg(py)
        src_layer = LAYER.get(src_pkg, -1)
        if src_layer < 0:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for imp, scope in _classify_imports(tree):
            dst_layer = LAYER.get(imp, -1)
            if dst_layer < 0 or imp == src_pkg:
                continue
            pkg_deps[src_pkg].add(imp)
            if scope == "top":
                load_deps[src_pkg].add(imp)
            if dst_layer > src_layer:
                violations.append((py, src_pkg, src_layer, imp, dst_layer, scope))

    return violations, dict(pkg_deps), dict(load_deps)


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    visited: set[str] = set()
    rec: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec.add(node)
        for nb in sorted(graph.get(node, [])):
            if nb not in visited:
                dfs(nb, path + [nb])
            elif nb in rec:
                idx = path.index(nb) if nb in path else 0
                cycles.append(path[idx:] + [nb])
        rec.discard(node)

    for node in sorted(graph):
        if node not in visited:
            dfs(node, [node])
    return cycles


def _dedupe(cycles: list[list[str]]) -> list[list[str]]:
    seen: set[tuple] = set()
    out: list[list[str]] = []
    for c in sorted(cycles, key=len):
        key = tuple(sorted(set(c)))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def main() -> None:
    args = sys.argv[1:]
    show_cycles = "--cycles" in args or not args
    show_violations = "--violations" in args or not args

    violations, pkg_deps, load_deps = _collect()

    if show_violations:
        print(f"\n{'FILE':<52} {'SRC':<11} {'L':>2}  {'IMPORTS':<12} {'L':>2}  SCOPE")
        print("-" * 96)
        seen = None
        for (path, src_pkg, sl, dst_pkg, dl, scope) in sorted(
            violations, key=lambda v: (v[1], v[3], v[5], str(v[0]))
        ):
            key = (src_pkg, dst_pkg)
            tag = " ← NEW PAIR" if key != seen else ""
            seen = key
            allow = "  [allowed]" if key in ALLOWED_EDGES else ""
            rel = str(path.relative_to(BRAIN))
            print(f"{rel:<52} {src_pkg:<11} {sl:>2}  {dst_pkg:<12} {dl:>2}  {scope}{allow}{tag}")

        by_scope = defaultdict(int)
        for v in violations:
            by_scope[v[5]] += 1
        hard = [v for v in violations
                if v[5] == "top" and (v[1], v[3]) not in ALLOWED_EDGES]
        hard_pairs = sorted({(v[1], v[3]) for v in hard})
        pairs = len({(v[1], v[3]) for v in violations})
        print(f"\n{len(violations)} violations / {pairs} pairs  "
              f"(top={by_scope['top']}, guarded={by_scope['guarded']}, deferred={by_scope['deferred']})")
        print(f"HARD violations (top-level, unguarded, not allowlisted): "
              f"{len(hard)} across {len(hard_pairs)} pair(s)")
        for p in hard_pairs:
            print(f"    {p[0]} → {p[1]}")
        print()

    if show_cycles:
        full = _dedupe(_find_cycles(pkg_deps))
        load = _dedupe(_find_cycles(load_deps))
        print("CIRCULAR CYCLES (full package graph — includes load-safe deferred/guarded edges):")
        for c in full:
            print("  " + " → ".join(c))
        print(f"\n{len(full)} unique cycles (full graph)")
        print("\nLOAD-TIME CYCLES (package pairs with mutual top-level-unguarded imports — the\n"
              "most likely source of a real circular ImportError; confirm with an actual import,\n"
              "since Python resolves at module granularity and these may still load cleanly):")
        if load:
            for c in load:
                print("  " + " → ".join(c))
        else:
            print("  (none)")
        print(f"\n{len(load)} unique load-time cycles\n")


if __name__ == "__main__":
    main()
