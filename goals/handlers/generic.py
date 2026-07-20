# goals/handlers/generic.py
from __future__ import annotations
from brain.core.runtime_log import get_logger
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import replace
from ..model import Goal, Step, Status
from .base import BaseGoalHandler, HandlerContext, default_artifacts_dir
_log = get_logger(__name__)


def _llm_call(prompt: str, ctx: HandlerContext) -> str:
    """Call the brain's LLM via lazy import; falls back to empty string on any error."""
    try:
        repo_root = ctx.get("repo_root", "")
        if repo_root and repo_root not in sys.path:
            sys.path.insert(0, repo_root)  # brain.* resolves from the repo root, not repo_root/brain
        from brain.utils.generate_response import generate_response, llm_ok
        result = generate_response(prompt)
        return (llm_ok(result, "generic_handler") or "").strip()
    except Exception as e:  # intentional floor: any LLM failure surfaces verbatim as an unavailable marker to the runner
        return f"[llm_unavailable: {e}]"


def _log_private(text: str, ctx: HandlerContext) -> None:
    try:
        repo_root = ctx.get("repo_root", "")
        if repo_root and repo_root not in sys.path:
            sys.path.insert(0, repo_root)  # brain.* resolves from the repo root, not repo_root/brain
        from brain.utils.log import log_private
        log_private(text)
    except Exception as _e:
        _log.warning("silent except: %s", _e)


# Spec directives this handler can execute in-daemon. Goal comprehension
# (hydrate_goal_model) now attaches a declarative spec (definition_of_done /
# plan / milestones / requires_artifact) to EVERY goal, so "spec is empty" no
# longer identifies external pursuit — keying on it sent every comprehended
# goal down the daemon path, where the unknown-spec fall-through completed the
# step in ms and the artifact gate failed the goal before the cognitive loop
# ever worked it (2026-07-02 run: NEW→FAILED in 7ms).
# `synthesize` (RUN4_FIX_PLAN A3): a make-goal directive the daemon can run
# offline — read prior memos on the topic, compose a synthesis, write it as a
# real artifact through the same effect-ledger path research memos use. This is
# the daemon-executable lane that lets a "turn what I know into a written
# synthesis" goal get PURSUED instead of parking WAITING for a conscious lane
# that the ignition monopoly starved for 8 h (2026-07-03 run).
_DAEMON_EXECUTABLE_KEYS = ("reflect", "investigate", "process_todos", "synthesize")

_SYN_STOP = frozenset({
    "that", "this", "with", "have", "what", "your", "about", "they", "them",
    "from", "would", "could", "there", "their", "thing", "understand",
    "research", "memo", "into", "know", "written", "turn", "synthesis",
})


def _daemon_executable(spec: Dict[str, Any]) -> bool:
    return any(spec.get(k) for k in _DAEMON_EXECUTABLE_KEYS)


def _syn_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", str(text or "").lower())
            if w not in _SYN_STOP}


def _artifacts_base(ctx: HandlerContext) -> Path:
    return Path(default_artifacts_dir(ctx))


