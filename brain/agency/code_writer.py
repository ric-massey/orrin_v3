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
from brain.cognition.global_workspace import bound_goal
from brain.core.runtime_log import get_logger

import ast
import re
import textwrap
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.utils.log import log_activity, log_error
from brain.cog_memory.working_memory import update_working_memory
from brain.think.sandbox_runner import run_python
from brain.paths import ROOT_DIR
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
# Orrin's self-written code lives in the writable per-user tree (§10.1), not the
# read-only program folder. self_code owns those dirs, the import namespace, and the
# manifest (relative paths) — this module just asks it to write/load/record.
from brain.agency.self_code import (
    SELF_COGNITION_DIR,
    SELF_SKILLS_DIR,
    ensure_tree,
    load_module_from,
    normalize_self_code_imports,
    load_manifest as _load_manifest,
    save_manifest as _save_manifest,
    append_manifest as _append_manifest,
    abs_path as _manifest_abs_path,
)
_log = get_logger(__name__)

_LOCK = threading.Lock()

# Safe write locations — the writable self-code subtrees (NOT the program folder).
_ALLOWED_WRITE_DIRS = [
    SELF_COGNITION_DIR,
    SELF_SKILLS_DIR,
]

# Resolved against ROOT_DIR so blocking is by path prefix, not substring —
# "think/" must not match e.g. "rethink/" or a filename containing the text.
_BLOCKED_PATHS = [
    (ROOT_DIR / p).resolve()
    for p in (
        "think",
        "cognition/repair",
        "cognition/self_state",
        "registry",
        "core",
        "ORRIN_loop.py",
        "utils/generate_response.py",
        "utils/llm_stub.py",
        "agency/tool_runner.py",
        "agency/code_writer.py",
    )
]

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

def _clean_llm_code_body(resp: Optional[str]) -> Optional[str]:
    """Turn an ask_llm response into a usable function BODY, or None.

    ask_llm returns plain strings for BOTH success (the code) and failure ("ask_llm:
    …", "LLM tool unavailable …", cooldown, etc.) — map the failure/unavailable
    sentinels to None (→ no stub, capability-unavailable path). On success, strip
    markdown fences / def-line / imports and normalise the smart-punctuation the LLM
    likes to emit (em-dash etc.) that would otherwise fail the syntax check."""
    if not resp or not isinstance(resp, str):
        return None
    s = resp.strip()
    low = s.lower()
    if (s.startswith("ask_llm:") or "llm tool unavailable" in low
            or "llm_tool_blocked" in low or "cooldown active" in low
            or "no response received" in low or "llm call failed" in low):
        return None
    if "```" in s:
        m = re.search(r"```(?:python|py)?\s*(.*?)```", s, re.DOTALL)
        if m:
            s = m.group(1).strip()
    # ASCII-normalise common smart punctuation so valid logic isn't rejected for a dash.
    for bad, good in (("—", "-"), ("–", "-"), ("‘", "'"), ("’", "'"),
                      ("“", '"'), ("”", '"'), (" ", " ")):
        s = s.replace(bad, good)
    keep = [ln for ln in s.splitlines()
            if not ln.strip().startswith(("def ", "import ", "from "))]
    s = "\n".join(keep).strip()
    return s or None


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
        from brain.cognition.skill_synthesis import verify_skill as _vsk
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
        from brain.cognition.skill_synthesis import check_code_safety as _safety
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

def _record_code_effect(kind: str, full_code: str, context, goal_id, name=None) -> None:
    """P0: a written-and-registered function/tool is a real, durable external effect.

    `name` indexes the artifact so a later invocation by name is credited as tier-3
    re-use — the only ungameable production signal (you can fabricate a file; you
    cannot fabricate your future self choosing to call it)."""
    try:
        from brain.agency.effect_ledger import record_effect
        _row = record_effect(
            kind, full_code, goal_id=goal_id, context=context,
            metadata={"name": name} if name else None,
        )
        if _row is not None and _row.significance > 0 and isinstance(context, dict):
            context["_production_effect_this_cycle"] = True
            context.setdefault("_effect_rows_this_cycle", []).append(_row.to_json())
        # P1a: capture the code TEXT keyed by content_hash so a later-reused
        # tool/function can be retrieved as an exemplar (the ledger stores only the hash).
        if _row is not None:
            try:
                from brain.agency.effect_artifacts import capture as _cap_artifact
                _cap_artifact(full_code, content_hash=_row.content_hash)
            except Exception as _ce:
                from brain.utils.failure_counter import record_failure
                record_failure("code_writer.capture_artifact", _ce)
    except Exception as _e:
        from brain.utils.failure_counter import record_failure
        record_failure("code_writer.record_effect", _e)


