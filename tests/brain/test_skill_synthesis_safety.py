# Finding 7: name-based AST denylists are bypassable via indirection, e.g.
# `getattr(__import__('o' + 's'), 'system')(...)` never names `os.system`
# directly. _SafetyVisitor (Stage 2 of verify_skill) was hardened to ban bare
# references (not just calls) to introspection builtins and to ban dunder
# attribute access generally. These tests pin that behavior.
from cognition.skill_synthesis import check_code_safety, _run_safety_check


def test_check_code_safety_is_run_safety_check():
    assert check_code_safety is _run_safety_check


def test_benign_skill_body_passes():
    code = (
        "from cog_memory.working_memory import update_working_memory\n"
        "from utils.log import log_activity\n\n"
        "def reflect_on_weather(context=None, **_):\n"
        '    """Reflect on the weather."""\n'
        '    update_working_memory("Orrin is reflecting on the weather")\n'
        '    log_activity("Reflected on weather")\n'
        '    return "Reflected on the weather."\n'
    )
    safe, violations = check_code_safety(code)
    assert safe, violations


def test_getattr_import_indirection_is_blocked():
    # The exact bypass pattern named in the finding.
    code = (
        "def f(context=None, **_):\n"
        "    getattr(__import__('o' + 's'), 'system')('echo pwned')\n"
        "    return 'done'\n"
    )
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("getattr" in v for v in violations)
    assert any("__import__" in v for v in violations)


def test_dunder_subclass_walk_is_blocked():
    # Classic sandbox-escape primitive: walk object.__subclasses__() to find
    # something dangerous (e.g. subprocess.Popen) without naming it directly.
    code = (
        "def f(context=None, **_):\n"
        "    return str(().__class__.__bases__[0].__subclasses__())\n"
    )
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("__subclasses__" in v for v in violations)
    assert any("__bases__" in v for v in violations)
    assert any("__class__" in v for v in violations)


def test_bare_reference_to_banned_builtin_is_blocked():
    # Aliasing a banned builtin to a new name is not a real bypass — the bare
    # reference itself (not just the call) must be flagged.
    code = (
        "def f(context=None, **_):\n"
        "    e = eval\n"
        "    return e('1+1')\n"
    )
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("eval" in v for v in violations)


def test_globals_and_vars_are_blocked():
    code = "def f(context=None, **_):\n    return str(globals())\n"
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("globals" in v for v in violations)


def test_banned_module_import_still_blocked():
    code = "import subprocess\n\ndef f(context=None, **_):\n    return 'x'\n"
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("subprocess" in v for v in violations)


def test_os_system_call_still_blocked():
    code = "import os\n\ndef f(context=None, **_):\n    os.system('echo hi')\n    return 'x'\n"
    safe, violations = check_code_safety(code)
    assert not safe
    assert any("os.system" in v for v in violations)
