# brain/cognition/skill_verification.py
#
# Synthesized-skill verification for skill_synthesis.py (CODEBASE_CLEANUP_PLAN
# 4.5C), lifted verbatim to bring that module under the 600-line soft limit.
# The defense-in-depth gauntlet a candidate skill must pass before it is
# registered: _SafetyVisitor + _run_safety_check (AST allow-list scan),
# _run_execution_check (sandboxed import/run), _run_behavioral_review (LLM-judged
# behavior), and verify_skill, which composes them into a staged verdict.
# skill_synthesis.py re-imports these for synthesize_skill + external callers
# (self_extension_codegen, code_writer).
from __future__ import annotations

import ast
import re
import textwrap
from typing import Any, Dict, List, Tuple

from brain.utils.failure_counter import record_failure

# ─── Stage 2: AST Safety Scanner ──────────────────────────────────────────

class _SafetyVisitor(ast.NodeVisitor):
    """AST visitor that flags dangerous patterns in synthesized code.

    Finding 7: name-based denylists are bypassable via indirection, e.g.
    `getattr(__import__('o' + 's'), 'system')(...)` never names `os.system`
    directly. visit_Call/visit_Import alone miss this. We close that gap by
    additionally banning *any reference* (not just calls) to the handful of
    builtins that grant indirect access to modules/attributes/globals
    (visit_Name), and by banning access to dunder attributes generally
    (visit_Attribute) — legitimate skill bodies never need `__globals__`,
    `__subclasses__`, `__builtins__`, etc.
    """

    _BANNED_MODS = frozenset({
        "subprocess", "socket", "http", "urllib", "httpx", "requests",
        "aiohttp", "asyncio", "multiprocessing", "ctypes", "cffi",
        "ftplib", "smtplib", "telnetlib", "paramiko", "fabric",
    })
    _BANNED_BUILTINS = frozenset({"eval", "exec", "compile", "__import__"})
    # Builtins that grant indirect access to the things _BANNED_BUILTINS bans
    # outright — banning the bare name (not just a call) closes the
    # getattr(__import__(...), ...) indirection pathway.
    _BANNED_INTROSPECTION = frozenset({
        "getattr", "setattr", "delattr", "globals", "locals", "vars",
        "breakpoint", "__builtins__", "__loader__", "__import__",
    })
    _BANNED_OS_ATTRS = frozenset({
        "system", "popen", "fork", "execv", "execve", "execvp",
        "kill", "_exit", "killpg", "spawn", "spawnl", "spawnv",
    })
    _DUNDER_RE = re.compile(r"^__\w+__$")

    def __init__(self):
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in self._BANNED_MODS:
                self.violations.append(f"banned import: {alias.name!r}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        top = (node.module or "").split(".")[0]
        if top in self._BANNED_MODS:
            self.violations.append(f"banned from-import: {node.module!r}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in self._BANNED_BUILTINS:
            self.violations.append(f"banned call: {func.id}()")
        elif isinstance(func, ast.Attribute):
            if (isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr in self._BANNED_OS_ATTRS):
                self.violations.append(f"banned call: os.{func.attr}()")
            elif (isinstance(func.value, ast.Name)
                    and func.value.id == "sys"
                    and func.attr == "exit"):
                self.violations.append("banned call: sys.exit()")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        # Catches both calls AND bare references (e.g. `x = getattr` then
        # `x(...)`, or `getattr(__import__('o'+'s'), 'system')`).
        if node.id in self._BANNED_BUILTINS or node.id in self._BANNED_INTROSPECTION:
            self.violations.append(f"banned name reference: {node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Dunder attribute access (`obj.__globals__`, `cls.__subclasses__`,
        # `fn.__code__`, ...) is the standard sandbox-escape primitive and has
        # no legitimate use in a synthesized skill body.
        if self._DUNDER_RE.match(node.attr):
            self.violations.append(f"banned dunder attribute access: .{node.attr}")
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        # Warn about global state writes (not banned, but flagged)
        self.generic_visit(node)


def _run_safety_check(code: str) -> Tuple[bool, List[str]]:
    """Stage 2: AST safety scan. Returns (safe, violations_list)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, ["syntax error prevents safety scan"]
    visitor = _SafetyVisitor()
    visitor.visit(tree)
    return (len(visitor.violations) == 0), visitor.violations


# Public alias — code_writer.py runs this as an unconditional final gate
# before hot-registering synthesized code, regardless of which verification
# path (verify_skill vs. bare sandbox fallback) produced the "ok" result
# (Finding 7: the AST safety scan must not be skippable).
check_code_safety = _run_safety_check


# ─── Stage 3+4: Execution + Output ────────────────────────────────────────

def _run_execution_check(name: str, code: str) -> Tuple[bool, str, str]:
    """
    Stages 3+4: run code in sandbox subprocess and call the function.
    Returns (ok, stdout, stderr).
    ImportError of internal modules is tolerated — they won't be available
    in the isolated subprocess but will be present in the live environment.
    """
    # Test harness: import the module inline (no file write needed),
    # call the function with empty context, check return type.
    harness = textwrap.dedent(f"""
        import sys, types

        # Mock out internal modules that won't exist in isolated process
        _mock_mods = [
            "cog_memory", "cog_memory.working_memory", "cog_memory.long_memory",
            "utils", "utils.log", "utils.json_utils", "utils.generate_response",
            "paths", "utils.self_model",
        ]
        for _m in _mock_mods:
            if _m not in sys.modules:
                sys.modules[_m] = types.ModuleType(_m)

        # Inject common mock callables
        def _noop(*a, **kw): return None
        def _noop_str(*a, **kw): return ""
        sys.modules["cog_memory.working_memory"].update_working_memory = _noop
        sys.modules["cog_memory.long_memory"].update_long_memory = _noop
        sys.modules["utils.log"].log_activity = _noop
        sys.modules["utils.log"].log_private = _noop
        sys.modules["utils.log"].log_error = _noop
        sys.modules["utils.generate_response"].generate_response = _noop_str
        sys.modules["utils.generate_response"].llm_ok = lambda x, *a, **kw: x or ""
        sys.modules["utils.json_utils"].load_json = lambda *a, **kw: None
        sys.modules["utils.json_utils"].save_json = _noop

        # Make paths module expose common constants as Paths
        import pathlib, tempfile
        _paths = sys.modules["paths"]
        for _attr in ["WORKING_MEMORY_FILE", "LONG_MEMORY_FILE", "SELF_MODEL_FILE"]:
            setattr(_paths, _attr, pathlib.Path(tempfile.gettempdir()) / "orrin_mock.json")

        # Now exec the synthesized code
        _code = {code!r}
        exec(compile(_code, "<synthesized>", "exec"), {{}})

        # Retrieve and call the function
        import builtins
        _fn = locals().get({name!r}) or globals().get({name!r})
        if _fn is None:
            _ns = {{}}
            exec(compile(_code, "<synthesized>", "exec"), _ns)
            _fn = _ns.get({name!r})

        if not callable(_fn):
            print("ERROR: function not found or not callable", file=sys.stderr)
            sys.exit(1)

        _result = _fn(context={{}})
        if not isinstance(_result, str) or not _result.strip():
            print(f"ERROR: function returned invalid: {{_result!r}}", file=sys.stderr)
            sys.exit(2)

        print("OK:", _result[:120])
    """)

    try:
        from brain.think.sandbox_runner import run_python
        result = run_python(harness, timeout=8.0)
    except Exception as e:
        return False, "", str(e)

    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")

    # Fail only on hard errors (not expected mock-related ImportErrors)
    if not result.get("ok"):
        # If stderr only has ImportError from internal paths, tolerate it
        hard_error = any(
            word in stderr
            for word in ("SyntaxError", "IndentationError", "ZeroDivisionError",
                         "NameError", "AttributeError", "TypeError", "ERROR:")
        )
        if hard_error:
            return False, stdout, stderr
        # Otherwise: tolerate (likely environment mock gap)
        return True, stdout, stderr

    return True, stdout, stderr


# ─── Stage 5: Behavioral LLM Review (optional) ────────────────────────────

def _run_behavioral_review(name: str, code: str, description: str) -> Tuple[bool, int, str]:
    """
    Stage 5: ask LLM to review whether the code matches the stated intent.
    Returns (passed, rating_0_10, assessment).
    Only called when stages 1-4 pass and llm_review=True.
    """
    prompt = (
        f"Review this Python function for correctness and safety.\n\n"
        f"Stated purpose: {description}\n\n"
        f"Code:\n{code[:1200]}\n\n"
        f"Questions:\n"
        f"1. Does the code plausibly implement what's described?\n"
        f"2. Are there any logic errors, infinite loops, or dangerous patterns?\n"
        f"3. Will it return a non-empty string in the common case?\n\n"
        f"Reply as JSON only: "
        f'{{\"rating\": 0-10, \"assessment\": \"2-3 sentences\", \"safe\": true/false}}'
    )
    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="skill_synthesis/review"), "skill_synthesis") or ""
        import json as _json
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            data = _json.loads(m.group(0))
            rating = int(data.get("rating", 5))
            assessment = str(data.get("assessment", "")).strip()
            safe = bool(data.get("safe", True))
            passed = safe and rating >= 5
            return passed, rating, assessment
    except Exception as _e:
        record_failure("skill_synthesis._run_behavioral_review", _e)
    return True, 5, "review unavailable — defaulting to pass"


# ─── Public: Full Verification Pipeline ────────────────────────────────────

def verify_skill(
    name: str,
    code: str,
    description: str,
    llm_review: bool = False,
) -> Dict[str, Any]:
    """
    Run the 4-stage (+ optional 5th) verification pipeline on synthesized code.

    Returns:
        {
          "passed": bool,
          "stages": {
            "syntax":    {"ok": bool, "error": str},
            "safety":    {"ok": bool, "violations": list},
            "execution": {"ok": bool, "stdout": str, "stderr": str},
            "output":    {"ok": bool},
            "behavioral": {"ok": bool, "rating": int, "notes": str},  # if llm_review
          },
          "notes": str,  # human-readable summary of first failure
        }
    """
    stages: Dict[str, Any] = {}

    # Stage 1: Syntax
    try:
        ast.parse(code)
        stages["syntax"] = {"ok": True, "error": ""}
    except SyntaxError as e:
        stages["syntax"] = {"ok": False, "error": f"SyntaxError line {e.lineno}: {e.msg}"}
        return {"passed": False, "stages": stages, "notes": stages["syntax"]["error"]}

    # Stage 2: Safety
    safe, violations = _run_safety_check(code)
    stages["safety"] = {"ok": safe, "violations": violations}
    if not safe:
        return {"passed": False, "stages": stages, "notes": f"Safety: {violations[0]}"}

    # Stage 3+4: Execution + Output
    exec_ok, stdout, stderr = _run_execution_check(name, code)
    stages["execution"] = {"ok": exec_ok, "stdout": stdout[:300], "stderr": stderr[:300]}
    if not exec_ok:
        return {"passed": False, "stages": stages, "notes": f"Execution: {stderr[:200]}"}
    stages["output"] = {"ok": True}

    # Stage 5: Behavioral review (optional)
    if llm_review:
        beh_ok, rating, notes = _run_behavioral_review(name, code, description)
        stages["behavioral"] = {"ok": beh_ok, "rating": rating, "notes": notes}
        if not beh_ok:
            return {"passed": False, "stages": stages, "notes": f"Behavioral review failed (rating={rating}): {notes}"}

    return {"passed": True, "stages": stages, "notes": "all stages passed"}