def _announce_selfmod(kind: str, name: str, context) -> None:
    """R5 (Companion & Presence plan): authoring a new piece of himself is a
    headline, not buried Brain telemetry. Compose through the expression door
    (membrane-clean) and offer it to the P1 presence channel — the ignition +
    rarity budget in presence_notify still gates whether it actually shows."""
    try:
        from brain.behavior.express_to_user import Motive, compose_from_motive
        from brain.behavior.presence_notify import notify_spontaneous
        seed = f"I taught myself something new today — a {kind} called {name}"[:140]
        text = compose_from_motive(
            Motive(intent="announce_selfmod", recipient="Ric", seed=seed),
            context if isinstance(context, dict) else {},
        )
        ignited = bool(isinstance(context, dict) and context.get("_conscious_cycle") is True)
        notify_spontaneous(text, ignited=ignited)
    except Exception as _e:
        from brain.utils.failure_counter import record_failure
        record_failure("code_writer.announce_selfmod", _e)


def write_cognitive_function(
    name: str,
    description: str,
    body: str,
    *,
    test: bool = True,
    context: Dict[str, Any] = None,
    goal_id: str = None,
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
        f"from brain.cog_memory.working_memory import update_working_memory\n"
        f"from brain.utils.log import log_activity\n\n"
        f"def {name}(context=None, **_):\n"
        f'    """{description}"""\n'
        f"{body_indented}\n"
    )
    full_code = normalize_self_code_imports(full_code)

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

    # Write file into the writable self-code tree (never the program folder).
    ensure_tree()
    target_dir = SELF_COGNITION_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{name}.py"

    with _LOCK:
        file_path.write_text(full_code, encoding="utf-8")

    # Hot-register into live COGNITIVE_FUNCTIONS
    try:
        mod = load_module_from(file_path, "custom_cognition")
        fn = getattr(mod, name, None) if mod is not None else None
        if callable(fn):
            from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
            COGNITIVE_FUNCTIONS[name] = {"function": fn, "is_cognition": True}
            log_activity(f"Orrin wrote and registered new function: {name}")
    except Exception as e:
        log_error(f"Hot-registration of {name} failed: {e} — will load on next restart")

    # Update manifest (path stored relative to the self-code root)
    _append_manifest(name, "cognitive_function", description, file_path)

    update_working_memory(f"Wrote new cognitive function: '{name}' — {description}")
    _record_code_effect("code_committed", full_code, context, goal_id, name=name)
    _announce_selfmod("skill", name, context)
    return {"success": True, "path": str(file_path), "error": None}

# Write a new tool

