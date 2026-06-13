# agency/skills/list_directory.py
from __future__ import annotations

from pathlib import Path
from utils.log import log_activity, log_error


def list_directory(args=None, **kwargs) -> dict:
    """
    List files and folders in a directory.
    args: path string, or dict with key 'path'.
    Returns {"success": bool, "entries": [...], "path": str}
    """
    if isinstance(args, dict):
        kwargs.update(args)
        args = None

    raw_path = str(args or kwargs.get("path") or kwargs.get("directory") or ".")
    try:
        p = Path(raw_path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Path does not exist: {p}"}
        if not p.is_dir():
            return {"success": False, "error": f"Not a directory: {p}"}

        entries = []
        for item in sorted(p.iterdir()):
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })

        log_activity(f"Listed directory: {p} ({len(entries)} entries)")
        return {"success": True, "path": str(p), "entries": entries[:200]}
    except Exception as e:
        log_error(f"list_directory failed: {e}")
        return {"success": False, "error": str(e)}
