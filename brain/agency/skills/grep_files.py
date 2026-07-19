# agency/skills/grep_files.py
# Content-search across files — lets Orrin grep his own source/data files.
# Returns matching lines with surrounding context, like grep -n -C 2.
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any

from brain.utils.log import log_activity


def grep_files(args=None, **kwargs) -> Dict[str, Any]:
    """
    Search file contents for a keyword or regex pattern.

    Args (dict or positional string):
        query       (str, required) — substring or regex to search for
        root        (str)  — directory to search under (default: brain/data/)
        pattern     (str)  — glob to filter files (default: "*.json,*.txt,*.py")
        max_results (int)  — max matching lines to return (default: 50)
        context_lines (int)— lines of context before/after each match (default: 1)
        case_sensitive (bool) — default False

    Returns:
        {"success": bool, "query": str, "matches": [...], "count": int}
        Each match: {"file": str, "line": int, "text": str, "context": [str]}
    """
    if isinstance(args, dict):
        kwargs.update(args)
        args = None

    query = str(args or kwargs.get("query") or kwargs.get("pattern") or "").strip()
    if not query:
        return {"success": False, "error": "No query provided."}

    _brain_root = Path(__file__).resolve().parent.parent.parent  # brain/
    # Resolve the default through brain.paths (never hand-built): a hardcoded
    # brain/data bypasses ORRIN_DATA_DIR and breaks test isolation (golden rule 3).
    from brain.paths import DATA_DIR as _data_dir
    root_raw = str(kwargs.get("root") or kwargs.get("directory") or _data_dir)
    root = Path(root_raw).expanduser().resolve()

    if not root.exists():
        return {"success": False, "error": f"Path does not exist: {root}"}

    # Respect a safety boundary — only allow searching within the brain
    # directory or the (possibly redirected) data tree.
    try:
        root.relative_to(_brain_root)
    except ValueError:
        try:
            root.relative_to(_data_dir.resolve())
        except ValueError:
            return {"success": False, "error": "Search root must be within the brain directory."}

    glob_patterns = str(kwargs.get("file_pattern") or "*.json,*.txt,*.py,*.md").split(",")
    max_results = int(kwargs.get("max_results", 50))
    ctx_lines = int(kwargs.get("context_lines", 1))
    case_sensitive = bool(kwargs.get("case_sensitive", False))

    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(query, flags)
    except re.error as e:
        return {"success": False, "error": f"Invalid regex: {e}"}

    # ANATOMY MEMBRANE (M1/M2/M3): an unidentified caller is reasoning-layer —
    # blueprints (source), organ state (brain/data) and flight-recorder
    # transcripts never enter its result set; the diary exception and the
    # agency organs (caller in membrane.ORGAN_CALLERS) pass. Fail-closed wall.
    from brain.cognition.membrane import caller_is_organ, deny_reason
    _organ = caller_is_organ(kwargs.get("caller"))
    denied = 0

    matches: List[Dict[str, Any]] = []

    for glob_pat in glob_patterns:
        glob_pat = glob_pat.strip()
        if not glob_pat:
            continue
        for file_path in root.rglob(glob_pat):
            if len(matches) >= max_results:
                break
            if not _organ and deny_reason(file_path) is not None:
                denied += 1
                continue
            # Skip large files and binary-looking files
            try:
                if file_path.stat().st_size > 500_000:
                    continue
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:  # intentional: skip unreadable/oversized file
                continue

            for i, line in enumerate(lines):
                if len(matches) >= max_results:
                    break
                if regex.search(line):
                    start = max(0, i - ctx_lines)
                    end = min(len(lines), i + ctx_lines + 1)
                    context = lines[start:end]
                    try:
                        _rel = str(file_path.relative_to(_brain_root))
                    except ValueError:   # redirected data tree lives outside brain/
                        _rel = str(file_path)
                    matches.append({
                        "file": _rel,
                        "line": i + 1,
                        "text": line.strip()[:300],
                        "context": [l.strip()[:200] for l in context],
                    })

        if len(matches) >= max_results:
            break

    try:
        _root_rel = str(root.relative_to(_brain_root))
    except ValueError:
        _root_rel = str(root)
    log_activity(f"grep_files '{query}' under {_root_rel}: "
                 f"{len(matches)} matches ({denied} behind the membrane)")
    return {
        "success": True,
        "query": query,
        "root": _root_rel,
        "matches": matches,
        "count": len(matches),
        "truncated": len(matches) >= max_results,
        "membrane_denied": denied,
    }
