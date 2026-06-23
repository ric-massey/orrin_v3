# goals/handlers/dummy.py
from __future__ import annotations
from typing import List, Optional, Tuple
from datetime import datetime, timezone

from ..model import Goal, Step, Status
from .base import BaseGoalHandler, HandlerContext

def UTCNOW() -> datetime:
    return datetime.now(timezone.utc)

class DummyHandler(BaseGoalHandler):
    """Tiny test handler for kind='dummy' that completes a step immediately."""
    kind = "dummy"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        return []

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        return False, None

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        if step.started_at is None:
            step.started_at = UTCNOW()
            step.status = Status.RUNNING
            return step
        step.status = Status.DONE
        step.finished_at = UTCNOW()
        return step

__all__ = ["DummyHandler"]