"""Phase-3 import-normalization ratchet.

The runtime puts both the repo root and `brain/` on sys.path, so a brain module
can be imported under two names (`paths` and `brain.paths`). Those are two
distinct module objects with independent module-level constants — the dual-root
hazard that produced an order-dependent `/api/death` failure (a reloaded `paths`
leaked a tmp DATA_DIR into every later test).

The fix is to converge each leaf package on the single `brain.<pkg>` spelling.
As each leaf is fully converted (every `from <pkg> import` / `import <pkg>` in
source AND tests), add it to ``CONVERTED`` below. This test then fails if any
bare import of an already-converted leaf reappears, so the migration can only
move forward.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Leaf packages whose bare-import conversion to `brain.<pkg>` is complete.
# Append a name here only once `make verify` is green with zero bare imports.
# (Root-level `goals`, `memory`, `supervisor` are legitimately top-level — not leaves.)
CONVERTED = (
    "paths", "utils", "core", "cog_memory", "cognition", "affect", "think",
    "behavior", "agency", "registry", "symbolic", "embodiment", "motivation",
    "peers", "benchmarks", "evidence", "config", "eval",
    # brain-root *modules* (not packages) — bare imports of these only resolved
    # while brain/ was on sys.path (removed in Phase 3 tail), so they belong in
    # the ratchet too.
    "version", "goal_io", "memory_io", "events", "ORRIN_loop",
)

# Source trees that must honor the contract. (Root-level packages like `goals`,
# `memory`, and `supervisor` are legitimately top-level and are not brain leaves.)
SRC_DIRS = ("brain", "backend", "tests", "observability")

# This file intentionally contains the patterns as data; never scan it.
_SELF = Path(__file__).resolve()


def _py_files():
    for d in SRC_DIRS:
        root = REPO / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts or p.resolve() == _SELF:
                continue
            yield p


_LEAF_ALT = "|".join(CONVERTED)
# Bare import statements: `from <leaf>[.x] import` / `import <leaf>[.x][ as A]`.
_STMT_RE = re.compile(
    rf"^[ \t]*(?:from ({_LEAF_ALT})(?:\.|\s+import\b)|import ({_LEAF_ALT})(?:\.|\s+as\b|\s*$|\s*#))",
    re.M,
)
# Dynamic module-path strings that bypass import statements but still create a
# distinct (bare-named) module object: mock targets and runtime imports.
_DYN_RE = re.compile(
    rf"(?:patch|import_module|__import__)\(\s*['\"](?:{_LEAF_ALT})\.",
)


def test_converted_leaves_use_brain_namespace():
    offenders = []
    for p in _py_files():
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in (_STMT_RE, _DYN_RE):
            for m in pat.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                offenders.append(f"{p.relative_to(REPO)}:{line_no}: {m.group(0).strip()}")
    assert not offenders, (
        "bare references to converted leaf package(s) — use `brain.<pkg>`:\n"
        + "\n".join(sorted(offenders))
    )
