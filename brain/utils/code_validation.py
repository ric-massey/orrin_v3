from __future__ import annotations
from brain.core.runtime_log import get_logger
import tempfile
import os
import importlib.util
import traceback
import sys
import ast
from typing import Dict, FrozenSet, List, Optional, Tuple
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


# ─── Symbolic alignment check ─────────────────────────────────────────────────
#
# Before writing a new think(), verify the proposed AST still honours the
# architectural contract:
#   1. Gate families — three groups of required call sites must each have at
#      least one member present in the proposed code.
#   2. Size floor   — proposed code must be >= _MIN_SIZE_RATIO of the original
#      to guard against silent gutting (LLM removing logic it doesn't "need").
#   3. Values hook  — reads identity_constraints from self_model.json and rejects
#      any proposed code that contains a forbidden pattern string.
#
# Adding a new gate: append to _REQUIRED_GATE_FAMILIES.
# Adding a value constraint: add {"forbidden_pattern": "..."} to
#   self_model["identity_constraints"].

_REQUIRED_GATE_FAMILIES: List[Tuple[str, FrozenSet[str]]] = [
    (
        "threat_detector/emotional-processing",
        frozenset({
            "idle_consolidation_logic",
            "process_affective_signals",
            "update_affect_state",
            "check_affect_drift",
        }),
    ),
    (
        "function-selection",
        frozenset({
            "select_function",
            "choose_next_cognition",
        }),
    ),
    (
        "cycle-finalization",
        frozenset({
            "finalize_cycle",
            "finalize",
        }),
    ),
]

# New think() must have >= this fraction of the original's non-blank lines.
# Below this floor is treated as silent gutting: the LLM removed logic it
# didn't understand rather than genuinely simplifying.
_MIN_SIZE_RATIO: float = 0.35


def _collect_call_names(tree: ast.AST) -> FrozenSet[str]:
    """
    Walk every Call node in the AST and return the set of called function names.
    Handles bare calls (foo()), attribute calls (obj.foo()), and nested calls.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            names.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            names.add(fn.attr)
    return frozenset(names)


def check_think_alignment(
    new_code:   str,
    old_code:   str,
    self_model: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    Symbolic alignment gate — call this AFTER syntax/sandbox checks, BEFORE writing.

    Returns (ok, rejection_reason).  rejection_reason is "" on success.

    Parameters
    ----------
    new_code   : proposed replacement think() source
    old_code   : current think_module.py source (used for size comparison)
    self_model : loaded self_model dict — checked for identity_constraints
    """
    # Parse (syntax errors caught by validate_think_code already, but be safe)
    try:
        tree = ast.parse(new_code)
    except SyntaxError as e:
        return False, f"syntax error in proposed think(): {e}"

    called = _collect_call_names(tree)

    # 1. Gate family check — each family needs >= 1 member called
    missing: List[str] = []
    for family_name, members in _REQUIRED_GATE_FAMILIES:
        if not (called & members):
            missing.append(
                f"{family_name} — expected one of: {', '.join(sorted(members))}"
            )
    if missing:
        return False, (
            "proposed think() removes required architectural gates:\n  • "
            + "\n  • ".join(missing)
            + "\n\nThese gates enforce emotional processing, function selection, "
              "and cycle finalization. Removing them risks executive dysfunction."
        )

    # 2. Size floor — prevent silent gutting
    old_lines = sum(1 for l in old_code.splitlines() if l.strip())
    new_lines = sum(1 for l in new_code.splitlines() if l.strip())
    if old_lines > 30 and new_lines < old_lines * _MIN_SIZE_RATIO:
        pct = 100.0 * new_lines / old_lines
        return False, (
            f"proposed think() has {new_lines} non-blank lines "
            f"({pct:.0f}% of the original {old_lines}). "
            f"Minimum is {100 * _MIN_SIZE_RATIO:.0f}%. "
            "This looks like silent gutting — reject to prevent data loss."
        )

    # 3. Identity constraints from self_model (extensible hook)
    constraints = (self_model or {}).get("identity_constraints") or []
    if isinstance(constraints, list):
        for c in constraints:
            if not isinstance(c, dict):
                continue
            pat = c.get("forbidden_pattern", "")
            label = c.get("label", pat)
            if pat and pat in new_code:
                return False, (
                    f"identity constraint violated: forbidden pattern "
                    f"{pat!r} ({label}) found in proposed think(). "
                    "Rejecting to preserve core identity."
                )

    return True, ""

def validate_think_code(code_text: str) -> Tuple[bool, str]:
    """
    Validates candidate code for a `think(context)` function:
    - Syntax check
    - Structural check (a function named `think` accepting at least 1 arg)
    - Dynamic import
    - Dry-run invocation with a minimal context
    Returns (ok, message).
    """
    temp_path = None
    module_name = None

    try:
        # 1) Syntax & AST structure
        tree = ast.parse(code_text, filename="<think_candidate>", mode="exec")
        has_think = False
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "think":
                # must accept at least 1 parameter (context)
                if len(node.args.args) < 1:
                    return False, "❌ `think` must accept at least one argument (context)."
                has_think = True
                break
        if not has_think:
            return False, "❌ No `think(context)` function defined."

        # 2) Write to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as tmp:
            tmp.write(code_text)
            temp_path = tmp.name

        # 3) Dynamic import
        module_name = os.path.splitext(os.path.basename(temp_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, temp_path)
        if spec is None or spec.loader is None:
            return False, "❌ Failed to build import spec for candidate module."
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # may raise

        # 4) Presence of think
        think_fn = getattr(module, "think", None)
        if not callable(think_fn):
            return False, "❌ No callable `think` found after import."

        # 5) Dry run (use a minimal context that won’t explode on key lookups)
        minimal_context = {
            "cycle_count": {"count": 0},
            "working_memory": [],
            "long_memory": [],
            "relationships": {},
            "affect_state": {},
        }
        result = think_fn(minimal_context)

        # 6) Validate return shape
        if not isinstance(result, dict):
            return False, "❌ Dry run must return a dict."
        if "next_function" not in result and "action" not in result:
            return False, "❌ Expected `next_function` or `action` in result dict."

        return True, "✅ Passed validation."

    except SyntaxError as e:
        return False, f"❌ Syntax error: {e}"
    except Exception as _e:
        record_failure("code_validation.validate", _e)
        return False, f"❌ Exception during validation:\n{traceback.format_exc()}"
    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as _e:
                record_failure("code_validation.validate_think_code", _e)
        # Remove temp module from sys.modules so future imports don’t collide
        if module_name and module_name in sys.modules:
            try:
                del sys.modules[module_name]
            except Exception as _e:
                record_failure("code_validation.validate_think_code.2", _e)
