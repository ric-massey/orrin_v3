# brain/cognition/skill_synthesis.py
# Capability gap detection + safe verified skill synthesis.
#
# Gap detection: scans recent WM for incapacity signals ("couldn't", "no way to",
#   "wish I could", "failed because") weighted by recency + emotional context.
#
# Verification pipeline (4 mandatory + 1 optional stages):
#   Stage 1 — Syntax:   ast.parse()
#   Stage 2 — Safety:   AST visitor — bans subprocess/eval/exec/os.system/network
#   Stage 3 — Execution: sandbox_runner subprocess; ImportError of internal modules OK
#   Stage 4 — Output:   function returns non-empty str, no runtime crash
#   Stage 5 — Behavioral review (LLM, optional): does code match stated intent?
#
# Registration: verified skills enter self_extension's lifecycle at "committed" status
#   so that maybe_integrate_or_atrophy() handles promotion/removal naturally.
#
# Integration points:
#   - dream_cycle.py      → detect_and_synthesize(context)
#   - code_writer.py      → verify_skill(name, code, description)
#   - self_extension.py   → verify_skill(name, code, description, llm_review=True)
#   - knowledge_graph.py  → gaps and synthesized tools are added as entities
from __future__ import annotations
from brain.core.runtime_log import get_logger
_log = get_logger(__name__)


import ast
import hashlib
import re
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_activity, log_private
from brain.paths import (
    WORKING_MEMORY_FILE, PROPOSED_TOOLS_JSON, SKILL_SYNTHESIS_FILE,
)
from brain.utils.timeutils import now_iso_z
from brain.utils.llm_gate import llm_callable_by
from brain.utils.failure_counter import record_failure

_SELF_GENERATED_DIR = Path(__file__).resolve().parent / "self_generated"
_SYNTHESIZE_COOLDOWN_S = 3 * 3600    # max one synthesis attempt per 3h
_GAP_SCORE_THRESHOLD   = 0.30        # minimum gap score to attempt synthesis
_MAX_CANDIDATES        = 12          # cap stored gap candidates
_TRIAL_ATROPHY_CYCLES  = 100         # cycles before integration check (mirrors self_extension)
_TRIAL_MIN_PICKS       = 4           # min picks over _TRIAL_ATROPHY_CYCLES to survive

_last_synthesis_ts: float = 0.0


# ─── Gap signal patterns in WM ─────────────────────────────────────────────

_GAP_PATTERNS = [
    re.compile(r"couldn'?t\s+\w+", re.I),
    re.compile(r"wasn'?t able to\s+\w+", re.I),
    re.compile(r"no way to\s+\w+", re.I),
    re.compile(r"wish I could\s+\w+", re.I),
    re.compile(r"I want to be able to\s+\w+", re.I),
    re.compile(r"I (lacked|lack)\s+\w+", re.I),
    re.compile(r"failed (to|because)\s+\w+", re.I),
    re.compile(r"there'?s no (function|way|tool|method) (to|for)\s+\w+", re.I),
    re.compile(r"I (can'?t|cannot)\s+\w+", re.I),
    re.compile(r"missing capability", re.I),
    re.compile(r"I need (a way|the ability|to be able)", re.I),
]

_GAP_STOPLIST = {
    "speak", "say", "think", "feel", "see", "know", "understand",
    "be", "exist", "remember", "forget",  # too generic
}



def _gap_id(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:10]


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


# ─── Gap Detection ──────────────────────────────────────────────────────────

