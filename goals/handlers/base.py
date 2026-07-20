# goals/handlers/base.py
# Base protocol and helpers for goal handlers in the Goals daemon (defines handler interface)

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable, Optional, Tuple, List, Dict, Any, Union

from brain.core.runtime_log import get_logger

from ..model import Goal, Step, Status

_log = get_logger(__name__)

# Public type alias for anything we pass around to handlers (services, paths, config, clients, etc.)
HandlerContext = Dict[str, Any]


def default_artifacts_dir(ctx: HandlerContext) -> Any:
    """The artifacts base for handler outputs. Prefer the daemon-provisioned
    ctx["artifacts_dir"]; the fallback resolves through the SAME env vars as
    brain/paths.py (ORRIN_GOALS_DIR → ORRIN_STATE_DIR/goals → repo data/goals)
    instead of a cwd-relative literal — the 2026-07-20 smoke life leaked
    artifacts into the live repo tree through that literal (golden rule 3)."""
    import os
    from pathlib import Path
    explicit = ctx.get("artifacts_dir")
    if explicit:
        return Path(explicit)
    goals_dir = os.environ.get("ORRIN_GOALS_DIR")
    if goals_dir:
        return Path(goals_dir).resolve() / "artifacts"
    state_dir = os.environ.get("ORRIN_STATE_DIR")
    if state_dir:
        return Path(state_dir).resolve() / "goals" / "artifacts"
    return Path("data/goals/artifacts").resolve()

# NEW: standard result type a handler may return from its internal ops (plan/tick helpers, etc.)
HandlerResult = Union[bool, Tuple[bool, Dict[str, Any]]]


@runtime_checkable
class GoalHandler(Protocol):
    """
    Minimal contract each goal handler must satisfy.

    Semantics:
      - accept(goal): True if this handler is appropriate for goal.kind/spec.
      - plan(goal, ctx): Return an initial list of Steps (may be empty). Called when a NEW goal is admitted.
      - is_blocked(goal, ctx): Return (True, reason) if the goal cannot currently progress (e.g., waiting on lock, IO).
      - tick(goal, step, ctx): Execute or advance one step; return the updated Step (or None if no change this tick).
      - on_event(goal, event, ctx): Optional hook for reacting to external system events (supervisor/memory/watchdogs).
    """
    kind: str

    def accept(self, goal: Goal) -> bool: ...
    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]: ...
    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]: ...
    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]: ...
    def on_event(self, goal: Goal, event: Dict[str, Any], ctx: HandlerContext) -> None: ...


class BaseGoalHandler(ABC):
    """
    Convenience abstract base class that implements sensible defaults.
    Subclass and override as needed; set `kind` to your handler's name.
    """
    kind: str = "base"

    def accept(self, goal: Goal) -> bool:
        # Default: match by kind string
        return getattr(goal, "kind", None) == self.kind

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        # Default: no preplanned steps; daemon/other hooks may enqueue later
        return []

    def is_blocked(self, goal: Goal, ctx: HandlerContext) -> Tuple[bool, Optional[str]]:
        # Default: not blocked
        return False, None

    @abstractmethod
    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        """
        Required: advance work for a single step.
        Return the updated Step (mutated or replacement), or None if nothing changed this tick.
        Raise exceptions only for *unexpected* errors; expected transient issues should surface via is_blocked().
        """
        raise NotImplementedError

    def on_event(self, goal: Goal, event: Dict[str, Any], ctx: HandlerContext) -> None:
        # Default: ignore external events
        return None

    # NEW: normalize a handler's boolean/tuple result into (ok, info)
    @staticmethod
    def normalize_result(result: HandlerResult) -> Tuple[bool, Dict[str, Any]]:
        """
        Accepts either:
          - True/False
          - (ok: bool, info: dict)
        Returns (ok: bool, info: dict) where info is always a dict.
        """
        if isinstance(result, tuple) and len(result) == 2:
            ok, info = result
            return bool(ok), (info or {})
        return bool(result), {}
        

# ── Shared handler helpers ────────────────────────────────────────────────────
# Step construction and the lock acquire/release dance were copy-pasted across the
# coding/research/housekeeping handlers (structure audit §8). They live here, on
# the handler base, so every handler shares one implementation.

def new_step(
    goal_id: str,
    name: str,
    action: Dict[str, Any],
    *,
    max_attempts: int = 3,
    deps: Optional[List[str]] = None,
) -> Step:
    """Construct a READY Step with a fresh id."""
    return Step(
        id=f"s_{uuid.uuid4().hex[:10]}",
        goal_id=goal_id,
        name=name,
        action=action,
        max_attempts=max_attempts,
        deps=list(deps or []),
        status=Status.READY,
    )


def acquire_lock(ctx: HandlerContext, name: str, goal_id: str) -> bool:
    """Try to take the named lock for `goal_id`. Returns True (proceed) when no
    lock manager is configured in ctx; False if a configured acquire fails."""
    locks = ctx.get("locks")
    if not locks:
        return True  # no lock manager configured; proceed
    try:
        return bool(locks.acquire(name, goal_id))
    except (OSError, RuntimeError, AttributeError):  # intentional: lock acquire failed → not acquired
        return False


def release_lock(ctx: HandlerContext, name: str, goal_id: str) -> None:
    """Release the named lock for `goal_id`; best-effort, no-op without a manager."""
    locks = ctx.get("locks")
    if not locks:
        return
    try:
        locks.release(name, goal_id)
    except Exception as _e:
        _log.warning("silent except: %s", _e)


__all__ = [
    "GoalHandler", "BaseGoalHandler", "HandlerContext", "HandlerResult",
    "new_step", "acquire_lock", "release_lock",
]
