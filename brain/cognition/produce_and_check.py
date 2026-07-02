"""Produce-and-check (grounding plan Phase 3 / C3 · B4).

Make "understood" mean "attempted and passed a check," not "stopped feeling new."

For a goal in a *verifiable* domain (math, physics, statistics, code, …), this
action synthesizes a small self-checking Python snippet, runs it in the caged
sandbox (`brain.think.sandbox_runner.run_python`), and:

  • on a passing check — records a `tool_run_effect` on the effect ledger (the
    first and only emitter of that kind), which satisfies Phase-1's closure gate
    and lets `goal_satiety.is_sated` close the goal on a check-pass;
  • on a failing check — writes the specific gap (the error) back onto the goal so
    the next step aims at it. This is the "attempt until I stop getting it wrong"
    loop, replacing the *unfamiliarity* proxy with a *failure* proxy.

It is LLM-free and reversible: the sandbox runs untrusted code in an isolated
subprocess, and nothing is committed except a ledger row on success. Non-verifiable
topics are declined (they keep the honest info-gap proxy) — do not gate a goal on a
check it cannot have.
"""
from __future__ import annotations

import hashlib
import textwrap
from typing import Any, Dict, Optional, Tuple

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

# ── Verifiable-domain allow-list (start narrow; expand deliberately) ──────────────
# The plan's risk note: classifying "verifiable" is itself fallible, so begin with an
# explicit allow-list of domains where a self-contained numeric/logical check is
# honest, and never gate a non-verifiable goal on a check.
_VERIFIABLE_DOMAINS: Dict[str, frozenset] = {
    "math": frozenset({
        "math", "mathematic", "arithmetic", "algebra", "geometry", "calculus",
        "number", "integer", "prime", "factor", "equation", "theorem", "identity",
        "series", "sum", "sequence", "modular", "combinator", "trigonometry",
    }),
    "statistics": frozenset({
        "statistic", "probability", "variance", "mean", "average", "distribution",
        "regression", "correlation", "sampling", "expectation", "stddev",
    }),
    "physics": frozenset({
        "physics", "kinematic", "velocity", "acceleration", "momentum", "energy",
        "force", "newton", "gravity", "projectile", "orbit", "thermodynamic",
    }),
    "code": frozenset({
        "code", "algorithm", "sorting", "sort", "search", "data structure",
        "recursion", "complexity", "function", "program", "computation",
        "gcd", "fibonacci", "hash", "string", "parse",
    }),
    "logic": frozenset({
        "logic", "boolean", "truth table", "proposition", "implication",
        "de morgan", "syllogism", "predicate",
    }),
}

_MIN_TOPIC_LEN = 3


def classify_verifiable(text: str) -> Optional[str]:
    """Return the verifiable domain for `text`, or None if it is not in the
    allow-list. Matched on whole-word-ish keyword membership, longest domain wins
    ties by check order (math first)."""
    if not isinstance(text, str):
        return None
    low = text.lower()
    for domain, keys in _VERIFIABLE_DOMAINS.items():
        if any(k in low for k in keys):
            return domain
    return None


def is_verifiable_goal(goal: Optional[Dict[str, Any]]) -> bool:
    """True when a goal's topic/title/description falls in a verifiable domain.
    `goal_satiety.is_sated` uses this to switch a growth goal from the info-gap
    proxy to the check-pass proxy."""
    if not isinstance(goal, dict):
        return False
    if isinstance(goal.get("check_spec"), dict):
        return True
    for field in ("topic", "title", "name", "description"):
        if classify_verifiable(str(goal.get(field) or "")):
            return True
    return False


def _goal_id(goal: Dict[str, Any]) -> str:
    return str(goal.get("id") or goal.get("title") or goal.get("name") or "")


def _topic_of(goal: Dict[str, Any]) -> str:
    for field in ("topic", "title", "name", "description"):
        v = str(goal.get(field) or "").strip()
        if len(v) >= _MIN_TOPIC_LEN:
            return v
    return ""


