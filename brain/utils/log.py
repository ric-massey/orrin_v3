from __future__ import annotations

import os
from pathlib import Path
from typing import List, Union, Dict, Any

from brain.paths import ERROR_FILE, MODEL_FAILURE, ACTIVITY_LOG, PRIVATE_THOUGHTS_FILE
from brain.utils.timeutils import now_iso_z

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None  # type: ignore[assignment]

try:
    from brain.utils.path_redact import redact as _redact
except Exception:
    def _redact(text: str) -> str:  # noqa: F811
        return text

# --- helpers ---
utc_now = now_iso_z  # public alias — import this instead of defining _utc_now locally

_LOG_MAX_BYTES   = 2_000_000   # 2 MB — rotate when a log file exceeds this
_LOG_KEEP_BYTES  = 500_000     # keep the most recent 500 KB after rotation

def _maybe_rotate(p: Path) -> None:
    """If the log file exceeds _LOG_MAX_BYTES, trim it to the last _LOG_KEEP_BYTES.

    The trimmed-off head is archived, not discarded: truncation destroyed the
    only evidence of the 2026-06-11 14:38 death (DATA_FILE_AUDIT §3) — a
    rotated segment may be the sole record of what happened.
    """
    try:
        if p.stat().st_size <= _LOG_MAX_BYTES:
            return
        data = p.read_bytes()
        # Keep the tail so we don't lose recent entries
        trimmed = data[-_LOG_KEEP_BYTES:]
        # Find the first newline so we don't start mid-line
        nl = trimmed.find(b"\n")
        if nl != -1:
            trimmed = trimmed[nl + 1:]
        head = data[: len(data) - len(trimmed)]
        try:
            archive_dir = p.parent / "rotated"
            archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = now_iso_z().replace(":", "-")
            (archive_dir / f"{p.stem}.{stamp}{p.suffix}").write_bytes(head)
            # Keep the archive itself bounded: oldest segments go first.
            segments = sorted(archive_dir.glob(f"{p.stem}.*{p.suffix}"))
            for old in segments[:-20]:
                old.unlink(missing_ok=True)
        except Exception:
            pass  # archiving is best-effort; rotation must still happen
        p.write_bytes(b"[log rotated]\n" + trimmed)
    except Exception:
        pass

def _append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    _maybe_rotate(p)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        if _fcntl is not None:
            try:
                _fcntl.flock(f, _fcntl.LOCK_EX)
            except Exception:
                pass
        f.write(_redact(line))
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
        if _fcntl is not None:
            try:
                _fcntl.flock(f, _fcntl.LOCK_UN)
            except Exception:
                pass

# --- writers ---
def log_error(content: Any) -> None:
    _append_line(ERROR_FILE, f"\n[{now_iso_z()}] {str(content)}\n")

def log_model_issue(message: Any) -> None:
    _append_line(MODEL_FAILURE, f"[{now_iso_z()}] {str(message)}\n")

def log_activity(message: Any) -> None:
    _append_line(ACTIVITY_LOG, f"[{now_iso_z()}] {str(message)}\n")

def log_private(message: Any) -> None:
    _append_line(PRIVATE_THOUGHTS_FILE, f"[{now_iso_z()}] {str(message)}\n")

# --- readers ---
def read_recent_errors_txt(path: Union[str, Path], max_lines: int = 5) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-max_lines:] if lines else []
    except Exception as e:
        return [f"⚠️ Failed to read {path}: {e}"]

def read_recent_errors_json(path: Union[str, Path], max_items: int = 5) -> List[Dict[str, Any]]:
    from brain.utils.json_utils import load_json
    try:
        data: List[Any] = load_json(path, default_type=list)
        return data[-max_items:] if isinstance(data, list) else []
    except Exception as e:
        return [{"error": f"⚠️ Failed to read {path}: {e}"}]

def read_recent_errors_jsonl(path: Union[str, Path], max_items: int = 5) -> List[Dict[str, Any]]:
    """Tail a JSONL error log (error_router's model_failures.jsonl events)."""
    import json as _json
    try:
        p = Path(path)
        if not p.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_items:]:
            line = line.strip()
            if not line:
                continue
            try:
                ev = _json.loads(line)
                if isinstance(ev, dict):
                    out.append(ev)
            except Exception:
                continue
        return out
    except Exception as e:
        return [{"error": f"⚠️ Failed to read {path}: {e}"}]
