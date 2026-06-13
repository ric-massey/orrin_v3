# Finding 7 (post-registration sandboxing): _validate_in_sandbox previously
# fell back to a bare subprocess run (run_python) — which never runs the AST
# safety scan — whenever importing cognition.skill_synthesis raised for any
# reason. That fallback could let code with the getattr(__import__(...))
# indirection bypass through to hot-registration. _validate_in_sandbox now
# re-runs the safety scan unconditionally as a final gate.
import agency.code_writer as code_writer
import cognition.skill_synthesis as skill_synthesis

MALICIOUS = (
    "def f(context=None, **_):\n"
    "    getattr(__import__('o' + 's'), 'system')('echo pwned')\n"
    "    return 'done'\n"
)

BENIGN = (
    "from cog_memory.working_memory import update_working_memory\n\n"
    "def f(context=None, **_):\n"
    '    update_working_memory("hi")\n'
    '    return "ok"\n'
)


def test_malicious_code_blocked_via_normal_path():
    result = code_writer._validate_in_sandbox(MALICIOUS, name="f")
    assert result["ok"] is False
    assert "getattr" in result["stderr"] or "getattr" in str(result.get("stages"))


def test_malicious_code_blocked_even_if_skill_synthesis_path_raises(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("verify_skill unavailable")

    monkeypatch.setattr(skill_synthesis, "verify_skill", boom)

    result = code_writer._validate_in_sandbox(MALICIOUS, name="f")
    assert result["ok"] is False
    assert "Safety" in result["stderr"]


def test_benign_code_passes():
    result = code_writer._validate_in_sandbox(BENIGN, name="f")
    assert result["ok"] is True
