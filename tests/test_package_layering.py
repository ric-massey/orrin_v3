"""Phase-4.5D package dependency-direction ratchet.

Phase 3 normalized import *naming* (one `brain.<pkg>` spelling, locked by
``test_import_contract.py``) but never built the checklist item "define allowed
package dependency directions / forbidden reverse dependencies fail an
architecture check." This test is that guard.

A 2026-06-22 audit found the real brain package graph is **heavily cyclic** —
``cognition ↔ think ↔ affect ↔ cog_memory ↔ symbolic ↔ utils`` are all mutually
coupled, and ``utils`` (nominally the lowest layer) imports ``affect`` /
``cognition``. Declaring a strict layered order and failing on every back-edge
would fail on day one, and breaking those cycles is a behavior-changing refactor
that is out of scope for the pure-move decomposition phase.

So this is a **forward ratchet**, exactly like the bare-import ratchet: the
current cross-package edge set is frozen as ``BASELINE_EDGES``; the build fails
if a *new* inter-package edge appears. Because any new import cycle requires at
least one new edge, this prevents new cycles and new reverse dependencies from
being introduced — which is the real risk while the monoliths (4.5B/4.5C) are
carved up — without forcing resolution of the pre-existing coupling.

The *intended* dependency direction (the target a future de-cycling pass would
move toward) is documented in ``LAYER_ORDER`` below for reference; it is not
enforced as a hard order while the legacy cycles exist.

To intentionally add a new cross-package edge: add the (src, tgt) pair to
``BASELINE_EDGES`` in a commit that explains why the new coupling is warranted.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRAIN = REPO / "brain"
TOP_LEVEL = {"goals", "memory", "supervisor"}

# Intended layering (low → high), documentation only. A lower layer should not
# import a higher one; the legacy graph violates this (see module docstring), so
# it is recorded here as the de-cycling target, not enforced as a hard order.
LAYER_ORDER = (
    ("utils", "config", "core"),          # foundation
    ("registry", "symbolic", "cog_memory"),
    ("control_signals", "motivation", "runtime_coupling"),
    ("cognition",),
    ("think", "agency", "behavior"),
    ("eval", "peers", "benchmarks", "evidence"),
    ("loop",),                            # orchestration / entry layer
)

# Frozen baseline of cross-package edges (src_pkg -> tgt_pkg) among brain
# subpackages, captured 2026-06-22. A new edge not listed here fails the build.
BASELINE_EDGES = {
    ('(root)', 'cog_memory'), ('(root)', 'cognition'), ('(root)', 'core'),
    ('(root)', 'eval'), ('(root)', 'loop'), ('(root)', 'registry'),
    ('(root)', 'think'), ('(root)', 'utils'),
    # RUN4_FIX_PLAN A2: goal_io credits tier-3 re-use of a produced artifact when a
    # new goal's spec references a prior goal's artifact dir — goal_io (root) →
    # agency (effect_ledger.mark_reused_path). No cycle (effect_ledger doesn't
    # import goal_io); mirrors the existing cognition/control_signals → agency edges.
    ('(root)', 'agency'),
    ('control_signals', 'cog_memory'), ('control_signals', 'cognition'), ('control_signals', 'config'),
    ('control_signals', 'core'), ('control_signals', 'registry'), ('control_signals', 'symbolic'),
    ('control_signals', 'utils'),
    # P2b: feedback_log.log_correction writes a corrected artifact's significance down
    # via effect_ledger (mark_corrected) — control_signals → agency. No cycle
    # (effect_ledger doesn't import control_signals); mirrors the existing
    # cognition → agency edge.
    ('control_signals', 'agency'),
    # AR1 (audit D7): symbolic production points (rule_synthesis, crystallization,
    # autonomous_experiment, causal_graph) record their artifacts on the effect
    # ledger via symbolic_effects — symbolic → agency. No cycle (effect_ledger
    # doesn't import symbolic); mirrors the cognition → agency edge.
    ('symbolic', 'agency'),
    ('agency', 'behavior'), ('agency', 'cog_memory'), ('agency', 'cognition'),
    ('agency', 'core'), ('agency', 'registry'), ('agency', 'think'),
    ('agency', 'utils'),
    ('behavior', 'control_signals'), ('behavior', 'agency'), ('behavior', 'cog_memory'),
    ('behavior', 'cognition'), ('behavior', 'core'), ('behavior', 'runtime_coupling'),
    ('behavior', 'think'), ('behavior', 'utils'),
    ('benchmarks', 'cognition'), ('benchmarks', 'utils'),
    ('cog_memory', 'control_signals'), ('cog_memory', 'cognition'), ('cog_memory', 'core'),
    ('cog_memory', 'utils'),
    ('cognition', 'control_signals'), ('cognition', 'agency'), ('cognition', 'behavior'),
    ('cognition', 'cog_memory'), ('cognition', 'config'), ('cognition', 'core'),
    ('cognition', 'runtime_coupling'), ('cognition', 'evidence'),
    ('cognition', 'motivation'), ('cognition', 'registry'),
    ('cognition', 'symbolic'), ('cognition', 'think'), ('cognition', 'utils'),
    ('core', 'agency'), ('core', 'utils'),
    ('runtime_coupling', 'control_signals'), ('runtime_coupling', 'cog_memory'), ('runtime_coupling', 'core'),
    ('runtime_coupling', 'registry'), ('runtime_coupling', 'symbolic'), ('runtime_coupling', 'utils'),
    ('eval', 'control_signals'), ('eval', 'core'), ('eval', 'think'), ('eval', 'utils'),
    # F15 (2026-07-08 addendum): the evaluator's delayed goal-closure reward is
    # gated on a grounded credited effect (effect_ledger.has_qualifying_effect)
    # and scaled by the closure's significance (goal_outcomes.achievement_
    # significance) — eval → agency/cognition. No cycle (neither package imports
    # eval), and both edges follow LAYER_ORDER (eval sits above cognition/agency).
    ('eval', 'agency'), ('eval', 'cognition'),
    ('evidence', 'utils'),
    ('loop', 'control_signals'), ('loop', 'agency'), ('loop', 'behavior'),
    ('loop', 'benchmarks'), ('loop', 'cog_memory'), ('loop', 'cognition'),
    ('loop', 'config'), ('loop', 'core'), ('loop', 'runtime_coupling'), ('loop', 'eval'),
    ('loop', 'motivation'), ('loop', 'peers'), ('loop', 'registry'),
    ('loop', 'symbolic'), ('loop', 'think'), ('loop', 'utils'),
    ('motivation', 'control_signals'), ('motivation', 'cog_memory'), ('motivation', 'core'),
    ('motivation', 'think'), ('motivation', 'utils'),
    ('peers', 'cognition'), ('peers', 'core'), ('peers', 'symbolic'),
    ('peers', 'utils'),
    ('registry', 'cognition'), ('registry', 'core'), ('registry', 'utils'),
    ('scripts', 'cog_memory'), ('scripts', 'cognition'), ('scripts', 'utils'),
    ('symbolic', 'cog_memory'), ('symbolic', 'cognition'), ('symbolic', 'core'),
    ('symbolic', 'utils'),
    ('think', 'control_signals'), ('think', 'behavior'), ('think', 'cog_memory'),
    ('think', 'cognition'), ('think', 'config'), ('think', 'core'),
    ('think', 'motivation'), ('think', 'registry'), ('think', 'symbolic'),
    ('think', 'utils'),
    ('utils', 'control_signals'), ('utils', 'cognition'), ('utils', 'core'),
    ('utils', 'registry'), ('utils', 'symbolic'),
}

# The only brain files allowed to import the top-level v1 packages
# (goals/memory/supervisor). These are the documented adapter/seam files; the
# coupling is the v1↔v2 bridge the cleanup plan keeps behind ownership tables.
# Any OTHER brain file importing goals/memory/supervisor fails the build.
ADAPTER_FILES = {
    "brain/ORRIN_loop.py",
    "brain/cognition/terminal.py",
    "brain/evidence/life_capsule.py",
    "brain/goal_io.py",
    "brain/loop/finalize.py",
    "brain/memory_io.py",
    "brain/scripts/resource_floor_calibration_run.py",
    "brain/utils/goals_feed.py",
    "brain/utils/mind_archive.py",
}


def _brain_pkgs():
    return {p.name for p in BRAIN.iterdir()
            if p.is_dir() and not p.name.startswith("__") and any(p.rglob("*.py"))}


def _imported_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _scan():
    """Return (cross_package_edges, top_level_violations)."""
    pkgs = _brain_pkgs()
    edges = set()
    top_violations = []
    for py in BRAIN.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        rel_parts = py.relative_to(BRAIN).parts
        src = rel_parts[0] if len(rel_parts) > 1 else "(root)"
        rel_path = py.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for mod in _imported_modules(tree):
            parts = mod.split(".")
            if parts[0] == "brain" and len(parts) >= 2 and parts[1] in pkgs and parts[1] != src:
                edges.add((src, parts[1]))
            if parts[0] in TOP_LEVEL and rel_path not in ADAPTER_FILES:
                top_violations.append((rel_path, mod))
    return edges, top_violations


def test_no_new_cross_package_edges():
    edges, _ = _scan()
    new_edges = sorted(edges - BASELINE_EDGES)
    assert not new_edges, (
        "New cross-package import edge(s) introduced among brain subpackages:\n"
        + "\n".join(f"  brain.{s} -> brain.{t}" for s, t in new_edges)
        + "\n\nThis ratchet prevents new package coupling / import cycles during "
        "decomposition. If the new edge is intentional, add the (src, tgt) pair "
        "to BASELINE_EDGES in tests/test_package_layering.py with a justification."
    )


def test_brain_does_not_import_top_level_outside_adapters():
    _, top_violations = _scan()
    assert not top_violations, (
        "brain.* imported a top-level v1 package (goals/memory/supervisor) outside the "
        "documented adapter seam:\n"
        + "\n".join(f"  {f}: import {m}" for f, m in sorted(set(top_violations)))
        + "\n\nKeep the v1↔v2 coupling confined to ADAPTER_FILES, or add the new "
        "seam file there with a justification."
    )


def test_adapter_files_exist():
    # Keep the allowlist honest: a stale entry means the seam moved/was deleted.
    for f in ADAPTER_FILES:
        assert (REPO / f).exists(), f"ADAPTER_FILES lists a missing file: {f}"
