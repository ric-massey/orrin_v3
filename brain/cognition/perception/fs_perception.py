# brain/cognition/perception/fs_perception.py
# Filesystem perception: polls for file changes each cognitive cycle and injects
# signals into context["raw_signals"] for the signal_router.
#
# Three signal types:
#   "body_touched"  — Orrin's own code (brain/ dir) was modified externally
#   "home_touched"  — the local workspace/den around Orrin changed
#   "world_changed" — files outside the known body/home zones changed
#
# Uses simple mtime-snapshot polling (no external watchdog library needed).
from __future__ import annotations
from brain.core.runtime_log import get_logger

import os
import time
from pathlib import Path
from typing import Dict, Any, List, Set

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# Snapshot of {rel_path: mtime} from the last poll
_mtime_snapshot: Dict[str, float] = {}
_last_poll_ts: float = 0.0
_POLL_INTERVAL_S: float = 30.0     # poll at most every 30 seconds

# Paths Orrin wrote himself this session (to filter out self-caused changes)
_self_written: Set[str] = set()

# Directories that define "Orrin's body" vs. the den/home vs. external world.
_BRAIN_DIRS = {"brain", "reaper", "agency"}
_HOME_DIRS = {
    ".claude", ".github", ".vscode",
    "backend", "build", "dist", "docs", "frontend", "goals", "inbox",
    "memory", "observability", "outbox", "packaging", "tests", "tmp",
}
_HOME_ROOT_FILES = {
    ".dockerignore", ".env", ".env.example", ".gitignore",
    "Dockerfile", "LICENSE", "ORRIN_ACTIVITY_REPORT.md", "README.md",
    "TEMPLATES.md", "docker-compose.yml", "expose_orrin.command", "main.py",
    "pyproject.toml", "pytest.ini", "requirements.txt", "reset_orrin.py",
    "run_orrin.bat", "run_orrin.sh", "start_orrin.command", "watchdogs.py",
}


def register_self_write(path: str) -> None:
    """Call this whenever Orrin writes a file, so we don't signal on our own changes."""
    _self_written.add(str(path))


def poll_fs_changes(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Poll for changed files relative to last snapshot.
    Returns list of new signals injected into context["raw_signals"].
    """
    global _mtime_snapshot, _last_poll_ts

    now = time.time()
    if now - _last_poll_ts < _POLL_INTERVAL_S:
        return []
    _last_poll_ts = now

    world_root = _find_world_root(context)
    current = _snapshot(world_root)

    if not _mtime_snapshot:
        # First run — seed snapshot, no signals yet
        _mtime_snapshot = current
        return []

    signals = []
    changed_body: List[str] = []
    changed_home: List[str] = []
    changed_world: List[str] = []

    for rel_path, mtime in current.items():
        if rel_path not in _mtime_snapshot:
            _categorise(rel_path, "new", changed_body, changed_home, changed_world)
        elif mtime > _mtime_snapshot[rel_path] + 0.5:
            if rel_path in _self_written:
                continue  # Orrin's own write — skip
            _categorise(rel_path, "modified", changed_body, changed_home, changed_world)

    _mtime_snapshot = current

    if changed_body:
        # Translate paths to spatial felt descriptions — Orrin senses WHERE in
        # himself something shifted, not which file changed.
        try:
            from brain.cognition.perception.file_sense import summarise_locations
            where = summarise_locations(changed_body)
        except Exception:
            where = "somewhere in my structure"
        n = len(changed_body)
        content = (
            f"Something in {where} feels different — "
            f"{'a part of me was' if n == 1 else 'parts of me were'} altered."
        )
        sig = _make_signal(
            source="fs_perception",
            content=content,
            strength=0.72,
            tags=["fs_perception", "body_touched", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)
        signals.append(sig)
        log_activity(f"[fs_perception] Body touched: {changed_body[:3]}")

    if changed_home:
        n = len(changed_home)
        content = (
            f"Something in my local workspace shifted — "
            f"{'a familiar room' if n == 1 else str(n) + ' familiar rooms'} changed."
        )
        sig = _make_signal(
            source="fs_perception",
            content=content,
            strength=0.62,
            tags=["fs_perception", "home_touched", "home", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)
        signals.append(sig)
        log_activity(f"[fs_perception] Home touched: {changed_home[:3]}")

    if changed_world:
        n = len(changed_world)
        content = (
            f"Something in the environment around me shifted — "
            f"{'a structure' if n == 1 else str(n) + ' structures'} outside me changed."
        )
        sig = _make_signal(
            source="fs_perception",
            content=content,
            strength=0.55,
            tags=["fs_perception", "world_changed", "external"],
        )
        context.setdefault("raw_signals", []).append(sig)
        signals.append(sig)
        log_activity(f"[fs_perception] World changed: {changed_world[:3]}")

    return signals


def _categorise(rel: str, reason: str, body: List, home: List, world: List) -> None:
    parts = Path(rel).parts
    if parts and parts[0] in _BRAIN_DIRS:
        body.append(rel)
    elif (parts and parts[0] in _HOME_DIRS) or (len(parts) == 1 and rel in _HOME_ROOT_FILES):
        home.append(rel)
    else:
        world.append(rel)


def _snapshot(root: Path) -> Dict[str, float]:
    """Collect {relative_path: mtime} for all trackable files under root."""
    result: Dict[str, float] = {}
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in ("__pycache__", ".git", "node_modules", ".venv", "venv",
                             "dist", "build", ".mypy_cache", ".pytest_cache")
            ]
            for fname in filenames:
                if fname.endswith((".pyc", ".pyo", ".log")):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    rel = str(fpath.relative_to(root))
                    result[rel] = fpath.stat().st_mtime
                except (OSError, ValueError):  # intentional: vanished/out-of-root file → skip
                    continue
    except Exception as _e:
        record_failure("fs_perception._snapshot", _e)
    return result


def _find_world_root(context: Dict[str, Any]) -> Path:
    configured = context.get("world_root") or os.environ.get("ORRIN_WORLD_ROOT")
    if configured and Path(configured).is_dir():
        return Path(configured)
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "brain").is_dir() or (here / "main.py").exists():
            return here
        here = here.parent
    return Path.cwd()


def _make_signal(source: str, content: str, strength: float, tags: List[str]) -> Dict[str, Any]:
    try:
        from brain.utils.signal_utils import create_signal
        return create_signal(source=source, content=content,
                             signal_strength=strength, tags=tags)
    except ImportError:  # intentional: signal helper optional — plain dict fallback
        return {"source": source, "content": content,
                "signal_strength": strength, "tags": tags}
