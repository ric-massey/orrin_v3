# brain/symbolic/reasoning_router.py
# The symbolic reasoning router — checks all local symbolic sources before
# any LLM call is allowed.
#
# Resolution order (fastest/cheapest first):
#   1. Rule engine  — all matching rules passed through meta-rule resolver
#   2. Analogy      — structural match (SPO graph + intent type)
#   3. Symbolic BFS — knowledge graph traversal
#   4. Intrinsic motivation — exploration_drive drives LLM gate decision
#   5. LLM fallback (gated)
#
# Return value from route():
#   {
#     "resolved":      bool,
#     "answer":        str,
#     "source":        str,   # "rule" | "analogy" | "symbolic_search" | "llm_needed" | "suppressed"
#     "rule_id":       str,
#     "meta_rule_id":  str,   # which meta-rule resolved the conflict (if any)
#     "conflict":      bool,  # True if contradicting rules were detected
#     "drive":         dict,
#   }
from __future__ import annotations
from brain.core.runtime_log import get_logger

from typing import Dict, Optional

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def route(query: str, *, context: Optional[Dict] = None) -> Dict:
    """
    Attempt to answer `query` without LLM.  Returns resolution dict.
    The `context` dict may be mutated (exploration_drive_score, proposed_goals added).
    """
    ctx = context if context is not None else {}
    result: Dict = {
        "resolved": False, "answer": "", "source": "llm_needed",
        "rule_id": "", "meta_rule_id": "", "conflict": False, "drive": {},
        "signal_score": {},
    }

    # Stage -1 — Sub-symbolic signal_score (fastest path, no rules or LLM)
    signal_score: Dict = {}
    try:
        from brain.symbolic.pattern_scorer import score_signal
        signal_score = score_signal(query, context=ctx)
        result["signal_score"] = signal_score
        ctx["_signal_score"]   = signal_score

        # Hard suppress: deeply familiar + aversive → skip entire symbolic stack
        if signal_score["familiarity_score"] > 0.85 and signal_score["valence"] < -0.40:
            result.update(resolved=True, answer="", source="suppressed")
            log_activity(
                f"[router] Intuition hard-suppressed (familiar+aversive): {query[:60]}"
            )
            return result

        # Unknown territory + no self-confidence → open LLM gate immediately
        if signal_score["label"] == "pattern_unrecognized" and signal_score["pattern_confidence"] < 0.15:
            drive = _set_drive(ctx, query)
            result["drive"] = drive
            log_activity(f"[router] Intuition: unknown territory — direct to LLM: {query[:60]}")
            return result
    except Exception as e:
        log_activity(f"[router] pattern_scorer error: {e}")

    # Stage 0 — Symbolic self-assessment (pre-screen before any matching)
    _self_conf = 0.5
    _high_confidence_domain = False
    try:
        from brain.symbolic.symbolic_self_model import self_assess
        _assessment = self_assess(query)
        _self_conf = _assessment["confidence"]
        ctx["_self_assessment"] = _assessment

        # Strong domain: set fast-path flag (skip analogy+BFS, trust rule result directly)
        if _self_conf >= 0.75:
            _high_confidence_domain = True
            log_activity(
                f"[router] Self-assess: strong domain '{_assessment['domain']}' "
                f"(conf={_self_conf:.2f}) — fast-path symbolic"
            )
        # Weak domain (below 0.50): open the LLM gate, but only if LLM is available.
        # Tool-only is the default (ORRIN_LLM_TOOL_ONLY=0 to disable): cognition
        # never routes to the LLM; symbolic stages always try.
        elif not _assessment["trust_symbolic"]:
            try:
                from brain.utils.generate_response import _llm_tool_only
                _tool_only = _llm_tool_only()
            except Exception:
                _tool_only = True
            if _tool_only:
                log_activity(
                    f"[router] Self-assess: weak domain '{_assessment['domain']}' "
                    f"(conf={_self_conf:.2f}) — continuing symbolic (LLM tool-only mode)"
                )
            else:
                log_activity(
                    f"[router] Self-assess: weak domain '{_assessment['domain']}' "
                    f"(conf={_self_conf:.2f}) — routing to LLM"
                )
                drive = _set_drive(ctx, query)
                result["drive"] = drive
                return result
    except Exception as e:
        log_activity(f"[router] self_assess error: {e}")

    # Stage 1 — Rule engine + meta-rule conflict resolution
    try:
        from brain.symbolic.rule_engine import match_all
        from brain.symbolic.meta_rules import resolve_conflict
        matched = match_all(query, threshold=0.40)
        if matched:
            resolution = resolve_conflict(matched, query=query)
            action = resolution.get("action", "")
            if resolution.get("conflict"):
                result["conflict"] = True
                result["meta_rule_id"] = resolution.get("meta_rule_id", "")
                log_activity(
                    f"[router] Rule conflict detected — deferring to LLM: {query[:60]}"
                )
                # Fall through — conflict forces LLM
            elif action == "defer_llm":
                result["meta_rule_id"] = resolution.get("meta_rule_id", "")
                log_activity(f"[router] Meta-rule defers to LLM: {resolution['reason'][:80]}")
                # Fall through — low-confidence forces LLM
            elif resolution.get("winner"):
                winner = resolution["winner"]
                # Apply the rule (bumps hit count)
                from brain.symbolic.rule_engine import apply as rule_apply
                answer = rule_apply(winner)
                result.update(
                    resolved=True, answer=answer, source="rule",
                    rule_id=winner.get("id", ""),
                    meta_rule_id=resolution.get("meta_rule_id", ""),
                )
                log_activity(
                    f"[router] Rule '{winner['id']}' via meta-rule '{resolution.get('meta_rule_id', 'none')}'"
                    f" — {resolution.get('reason', '')[:60]}"
                )
                # Record firing for verifier and prediction engine
                try:
                    from brain.symbolic.rule_verifier import record_firing as _rf
                    _rf(winner["id"], query, answer,
                        meta_rule_id=resolution.get("meta_rule_id", ""),
                        context=ctx)
                    _recent = ctx.setdefault("_recent_rule_firings", [])
                    _recent.append({
                        "rule_id": winner["id"],
                        "query_head": query[:80],
                        "answer_head": answer[:80],
                        "confidence": winner.get("confidence", 0.72),
                    })
                except Exception as _e:
                    record_failure("reasoning_router.route", _e)
                _set_drive(ctx, query)
                return result
    except Exception as e:
        log_activity(f"[router] rule_engine/meta_rules error: {e}")

    # Fast-path: high-confidence domain + rule resolved → skip analogy & BFS
    if _high_confidence_domain and result.get("resolved"):
        _set_drive(ctx, query)
        return result

    # Stage 2 — Analogy engine (structural + goal similarity)
    try:
        from brain.symbolic.analogy_engine import best_analogue_answer
        analogy = best_analogue_answer(query)
        if analogy:
            result.update(resolved=True, answer=analogy, source="analogy")
            log_activity(f"[router] Analogy match for: {query[:60]}")
            _set_drive(ctx, query)
            return result
    except Exception as e:
        log_activity(f"[router] analogy_engine error: {e}")

    # Stage 3 — Symbolic BFS search
    try:
        from brain.symbolic.symbolic_search import search as sym_search
        sym_answer = sym_search(query, context=ctx)
        if sym_answer:
            result.update(resolved=True, answer=sym_answer, source="symbolic_search")
            log_activity(f"[router] Symbolic search answered: {query[:60]}")
            _set_drive(ctx, query)
            return result
    except Exception as e:
        log_activity(f"[router] symbolic_search error: {e}")

    # Stage 4 — Intrinsic motivation: set drive, maybe spawn sub-goal
    drive = _set_drive(ctx, query)
    result["drive"] = drive

    # Maybe spawn investigation sub-goal when exploration_drive is high
    try:
        from brain.symbolic.intrinsic_motivation import maybe_spawn_subgoal
        maybe_spawn_subgoal(query, ctx)
    except Exception as _e:
        record_failure("reasoning_router.route.2", _e)

    # Stage 4.5 — Causal explanation (between motivation and LLM gate)
    try:
        from brain.symbolic.causal_graph import causal_explanation
        causal = causal_explanation(query)
        if causal:
            result.update(resolved=True, answer=causal, source="causal_graph")
            log_activity(f"[router] Causal explanation for: {query[:60]}")
            return result
    except Exception as e:
        log_activity(f"[router] causal_graph error: {e}")

    # Soft-suppress LLM when exploration_drive is very low (repeated/trivial query)
    # Raised from 0.20 → 0.30 to suppress more aggressively
    if drive.get("score", 1.0) < 0.30 and not result["conflict"]:
        result.update(resolved=True, answer="", source="suppressed")
        log_activity(
            f"[router] Low exploration_drive ({drive['score']:.2f}) — LLM suppressed: {query[:60]}"
        )
        return result

    # Stage 5 — LLM needed
    log_activity(
        f"[router] LLM gate open (drive={drive.get('label','?')}, score={drive.get('score',0)}, "
        f"conflict={result['conflict']})"
    )
    return result


def _set_drive(ctx: Dict, query: str) -> Dict:
    try:
        from brain.symbolic.intrinsic_motivation import get_drive
        drive = get_drive(query, context=ctx)
        ctx["_intrinsic_drive"] = drive
        ctx["exploration_drive_score"] = drive["score"]
        return drive
    except Exception as e:
        log_activity(f"[router] intrinsic_motivation error: {e}")
        return {"score": 0.5, "label": "investigate"}


def needs_llm(query: str, *, context: Optional[Dict] = None) -> bool:
    r = route(query, context=context)
    return not r["resolved"] or r.get("source") == "llm_needed"
