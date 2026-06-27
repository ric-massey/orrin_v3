# goals/store.py
# File-backed goals store: loads on start, persists to JSONL + WAL, provides filtering/indexing APIs.

from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .model import Goal, Step, Status, Priority, goal_from_dict, step_from_dict
from . import wal as WAL
from .utils import ensure_dir, iso as _iso, append_jsonl, iter_jsonl
_log = get_logger(__name__)

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        obj = asdict(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, datetime):
                out[k] = _iso(v)
            else:
                out[k] = _jsonable(v)
        return out
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return _iso(obj)
    return obj


class FileGoalsStore:
    """
    Simple file-backed store.

    Directory layout:
      data_dir/
        state.jsonl   # append-only snapshots: {"goal":{...}} / {"step":{...}}
        wal.log       # append-only operational log (goal_upsert/step_upsert)

    On init, we load from state.jsonl if present; otherwise we replay WAL.
    """

    def __init__(self, data_dir: Path | str):
        self._dir = ensure_dir(Path(data_dir))
        self._state = self._dir / "state.jsonl"
        self._wal = self._dir / "wal.log"
        # Ensure files exist
        self._state.touch(exist_ok=True)
        self._wal.touch(exist_ok=True)

        self._goals: Dict[str, Goal] = {}
        self._steps: Dict[str, Step] = {}
        self._by_goal_steps: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

        self._load()

    # ---------------- paths / counts ----------------

    def paths(self) -> Dict[str, str]:
        return {"dir": str(self._dir), "state": str(self._state), "wal": str(self._wal)}

    def checkpoint(self, *, keep_tail_lines: int = 5_000) -> Dict[str, Any]:
        """Compact the append-only state.jsonl into a fresh snapshot and rotate the
        WAL, bounding BOTH for long / multi-day runs (T0.4 — neither was ever
        compacted: every upsert appends a line to both files forever). Holds the
        store lock so it serializes against concurrent upserts — rotate_wal
        rewrites the WAL non-atomically, so it must not race a worker append.
        Best-effort: returns the checkpoint report, or {} on failure."""
        with self._lock:
            try:
                # Call the primitives directly with EXPLICIT paths derived from this
                # store's own dir — snapshots.checkpoint would default rotated_dir to
                # a relative "data/goals/wal-rotated" and scatter rotated segments to
                # the process CWD instead of next to this store's WAL.
                from .snapshots import snapshot_state, rotate_wal
                state = snapshot_state(self, out_path=self._state, atomic=True)
                gz = rotate_wal(
                    self._wal, rotated_dir=self._dir / "wal-rotated",
                    keep_tail_lines=keep_tail_lines,
                )
                return {"state": str(state), "wal_rotated": str(gz) if gz else None,
                        "keep_tail_lines": keep_tail_lines}
            except Exception as _e:
                _log.warning("store.checkpoint failed: %s", _e)
                return {}

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return {"goals": len(self._goals), "steps": len(self._steps)}

    # ---------------- loading ----------------

    def _load(self) -> None:
        """
        Load state from state.jsonl; if empty, try replaying wal.log.
        """
        loaded_any = False
        try:
            for rec in iter_jsonl(self._state):
                goal_payload = self._goal_payload_from_state_record(rec)
                if goal_payload is not None:
                    g = goal_from_dict(goal_payload)
                    self._goals[g.id] = g
                    loaded_any = True
                step_payload = self._step_payload_from_state_record(rec)
                if step_payload is not None:
                    s = step_from_dict(step_payload)
                    self._apply_loaded_step(s)
                    loaded_any = True
        except Exception:
            # fall back to WAL replay below
            loaded_any = False

        if not loaded_any:
            # Try WAL replay
            try:
                WAL.replay_to_store(self, self._wal)
            except Exception as _e:
                _log.warning("silent except: %s", _e)

    @staticmethod
    def _goal_payload_from_state_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if isinstance(rec.get("goal"), dict):
            return dict(rec["goal"])
        if str(rec.get("type") or "").lower() == "goal":
            return {k: v for k, v in rec.items() if k != "type"}
        return None

    @staticmethod
    def _step_payload_from_state_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if isinstance(rec.get("step"), dict):
            return dict(rec["step"])
        if str(rec.get("type") or "").lower() == "step":
            return {k: v for k, v in rec.items() if k != "type"}
        return None

    def _apply_loaded_step(self, s: Step) -> None:
        self._steps[s.id] = s
        lst = self._by_goal_steps.setdefault(s.goal_id, [])
        if s.id not in lst:
            lst.append(s.id)

    # ---------------- CRUD: goals ----------------

    def upsert_goal(self, g: Goal) -> Goal:
        with self._lock:
            # normalize/update timestamps
            g.updated_at = UTCNOW() if getattr(g, "updated_at", None) is None else g.updated_at
            if getattr(g, "created_at", None) is None:
                g.created_at = UTCNOW()

            self._goals[g.id] = g

            # append state snapshot & wal
            append_jsonl(self._state, [{"goal": _jsonable(g)}])
            WAL.append(self._wal, {"type": "goal_upsert", "goal": _jsonable(g)})
            return g

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        with self._lock:
            return self._goals.get(goal_id)

    def list_goals(
        self,
        *,
        kinds: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[Status]] = None,
        priorities: Optional[Sequence[Priority]] = None,
        tags: Optional[Sequence[str]] = None,
        text: Optional[str] = None,
        limit: Optional[int] = None,
        sort: str = "-updated_at",
    ) -> List[Goal]:
        with self._lock:
            items = list(self._goals.values())

        if kinds:
            kset = {k.lower() for k in kinds}
            items = [g for g in items if (g.kind or "").lower() in kset]
        if statuses:
            sset = {s for s in statuses}
            items = [g for g in items if g.status in sset]
        if priorities:
            pset = {p for p in priorities}
            items = [g for g in items if g.priority in pset]
        if tags:
            tset = {t.lower() for t in tags}
            items = [g for g in items if tset.issubset({t.lower() for t in (g.tags or [])})]
        if text:
            t = text.lower()
            items = [g for g in items if t in (g.title or "").lower() or t in (g.last_error or "").lower()]

        # sort
        rev = sort.startswith("-")
        key = sort[1:] if rev else sort
        def _key(g: Goal) -> Any:
            v = getattr(g, key, None)
            if isinstance(v, datetime):
                return v.timestamp()
            if isinstance(v, Priority):
                return int(v)
            if isinstance(v, Status):
                return v.name
            return v
        try:
            items.sort(key=_key, reverse=rev)
        except Exception as _e:
            _log.warning("silent except: %s", _e)

        if limit:
            items = items[: int(limit)]
        return items

    def iter_goals(self) -> Iterator[Goal]:
    # Take a snapshot under the lock, then yield outside to avoid deadlocks
        with self._lock:
            items = list(self._goals.values())
        for g in items:
            yield g

    def ready_goals(self) -> List[Goal]:
        """Goals that should be considered by a scheduler (READY/RUNNING/WAITING)."""
        with self._lock:
            return [g for g in self._goals.values() if g.status in {Status.READY, Status.RUNNING, Status.WAITING}]

    # ---------------- CRUD: steps ----------------

    def upsert_step(self, s: Step) -> Step:
        with self._lock:
            self._steps[s.id] = s
            lst = self._by_goal_steps.setdefault(s.goal_id, [])
            if s.id not in lst:
                lst.append(s.id)

            append_jsonl(self._state, [{"step": _jsonable(s)}])
            WAL.append(self._wal, {"type": "step_upsert", "step": _jsonable(s)})
            return s

    def get_step(self, step_id: str) -> Optional[Step]:
        with self._lock:
            return self._steps.get(step_id)

    def list_steps(
        self,
        *,
        goal_id: Optional[str] = None,
        statuses: Optional[Sequence[Status]] = None,
    ) -> List[Step]:
        with self._lock:
            if goal_id:
                ids = list(self._by_goal_steps.get(goal_id, []))
                items = [self._steps[i] for i in ids if i in self._steps]
            else:
                items = list(self._steps.values())

        if statuses:
            sset = set(statuses)
            items = [s for s in items if s.status in sset]
        return items

    def iter_steps(self) -> Iterator[Step]:
    # Same pattern for steps
        with self._lock:
            items = list(self._steps.values())
        for s in items:
            yield s

    def steps_for(self, goal_id: Optional[str], *, statuses: Optional[Sequence[Status]] = None) -> List[Step]:
        return self.list_steps(goal_id=goal_id, statuses=statuses)