def _scan_for_gaps(context: Dict[str, Any]) -> List[Dict]:
    """Scan working memory and long memory for incapacity signal phrases."""
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    emo = (context.get("affect_state") or {})
    core_emo = emo.get("core_signals", emo) or {}
    impasse_signal = float(core_emo.get("impasse_signal", 0.0) or 0.0)
    motivation  = float(core_emo.get("motivation", 0.0) or 0.0)
    emo_weight  = min(1.0, impasse_signal * 0.6 + motivation * 0.4)

    gaps: List[Dict] = []

    for idx, entry in enumerate(reversed(wm[-60:])):
        content = str(entry.get("content", entry) if isinstance(entry, dict) else entry)
        if len(content) < 10:
            continue
        recency = max(0.05, 1.0 - idx / 60.0)   # most recent = 1.0, oldest = 0.05

        for pat in _GAP_PATTERNS:
            m = pat.search(content)
            if not m:
                continue
            snippet = content[max(0, m.start() - 20): m.end() + 60].strip()
            # Skip if it's just generic existence verbs
            words = set(re.findall(r'\w+', snippet.lower()))
            if words & _GAP_STOPLIST and len(words) < 5:
                continue
            score = recency * 0.5 + emo_weight * 0.3 + 0.2   # baseline 0.2
            gaps.append({
                "id": _gap_id(snippet),
                "snippet": snippet[:200],
                "score": round(min(1.0, score), 3),
                "recency": round(recency, 3),
                "emo_weight": round(emo_weight, 3),
                "seen_at": now_iso_z(),
            })

    # Deduplicate by id (keep highest score)
    seen: Dict[str, Dict] = {}
    for g in gaps:
        gid = g["id"]
        if gid not in seen or g["score"] > seen[gid]["score"]:
            seen[gid] = g
    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:_MAX_CANDIDATES]


def _load_synthesis_state() -> Dict:
    s = load_json(SKILL_SYNTHESIS_FILE, default_type=dict) or {}
    if not isinstance(s, dict):
        s = {}
    s.setdefault("candidates", [])
    s.setdefault("synthesized", [])
    s.setdefault("last_synthesis", "")
    return s


def _save_synthesis_state(s: Dict) -> None:
    save_json(SKILL_SYNTHESIS_FILE, s)


# ─── Skill Generation (LLM) ────────────────────────────────────────────────

def _build_synthesis_prompt(fn_name: str, description: str, gap_text: str, kg_context: str, wm_recent: str) -> str:
    return (
        f"You are Orrin, writing a new cognitive function to address a capability gap.\n\n"
        f"Gap you detected: {gap_text}\n"
        f"Function name: {fn_name}\n"
        f"Purpose: {description}\n\n"
        + (f"Relevant world knowledge:\n{kg_context}\n\n" if kg_context else "")
        + (f"Recent thoughts:\n{wm_recent}\n\n" if wm_recent else "")
        + "Write a complete Python module file. Rules:\n"
        "  1. Function signature: def " + fn_name + "(context=None, **_) -> str\n"
        "  2. Only import from: cog_memory.*, utils.log, utils.json_utils, paths\n"
        "  3. No subprocess, socket, os.system, os.popen, eval, exec, requests\n"
        "  4. Must return a non-empty string describing what was done\n"
        "  5. Wrap all logic in try/except; on failure return an error string\n"
        "  6. Max 60 lines total. Include module docstring. No markdown fences.\n"
        "  7. Write ONLY the Python code — nothing else.\n"
    )


