# brain/cognition/planning/diagnosis.py
#
# Abductive fault diagnosis — generate ranked candidate CAUSES for a failure,
# so Orrin can reason about *why* something broke instead of blindly retrying.
#
# ── WHY ───────────────────────────────────────────────────────────────────────
# Peirce (1903, Collected Papers) introduced ABDUCTION: from a surprising
# observation, infer the hypothesis that, if true, would best explain it.
# Lipton (2004), "Inference to the Best Explanation" (2nd ed.) — we adopt the
# explanation that best trades off plausibility against simplicity.
# de Kleer & Williams (1987), "Diagnosing multiple faults", Artificial
# Intelligence 32:97, and Reiter (1987), "A theory of diagnosis from first
# principles", AI 32:57 — model-based diagnosis: enumerate candidate causes from
# a model of the system, then discriminate among them with observations.
# Heckerman, Breese & Rommelse (1995), "Decision-theoretic troubleshooting",
# CACM 38:49 — try the cheapest promising repair FIRST (best benefit/cost).
#
# ── HOW ───────────────────────────────────────────────────────────────────────
# For each capability class we keep a small "fault model": a list of candidate
# causes, each with a cheap CHECK over real system state, an optional FIX, a
# fixability flag, and a cost. `abduce()` runs the checks, ranks the candidates
# (confirmed-and-fixable-and-cheap first), and augments them with learned causes
# pulled from the causal graph (Peirce-style abduction over learned structure).
#
# Hypotheses returned are JSON-serialisable (no callables) so a caller can stash
# them in context across cycles; the live check/fix are re-derived by key via
# check_cause() / apply_fix(). This module is fully symbolic (no LLM) so it works
# with the LLM gate closed — which matters, because the LLM is itself a thing
# that can fail.
from __future__ import annotations

import re

from brain.core.runtime_log import get_logger
from typing import Any, Callable, Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.json_utils import modify_json
from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

# How many cycles to let a fixable cause's repair take effect before escalating
# to the next candidate (Heckerman et al. 1995 — bounded per-repair trials).
FIX_TRIES_PER_CAUSE = 2


# ── Real-state checks (cheap predicates over system health) ────────────────────

def _llm_disabled_in_config(context: Dict[str, Any]) -> bool:
    try:
        from brain.utils.llm_gate import llm_available
        from brain.utils.generate_response import _cb_is_open
        # disabled-by-config looks like: not available AND the breaker is NOT open
        # (an open breaker is a transient network condition, handled separately).
        return (not llm_available()) and (not _cb_is_open())
    except ImportError:  # intentional: gate/breaker unavailable → not a config-disable
        return False


def _llm_circuit_open(context: Dict[str, Any]) -> bool:
    try:
        from brain.utils.generate_response import _cb_is_open
        return bool(_cb_is_open())
    except ImportError:  # intentional: breaker unavailable → treat as closed
        return False


def _noop_wait_fix(context: Dict[str, Any]) -> bool:
    """The 'fix' for a transient condition is to let it clear — recovery is then
    confirmed by the capability health check on a later cycle."""
    log_activity("[diagnosis] Transient condition — waiting for it to clear before routing around.")
    return True


# ── Fault models: per-capability candidate causes ──────────────────────────────
# Each cause: key (stable id), cause (human text), check, fix (or None),
# fixable (can Orrin do anything?), cost (cheaper → tried first).

CauseModel = Dict[str, Any]


def _llm_models() -> List[CauseModel]:
    return [
        {
            "key": "transient_network",
            "cause": "a transient network problem (the API circuit-breaker is open)",
            "check": _llm_circuit_open,
            "fix": _noop_wait_fix,
            "fixable": True,    # self-heals once the breaker closes
            "cost": 0.2,
        },
        {
            "key": "disabled_in_config",
            "cause": "the language model is switched off in my configuration",
            "check": _llm_disabled_in_config,
            "fix": None,
            "fixable": False,   # the brain does not flip its own LLM switch
            "cost": 0.1,
        },
        {
            "key": "persistent_outage",
            "cause": "a persistent outage I can't fix from here",
            "check": lambda ctx: True,   # fallback explanation if nothing else matched
            "fix": None,
            "fixable": False,
            "cost": 0.9,
        },
    ]


def _generic_models() -> List[CauseModel]:
    return [
        {
            "key": "transient",
            "cause": "a transient / intermittent error",
            "check": lambda ctx: True,
            "fix": _noop_wait_fix,
            "fixable": True,
            "cost": 0.3,
        },
        {
            "key": "persistent",
            "cause": "a persistent failure I can't fix from here",
            "check": lambda ctx: True,
            "fix": None,
            "fixable": False,
            "cost": 0.9,
        },
    ]


_MODELS: Dict[str, Callable[[], List[CauseModel]]] = {
    "llm": _llm_models,
}


def _models_for(capability: str) -> List[CauseModel]:
    return _MODELS.get(capability, _generic_models)()


# ── Public API ─────────────────────────────────────────────────────────────────

def failure_node(capability: str) -> str:
    """
    Canonical causal-graph node string for "this capability failed". Used by BOTH
    the repair writer (problem_refocus records cause → failure_node) and the
    abduction reader below, so the loop is guaranteed to close: a confirmed cause
    recorded after one repair is surfaced as a learned candidate on the next.
    """
    return f"{capability} failure"


