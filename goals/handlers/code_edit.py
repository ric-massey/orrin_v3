# goals/handlers/code_edit.py
# Handler wrapper for safe, git-backed code edits. The registry imports
# `CodeEditHandler` from this module (goals/registry.py), but the implementation
# historically lived in the mis-named sibling `code_editor.py` as a bare
# `execute(goal, ctx)` function with no handler class — so the import failed and
# the code_edit goal-kind was silently disabled. This adapts that proven
# implementation to the BaseGoalHandler interface the daemon expects.
from __future__ import annotations
from brain.core.runtime_log import get_logger

import uuid
from dataclasses import replace
from typing import List, Optional

from ..model import Goal, Step, Status
from .base import BaseGoalHandler, HandlerContext
from .code_editor import execute as _execute_code_edit
_log = get_logger(__name__)


class CodeEditHandler(BaseGoalHandler):
    kind = "code_edit"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        # One step: run the (branch → apply → test → commit/revert) flow.
        return [Step(id=str(uuid.uuid4()), goal_id=goal.id,
                     name="code_edit", action={}, status=Status.READY)]

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        if step.status != Status.READY:
            return None
        try:
            ok = bool(_execute_code_edit(goal, ctx))
        except Exception as e:
            _log.warning("code_edit execute failed: %s", e)
            ok = False
        return replace(step, status=Status.DONE if ok else Status.FAILED)
