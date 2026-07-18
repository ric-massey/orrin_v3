# Owed regression test from the Run 8 verdict (NEXT_RUN_TESTS §Run-8 (b)): an
# uncaught `TypeError: make_candidate() missing ... keyword-only arguments
# 'kind','direction'` at invoke.py's bare re-raise killed the brain thread
# mid-cycle 4418 — the dispatchability guard checked POSITIONAL params but
# ignored required KEYWORD_ONLY ones. Fixed in e70ac98; these pin it.

from brain.loop.invoke import _invoke_cognition


def test_required_keyword_only_fn_is_skipped_not_dispatched():
    calls = []

    def make_candidate(*, kind, direction):  # the exact crash shape
        calls.append((kind, direction))
        return "made"

    ctx: dict = {}
    out = _invoke_cognition(make_candidate, "make_candidate", ctx)

    assert not calls, "an unsatisfiable function must never be called"
    assert isinstance(out, dict) and out.get("status") == "error"
    assert "unsatisfiable_args" in str(out.get("error"))
    assert "kind" in str(out.get("error")) and "direction" in str(out.get("error"))
    # Selection must learn it: the fn leaves the candidate pool instead of
    # being re-picked (and re-crashed) every cycle.
    assert "make_candidate" in ctx.get("_undispatchable_fns", [])


def test_keyword_only_with_defaults_still_dispatches():
    def fn(*, kind="note", direction="out"):
        return f"{kind}:{direction}"

    assert _invoke_cognition(fn, "fn", {}) == "note:out"


def test_satisfiable_keyword_only_param_dispatches():
    def fn(*, context):
        return context.get("x")

    assert _invoke_cognition(fn, "fn", {"x": 5}) == 5