def abduce(capability: str, context: Dict[str, Any], description: str = "") -> List[Dict[str, Any]]:
    """
    Return JSON-serialisable candidate causes for a failure of `capability`,
    ranked best-first: confirmed (check passes) before unconfirmed, then fixable
    before unfixable, then cheapest first (Heckerman et al. 1995). Augmented with
    learned causes from the causal graph (abduction over learned structure).
    """
    models = _models_for(capability)
    hyps: List[Dict[str, Any]] = []
    for m in models:
        try:
            confirmed = bool(m["check"](context))
        except Exception:
            confirmed = False
        hyps.append({
            "key": m["key"],
            "cause": m["cause"],
            "fixable": bool(m["fixable"]),
            "cost": float(m["cost"]),
            "confirmed": confirmed,
            "source": "fault_model",
        })

    # Rank: confirmed first, then fixable, then cheapest.
    hyps.sort(key=lambda h: (not h["confirmed"], not h["fixable"], h["cost"]))

    # Augment with learned causes of this failure from the causal graph — causes
    # recorded by past repairs (problem_refocus) and observation. Query the
    # canonical failure node so prior learning is reliably surfaced.
    try:
        from brain.symbolic.causal_graph import get_causes
        known_keys = {h["key"] for h in hyps}
        for edge in (get_causes(failure_node(capability)) or [])[:2]:
            cause_txt = str(edge.get("cause", "")).strip()
            key = f"causal:{cause_txt[:40]}"
            if cause_txt and key not in known_keys:
                hyps.append({
                    "key": key,
                    "cause": cause_txt,
                    "fixable": False,           # explanatory, not directly actionable here
                    "cost": 0.6,
                    "confirmed": False,
                    "source": "causal_graph",
                })
                known_keys.add(key)
    except Exception as _e:
        record_failure("diagnosis.abduce", _e)

    return hyps


def _lookup(capability: str, key: str) -> Optional[CauseModel]:
    for m in _models_for(capability):
        if m["key"] == key:
            return m
    return None


def check_cause(capability: str, key: str, context: Dict[str, Any]) -> bool:
    """Re-run the check for a (capability, cause-key). False for unknown keys."""
    m = _lookup(capability, key)
    if not m:
        return False
    try:
        return bool(m["check"](context))
    except Exception as exc:  # cause-check predicate raised — record, treat as not-present
        record_failure("diagnosis.check_cause", exc)
        return False


def apply_fix(capability: str, key: str, context: Dict[str, Any]) -> bool:
    """
    Attempt the fix for a (capability, cause-key). Returns True if a fix action
    was taken (recovery is confirmed separately by the capability health check),
    False if the cause is unfixable or unknown.
    """
    m = _lookup(capability, key)
    if not m or not m.get("fixable") or not m.get("fix"):
        return False
    try:
        return bool(m["fix"](context))
    except Exception as exc:  # fix action raised — record, report no fix taken
        record_failure("diagnosis.apply_fix", exc)
        return False


# ── Diagnostic evidence (RUN7_FIX_PLAN F7, wiring C1–C3) ────────────────────────
# Three evidence primitives problem_refocus consumes:
#   C2 — recovery must be VERIFIED by a re-attempt / side-effect-free probe;
#   C3 — a persisted per-failure-key episode count refutes "transient" at 3;
#   C1 — a dotted-module-path failure key names Orrin's OWN code (route inward).

_RECURRENCE_FILE = DATA_DIR / "problem_recurrence.json"
RECURRENCE_ESCALATE = 3

_INTERNAL_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z0-9_]+)+$", re.IGNORECASE)


def is_internal_failure(capability: str) -> bool:
    """C1: True when the failure key is a dotted internal module path (a
    failure_counter site), i.e. the broken thing is Orrin's own machinery."""
    return bool(_INTERNAL_KEY_RE.match(str(capability or "")))


def bump_recurrence(capability: str) -> int:
    """C3: increment and return the persisted episode count for this failure key.
    Run 6 called the same write failure 'transient' twelve times over fifteen
    hours; at RECURRENCE_ESCALATE the transient hypothesis is refuted."""
    try:
        with modify_json(_RECURRENCE_FILE, dict) as d:
            n = int(d.get(str(capability), 0) or 0) + 1
            d[str(capability)] = n
            return n
    except Exception as exc:
        record_failure("diagnosis.bump_recurrence", exc)
        return 1


def _probe_write_exemplar() -> bool:
    from brain.cognition.quality_standard.gate import writability_probe
    ok, _diag = writability_probe()
    return ok


# C2: side-effect-free probes that RE-ATTEMPT a failed operation. Nine of Run
# 6's twelve episodes declared "working again" ~3 s after parking, because
# "failures stopped growing" is trivially true while nothing re-attempts.
RECOVERY_PROBES: Dict[str, Callable[[], bool]] = {
    "quality_standard.gate.write_exemplar": _probe_write_exemplar,
}


def recovery_probe(capability: str) -> Optional[bool]:
    """Run the capability's recovery probe. True/False = verified working/broken;
    None = no probe exists, so recovery cannot be verified at all."""
    probe = RECOVERY_PROBES.get(str(capability or ""))
    if probe is None:
        return None
    try:
        return bool(probe())
    except Exception as exc:
        record_failure("diagnosis.recovery_probe", exc)
        return False
