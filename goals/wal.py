# goals/wal.py
# Append-only JSONL Write-Ahead Log helpers (append, tail/follow, and replay into a store)

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, Iterator, List, Optional, Union

from .model import goal_from_dict, step_from_dict

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------------------------------------------------------------
# Basic I/O
# -----------------------------------------------------------------------------

def append(path: Union[str, Path], record: Dict[str, Any]) -> Path:
    """
    Append one compact JSON record (single line) to the WAL.
    A 'ts' field is injected if missing.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = dict(record)
    rec.setdefault("ts", _iso(UTCNOW()))
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
    # Best-effort write
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
    return p


def append_many(path: Union[str, Path], records: Iterable[Dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in records:
            rec = dict(r)
            rec.setdefault("ts", _iso(UTCNOW()))
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    return p


def iter_lines(path: Union[str, Path]) -> Iterator[Dict[str, Any]]:
    """
    Stream parsed JSON objects from the WAL. Skips malformed lines.
    """
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except Exception:
                continue


def tail(path: Union[str, Path], n: int = 200) -> List[Dict[str, Any]]:
    """
    Return the last `n` parsed records from the WAL (best-effort).
    """
    n = max(0, int(n))
    p = Path(path)
    if not p.exists() or n == 0:
        return []
    try:
        # Simple approach: read all and slice. Adequate for typical WAL sizes between rotations.
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for s in lines[-n:]:
        try:
            out.append(json.loads(s))
        except Exception:
            continue
    return out


def follow(
    path: Union[str, Path],
    *,
    from_end: bool = True,
    poll_seconds: float = 0.25,
    stop: Optional["object"] = None,  # any object with is_set() -> bool (e.g., threading.Event)
) -> Generator[Dict[str, Any], None, None]:
    """
    Generator that yields new records appended to the WAL (like `tail -f`).
    Stop by passing `stop` with an is_set() method and setting it from another thread.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch(exist_ok=True)

    with p.open("r", encoding="utf-8") as f:
        if from_end:
            # seek to end
            f.seek(0, os.SEEK_END)
        buf = ""
        while True:
            if stop is not None and getattr(stop, "is_set", lambda: False)():
                return
            chunk = f.read()
            if not chunk:
                time.sleep(max(0.01, float(poll_seconds)))
                continue
            buf += chunk
            while True:
                i = buf.find("\n")
                if i < 0:
                    break
                line = buf[:i].strip()
                buf = buf[i + 1 :]
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    # tolerate malformed lines
                    continue


# -----------------------------------------------------------------------------
# Replay into a store
# -----------------------------------------------------------------------------

def replay_to_store(
    store: Any,
    wal_path: Union[str, Path],
    *,
    since_ts: Optional[str] = None,
    apply_unknown: bool = False,
) -> Dict[str, int]:
    """
    Re-apply WAL records to a store. Recognized records:
      - {"type":"goal_upsert","goal":{...}}
      - {"type":"step_upsert","step":{...}}

    Parameters
    ----------
    store : duck-typed store
        Exposes upsert_goal(Goal) and upsert_step(Step).
    wal_path : str|Path
        Path to WAL file.
    since_ts : ISO timestamp string
        If provided, only apply records with ts >= since_ts.
    apply_unknown : bool
        If True, will try to apply {"goal":{...}}/{"step":{...}} even if 'type' is unrecognized.

    Returns
    -------
    dict: counts {"goals": X, "steps": Y, "skipped": Z}
    """
    since = _parse_iso(since_ts) if since_ts else None
    counts = {"goals": 0, "steps": 0, "skipped": 0}

    for rec in iter_lines(wal_path):
        ts = _parse_iso(rec.get("ts"))
        if since and ts and ts < since:
            continue

        typ = str(rec.get("type") or "").strip().lower()
        try:
            if typ == "goal_upsert" or (apply_unknown and "goal" in rec):
                gdict = dict(rec.get("goal") or {})
                g = goal_from_dict(gdict)
                if hasattr(store, "upsert_goal"):
                    store.upsert_goal(g)
                    counts["goals"] += 1
                    continue

            if typ == "step_upsert" or (apply_unknown and "step" in rec):
                sdict = dict(rec.get("step") or {})
                s = step_from_dict(sdict)
                if hasattr(store, "upsert_step"):
                    store.upsert_step(s)
                    counts["steps"] += 1
                    continue
        except Exception:
            counts["skipped"] += 1
            continue

        counts["skipped"] += 1

    return counts


# -----------------------------------------------------------------------------
# Rotation (thin wrapper to keep API in one place)
# -----------------------------------------------------------------------------

def rotate(
    wal_path: Union[str, Path] = "data/goals/wal.log",
    *,
    rotated_dir: Union[str, Path] = "data/goals/wal-rotated",
    keep_tail_lines: int = 5_000,
) -> Optional[Path]:
    """
    Compact the WAL by gzipping everything except the last `keep_tail_lines` lines.
    Returns the Path to the created .gz (or None if nothing rotated).
    """
    from .snapshot import rotate_wal  # avoid circular import at module load
    return rotate_wal(wal_path, rotated_dir=rotated_dir, keep_tail_lines=keep_tail_lines)


# -----------------------------------------------------------------------------
# (De)serialization helpers (kept local to avoid importing store internals)
# -----------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    ss = str(s).strip()
    if ss.endswith("Z"):
        ss = ss[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ss)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

__all__ = [
    "append",
    "append_many",
    "iter_lines",
    "tail",
    "follow",
    "replay_to_store",
    "rotate",
]
