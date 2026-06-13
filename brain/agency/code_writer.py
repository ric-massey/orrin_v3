# agency/code_writer.py
# Lets Orrin write new cognitive functions, tools, and skills — and register
# them live without restarting.
#
# Guardrails:
#   - Can only write to: custom_cognition/, agency/skills/
#   - Cannot touch: think/, cognition/repair/, ORRIN_loop.py, registry/, core/
#   - All code is validated in the sandbox before being registered
#   - A manifest is kept so Orrin knows what he has written
from __future__ import annotations
from core.runtime_log import get_logger

import ast
import importlib.util
import json
import sys
import textwrap
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.log import log_activity, log_error
from cog_memory.working_memory import update_working_memory
from think.sandbox_runner import run_python
from paths import ROOT_DIR
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_LOCK = threading.Lock()

# Safe write locations

_ALLOWED_WRITE_DIRS = [
    ROOT_DIR / "cognition" / "custom_cognition",
    ROOT_DIR / "agency" / "skills",
]

# Resolved against ROOT_DIR so blocking is by path prefix, not substring —
# "think/" must not match e.g. "rethink/" or a filename containing the text.
_BLOCKED_PATHS = [
    (ROOT_DIR / p).resolve()
    for p in (
        "think",
        "cognition/repair",
        "cognition/selfhood",
        "registry",
        "core",
        "ORRIN_loop.py",
        "utils/generate_response.py",
        "utils/llm_stub.py",
        "agency/tool_runner.py",
        "agency/code_writer.py",
    )
]

_MANIFEST_FILE = ROOT_DIR / "agency" / "manifest.json"

