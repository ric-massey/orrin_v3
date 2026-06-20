# tests/test_import_safety.py
# Import-safety smoke tests (CODEBASE_CLEANUP_PLAN Milestone A §3).
#
# The structure audit flagged several ordinary library modules that perform
# real work at *import* time — registries rewrite their JSON catalogs,
# intrinsic_goals migrates completed-goal files, temporal_planner deletes orphan
# plans, self_code ensures its tree, paths/config create directories. That makes
# imports unsafe for tooling, packaging inspection, and tests.
#
# These tests don't (yet) forbid the side effects — that's the explicit-startup
# refactor in Milestone C. What they DO guarantee, and guard against regression,
# is that importing those modules:
#   1. succeeds in a clean process, and
#   2. writes only into the redirected ORRIN_* state dirs, never the developer's
#      live brain/data, brain/logs, or single-instance lock.
#
# main.py is deliberately excluded: it acquires the single-instance lock and
# starts MemoryDaemon at import, which is the very behaviour Milestone C moves
# into an explicit startup object.

from __future__ import annotations
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LIVE_DATA = _REPO_ROOT / "brain" / "data"
_LIVE_LOGS = _REPO_ROOT / "brain" / "logs"

# Ordinary library modules the audit names as mutating state at import. Importing
# any of these must NOT touch the live tree once state dirs are redirected.
_LIBRARY_MODULES = [
    "brain.paths",
    "registry.behavior_registry",
    "registry.cognition_registry",
    "cognition.intrinsic_goals",
    "symbolic.temporal_planner",
    "agency.self_code",
    "memory.config",
]

_IMPORT_SCAN_ROOTS = (
    _REPO_ROOT / "brain",
    _REPO_ROOT / "backend",
    _REPO_ROOT / "goals",
    _REPO_ROOT / "memory",
    _REPO_ROOT / "tests",
)


def test_paths_has_one_canonical_import_name():
    """Prevent reintroducing the dual ``paths`` / ``brain.paths`` module identity."""
    violations: list[str] = []
    candidates = [_REPO_ROOT / "main.py"]
    for root in _IMPORT_SCAN_ROOTS:
        candidates.extend(root.rglob("*.py"))

    for path in candidates:
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "paths":
                violations.append(f"{path.relative_to(_REPO_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "paths":
                        violations.append(f"{path.relative_to(_REPO_ROOT)}:{node.lineno}")

    assert not violations, (
        "Use only `brain.paths`; bare `paths` creates a second module instance:\n"
        + "\n".join(violations)
    )


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snap: dict[str, tuple[int, int]] = {}
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                st = p.stat()
                snap[str(p)] = (st.st_mtime_ns, st.st_size)
    return snap


def _child_env(state_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["ORRIN_DATA_DIR"] = str(state_root / "data")
    env["ORRIN_LOGS_DIR"] = str(state_root / "logs")
    env["ORRIN_THINK_DIR"] = str(state_root / "think")
    env["ORRIN_STATE_DIR"] = str(state_root / "state")
    env["ORRIN_KEYRING"] = "0"
    env.setdefault("PYSTRAY_BACKEND", "dummy")
    # brain/ is a second import root (pytest.ini: pythonpath = . brain)
    env["PYTHONPATH"] = os.pathsep.join([str(_REPO_ROOT), str(_REPO_ROOT / "brain")])
    return env


@pytest.mark.parametrize("module", _LIBRARY_MODULES)
def test_library_import_succeeds_and_spares_live_state(module, tmp_path):
    before_data = _snapshot(_LIVE_DATA)
    before_logs = _snapshot(_LIVE_LOGS)
    before_json = {
        str(p): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in (_REPO_ROOT / "brain").glob("*.json")
    }
    # The live lock may already exist (Orrin runs from this repo); the invariant
    # is that a library import doesn't *change* it, not that it's absent.
    live_lock = _LIVE_DATA / ".orrin.instance.lock"
    lock_before = live_lock.exists()

    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(_REPO_ROOT),
        env=_child_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"importing {module} failed:\n{proc.stderr}"

    after_json = {
        str(p): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in (_REPO_ROOT / "brain").glob("*.json")
    }
    assert _snapshot(_LIVE_DATA) == before_data, f"importing {module} mutated live brain/data"
    assert _snapshot(_LIVE_LOGS) == before_logs, f"importing {module} mutated live brain/logs"
    assert after_json == before_json, f"importing {module} mutated a live brain/*.json file"

    # The redirected data dir is fair game; importing must not create/remove the
    # live single-instance lock.
    assert live_lock.exists() == lock_before, f"importing {module} altered the live instance lock"


def test_importing_library_module_does_not_acquire_instance_lock(tmp_path):
    # Importing a library module must not grab the single-instance lock (that is
    # main.py's job, at explicit startup). Prove a *second* import in a separate
    # process still succeeds — if the first had taken an exclusive flock in the
    # shared state dir, a concurrent boot could be wrongly blocked.
    env = _child_env(tmp_path)
    code = "import registry.behavior_registry, cognition.intrinsic_goals"
    first = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO_ROOT),
                           env=env, capture_output=True, text=True, timeout=120)
    second = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO_ROOT),
                            env=env, capture_output=True, text=True, timeout=120)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert not (tmp_path / "data" / ".orrin.instance.lock").exists()
