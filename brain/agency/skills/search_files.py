# agency/skills/search_files.py
from __future__ import annotations

from pathlib import Path
from brain.utils.log import log_activity, log_error


def search_files(args=None, **kwargs) -> dict:
    """
    Recursively search for files matching a glob pattern under a root directory.
    args: str pattern (e.g. '*.py'), or dict with 'pattern' and optional 'root'.
    Returns {"success": bool, "matches": [str, ...], "count": int}
    """
    if isinstance(args, dict):
        kwargs.update(args)
        args = None

    pattern = str(args or kwargs.get("pattern") or "*")
    root_raw = str(kwargs.get("root") or kwargs.get("directory") or ".")
    max_results = int(kwargs.get("max_results", 100))

    try:
        root = Path(root_raw).expanduser().resolve()
        if not root.exists():
            return {"success": False, "error": f"Root path does not exist: {root}"}

        matches = []
        for p in root.rglob(pattern):
            if len(matches) >= max_results:
                break
            matches.append(str(p))

        log_activity(f"search_files '{pattern}' under {root}: {len(matches)} matches")
        return {"success": True, "pattern": pattern, "root": str(root), "matches": matches, "count": len(matches)}
    except Exception as e:
        log_error(f"search_files failed: {e}")
        return {"success": False, "error": str(e)}