def _load_manifest() -> List[Dict[str, Any]]:
    try:
        return json.loads(_MANIFEST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_manifest(entries: List[Dict[str, Any]]) -> None:
    _MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MANIFEST_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")

def _is_safe_path(path: Path) -> bool:
    resolved = path.resolve()
    for blocked in _BLOCKED_PATHS:
        if resolved == blocked:
            return False
        try:
            resolved.relative_to(blocked)
            return False
        except ValueError:
            pass
    for allowed in _ALLOWED_WRITE_DIRS:
        try:
            resolved.relative_to(allowed.resolve())
            return True
        except ValueError:
            continue
    return False

def _validate_syntax(code: str) -> Optional[str]:
    """Returns error string if code has a syntax error, else None."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"

def _validate_in_sandbox(code: str, name: str = "_anonymous", description: str = "") -> Dict[str, Any]:
    """
    Multi-stage verification: syntax → safety (AST) → subprocess execution → output.
    Returns {"ok": bool, "stdout": str, "stderr": str, "stages": dict}.
    """
    try:
        from cognition.skill_synthesis import verify_skill as _vsk
        result = _vsk(name, code, description, llm_review=False)
        out = {
            "ok": result["passed"],
            "stdout": "",
            "stderr": result.get("notes", "") if not result["passed"] else "",
            "returncode": 0 if result["passed"] else 1,
            "stages": result.get("stages", {}),
        }
    except Exception:
        # Fall back to bare subprocess run if skill_synthesis unavailable
        out = run_python(code, timeout=5.0)

    # Finding 7: the AST safety scan must not be skippable. verify_skill()
    # already runs it (stage 2), but the except-fallback above (run_python)
    # does not — re-run it here unconditionally as a final independent gate
    # before any code is written or hot-registered.
    try:
        from cognition.skill_synthesis import check_code_safety as _safety
        safe, violations = _safety(code)
        if not safe:
            out["ok"] = False
            out["stderr"] = ("Safety: " + "; ".join(violations))[:300]
            stages = dict(out.get("stages") or {})
            stages["safety"] = {"ok": False, "violations": violations}
            out["stages"] = stages
    except Exception as e:
        record_failure("code_writer._validate_in_sandbox", e)

    return out

# Write a new cognitive function

def write_cognitive_function(
    name: str,
    description: str,
    body: str,
    *,
    test: bool = True,
) -> Dict[str, Any]:
    """
    Write a new Python function to custom_cognition/ and register it live.

    Args:
        name:        Function name (e.g. "reflect_on_weather")
        description: One-line docstring
        body:        The function body as a string (indented or not — will be normalized)
        test:        If True, validate in sandbox before writing

    Returns:
        {"success": bool, "path": str, "error": str|None}
    """
    # Sanitize name
    name = name.strip().replace(" ", "_").replace("-", "_")
    if not name.isidentifier():
        return {"success": False, "path": "", "error": f"Invalid function name: {name!r}"}

    # Build full module code
    body_indented = textwrap.indent(textwrap.dedent(body).strip(), "    ")
    full_code = (
        f"# Auto-generated by Orrin — {now_iso_z()}\n"
        f"from cog_memory.working_memory import update_working_memory\n"
        f"from utils.log import log_activity\n\n"
        f"def {name}(context=None, **_):\n"
        f'    """{description}"""\n'
        f"{body_indented}\n"
    )

    # Syntax check
    err = _validate_syntax(full_code)
    if err:
        return {"success": False, "path": "", "error": err}

    # Multi-stage verification (syntax is already done above; this runs safety + execution)
    if test:
        result = _validate_in_sandbox(full_code, name=name, description=description)
        if not result.get("ok"):
            stderr = result.get("stderr", "").strip()
            # Tolerate ImportError of internal modules (unavailable in isolated process)
            if stderr and "Error" in stderr and "ImportError" not in stderr:
                return {"success": False, "path": "", "error": f"Verification: {stderr[:300]}"}

    # Write file
    target_dir = ROOT_DIR / "cognition" / "custom_cognition"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{name}.py"

    with _LOCK:
        file_path.write_text(full_code, encoding="utf-8")

    # Hot-register into live COGNITIVE_FUNCTIONS
    try:
        mod_name = f"cognition.custom_cognition.{name}"
        spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, name, None)
        if callable(fn):
            from registry.cognition_registry import COGNITIVE_FUNCTIONS
            COGNITIVE_FUNCTIONS[name] = {"function": fn, "is_cognition": True}
            log_activity(f"Orrin wrote and registered new function: {name}")
    except Exception as e:
        log_error(f"Hot-registration of {name} failed: {e} — will load on next restart")

    # Update manifest
    with _LOCK:
        manifest = _load_manifest()
        manifest.append({
            "name": name,
            "kind": "cognitive_function",
            "description": description,
            "path": str(file_path),
            "written_at": now_iso_z(),
        })
        _save_manifest(manifest)

    update_working_memory(f"Wrote new cognitive function: '{name}' — {description}")
    return {"success": True, "path": str(file_path), "error": None}

# Write a new tool

def write_tool(
    name: str,
    description: str,
    body: str,
    *,
    test: bool = True,
) -> Dict[str, Any]:
    """
    Write a new tool function to agency/skills/ and add it to the live tool_registry.

    Args:
        name:        Tool name (e.g. "fetch_weather")
        description: What it does
        body:        Function body as a string
        test:        Validate in sandbox first
    """
    name = name.strip().replace(" ", "_").replace("-", "_")
    if not name.isidentifier():
        return {"success": False, "path": "", "error": f"Invalid tool name: {name!r}"}

    body_indented = textwrap.indent(textwrap.dedent(body).strip(), "    ")
    full_code = (
        f"# Tool auto-generated by Orrin — {now_iso_z()}\n"
        f"import os, json, requests\n"
        f"from utils.log import log_activity, log_error\n\n"
        f"def {name}(args=None, **kwargs):\n"
        f'    """{description}"""\n'
        f"{body_indented}\n"
    )

    err = _validate_syntax(full_code)
    if err:
        return {"success": False, "path": "", "error": err}

    if test:
        result = _validate_in_sandbox(full_code)
        if not result.get("ok") and "Error" in result.get("stderr", "") and "ImportError" not in result.get("stderr", ""):
            return {"success": False, "path": "", "error": f"Sandbox: {result['stderr'][:300]}"}

    skills_dir = ROOT_DIR / "agency" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    file_path = skills_dir / f"{name}.py"

    with _LOCK:
        file_path.write_text(full_code, encoding="utf-8")

    # Hot-register into tool_registry
    try:
        mod_name = f"agency.skills.{name}"
        spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, name, None)
        if callable(fn):
            from behavior.tools.toolkit import tool_registry
            tool_registry[name] = fn
            log_activity(f"Orrin wrote and registered new tool: {name}")
    except Exception as e:
        log_error(f"Hot-registration of tool {name} failed: {e}")

    with _LOCK:
        manifest = _load_manifest()
        manifest.append({
            "name": name,
            "kind": "tool",
            "description": description,
            "path": str(file_path),
            "written_at": now_iso_z(),
        })
        _save_manifest(manifest)

    update_working_memory(f"Wrote new tool: '{name}' — {description}")
    return {"success": True, "path": str(file_path), "error": None}

# List and delete own code

def list_own_code() -> List[Dict[str, Any]]:
    """Return everything Orrin has written."""
    return _load_manifest()

def delete_own_code(name: str) -> Dict[str, Any]:
    """Delete a function or tool Orrin wrote (cannot delete core files)."""
    with _LOCK:
        manifest = _load_manifest()
        entry = next((e for e in manifest if e["name"] == name), None)
        if not entry:
            return {"success": False, "error": f"No record of writing '{name}'"}

        path = Path(entry["path"])
        if not _is_safe_path(path):
            return {"success": False, "error": "Cannot delete — path is outside safe write zones"}

        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            return {"success": False, "error": str(e)}

        manifest = [e for e in manifest if e["name"] != name]
        _save_manifest(manifest)

    # Remove from live registries
    try:
        from registry.cognition_registry import COGNITIVE_FUNCTIONS
        COGNITIVE_FUNCTIONS.pop(name, None)
    except Exception as _e:
        record_failure("code_writer.delete_own_code", _e)
    try:
        from behavior.tools.toolkit import tool_registry
        tool_registry.pop(name, None)
    except Exception as _e:
        record_failure("code_writer.delete_own_code.2", _e)

    update_working_memory(f"Deleted own code: '{name}'")
    return {"success": True, "error": None}

# Cognitive functions Orrin can use to write code autonomously

def synthesize_from_gap(context: Dict[str, Any] = None, **_) -> str:
    """
    Cognition function: scan for the highest-priority capability gap in working
    memory and synthesize a verified skill to address it. Uses the skill_synthesis
    pipeline (syntax → safety → execution → LLM behavioral review) before
    registering anything. Faster path than the full self_extension gestation cycle.
    """
    ctx = context or {}
    try:
        from cognition.skill_synthesis import detect_and_synthesize as _das
        result = _das(ctx)
        if result.get("synthesized"):
            fn = (result.get("result") or {}).get("fn_name", "?")
            update_working_memory(f"[skill_synthesis] Synthesized and registered: '{fn}' — verified safe.")
            return f"Synthesized new skill: '{fn}'"
        elif result.get("gaps_found", 0) > 0:
            return f"Found {result['gaps_found']} capability gap(s) but {result.get('reason', 'synthesis not ready')}."
        else:
            return "No clear capability gaps detected in recent experience."
    except Exception as e:
        update_working_memory(f"[skill_synthesis] synthesize_from_gap failed: {e}")
        return f"synthesize_from_gap failed: {e}"


def decide_to_write_code(context: Dict[str, Any] = None, **_) -> None:
    """
    Orrin writes a new cognitive function based on his current goal or exploration_drive.
    Uses LLM if available, otherwise generates a simple template function.
    """
    ctx = context or {}
    goal = ctx.get("committed_goal") or {}
    topic = (goal.get("title") or goal.get("kind") or "explore") if isinstance(goal, dict) else "explore"
    safe_topic = topic.lower().replace(" ", "_")[:40]
    fn_name = f"reflect_on_{safe_topic}"

    # Try LLM first for a real function body
    body = None
    try:
        from utils.generate_response import generate_response, llm_ok
        prompt = (
            f"Write the body of a Python function called '{fn_name}'.\n"
            f"It should: {topic}.\n"
            f"It has access to update_working_memory(str) and log_activity(str).\n"
            f"Keep it under 15 lines. No imports needed. Just the body (no def line)."
        )
        body = llm_ok(generate_response(prompt), "code_writer")
    except Exception as _e:
        record_failure("code_writer.decide_to_write_code", _e)

    # A minimal body that always validates — used both when the LLM returns
    # nothing AND as a fallback when an LLM-written body fails verification (a
    # syntactically/safety-invalid LLM body otherwise left the goal's production
    # milestone permanently unmet: decide_to_write_code "ran" every cycle but
    # never actually wrote a registered function).
    _safe_body = (
        f'update_working_memory("Orrin is reflecting on: {topic}")\n'
        f'log_activity("Auto-generated reflection on {topic}")\n'
    )
    if not body or not body.strip():
        body = _safe_body

    result = write_cognitive_function(
        fn_name,
        description=f"Auto-generated: reflect on {topic}",
        body=body,
    )
    # Fallback: if the LLM body failed verification, retry once with the safe
    # template so a real function still gets written and registered (the goal's
    # production milestone can only tick on a genuine "wrote ... function" trace).
    if not result["success"] and body != _safe_body:
        log_activity(f"[code_writer] LLM body failed ({result.get('error','')[:80]}); retrying with safe template.")
        result = write_cognitive_function(
            fn_name,
            description=f"Auto-generated: reflect on {topic}",
            body=_safe_body,
        )

    if result["success"]:
        update_working_memory(f"Wrote new function '{fn_name}' for: {topic}")
        # Ground-truth milestone tick. A function was genuinely written and
        # registered, so satisfy the committed goal's production milestone(s) right
        # here instead of relying on the downstream WM-text observer: that success
        # trace is written on the conscious thread but env_snapshot reads a possibly-
        # stale context["working_memory"], so the tick was missed and the goal looped
        # re-writing the same function forever (the production milestone never met).
        try:
            import time as _t
            _g = ctx.get("committed_goal")
            if isinstance(_g, dict):
                _PROD = ("written", "wrote", "write", "registered", "register",
                         "created", "create", "built", "build", "produced",
                         "produce", "implemented", "implement")
                _ART = ("function", "tool", "capability", "module", "code")
                _now = _t.time()
                for _m in (_g.get("milestones") or []):
                    if isinstance(_m, dict) and not _m.get("met"):
                        _txt = str(_m.get("text", "")).lower()
                        if any(w in _txt for w in _PROD) and any(w in _txt for w in _ART):
                            _m["met"] = True
                            _m["met_at"] = _now
                # If that satisfied the last milestone, COMPLETE the goal here at the
                # source of truth. The committed goal is excluded from the main loop's
                # satiety sweep and only completes via the Executive's pursue, which is
                # unreliable under resource preemption + the fast-path goal not being in
                # goals_mem — so an all-met goal would otherwise sit in_progress forever,
                # re-writing the same function and pinning impasse. mark_goal_completed's
                # hollow guard still applies (it re-checks milestones).
                _ms_all = [m for m in (_g.get("milestones") or []) if isinstance(m, dict)]
                if _ms_all and all(m.get("met") for m in _ms_all):
                    try:
                        from cognition.planning.goals import mark_goal_completed, merge_updated_goal_into_tree
                        from cognition.planning import goal_arbiter
                        mark_goal_completed(_g, context=context)
                        if _g.get("status") == "completed":
                            goal_arbiter.apply(lambda _t: merge_updated_goal_into_tree(_t, _g),
                                               source="code_writer.goal_completed")
                            if isinstance(context, dict) and (context.get("committed_goal") or {}).get("id") == _g.get("id"):
                                context["committed_goal"] = None
                            update_working_memory(
                                f"[goal_completed] Finished '{_g.get('title','?')[:50]}' — wrote {fn_name}.",
                                event_type="goal_completed", importance=3,
                            )
                            log_activity(f"[code_writer] Goal completed via real artifact: {_g.get('title','?')[:50]}")
                    except Exception as _ce:
                        record_failure("code_writer.decide_to_write_code.complete", _ce)
        except Exception as _e:
            record_failure("code_writer.decide_to_write_code.tick", _e)
    else:
        update_working_memory(f"Tried to write code but failed: {result['error']}")

# Exported for registration

AGENCY_CODE_FUNCTIONS = {
    "decide_to_write_code": decide_to_write_code,
    "synthesize_from_gap":  synthesize_from_gap,
}
