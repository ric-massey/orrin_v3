# goals/model.py
# Core dataclasses and enums for the Goals subsystem (Goal, Step, Status, Priority, Progress)

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .utils import parse_iso

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)


class Status(str, Enum):
    NEW = "NEW"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    WAITING = "WAITING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"


class Priority(int, Enum):
    LOW = 0          # ROUTINE
    NORMAL = 1       # IMPORTANT
    HIGH = 2
    CRITICAL = 3


@dataclass
class Progress:
    percent: float = 0.0
    note: str = ""
    evidence: Dict[str, str] = field(default_factory=dict)

    def set(self, *, percent: Optional[float] = None, note: Optional[str] = None) -> None:
        if percent is not None:
            # Clamp to [0, 100]
            self.percent = max(0.0, min(100.0, float(percent)))
        if note is not None:
            self.note = note


@dataclass
class Step:
    id: str
    goal_id: str
    name: str
    action: Dict[str, Any]
    status: Status = Status.READY
    attempts: int = 0
    max_attempts: int = 3
    deps: List[str] = field(default_factory=list)

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_error: Optional[str] = None

    artifacts: List[str] = field(default_factory=list)


@dataclass
class Goal:
    id: str
    title: str
    kind: str
    spec: Dict[str, Any]

    priority: Priority = Priority.NORMAL
    status: Status = Status.NEW

    created_at: datetime = field(default_factory=UTCNOW)
    updated_at: datetime = field(default_factory=UTCNOW)
    deadline: Optional[datetime] = None

    parent_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    progress: Progress = field(default_factory=Progress)
    acceptance: Dict[str, Any] = field(default_factory=dict)

    last_error: Optional[str] = None
    step_order: List[str] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = UTCNOW()

    def is_terminal(self) -> bool:
        return self.status in {Status.DONE, Status.FAILED, Status.CANCELLED}

    def overdue(self, now: Optional[datetime] = None) -> bool:
        if not self.deadline or self.is_terminal():
            return False
        now = now or UTCNOW()
        try:
            return (now - self.deadline).total_seconds() > 0
        except Exception:
            return False


# ── Deserialization ───────────────────────────────────────────────────────────
# Canonical dict→model constructors, kept next to the models per the structure
# audit (§8): they were duplicated verbatim in store.py (_goal_from_dict /
# _step_from_dict / _to_status / _to_priority) and wal.py (_dict_to_goal /
# _dict_to_step / …). Both call sites now import these.

def to_status(x: Any) -> Status:
    if isinstance(x, Status):
        return x
    try:
        return Status[str(x).upper()]
    except Exception:
        return Status.READY


def to_priority(x: Any) -> Priority:
    if isinstance(x, Priority):
        return x
    try:
        return Priority[str(x).upper()]
    except Exception:
        try:
            return Priority(int(x))
        except Exception:
            return Priority.NORMAL


def goal_from_dict(d: Dict[str, Any]) -> Goal:
    return Goal(
        id=str(d["id"]),
        title=str(d.get("title", "")),
        kind=str(d.get("kind", "")),
        spec=dict(d.get("spec") or {}),
        priority=to_priority(d.get("priority", Priority.NORMAL)),
        status=to_status(d.get("status", Status.NEW)),
        created_at=parse_iso(d.get("created_at")) or UTCNOW(),
        updated_at=parse_iso(d.get("updated_at")) or UTCNOW(),
        deadline=parse_iso(d.get("deadline")),
        parent_id=d.get("parent_id"),
        tags=list(d.get("tags") or []),
        progress=Progress(**(d.get("progress") or {})),
        acceptance=dict(d.get("acceptance") or {}),
        last_error=d.get("last_error"),
        step_order=list(d.get("step_order") or []),
    )


def step_from_dict(d: Dict[str, Any]) -> Step:
    return Step(
        id=str(d["id"]),
        goal_id=str(d.get("goal_id") or d.get("goalId") or ""),
        name=str(d.get("name", "")),
        action=dict(d.get("action") or {}),
        status=to_status(d.get("status", Status.READY)),
        attempts=int(d.get("attempts", 0)),
        max_attempts=int(d.get("max_attempts", 3)),
        deps=list(d.get("deps") or []),
        started_at=parse_iso(d.get("started_at")),
        finished_at=parse_iso(d.get("finished_at")),
        last_error=d.get("last_error"),
        artifacts=list(d.get("artifacts") or []),
    )


# ── Serialization ─────────────────────────────────────────────────────────────
def goal_to_jsonable(g: Goal) -> Dict[str, Any]:
    """Convert a Goal to a plain JSON-serializable dict (enums→names, datetimes→
    ISO, dataclass progress→dict). Canonical encoder, shared by the dashboard
    feed (brain/utils/goals_feed.py) and the CLI (goals/cli.py) — it was
    duplicated verbatim in both (structure audit §8)."""
    d = g.__dict__.copy()
    d["status"] = getattr(g.status, "name", str(g.status))
    d["priority"] = getattr(g.priority, "name", str(g.priority))
    if g.deadline:    d["deadline"]    = g.deadline.isoformat()
    if d.get("created_at"):  d["created_at"]  = g.created_at.isoformat()
    if d.get("updated_at"):  d["updated_at"]  = g.updated_at.isoformat()
    pr = d.get("progress")
    if is_dataclass(pr) and not isinstance(pr, type):
        d["progress"] = asdict(pr)
    if d.get("acceptance") is not None:
        d["acceptance"] = dict(d["acceptance"])
    if d.get("spec") is not None:
        d["spec"] = dict(d["spec"])
    return d


__all__ = [
    "Status", "Priority", "Progress", "Step", "Goal",
    "to_status", "to_priority", "goal_from_dict", "step_from_dict",
    "goal_to_jsonable",
]
