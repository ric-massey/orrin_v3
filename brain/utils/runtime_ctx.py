# utils/runtime_ctx.py
"""
Process-local store for the current cognitive cycle's context.

Allows build_system_prompt() and other utilities to read runtime state
(retrieved memories, active goal, relationship info) without threading
context through every call signature. Set once per cycle in ORRIN_loop
before think(); read-only everywhere else.
"""
from __future__ import annotations
from typing import Any, Dict

_ctx: Dict[str, Any] = {}


def set_cycle_context(ctx: Dict[str, Any]) -> None:
    global _ctx
    _ctx = ctx if isinstance(ctx, dict) else {}


def get_cycle_context() -> Dict[str, Any]:
    return _ctx


def get(key: str, default: Any = None) -> Any:
    return _ctx.get(key, default)