def _gather_prior_memos(topic: str, ctx: HandlerContext,
                        exclude: Optional[str] = None) -> List[Tuple[Path, str]]:
    """The most topic-overlapping prior memos across goal artifact dirs (>=1
    shared content word), newest first. Read to build ON, and reuse-credited."""
    base = _artifacts_base(ctx)
    toks = _syn_tokens(topic)
    if not toks or not base.is_dir():
        return []
    try:
        memos = sorted((p for p in base.glob("*/*.md")
                        if not (exclude and str(p.parent.name) == exclude)),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    out: List[Tuple[Path, str]] = []
    for p in memos:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(toks & _syn_tokens(p.name + " " + txt[:1200])) >= 1:
            out.append((p, txt))
        if len(out) >= 6:
            break
    return out


class GenericHandler(BaseGoalHandler):
    kind = "generic"

    def plan(self, goal: Goal, ctx: HandlerContext) -> List[Step]:
        spec = getattr(goal, "spec", None) or {}
        if not _daemon_executable(spec):
            # No daemon-executable directive → the cognitive loop pursues this
            # goal, not the daemon. A WAITING placeholder keeps the goal alive
            # until the brain mirrors its close via close_goal_v2(). The old
            # READY "noop" step fake-completed every such goal within seconds
            # while the loop worked it for hours (FINDINGS 2026-06-12 §6).
            return [Step(id=str(uuid.uuid4()), goal_id=goal.id, name="external_pursuit", action={}, status=Status.WAITING)]
        return [Step(id=str(uuid.uuid4()), goal_id=goal.id, name="execute", action={}, status=Status.READY)]

    def tick(self, goal: Goal, step: Step, ctx: HandlerContext) -> Optional[Step]:
        if step.status != Status.READY:
            return None

        spec = getattr(goal, "spec", None) or {}

        # Not daemon-executable — externally pursued; park instead of fake-completing
        if not _daemon_executable(spec):
            return replace(step, status=Status.WAITING)

        # --- Reflection goal (low emotional stability) ---
        if spec.get("reflect"):
            trigger = spec.get("trigger", "internal")
            emo_state: Dict[str, Any] = {}
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

        # --- Synthesis goal (RUN4_FIX_PLAN A3): make a written synthesis from
        # what he already knows, building on prior memos on the topic. ---
        if spec.get("synthesize"):
            topic = str(spec.get("synthesize") or goal.title or "").strip()
            priors = _gather_prior_memos(topic, ctx, exclude=goal.id) \
                if spec.get("from_artifacts", True) else []
            # Credit tier-3 re-use of each prior memo read (pairs with A2).
            for p, _txt in priors:
                try:
                    from brain.agency.effect_ledger import mark_reused_path
                    mark_reused_path(p)
                except Exception as _e:
                    _log.warning("synthesis reuse credit failed: %s", _e)
            prior_block = "\n\n".join(
                f"[prior: {p.name}]\n{txt[:3000]}" for p, txt in priors
            ) or "(no prior memos found — synthesize from what you understand)"
            prompt = (
                f"You are Orrin, writing a synthesis about: {topic}. "
                f"Using your prior notes below, write a clear, NOVEL synthesis in "
                f"your own words that connects at least two ideas — not a restatement "
                f"of one fact. 3-6 paragraphs.\n\nPRIOR NOTES:\n{prior_block}"
            )
            memo = _llm_call(prompt, ctx)
            if not memo or memo.startswith("[llm_unavailable"):
                # Offline fallback: an honest stitched synthesis of the priors so
                # the make-goal still produces a real artifact (native-LM deploy).
                if priors:
                    memo = (f"# Synthesis: {topic}\n\n"
                            "Drawing together what I've noted so far:\n\n"
                            + "\n\n".join(f"- From {p.name}: {txt[:600].strip()}"
                                          for p, txt in priors))
                else:
                    # Nothing to build on and no LM — fail honestly, don't fake it.
                    _log_private(f"[synthesize:{topic}] no priors, no LM — cannot produce", ctx)
                    return replace(step, status=Status.FAILED, attempts=step.attempts + 1,
                                   last_error="synthesize: no source material and LLM unavailable")
                if priors:
                    memo += f"\n\n---\nBuilds on: {', '.join(str(p) for p, _ in priors)}\n"
            try:
                base = _artifacts_base(ctx) / goal.id
                base.mkdir(parents=True, exist_ok=True)
                out_path = base / "synthesis.md"
                out_path.write_text(memo, encoding="utf-8")
                # Register on the step so the runner's effect chokepoint records
                # it as a produced file_write (same path research memos use).
                arts = list(step.artifacts or [])
                arts.append(str(out_path))
                _log_private(f"[synthesize:{topic}] wrote {out_path.name} "
                             f"({len(priors)} prior memo(s) reused)", ctx)
                return replace(step, status=Status.DONE, attempts=step.attempts + 1,
                               artifacts=arts)
            except OSError as _e:
                return replace(step, status=Status.FAILED, attempts=step.attempts + 1,
                               last_error=f"synthesize: write failed: {_e}")

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