def write_tool(
    name: str,
    description: str,
    body: str,
    *,
    test: bool = True,
    context: Dict[str, Any] = None,
    goal_id: str = None,
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
        f"from brain.utils.log import log_activity, log_error\n\n"
        f"def {name}(args=None, **kwargs):\n"
        f'    """{description}"""\n'
        f"{body_indented}\n"
    )
    full_code = normalize_self_code_imports(full_code)

    err = _validate_syntax(full_code)
    if err:
        return {"success": False, "path": "", "error": err}

    if test:
        result = _validate_in_sandbox(full_code)
        if not result.get("ok") and "Error" in result.get("stderr", "") and "ImportError" not in result.get("stderr", ""):
            return {"success": False, "path": "", "error": f"Sandbox: {result['stderr'][:300]}"}

    ensure_tree()
    skills_dir = SELF_SKILLS_DIR
    skills_dir.mkdir(parents=True, exist_ok=True)
    file_path = skills_dir / f"{name}.py"

    with _LOCK:
        file_path.write_text(full_code, encoding="utf-8")

    # Hot-register into tool_registry
    try:
        mod = load_module_from(file_path, "skills")
        fn = getattr(mod, name, None) if mod is not None else None
        if callable(fn):
            from brain.behavior.tools.toolkit import tool_registry
            tool_registry[name] = fn
            log_activity(f"Orrin wrote and registered new tool: {name}")
    except Exception as e:
        log_error(f"Hot-registration of tool {name} failed: {e}")

    _append_manifest(name, "tool", description, file_path)

    update_working_memory(f"Wrote new tool: '{name}' — {description}")
    _record_code_effect("tool_written", full_code, context, goal_id, name=name)
    _announce_selfmod("tool", name, context)
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

        path = _manifest_abs_path(entry)
        if not _is_safe_path(path):
            return {"success": False, "error": "Cannot delete — path is outside safe write zones"}

        try:
            path.unlink(missing_ok=True)
        except OSError as e:  # intentional: filesystem delete failure → reported to caller
            return {"success": False, "error": str(e)}

        manifest = [e for e in manifest if e["name"] != name]
        _save_manifest(manifest)

    # Remove from live registries
    try:
        from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
        COGNITIVE_FUNCTIONS.pop(name, None)
    except Exception as _e:
        record_failure("code_writer.delete_own_code", _e)
    try:
        from brain.behavior.tools.toolkit import tool_registry
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
        from brain.cognition.skill_synthesis import detect_and_synthesize as _das
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
    Write a new cognitive function for the current goal — but ONLY when the
    code-writing tool can supply a genuine function body. Writing code is a
    generative act that needs the LLM tool; in tool-only mode (the default) this
    background caller is not on the LLM allow-list, so it gets nothing. That is the
    honest outcome: NO do-nothing stub is written and NO milestone is faked. The
    goal's production milestone then stays unmet, so the goal honestly degrades or
    disengages (pursue_goal._DELIBERATE_MAX_ROUNDS) instead of logging a hollow win.
    """
    ctx = context or {}
    goal = bound_goal(ctx) or {}
    topic = (goal.get("title") or goal.get("kind") or "explore") if isinstance(goal, dict) else "explore"
    safe_topic = topic.lower().replace(" ", "_")[:40]
    fn_name = f"reflect_on_{safe_topic}"

    # Writing code needs the LLM. Per the tool-only design, the LLM is reached as a
    # DELIBERATE TOOL (ask_llm) — Orrin's brain deciding to use a resource — not as
    # background cognition. When the LLM is down/unavailable, ask_llm returns an
    # unavailable message, which _clean_llm_code_body() maps to None below → no stub.
    body = None
    try:
        from brain.cognition.tools.ask_llm import ask_llm
        query = f"Write the body of a Python function named '{fn_name}'. It should: {topic}."
        body = _clean_llm_code_body(ask_llm(ctx, query=query, purpose="write_code", force=True))
    except Exception as _e:
        record_failure("code_writer.decide_to_write_code", _e)

    # No genuine body → the code-writing capability is unavailable right now. Do NOT
    # write a hollow stub and do NOT fake the milestone; surface the honest blocker so
    # the goal can degrade/disengage rather than loop on fake artifacts.
    if not body or not body.strip():
        update_working_memory(
            f"[capability_unavailable] Can't write code for '{topic[:50]}' — the "
            f"code-writing tool (LLM) is unavailable. No function written.",
            event_type="capability_unavailable", importance=2,
        )
        log_activity("[code_writer] decide_to_write_code: no LLM body available — not writing a stub.")
        return

    result = write_cognitive_function(
        fn_name,
        description=f"Auto-generated: reflect on {topic}",
        body=body,
        context=ctx,
        goal_id=(goal.get("id") if isinstance(goal, dict) else None),
    )
    if result["success"]:
        update_working_memory(f"Wrote new function '{fn_name}' for: {topic}")
    else:
        update_working_memory(f"Tried to write code but failed: {result['error']}")

# Exported for registration

AGENCY_CODE_FUNCTIONS = {
    "decide_to_write_code": decide_to_write_code,
    "synthesize_from_gap":  synthesize_from_gap,
}