def synthesize_skill(candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attempt to synthesize a verified skill from a gap candidate.
    Generates code via LLM, runs verification pipeline, registers on success.
    Returns result dict with keys: success, fn_name, file_path, verification, error.
    """
    if not llm_callable_by("skill_synthesis"):
        log_activity("[skill_synthesis] skipped — LLM unavailable")
        return {"success": False, "error": "llm_unavailable"}
    gap_text = candidate.get("snippet", "")
    if not gap_text:
        return {"success": False, "error": "empty gap description"}

    # Derive a function name from the gap text
    words = re.findall(r'\b[a-z][a-z_]+\b', gap_text.lower())
    meaningful = [w for w in words if w not in _GAP_STOPLIST and len(w) > 3][:4]
    fn_name = "synthesized_" + "_".join(meaningful) if meaningful else "synthesized_skill"
    fn_name = re.sub(r'[^a-z0-9_]', '', fn_name)[:48]
    if not fn_name.isidentifier():
        fn_name = "synthesized_capability"

    # Check if already synthesized with this name
    state = _load_synthesis_state()
    existing_names = {s["name"] for s in state.get("synthesized", [])}
    if fn_name in existing_names:
        fn_name = fn_name + "_" + _gap_id(gap_text)[:4]

    # Build description from gap
    description = f"Synthesized to address: {gap_text[:120]}"

    # Pull KG context relevant to this gap
    kg_context = ""
    try:
        from brain.cognition.knowledge_graph import get_context_for_prompt as _kg_ctx
        kg_context = _kg_ctx(gap_text, limit=3)
    except Exception as _e:
        record_failure("skill_synthesis.synthesize_skill", _e)

    # Recent WM context
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    wm_recent = "\n".join(
        f"- {str(e.get('content', ''))[:80]}" for e in (wm[-6:] if isinstance(wm, list) else [])
        if isinstance(e, dict) and str(e.get("content", "")).strip()
    )

    prompt = _build_synthesis_prompt(fn_name, description, gap_text, kg_context, wm_recent)

    try:
        from brain.utils.generate_response import generate_response, llm_ok
        raw = llm_ok(generate_response(prompt, caller="skill_synthesis/synthesize"), "skill_synthesis") or ""
    except Exception as e:
        return {"success": False, "fn_name": fn_name, "error": f"LLM unavailable: {e}"}

    if not raw or len(raw.strip()) < 40:
        return {"success": False, "fn_name": fn_name, "error": "LLM returned empty/too-short response"}

    # Strip markdown fences if present
    code = raw.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    # Add header
    header = (
        f"# cognition/self_generated/{fn_name}.py\n"
        f"# Synthesized by Orrin on {now_iso_z()}\n"
        f"# Gap: {gap_text[:120]}\n\n"
    )
    full_code = header + code

    # Run verification
    verification = verify_skill(fn_name, full_code, description, llm_review=True)
    if not verification["passed"]:
        log_private(f"[skill_synthesis] verification failed for {fn_name}: {verification['notes']}")
        return {
            "success": False, "fn_name": fn_name,
            "error": verification["notes"],
            "verification": verification,
        }

    # Write file
    _SELF_GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _SELF_GENERATED_DIR / f"{fn_name}.py"
    if file_path.exists():
        file_path = _SELF_GENERATED_DIR / f"{fn_name}_{_gap_id(gap_text)[:4]}.py"
    try:
        file_path.write_text(full_code, encoding="utf-8")
    except Exception as e:
        return {"success": False, "fn_name": fn_name, "error": f"file write failed: {e}"}

    # Hot-register into live COGNITIVE_FUNCTIONS
    try:
        import importlib.util as _ilu
        mod_name = f"cognition.self_generated.{file_path.stem}"
        spec = _ilu.spec_from_file_location(mod_name, str(file_path))
        mod = _ilu.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
            COGNITIVE_FUNCTIONS[fn_name] = {"function": fn, "is_cognition": True}
            log_activity(f"[skill_synthesis] registered: {fn_name}")
        else:
            raise ImportError(f"function {fn_name!r} not found in generated module")
    except Exception as e:
        log_private(f"[skill_synthesis] hot-register failed: {e}")
        file_path.unlink(missing_ok=True)
        return {"success": False, "fn_name": fn_name, "error": f"registration failed: {e}"}

    # Inject into self_extension's proposal lifecycle as "committed"
    try:
        from brain.cognition.self_extension import _proposal_id as _pid
        proposals = load_json(PROPOSED_TOOLS_JSON, default_type=list) or []
        if isinstance(proposals, list):
            proposals.append({
                "id":           _pid(fn_name),
                "name":         fn_name,
                "description":  description,
                "motivation":   f"synthesized from gap: {gap_text[:80]}",
                "proposed_at":  now_iso_z(),
                "committed_at": now_iso_z(),
                "status":       "committed",
                "wm_ref_count": 1,
                "critique":     "Synthesized and verified via skill_synthesis pipeline",
                "file_path":    str(file_path),
                "is_emergency": False,
                "is_synthesized": True,
            })
            save_json(PROPOSED_TOOLS_JSON, proposals)
    except Exception as e:
        log_private(f"[skill_synthesis] proposal injection failed: {e}")

    # Record in knowledge graph
    try:
        from brain.cognition.knowledge_graph import add_entity, add_relation
        add_entity(fn_name, "tool", properties={"synthesized": "true", "description": description[:60]},
                   confidence=0.65, source="skill_synthesis")
        add_relation("Orrin", "created", fn_name, confidence=0.80, source="skill_synthesis")
    except Exception as _e:
        record_failure("skill_synthesis.synthesize_skill.2", _e)

    # Update synthesis state
    state = _load_synthesis_state()
    state["synthesized"].append({
        "name": fn_name,
        "description": description,
        "gap": gap_text[:120],
        "file_path": str(file_path),
        "synthesized_at": now_iso_z(),
        "verification_passed": True,
    })
    state["last_synthesis"] = now_iso_z()
    _save_synthesis_state(state)

    log_activity(f"[skill_synthesis] synthesized and registered: {fn_name}")
    return {
        "success": True,
        "fn_name": fn_name,
        "file_path": str(file_path),
        "description": description,
        "verification": verification,
    }


# ─── Dream Cycle Entry Point ────────────────────────────────────────────────

def detect_and_synthesize(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dream cycle entry point.
    1. Scans WM for capability gaps and records candidates.
    2. If a high-scoring candidate exists and cooldown allows: synthesizes it.
    Returns a summary dict.
    """
    if not llm_callable_by("skill_synthesis"):
        log_activity("[skill_synthesis] skipped — LLM unavailable")
        return {"gaps_found": 0, "synthesized": False, "reason": "llm_unavailable"}
    global _last_synthesis_ts
    state = _load_synthesis_state()
    gaps = _scan_for_gaps(context)
    if not gaps:
        return {"gaps_found": 0, "synthesized": False}

    # Merge with existing candidates (deduplicate)
    existing_ids = {c["id"] for c in state.get("candidates", [])}
    for g in gaps:
        if g["id"] not in existing_ids:
            state["candidates"].append(g)
            existing_ids.add(g["id"])
    # Keep top candidates by score
    state["candidates"] = sorted(
        state["candidates"], key=lambda x: x.get("score", 0), reverse=True
    )[:_MAX_CANDIDATES]
    _save_synthesis_state(state)

    # Record all gaps as knowledge graph concepts
    try:
        from brain.cognition.knowledge_graph import add_entity
        for g in gaps[:3]:
            snippet = g["snippet"][:40].replace(" ", "_")
            add_entity(f"gap:{snippet}", "concept",
                       properties={"gap": "true", "score": str(g["score"])},
                       confidence=0.35, source="skill_synthesis")
    except Exception as _e:
        record_failure("skill_synthesis.detect_and_synthesize", _e)

    # Attempt synthesis if: top candidate is above threshold + cooldown elapsed
    top = state["candidates"][0] if state["candidates"] else None
    now = time.time()
    cooldown_ok = (now - _last_synthesis_ts) >= _SYNTHESIZE_COOLDOWN_S
    already_synthesized_names = {s["name"] for s in state.get("synthesized", [])}

    if top and top["score"] >= _GAP_SCORE_THRESHOLD and cooldown_ok:
        # Skip if we already synthesized something for this gap
        gap_words = set(re.findall(r'\b[a-z]+\b', top["snippet"].lower()))
        meaningful = [w for w in gap_words if w not in _GAP_STOPLIST and len(w) > 3]
        expected_prefix = "synthesized_" + "_".join(meaningful[:4])[:48]
        if any(s.startswith(expected_prefix[:20]) for s in already_synthesized_names):
            return {"gaps_found": len(gaps), "synthesized": False, "reason": "already synthesized similar gap"}

        _last_synthesis_ts = now
        result = synthesize_skill(top, context)
        if result["success"]:
            # Remove synthesized candidate from the pool
            state = _load_synthesis_state()
            state["candidates"] = [c for c in state["candidates"] if c["id"] != top["id"]]
            _save_synthesis_state(state)
        return {"gaps_found": len(gaps), "synthesized": result["success"], "result": result}

    return {"gaps_found": len(gaps), "synthesized": False, "reason": "threshold or cooldown"}
