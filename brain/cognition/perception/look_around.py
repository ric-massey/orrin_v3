# brain/cognition/perception/look_around.py
# Cognition function: Orrin surveys the world he inhabits.
# Produces a structured summary of the working directory — tree shape,
# recently modified files, files Orrin has touched vs. files that are new.
# Output writes to working memory tagged kind="world_perception".
from __future__ import annotations
from brain.core.runtime_log import get_logger

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple

from brain.utils.log import log_activity, log_private
from brain.utils.json_utils import load_json, save_json
from brain.cog_memory.working_memory import update_working_memory
from brain.cog_memory.long_memory import update_long_memory
from brain.paths import WORLD_PERCEPTION_FILE, LONG_MEMORY_FILE
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_LAST_LOOK_TS: float = 0.0
_MIN_INTERVAL_S: float = 300.0   # at most once per 5 minutes


def look_around(context: Dict[str, Any] = None) -> str:
    """
    Cognition function: produce a world-perception snapshot.
    Returns summary string; side-effects write to working memory.
    """
    global _LAST_LOOK_TS
    context = context or {}

    now = time.time()
    if now - _LAST_LOOK_TS < _MIN_INTERVAL_S:
        return "Already looked around recently — no new world snapshot needed."
    _LAST_LOOK_TS = now

    world_root = _find_world_root(context)
    tree_summary = _dir_tree(world_root, max_depth=3, max_items=60)
    recent_mods  = _recent_modifications(world_root, window_s=3600, limit=15)
    own_files    = _orrin_owned_files(context)

    new_files = [p for p, _ in recent_mods if p not in own_files]
    own_touched = [p for p, t in recent_mods if p in own_files]

    # Include world model narrative — the interpreted environment state
    env_narrative = ""
    try:
        from brain.embodiment.world_model import describe as _wm_describe
        env_narrative = _wm_describe()
    except Exception as _e:
        record_failure("look_around.look_around", _e)

    lines = [f"World root: {world_root}"]
    if env_narrative:
        lines.append(f"Environment: {env_narrative}")
    lines.append(f"Directory shape:\n{tree_summary}")
    if recent_mods:
        lines.append("Recently modified:")
        for p, age_s in recent_mods[:8]:
            tag = "[mine]" if p in own_files else "[new]"
            lines.append(f"  {tag} {p}  ({int(age_s)}s ago)")
    if new_files:
        lines.append(f"Files I didn't touch: {', '.join(new_files[:5])}")
    if own_touched:
        lines.append(f"My own files touched: {', '.join(own_touched[:5])}")

    summary = "\n".join(lines)

    # Persist snapshot
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "world_root": str(world_root),
        "tree_summary": tree_summary,
        "recent_modifications": [(p, int(a)) for p, a in recent_mods],
        "new_files": new_files,
        "own_touched": own_touched,
    }
    try:
        existing = load_json(WORLD_PERCEPTION_FILE, default_type=list) or []
        existing.append(snapshot)
        save_json(WORLD_PERCEPTION_FILE, existing[-20:])
    except Exception as _e:
        record_failure("look_around.look_around.2", _e)

    # Write to working memory
    wm_entry = f"[world_perception] {summary[:400]}"
    update_working_memory(wm_entry)

    # Write to long memory if there are notable new files
    if new_files:
        update_long_memory(
            f"[world_perception] New files appeared in my environment: {', '.join(new_files[:5])}",
            emotion="exploration_drive",
            event_type="world_perception",
            importance=2,
            context=context,
        )

    # Register the world root and any new files in the persistent location map
    try:
        from brain.cognition.perception.environment import register_location
        register_location(str(world_root), label="world root", context_note="look_around survey")
        for p, _ in recent_mods[:5]:
            register_location(str(world_root / p), context_note="recently modified")
    except Exception as _e:
        record_failure("look_around.look_around.3", _e)

    log_activity(f"[look_around] Surveyed {world_root} — {len(recent_mods)} recent mods.")
    log_private(f"[look_around] {summary[:300]}")
    return summary


def _find_world_root(context: Dict[str, Any]) -> Path:
    """Find a sensible world root: configured, or infer from brain path."""
    configured = context.get("world_root") or os.environ.get("ORRIN_WORLD_ROOT")
    if configured and Path(configured).is_dir():
        return Path(configured)
    # Walk up from brain/ to find the project root
    here = Path(__file__).resolve().parent
    for _ in range(5):
        if (here / "brain").is_dir() or (here / "main.py").exists():
            return here
        here = here.parent
    return Path.cwd()


def _dir_tree(root: Path, max_depth: int = 3, max_items: int = 60) -> str:
    """Return a compact indented directory tree string."""
    lines: List[str] = []
    _count = [0]

    def _walk(p: Path, depth: int) -> None:
        if depth > max_depth or _count[0] >= max_items:
            return
        try:
            children = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for child in children:
            if child.name.startswith(".") or child.name == "__pycache__":
                continue
            if child.name in ("node_modules", ".git", "venv", ".venv", "dist", "build"):
                continue
            _count[0] += 1
            if _count[0] >= max_items:
                lines.append(f"{'  ' * depth}… (truncated)")
                return
            prefix = "  " * depth
            if child.is_dir():
                lines.append(f"{prefix}{child.name}/")
                _walk(child, depth + 1)
            else:
                lines.append(f"{prefix}{child.name}")

    _walk(root, 0)
    return "\n".join(lines)


def _recent_modifications(root: Path, window_s: float, limit: int) -> List[Tuple[str, float]]:
    """Return (relative_path, age_seconds) for files modified within window_s."""
    now = time.time()
    results: List[Tuple[str, float]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip noise dirs
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", ".git", "node_modules", ".venv", "venv")]
            for fname in filenames:
                if fname.endswith((".pyc", ".pyo")):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    mtime = fpath.stat().st_mtime
                    age = now - mtime
                    if age <= window_s:
                        rel = str(fpath.relative_to(root))
                        results.append((rel, age))
                except Exception:
                    continue
    except Exception as _e:
        record_failure("look_around._recent_modifications", _e)
    results.sort(key=lambda x: x[1])
    return results[:limit]


def _orrin_owned_files(context: Dict[str, Any]) -> set:
    """Files Orrin has recently written/touched — from long memory or context hints."""
    owned: set = set()
    try:
        long_mem = load_json(LONG_MEMORY_FILE, default_type=list) or []
        for e in long_mem[-30:]:
            if not isinstance(e, dict):
                continue
            content = str(e.get("content", ""))
            if "wrote" in content.lower() or "created" in content.lower() or "modified" in content.lower():
                # crude: any path-like token in the content
                for token in content.split():
                    if "/" in token and "." in token:
                        owned.add(token.strip("\"',()[]"))
    except Exception as _e:
        record_failure("look_around._orrin_owned_files", _e)
    return owned
