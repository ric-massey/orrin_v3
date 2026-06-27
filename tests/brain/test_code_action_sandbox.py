# Phase 5 (function_selection_fix_v2.md §5b) — security tests for the
# self-written / auto-generated code-execution path.
#
# The action-gate `execute_python_code` handler used to run model-/auto-generated
# code via a bare in-process exec() with full builtins (no AST check, subprocess,
# timeout, or resource limit). It now (a) emits a structured append_thought for
# the auto-generated case, and (b) is disabled by default, only ever running
# through the hardened subprocess sandbox when ALLOW_CODE_ACTIONS is set.
#
# These tests assert the enforcement the handler relies on, and that no
# in-process exec of generated code remains.
import re
import time
from pathlib import Path

import pytest

from brain.behavior.tools.sandbox import run_python_sandboxed


# --- the sandbox blocks hostile code (AST allowlist) ------------------------

@pytest.mark.parametrize("code", [
    "import os\nos.listdir('/')",
    "from os import path",
    "open('/etc/passwd').read()",
    "__import__('socket')",
    "eval('1+1')",
    "exec('x=1')",
])
def test_sandbox_rejects_hostile_code(code):
    """A disallowed import or builtin is rejected by the AST allowlist BEFORE
    any execution (raises ValueError), so it is never run."""
    with pytest.raises(ValueError):
        run_python_sandboxed(code)


def test_sandbox_allows_safe_code():
    """Allowlisted, side-effect-free code still runs in the subprocess."""
    res = run_python_sandboxed("import math\nprint(math.sqrt(16))")
    assert res.get("status") == "ok"
    assert "4.0" in (res.get("stdout") or "")


# --- the sandbox terminates infinite loops instead of hanging ---------------

def test_sandbox_times_out_infinite_loop():
    """`while True: pass` must terminate (wall-clock timeout and/or CPU rlimit),
    not hang the caller. Bounded well under the in-process failure mode."""
    start = time.time()
    res = run_python_sandboxed("while True:\n    pass", timeout_s=2)
    elapsed = time.time() - start
    assert res.get("status") == "error"
    assert elapsed < 8.0, f"sandbox did not terminate promptly (took {elapsed:.1f}s)"


# --- no in-process exec of generated code remains on the action path --------

def _action_gate_source() -> str:
    # The action gate is now a package (Phase 4.5C split): action_gate.py keeps
    # evaluate_and_act_if_needed, take_action lives in action_gate_execute.py, and
    # the support helpers in action_gate_helpers.py. Inspect all three.
    base = Path(__file__).resolve().parents[2] / "brain" / "think" / "think_utils"
    return "\n".join(
        (base / name).read_text(encoding="utf-8")
        for name in ("action_gate.py", "action_gate_execute.py", "action_gate_helpers.py")
    )


def test_action_gate_has_no_inprocess_exec_call():
    """The bare in-process exec()/eval()/compile() of action code is gone."""
    src = _action_gate_source()
    # strip comment lines so we only inspect executable statements
    code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    body = "\n".join(code_lines)
    for forbidden in (r"\bexec\s*\(", r"\beval\s*\(", r"\bcompile\s*\("):
        assert re.search(forbidden, body) is None, f"unexpected {forbidden!r} call in action_gate"


def test_execute_python_code_is_gated_and_sandboxed():
    """The handler is disabled by default (ALLOW_CODE_ACTIONS) and delegates to
    the hardened sandbox rather than executing code itself."""
    src = _action_gate_source()
    assert "ALLOW_CODE_ACTIONS" in src
    assert "run_python_sandboxed" in src


def test_behavior_generation_no_longer_writes_or_execs_stubs():
    """Option A: behavior_generation emits append_thought, not a .py stub write
    or an execute_python_code proposal."""
    p = Path(__file__).resolve().parents[2] / "brain" / "behavior" / "behavior_generation.py"
    src = p.read_text(encoding="utf-8")
    assert '"execute_python_code"' not in src
    assert '"write_file"' not in src
    assert '"append_thought"' in src
