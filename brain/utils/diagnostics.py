"""
utils/diagnostics.py — the opt-in "Export diagnostics" bundle (§10.7).

"Anyone can download him" means crashes happen on machines you'll never see. This
produces a small, shareable archive of *operational* signal — recent logs plus the
boot/death/crash state tag (§10.5) and the schema version — that a user can choose to
send when something goes wrong. There is NO silent telemetry: the same
data-leaves-only-when-you-say-so principle as the rest of Part 9.

Privacy is enforced by an ALLOWLIST, not a denylist: only files known to be operational
are bundled, so memory content, private/final thoughts, the autobiography, chat logs,
and the conscious stream are NEVER included — adding a new state file can't accidentally
leak it. Each log is tail-bounded so the bundle stays small and can't smuggle history.
"""
from __future__ import annotations

import io
import json
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import brain.paths as paths

# Operational log files under DATA_DIR that are safe to share — errors, model/IO
# failures, incidents, the run-state marker, the schema stamp. Deliberately excludes
# anything carrying Orrin's content (long_memory, private_thoughts, final_thoughts,
# autobiography, chat_log, conscious_stream, log.txt, sandbox_log, …).
_DATA_LOG_ALLOWLIST = (
    "error_log.txt",
    "model_failures.txt",
    "model_failures.jsonl",
    "incidents.jsonl",
    "runstate.json",
    "schema_version.json",
)

# How much of each (potentially large) log to keep — last N bytes, tail only.
_TAIL_BYTES = 256 * 1024


def _tail(path: Path, limit: int = _TAIL_BYTES) -> bytes:
    """Last `limit` bytes of a file, read by seeking — never load a large log fully."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > limit:
                f.seek(size - limit)
            return f.read()
    except OSError:  # intentional: unreadable/absent log → empty tail
        return b""


def _state_tag() -> Dict[str, Any]:
    """The lifecycle state (§10.5) plus build/host context — the single most useful
    thing in a diagnostics bundle. Felt-only lifetime view; never the true lifespan."""
    out: Dict[str, Any] = {"captured_at": time.time()}
    try:
        from brain.utils import lifecycle as _lc

        out["lifecycle"] = _lc.status()
    except Exception as e:
        out["lifecycle"] = {"error": str(e)}
    try:
        from brain.utils import schema_migration as _sm

        out["state_schema_version"] = _sm.read_version()
    except (ImportError, OSError, ValueError):  # best-effort: schema version is optional
        pass
    out["platform"] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
    }
    return out


def build_manifest() -> Dict[str, Any]:
    files: List[str] = []
    for name in _DATA_LOG_ALLOWLIST:
        if (paths.DATA_DIR / name).exists():
            files.append(f"data/{name}")
    if paths.LOGS_DIR.exists():
        for f in sorted(paths.LOGS_DIR.glob("*")):
            if f.is_file() and not f.name.startswith("."):
                files.append(f"logs/{f.name}")
    return {"generated_at": time.time(), "files": files, "tail_bytes": _TAIL_BYTES}


def export_bytes() -> bytes:
    """Build the diagnostics zip in memory: state tag + allowlisted, tail-bounded logs.
    No memory, no thoughts — by construction (allowlist)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("state.json", json.dumps(_state_tag(), indent=2))
        zf.writestr("manifest.json", json.dumps(build_manifest(), indent=2))
        for name in _DATA_LOG_ALLOWLIST:
            p = paths.DATA_DIR / name
            if p.exists() and p.is_file():
                data = _tail(p)
                if data:
                    zf.writestr(f"data/{name}", data)
        if paths.LOGS_DIR.exists():
            for f in sorted(paths.LOGS_DIR.glob("*")):
                if f.is_file() and not f.name.startswith("."):
                    data = _tail(f)
                    if data:
                        zf.writestr(f"logs/{f.name}", data)
    return buf.getvalue()


def export_filename() -> str:
    return f"Orrin-diagnostics-{time.strftime('%Y-%m-%d')}.zip"