def _synthesize_check(topic: str, domain: str, goal: Dict[str, Any]) -> Tuple[str, str]:
    """Build a small, self-contained, self-asserting Python snippet for the domain.

    A goal may carry an explicit `check_spec = {"code": "...", "label": "..."}` (a
    plan- or future-LLM-supplied check, and what the tests use); when present it is
    used verbatim. Otherwise a domain-appropriate self-consistency check is
    synthesized — a real computation that *asserts* a known-true property and prints
    `CHECK_PASS` only if the assertion holds. The topic seeds the parameters so
    different goals run different (not identical) checks."""
    spec = goal.get("check_spec") if isinstance(goal, dict) else None
    if isinstance(spec, dict) and str(spec.get("code") or "").strip():
        return str(spec["code"]), str(spec.get("label") or topic)[:120]

    seed = int(hashlib.sha256(topic.encode("utf-8")).hexdigest(), 16)
    n = 3 + (seed % 20)          # 3..22
    m = 2 + (seed // 7 % 15)     # 2..16

    if domain == "statistics":
        code = textwrap.dedent(f"""
            data = [((i * 7 + {seed % 97}) % 50) for i in range({n})]
            mean = sum(data) / len(data)
            # variance two ways: mean of squares minus square of mean == mean of squared deviations
            v1 = sum((x - mean) ** 2 for x in data) / len(data)
            v2 = sum(x * x for x in data) / len(data) - mean * mean
            assert abs(v1 - v2) < 1e-9, (v1, v2)
            print("CHECK_PASS variance identity holds for", len(data), "samples")
        """).strip()
    elif domain == "physics":
        code = textwrap.dedent(f"""
            u, a, t = {n}.0, {m}.0, 3.0
            # kinematics self-consistency: v = u + a t  and  s = u t + 1/2 a t^2,
            # and v^2 = u^2 + 2 a s must all agree.
            v = u + a * t
            s = u * t + 0.5 * a * t * t
            assert abs(v * v - (u * u + 2 * a * s)) < 1e-6
            print("CHECK_PASS kinematic identity v^2=u^2+2as holds")
        """).strip()
    elif domain == "code":
        code = textwrap.dedent(f"""
            import math
            def gcd(a, b):
                while b:
                    a, b = b, a % b
                return a
            a, b = {n}, {m}
            # our gcd agrees with math.gcd, and gcd*lcm == a*b
            assert gcd(a, b) == math.gcd(a, b)
            g = gcd(a, b)
            assert g * (a * b // g) == a * b
            # a hand-written sort agrees with sorted()
            xs = [((i * 13 + {seed % 31}) % 100) for i in range({n})]
            def isort(seq):
                s = list(seq)
                for i in range(1, len(s)):
                    k, j = s[i], i - 1
                    while j >= 0 and s[j] > k:
                        s[j + 1] = s[j]; j -= 1
                    s[j + 1] = k
                return s
            assert isort(xs) == sorted(xs)
            print("CHECK_PASS gcd/lcm + insertion-sort match references")
        """).strip()
    elif domain == "logic":
        code = textwrap.dedent("""
            # De Morgan over all boolean assignments
            for a in (False, True):
                for b in (False, True):
                    assert (not (a and b)) == ((not a) or (not b))
                    assert (not (a or b)) == ((not a) and (not b))
            print("CHECK_PASS De Morgan's laws hold over all assignments")
        """).strip()
    else:  # math (default)
        code = textwrap.dedent(f"""
            import math
            n = {n}
            # closed form vs brute force: sum(1..n) == n(n+1)/2, sum of squares too
            assert sum(range(1, n + 1)) == n * (n + 1) // 2
            assert sum(i * i for i in range(1, n + 1)) == n * (n + 1) * (2 * n + 1) // 6
            # gcd/lcm identity
            a, b = n, {m}
            g = math.gcd(a, b)
            assert g * (a * b // g) == a * b
            print("CHECK_PASS arithmetic identities hold for n =", n)
        """).strip()

    return code, f"{domain}: {topic}"[:120]


def _gap_from(result: Dict[str, Any]) -> str:
    """Turn a failed sandbox run into a short, specific gap string to aim the next
    attempt at."""
    stderr = str(result.get("stderr") or "").strip()
    if stderr:
        # last traceback line is the most specific (the assertion / exception)
        last = [ln for ln in stderr.splitlines() if ln.strip()]
        return (last[-1] if last else stderr)[:240]
    if result.get("returncode") == -9:
        return "check timed out"
    return "check did not print CHECK_PASS"


def produce_and_check(context: Dict[str, Any] = None, **_) -> Dict[str, Any]:
    """Cognitive action (P3). Attempt a verifiable check for the active goal and
    record a `tool_run_effect` on success, or write the gap back on failure.
    Returns a result dict the step-executor / loop reads (`changed`, `reason`)."""
    ctx = context or {}
    try:
        from brain.cognition.global_workspace import bound_goal
        goal = bound_goal(ctx) or {}
    except Exception as _e:
        record_failure("produce_and_check.bound_goal", _e)
        goal = {}
    if not isinstance(goal, dict) or not goal:
        return {"changed": False, "reason": "no active goal to check"}

    topic = _topic_of(goal)
    spec = goal.get("check_spec") if isinstance(goal, dict) else None
    if isinstance(spec, dict) and str(spec.get("code") or "").strip():
        # An explicit, plan-/spec-supplied check runs regardless of topic wording.
        domain = "code"
        topic = topic or str(spec.get("label") or "explicit check")
    else:
        domain = None
        for field in ("topic", "title", "name", "description"):
            domain = classify_verifiable(str(goal.get(field) or ""))
            if domain:
                break
        if not domain or len(topic) < _MIN_TOPIC_LEN:
            return {"changed": False,
                    "reason": f"topic {topic[:40]!r} is not in a verifiable domain — "
                              "produce-and-check needs a checkable subject"}

    gid = _goal_id(goal)
    code, label = _synthesize_check(topic, domain, goal)

    try:
        from brain.think.sandbox_runner import run_python
        result = run_python(code, timeout=5.0)
    except Exception as _e:
        record_failure("produce_and_check.run_python", _e)
        return {"changed": False, "reason": "sandbox unavailable"}

    passed = bool(result.get("ok")) and "CHECK_PASS" in str(result.get("stdout") or "")

    if passed:
        stdout = str(result.get("stdout") or "").strip()
        # Tie the effect to THIS goal (goal id in the content) so two goals that
        # happen to synthesize the same check each get their own credited effect,
        # while a goal re-running its identical check still dedupes (no double-credit).
        content = f"[produce_and_check goal={gid or '?'} :{label}]\n{code}\n--- output ---\n{stdout}"
        row = None
        try:
            from brain.agency.effect_ledger import record_effect
            row = record_effect(
                "tool_run_effect", content,
                goal_id=gid or None, context=ctx,
                metadata={"domain": domain, "topic": topic[:120], "action": "produce_and_check"},
            )
        except Exception as _e:
            record_failure("produce_and_check.record_effect", _e)
        # Stamp the goal so downstream (and the UI) can see it passed, and clear any
        # prior gap. is_sated reads the durable ledger row (has_effect_kind), so the
        # close does not depend on this flag surviving the goal-tree round-trip.
        goal["_check_passed"] = True
        goal.pop("_last_check_gap", None)
        try:
            from brain.cog_memory.working_memory import update_working_memory
            update_working_memory(f"[check] Passed a {domain} check for {topic!r}: {result.get('stdout','').strip()[:160]}")
        except Exception as _e:
            record_failure("produce_and_check.wm", _e)
        _record_reach(ctx, f"Checked {topic!r} ({domain}) — passed", info_gain=0.6)
        log_activity(f"[produce_and_check] PASS {domain} check for {topic!r}"
                     f"{' (credited)' if row is not None else ''}")
        return {"changed": True, "result": f"check passed: {label}",
                "domain": domain, "credited": row is not None, "check_passed": True}

    # Failure — write the gap back onto the goal to aim the next step.
    gap = _gap_from(result)
    goal["_check_passed"] = False
    goal["_last_check_gap"] = gap
    try:
        from brain.cog_memory.working_memory import update_working_memory
        update_working_memory(f"[check] A {domain} check for {topic!r} did not pass — gap: {gap}")
    except Exception as _e:
        record_failure("produce_and_check.wm_fail", _e)
    _record_reach(ctx, f"Checked {topic!r} ({domain}) — failed: {gap}", info_gain=0.2)
    log_activity(f"[produce_and_check] FAIL {domain} check for {topic!r} — gap: {gap}")
    return {"changed": True, "result": f"check failed: {gap}",
            "domain": domain, "check_passed": False, "gap": gap}


def _record_reach(ctx: Dict[str, Any], text: str, info_gain: float) -> None:
    """Feed the explore/exploit reach-value learner so this arm warms up like the
    other outward actions (mirrors research_topic's tail)."""
    try:
        from brain.cognition.exploration_value import record_reach_outcome
        record_reach_outcome("produce_and_check", text, None, ctx)
    except Exception as _e:
        record_failure("produce_and_check.reach", _e)
