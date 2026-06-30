"""The outward predict→act→observe→learn loop (Phase 3A) + the transfer
experiment harness (Phase 3B/3C).

One episode:
  1. PREDICT a concrete external observable (will this command exit 0?) from the
     command's STRUCTURAL features — before running it.
  2. ACT: run it in the real subprocess sandbox (think.sandbox_runner.run_python).
  3. OBSERVE + GRADE against the WORLD — the actual exit code, which Orrin did not
     author. This is the honest external grader the inward prediction loop lacks.
  4. LEARN: the prediction error updates the grounded concept's signature.

Features are computed from the AST WITHOUT executing — so the mapping from a
structural feature to the real outcome is genuinely LEARNED, not authored. The one
feature that carries transfer is abstract enough to recur on unseen commands (e.g.
"references an unbound name"); the learner discovers from real exit codes that it
predicts failure, and that knowledge transfers to commands it has never seen.

Guardrails (direction doc): no internet, no LLM in this path; the predicted
variable is an external observable he did not author; authored symbols are not
retired here (Phase 4A only).
"""
from __future__ import annotations

import ast
import builtins as _builtins
import keyword as _keyword
from statistics import mean
from typing import Dict, List, Optional, Sequence, Set

from brain.cognition.grounding.grounded_concept import GroundedConcept
from brain.think.sandbox_runner import run_python
from brain.utils.failure_counter import record_failure

# Phase 3C — budget + kill criterion, declared UP FRONT (before running).
MAX_EPISODES = 400          # data budget for one experiment run
TRANSFER_MARGIN = 0.10      # accuracy must beat the base rate by this to count as transfer

_BUILTINS = set(dir(_builtins)) | set(_keyword.kwlist) | {"__name__", "__file__"}

# Phase 4A — the external observables the loop can ground a concept against. Each
# is a concrete fact about the real run that Orrin did NOT author. `exit_success`
# is whether-it-failed; `produces_stdout` is a different observable (a print that
# crashes produces none, a non-print success produces none) — richer grounding,
# closer to predicting WHAT happens, not just WHETHER it fails.
OBSERVABLES = ("exit_success", "produces_stdout")


def observe(result: Dict) -> Dict[str, bool]:
    """Extract the grounded observables from a real run result — the WORLD's report,
    not his logs."""
    return {
        "exit_success": int(result.get("returncode", -1)) == 0,
        "produces_stdout": bool(str(result.get("stdout", "")).strip()),
    }


# ── Structural feature extraction (no execution) ─────────────────────────────

