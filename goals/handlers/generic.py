# goals/handlers/generic.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
import sys
import uuid
from typing import List, Optional
from dataclasses import replace
from ..model import Goal, Step, Status
from .base import BaseGoalHandler, HandlerContext
_log = get_logger(__name__)


def _llm_call(prompt: str, ctx: HandlerContext) -> str:
    """Call the brain's LLM via lazy import; falls back to empty string on any error."""
    try:
        repo_root = ctx.get("repo_root", "")
        if repo_root and repo_root not in sys.path:
            sys.path.insert(0, repo_root + "/brain")
        from brain.utils.generate_response import generate_response, llm_ok  # type: ignore
        result = generate_response(prompt)
        return (llm_ok(result, "generic_handler") or "").strip()
    except Exception as e:
        return f"[llm_unavailable: {e}]"


def _log_private(text: str, ctx: HandlerContext) -> None:
    try:
        repo_root = ctx.get("repo_root", "")
        if repo_root and repo_root + "/brain" not in sys.path:
            sys.path.insert(0, repo_root + "/brain")
        from brain.utils.log import log_private  # type: ignore
        log_private(text)
    except Exception as _e:
        _log.warning("silent except: %s", _e)


class GenericHandler(BaseGoalHandler):
    kind = "generic"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        spec = getattr(goal, "spec", None) or {}
        if not spec:
            # No executable spec → the cognitive loop pursues this goal, not the
            # daemon. A WAITING placeholder keeps the goal alive until the brain
            # mirrors its close via close_goal_v2(). The old READY "noop" step
            # fake-completed every spec-less goal within seconds while the loop
            # worked it for hours (FINDINGS 2026-06-12 data sweep §6).
            return [Step(id=str(uuid.uuid4()), goal_id=goal.id, name="external_pursuit", action={}, status=Status.WAITING)]
        return [Step(id=str(uuid.uuid4()), goal_id=goal.id, name="execute", action={}, status=Status.READY)]

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        if step.status != Status.READY:
            return None

        spec = getattr(goal, "spec", None) or {}

        # No spec — externally pursued; park the step instead of fake-completing
        if not spec:
            return replace(step, status=Status.WAITING)

        # --- Reflection goal (low emotional stability) ---
        if spec.get("reflect"):
            trigger = spec.get("trigger", "internal")
            emo_state = {}
            try:
                get_emo = ctx.get("get_emotional_state")
                if callable(get_emo):
                    emo_state = get_emo() or {}
            except Exception as _e:
                _log.warning("silent except: %s", _e)
            emo_desc = ", ".join(
                f"{k}={round(float(v), 2)}"
                for k, v in (emo_state.get("core_emotions") or emo_state).items()
                if isinstance(v, (int, float)) and float(v) >= 0.1
            ) or "unknown"
            prompt = (
                f"You are Orrin, an autonomous AI reflecting on your emotional state. "
                f"Trigger: {trigger}. Current emotional state: {emo_desc}. "
                f"Write a brief internal reflection (2-4 sentences) on what you are feeling, "
                f"why, and what it means for how you should act right now."
            )
            reflection = _llm_call(prompt, ctx)
            _log_private(f"[reflect] {reflection}", ctx)
            return replace(step, status=Status.DONE, attempts=step.attempts + 1)

        # --- Investigation goal (step failures, perf, lint, mypy, deps) ---
        investigate = spec.get("investigate")
        if investigate:
            prompt = (
                f"You are Orrin, an autonomous AI. You need to investigate: {investigate}. "
                f"Goal: {goal.title}. "
                f"Write a brief analysis (3-5 sentences): what is likely causing the issue, "
                f"what should be checked or fixed, and what the highest-leverage action is."
            )
            analysis = _llm_call(prompt, ctx)
            _log_private(f"[investigate:{investigate}] {analysis}", ctx)
            return replace(step, status=Status.DONE, attempts=step.attempts + 1)

        # --- TODO processing ---
        if spec.get("process_todos"):
            try:
                import pathlib
                repo_root = ctx.get("repo_root", ".")
                todo_path = pathlib.Path(repo_root) / "TODO.md"
                todos = todo_path.read_text(encoding="utf-8")[:800] if todo_path.exists() else "(no TODO.md found)"
            except Exception:
                todos = "(could not read TODO.md)"
            prompt = (
                f"You are Orrin reviewing your TODO list. Here are the top items:\n{todos}\n"
                f"Pick the single most important item and write one sentence describing "
                f"what you will do next to address it."
            )
            plan = _llm_call(prompt, ctx)
            _log_private(f"[todos] {plan}", ctx)
            return replace(step, status=Status.DONE, attempts=step.attempts + 1)

        # Unknown spec — mark done rather than loop forever
        return replace(step, status=Status.DONE, attempts=step.attempts + 1)
