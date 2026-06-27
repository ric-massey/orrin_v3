# brain/think/think_generate.py
# Scratchpad-enforced LLM generation wrapper for all cognition modules.
#
# Every LLM call made by a cognition function should go through think_generate()
# so it is (a) always logged on the scratchpad and (b) routed through the cost-
# tracking / cache layer.  Direct calls to generate_response() are permitted
# inside think/ itself (inner_loop, meta_controller) but should be avoided in
# cognition/, reflection/, embodiment/ etc.
#
# Usage:
#   from think.think_generate import think_generate
#   text = think_generate(prompt, context=context, caller="my_module/step",
#                         role="draft", complexity="auto")
#
# Boot audit:
#   from think.think_generate import audit_direct_callers
#   audit_direct_callers(warn_only=True)   # prints warnings, never raises in prod
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, Optional

from brain.think.scratchpad import scratchpad_append
from brain.utils.llm_router import routed_response
from brain.utils.log import log_activity, log_private


def think_generate(
    prompt: str,
    context: Optional[Dict[str, Any]] = None,
    caller: str = "think_generate",
    role: str = "draft",
    phase: str = "",
    complexity: str = "auto",
    model: Optional[str] = None,
) -> str:
    """
    Route prompt through the LLM and log the result to the scratchpad.

    Parameters
    ----------
    prompt:     LLM prompt text.
    context:    Current cycle context dict.  When provided the result is
                appended to context["_scratchpad"]; skipped when None.
    caller:     Caller label for cost tracking.
    role:       Scratchpad role: "draft" | "critique" | "revision" | "plan" | "question"
    phase:      Optional phase label forwarded to metacog breadcrumb.
    complexity: "simple" | "standard" | "auto" — model selection hint.
    model:      Optional hard-coded model override (bypasses routing).

    Returns
    -------
    str — LLM output, or "" on error.
    """
    result = (routed_response(prompt, caller=caller, complexity=complexity, model=model) or "").strip()

    if result and context is not None:
        scratchpad_append(
            context,
            role=role,
            content=result,
            phase=phase or f"{caller}/{role}",
        )

    log_private(f"[think_generate] caller={caller} role={role} len={len(result)}")
    return result


# ---------------------------------------------------------------------------
# Boot-time audit
# ---------------------------------------------------------------------------

_BRAIN_ROOT = Path(__file__).resolve().parent.parent
_AUDIT_TARGETS = ["cognition", "embodiment", "peers"]
_BYPASS_IMPORT = "generate_response"


def audit_direct_callers(warn_only: bool = True) -> list[str]:
    """
    Static AST scan: find .py files in cognition/, embodiment/, peers/ that
    import generate_response directly.  Logs a warning for each violator.

    Returns a list of violating file paths (relative to brain/).
    Returns quickly and never raises — failures are logged, not thrown.
    """
    violators: list[str] = []
    try:
        for target_dir in _AUDIT_TARGETS:
            scan_root = _BRAIN_ROOT / target_dir
            if not scan_root.is_dir():
                continue
            for py_file in scan_root.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                try:
                    src = py_file.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(src, filename=str(py_file))
                except (OSError, SyntaxError, ValueError):  # intentional: skip unreadable/unparseable file
                    continue

                for node in ast.walk(tree):
                    bypasses = False
                    if isinstance(node, ast.ImportFrom):
                        if node.module and "generate_response" in node.module:
                            bypasses = any(a.name == _BYPASS_IMPORT for a in node.names)
                        elif any(a.name == _BYPASS_IMPORT for a in node.names):
                            bypasses = True
                    if isinstance(node, ast.Import):
                        bypasses = any(_BYPASS_IMPORT in a.name for a in node.names)

                    if bypasses:
                        rel = str(py_file.relative_to(_BRAIN_ROOT))
                        violators.append(rel)
                        log_activity(
                            f"[think_audit] WARN: {rel} imports generate_response directly "
                            f"— consider using think.think_generate.think_generate() instead"
                        )
                        break   # one warning per file

    except Exception as _e:
        log_activity(f"[think_audit] audit scan failed: {_e}")

    if not violators:
        log_private("[think_audit] No direct generate_response callers found in cognition/embodiment/peers.")
    else:
        log_activity(f"[think_audit] {len(violators)} module(s) bypass the scratchpad wrapper: {violators}")

    if not warn_only and violators:
        raise RuntimeError(
            f"[think_audit] Dev mode: {len(violators)} modules bypass scratchpad. "
            "Fix or set warn_only=True to suppress."
        )

    return violators
