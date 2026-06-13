# eval/evaluator_wal.py
# Append-only JSONL WAL for pending delayed rewards.
# Schema per entry:
#   decision_id : str   — UUID from select_function.py
#   action      : str   — bandit arm that was chosen
#   features    : dict  — feature vector at decision time
#   cycle       : int   — cycle number when decision was made
#   ts          : float — epoch seconds
#   resolved    : bool  — True once a delayed reward has been applied
#   reward      : float|null — populated on resolution; null while pending
#   resolved_by : str|null  — "retrieval_A" | "goal_B" | "pruned"
#   resolved_ts : float|null
from __future__ import annotations
from core.runtime_log import get_logger

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from paths import EVALUATOR_WAL
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_lock = threading.Lock()


def _atomic_append(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent), encoding="utf-8"
    ) as tmp:
        tmp.write(line)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    with open(path, "a", encoding="utf-8") as out, open(tmp_name, "r", encoding="utf-8") as src:
        out.write(src.read())
    try:
        os.unlink(tmp_name)
    except Exception as _unlink_err:
        # Log but don't crash — orphan tmp files are a minor disk-hygiene issue, not a data loss.
        try:
            from utils.log import log_model_issue as _lmi
            _lmi(f"[evaluator_wal] Failed to clean up tmp file {tmp_name}: {_unlink_err}")
        except Exception as _e:
            record_failure("evaluator_wal._atomic_append", _e)


def append_pending(
    decision_id: str,
    action: str,
    features: Dict[str, float],
    cycle: int,
    committed_goal_id: Optional[str] = None,
) -> None:
    entry: Dict[str, Any] = {
        "decision_id": decision_id,
        "action": action,
        "features": features,
        "cycle": cycle,
        "committed_goal_id": committed_goal_id,
        "ts": time.time(),
        "resolved": False,
        "reward": None,
        "resolved_by": None,
        "resolved_ts": None,
    }
    with _lock:
        _atomic_append(Path(EVALUATOR_WAL), entry)


def load_all() -> List[Dict[str, Any]]:
    path = Path(EVALUATOR_WAL)
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with _lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError as _e:
                            record_failure("evaluator_wal.load_all", _e)
        except Exception as _e:
            record_failure("evaluator_wal.load_all.2", _e)
    return entries


def rewrite(entries: List[Dict[str, Any]]) -> None:
    """Replace the WAL with the given list (used for compaction after resolution)."""
    path = Path(EVALUATOR_WAL)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) + "\n" for e in entries]
    with _lock:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(path.parent), encoding="utf-8"
        ) as tmp:
            tmp.writelines(lines)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, str(path))