def _assigned_names(tree: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def extract_features(command: str) -> Set[str]:
    """Structural signature of a command — computed WITHOUT running it. Abstract
    enough that a feature can recur on a command never seen before (the basis for
    transfer). Returns {'syntax_error'} for unparseable input."""
    feats: Set[str] = set()
    try:
        tree = ast.parse(command)
    except SyntaxError:
        return {"syntax_error"}
    except Exception:
        return {"unparseable"}

    assigned = _assigned_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            feats.add(f"calls:{node.func.id}")
        elif isinstance(node, ast.BinOp):
            feats.add("has_binop")
            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                feats.add("has_division")
                rhs = node.right
                if isinstance(rhs, ast.Constant) and rhs.value == 0:
                    feats.add("divides_by_zero_literal")
        elif isinstance(node, ast.Subscript):
            feats.add("has_subscript")
        elif isinstance(node, ast.Attribute):
            feats.add(f"attr:{node.attr}")
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in assigned and node.id not in _BUILTINS:
                # A name used but never bound here — the abstract, TRANSFERABLE
                # signature of a likely NameError. Structural (pre-execution); the
                # LINK to failure is what the concept learns from real exit codes.
                feats.add("references_unbound_name")
    if not feats:
        feats.add("trivial")
    return feats


# ── One grounded episode ─────────────────────────────────────────────────────

def query_world(command: str, *, timeout: float = 5.0) -> Dict:
    """Run a command ONCE and return its structural features + the real observables.
    Separated from learning so the expensive subprocess is hit once per command and
    learning can REPLAY the grounded outcome (the plan's replay mechanism)."""
    feats = extract_features(command)
    result = run_python(command, timeout=timeout)            # the ACT (real world)
    return {"command": command, "features": feats, "observables": observe(result)}


def run_episode(command: str, concept: GroundedConcept, *,
                target: str = "exit_success", learn: bool = True,
                timeout: float = 5.0) -> Dict:
    """One online predict→act→observe→learn step: predict the target observable, run
    the command, grade against the REAL observable (exit code / stdout — not his
    logs), and (optionally) learn from the error. Returns the episode record."""
    feats = extract_features(command)
    p_yes = concept.predict(feats)
    predicted_yes = p_yes >= 0.5

    result = run_python(command, timeout=timeout)             # the ACT (real world)
    actual_yes = bool(observe(result).get(target))           # the WORLD, not his logs

    error = abs(p_yes - (1.0 if actual_yes else 0.0))        # Friston prediction error
    correct = predicted_yes == actual_yes
    if learn:
        concept.update(feats, actual_yes)                    # corrected by reality

    return {
        "command": command,
        "target": target,
        "features": sorted(feats),
        "p_success": round(p_yes, 3),       # P(observable holds) — name kept for callers
        "predicted_success": predicted_yes,
        "actual_success": actual_yes,
        "correct": correct,
        "error": round(error, 3),
        "domain": "world",         # invariant #4: this is world-model, not self-model
    }


# ── The transfer experiment (Phase 3B/3C) ────────────────────────────────────

def run_experiment(train: Sequence[str], test: Sequence[str], *,
                   target: str = "exit_success",
                   concept: Optional[GroundedConcept] = None,
                   max_episodes: int = MAX_EPISODES,
                   epochs: int = 8,
                   margin: float = TRANSFER_MARGIN) -> Dict:
    """Train on `train` (query each command's real outcome ONCE, then replay the
    grounded pairs for `epochs` gradient passes so the online learner converges on
    small families), then measure TRANSFER on held-out `test` (predict WITHOUT
    learning, grade against the real `target` observable).

    Success = accuracy on UNSEEN commands beats the base rate (majority-class
    chance) by `margin`. Memorisation of the training set does NOT count — test
    commands must be unseen. Returns a verdict ('transfer' / 'no_transfer') with
    the numbers attached, so either outcome is an informative result (Part F)."""
    concept = concept or GroundedConcept()

    # ── Train: query the world ONCE per command, then REPLAY to learn ──
    budget = min(len(train), max_episodes)
    grounded: List[Dict] = []
    for cmd in train[:budget]:
        try:
            grounded.append(query_world(cmd))
        except Exception as exc:
            record_failure("grounding.run_experiment.train", exc)
    for _ in range(max(1, epochs)):
        for g in grounded:
            concept.update(g["features"], bool(g["observables"].get(target)))

    # ── Test: held-out, no learning — the honest transfer measurement ──
    correct = 0
    actuals: List[bool] = []
    test_records: List[Dict] = []
    for cmd in test:
        try:
            rec = run_episode(cmd, concept, target=target, learn=False)
        except Exception as exc:
            record_failure("grounding.run_experiment.test", exc)
            continue
        actuals.append(rec["actual_success"])
        correct += 1 if rec["correct"] else 0
        test_records.append(rec)

    n = len(test_records)
    accuracy = correct / n if n else 0.0
    # Base rate / chance level, declared up front: always predicting the majority
    # class. Beating it is evidence of real discrimination, not guessing.
    pos = mean(1.0 if a else 0.0 for a in actuals) if actuals else 0.0
    base_rate = max(pos, 1.0 - pos)
    transfer = accuracy - base_rate

    return {
        "verdict": "transfer" if transfer >= margin else "no_transfer",
        "target": target,
        "accuracy": round(accuracy, 3),
        "base_rate": round(base_rate, 3),
        "transfer": round(transfer, 3),
        "margin": margin,
        "train_episodes": len(grounded),
        "test_episodes": n,
        "budget_exhausted": len(train) > budget,
        "signature": concept.signature(),
        "test_records": test_records,
    }
