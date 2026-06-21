"""Cognitive-function invocation (Phase 4A, extracted from the ORRIN_loop
entrypoint).

`_invoke_cognition` is the loop's single dispatch point for a selected cognitive
function: it builds the call's kwargs from the live context by parameter name
(`_build_kwargs_for`), guards against functions whose required params can't be
satisfied (so the selector stops re-picking an undispatchable function), and
falls back through a few call shapes. run_cognitive_loop re-imports
`_invoke_cognition`; `_build_kwargs_for` is private to this stage.
"""
from __future__ import annotations

import inspect
from typing import Any, Dict

from brain.utils.log import log_error
from brain.utils.failure_counter import record_failure


def _build_kwargs_for(fn, name: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except Exception:
        return {}
    wm = ctx.get("working_memory", []) or []
    lm = ctx.get("long_memory", []) or []
    try:
        recent = (wm[-6:] if isinstance(wm, list) else []) + (lm[-6:] if isinstance(lm, list) else [])
    except Exception:
        recent = []
    mapping = {
        "context": ctx, "ctx": ctx,
        "self_model": ctx.get("self_model"),
        "affect_state": ctx.get("affect_state", {}),
        "emotions": ctx.get("affect_state", {}),
        "relationships": ctx.get("relationships", {}),
        "long_memory": lm,
        "working_memory": wm,
        "recent": recent,
        "recent_memories": recent,
        # reflect_on_affect / reflect_on_emotion_model take (context, self_model,
        # memory) — "memory" was missing from this mapping, so both were selected
        # and then skipped as "not directly dispatchable" dozens of times a day.
        "memory": recent,
        "memories": recent,
        "retrieved_memories": ctx.get("retrieved_memories", []),
        "speaker": ctx.get("speaker"),
        "goal": ctx.get("committed_goal") or ctx.get("focus_goal"),
        "focus_goal": ctx.get("focus_goal") or ctx.get("committed_goal"),
    }
    built = {}
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.name in mapping and mapping[p.name] is not None:
            built[p.name] = mapping[p.name]
    return built

def _invoke_cognition(fn, name: str, ctx: Dict[str, Any], *, args=None, kwargs=None):
    if isinstance(args, (list, tuple)) or isinstance(kwargs, dict):
        return fn(*(args or ()), **(kwargs or {}))
    built = _build_kwargs_for(fn, name, ctx)
    # Guard: if the function requires params that _build_kwargs_for can't supply,
    # bail now rather than crashing at the bare re-raise on the last line.
    try:
        sig = inspect.signature(fn)
        unsatisfied = [
            p.name for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
            and p.name not in ("self", "cls")
            and p.name not in built
        ]
        if unsatisfied:
            log_error(f"[invoke_cognition] {name} needs {unsatisfied} — not directly dispatchable; skipping")
            # Tell selection about it: an undispatchable function must leave the
            # candidate pool, otherwise the selector keeps picking it and the
            # cycle is wasted every time (the dominant error-log line of the
            # first 2.7k cycles).
            try:
                _ud = ctx.setdefault("_undispatchable_fns", [])
                if name not in _ud:
                    _ud.append(name)
            except Exception:
                pass
            return {"status": "error", "error": f"unsatisfiable_args: {unsatisfied}"}
    except Exception as _e:
        record_failure("ORRIN_loop._invoke_cognition", _e)
    for attempt in (
        lambda: fn(**built),
        lambda: fn(ctx),
        lambda: fn({"type": name, "name": name}, ctx),
        lambda: fn(),
    ):
        try:
            return attempt()
        except TypeError:
            continue
    return fn(**built)
