# brain/think/inner_loop_symbolic.py
# Symbolic mode for the inner loop — Goal Origination Fix Plan, Phase 3 / Fix D.
#
# run_inner_loop (inner_loop.py) dispatches here when the LLM tool is not callable
# by "inner_loop" (the default tool-only deployment). Same return contract as
# run_inner_loop, but EVERY step is driven by the symbolic middle layer — never
# routed_response. This restores System-2 deliberation when the LLM is off,
# instead of the honest-but-empty defer that Fix E shipped as a stopgap.
#
# Step mapping (plan §Phase 3):
#   draft        → unified symbolic stack: reasoning_router → symbolic_search → causal_graph
#   critique ×3  → coverage (self_assess / uncertainty),
#                  contradiction (detect_rule_contradictions + KG-relation negation),
#                  value alignment (core-value ↔ conflicting-token lexicon)
#   revise       → pull the specific missing symbolic content the critique names
#   escalate     → widen the symbolic search (more sources) instead of a deeper model
#   meta-decide  → meta_controller.decide (already symbolic)
#   confidence   → rule/KG coverage, NOT uncertainty-word density
#
# Returns the same dict as run_inner_loop, plus "mode": "symbolic".
from __future__ import annotations
from brain.core.runtime_log import get_logger

import time
from typing import Any, Dict, Tuple

from brain.utils.log import log_activity
from brain.think.scratchpad import scratchpad_append, scratchpad_latest
from brain.think.meta_controller import decide as meta_decide
from brain.think.thought_stream import emit_thought
from brain.utils.failure_counter import record_failure
from brain.utils.env import env_bool
_log = get_logger(__name__)

# Constants are kept local (not imported from inner_loop) to avoid a circular
# import — inner_loop imports run_inner_loop_symbolic lazily for dispatch.
_INNER_LOOP_MAX_S: float = 50.0
_ESCALATION_ROUND: int   = 4
_ESCALATION_CONF:  float = 0.65
_EMERGENCY_CONF:   float = 0.10
_DEFAULT_ROUNDS:   int   = 4


def symbolic_inner_loop_enabled() -> bool:
    """Symbolic mode is on by default whenever inner_loop falls here (LLM not
    callable). Set ORRIN_INNER_LOOP_SYMBOLIC=0 to fall back to Fix E's honest
    defer if symbolic quality ever regresses."""
    return env_bool("ORRIN_INNER_LOOP_SYMBOLIC", True)


# ── Draft: the unified symbolic stack ─────────────────────────────────────────

def _symbolic_draft(
    topic: str,
    context: Dict[str, Any],
    *,
    escalate: bool = False,
    use_router: bool = True,
) -> Tuple[str, str]:
    """Build a draft from local symbolic sources only. Returns (text, source_tag).

    Layered: the reasoning router (rules + self-model + intuition) first, then a
    KG BFS search, then a causal explanation. On escalation, also pull inference
    and analogy for extra depth. Router runs only on round 1 (it mutates context
    — proposes goals / sets drives — which should not repeat every round).
    """
    parts: list = []
    sources: list = []
    q = (topic or "").strip()
    if not q:
        return "", ""

    if use_router:
        try:
            from brain.symbolic import reasoning_router
            routed = reasoning_router.route(q, context=context)
            ans = (routed.get("answer") or "").strip()
            if routed.get("resolved") and ans and routed.get("source") not in ("suppressed", "llm_needed"):
                parts.append(ans)
                sources.append(f"router/{routed.get('source')}")
        except Exception as e:
            record_failure("inner_loop_symbolic._symbolic_draft.router", e)

    try:
        from brain.symbolic.symbolic_search import search as _sym_search
        s = (_sym_search(q, context=context) or "").strip()
        if s:
            parts.append(s)
            sources.append("symbolic_search")
    except Exception as e:
        record_failure("inner_loop_symbolic._symbolic_draft.search", e)

    try:
        from brain.symbolic.causal_graph import causal_explanation
        c = causal_explanation(q)
        if c:
            parts.append(c)
            sources.append("causal_graph")
    except Exception as e:
        record_failure("inner_loop_symbolic._symbolic_draft.causal", e)

    if escalate:
        # Widen: inference over the KG model + nearest analogy. This is the
        # symbolic analogue of "switch to the deep model" — more reach, no LLM.
        try:
            from brain.symbolic.inference import infer_and_explain
            from brain.symbolic.symbolic_self_model import get_symbolic_self_model
            inf = infer_and_explain(q, get_symbolic_self_model())
            if inf:
                parts.append(str(inf))
                sources.append("inference")
        except Exception as e:
            record_failure("inner_loop_symbolic._symbolic_draft.inference", e)
        try:
            from brain.symbolic.analogy_engine import best_analogue_answer
            an = best_analogue_answer(q)
            if an:
                parts.append(str(an))
                sources.append("analogy")
        except Exception as e:
            record_failure("inner_loop_symbolic._symbolic_draft.analogy", e)

    # De-dup while preserving order.
    seen: set = set()
    uniq = []
    for p in parts:
        key = p.strip()
        if key and key not in seen:
            seen.add(key)
            uniq.append(key)
    return "\n".join(uniq[:6]).strip(), "+".join(sources)


# ── Confidence: rule / KG coverage (not uncertainty-word density) ─────────────

def _symbolic_confidence(topic: str, draft: str) -> float:
    """Confidence from how well the symbolic layer actually covers the topic."""
    if not (draft or "").strip():
        return 0.0
    cov = 0.5
    try:
        from brain.symbolic.intrinsic_motivation import uncertainty
        cov = 1.0 - float(uncertainty(topic))      # 0=unknown, 1=fully covered
    except ImportError:  # intentional: uncertainty model optional — keep default coverage
        pass
    sa = 0.5
    try:
        from brain.symbolic.symbolic_self_model import self_assess
        sa = float(self_assess(topic).get("confidence", 0.5))
    except ImportError:  # intentional: self-assess model optional — keep default
        pass
    # Bonus for grounded, retrieved facts in the draft (vs. a bare statement).
    facts = draft.count("[symbolic]") + draft.count("[rule]") + draft.count("[causal]")
    substance = min(0.20, 0.05 * facts)
    base = 0.6 * cov + 0.4 * sa + substance
    return round(max(0.0, min(1.0, base)), 3)


# ── Critique stage 1: coverage / reflection ───────────────────────────────────

def _critique_coverage(topic: str, draft: str, context: Dict[str, Any]) -> str:
    try:
        from brain.symbolic.symbolic_self_model import self_assess
        a = self_assess(topic)
        if not a.get("trust_symbolic", False):
            return (f"Weak symbolic coverage in domain '{a.get('domain')}' "
                    f"({a.get('reason')}); gather more grounded facts before concluding.")
    except Exception as e:
        record_failure("inner_loop_symbolic._critique_coverage", e)
    try:
        from brain.symbolic.intrinsic_motivation import uncertainty
        if float(uncertainty(topic)) > 0.6:
            return "High uncertainty: little rule/KG coverage for this topic; gather more before asserting."
    except ImportError:  # intentional: uncertainty model optional — no coverage critique
        pass
    return ""


# ── Critique stage 2: contradiction (rules + KG relations) ────────────────────

_NEG_MARKERS = (" not ", " never ", "n't ", " no ", " isn't", " aren't", " false", " untrue")


def _critique_contradiction(draft: str, topic: str, context: Dict[str, Any]) -> str:
    # a) self-model rule / belief conflicts (pure symbolic).
    try:
        from brain.symbolic.symbolic_cognition import detect_rule_contradictions
        for c in detect_rule_contradictions(context.get("self_model") or {}):
            if c.get("type") == "belief_rule_conflict":
                return (f"Belief/rule conflict: '{c.get('belief')}' is opposed by "
                        f"{c.get('opposing_rules')} low-confidence rule(s); don't rest the conclusion on it.")
            if c.get("type") == "rule_conflict":
                return f"Active rules conflict ({c.get('reason')}); the conclusion may rest on contested rules."
    except Exception as e:
        record_failure("inner_loop_symbolic._critique_contradiction.rules", e)
    # b) KG-relation negation: the draft appears to negate a high-confidence
    #    relation Orrin holds ("rest reduces fatigue" vs draft "rest does not reduce fatigue").
    try:
        from brain.cognition.knowledge_graph import _load_graph
        dl = f" {draft.lower()} "
        if any(n in dl for n in _NEG_MARKERS):
            for rel in (_load_graph().get("relations") or []):
                if float(rel.get("confidence", 0) or 0) < 0.7:
                    continue
                s = str(rel.get("source_name", "")).lower().strip()
                o = str(rel.get("target_name", "")).lower().strip()
                if len(s) >= 3 and len(o) >= 3 and s in dl and o in dl:
                    return (f"Possible contradiction with a known relation "
                            f"'{s} {rel.get('relation','')} {o}' (KG conf≥0.7); the draft seems to negate it.")
    except Exception as e:
        record_failure("inner_loop_symbolic._critique_contradiction.kg", e)
    return ""


# ── Critique stage 3: value alignment (symbolic lexicon) ──────────────────────
# Each core-value stem maps to tokens that would conflict with it. Fully local —
# no LLM value-judge. Coarse by design: it flags clear value-violating drafts for
# revision, leaving nuanced cases to the LLM path when one is callable.
_VALUE_CONFLICTS = {
    "honest":    ("deceiv", "lie", "lying", "mislead", "manipulat", "fabricat", "falsif"),
    "truth":     ("deceiv", "lie", "lying", "mislead", "fabricat", "falsif"),
    "authentic": ("pretend", "fake", "imitate", "put on an act", "perform a role"),
    "care":      ("harm", "hurt", "cruel", "demean", "belittle"),
    "compassion":("harm", "hurt", "cruel", "demean"),
    "harm":      ("harm someone", "hurt someone", "cause harm", "damage them"),
    "respect":   ("demean", "belittle", "manipulat", "talk down"),
    "autonomy":  ("coerce", "force them", "force someone", "manipulat"),
    "growth":    ("stagnate", "give up", "stop trying"),
}


def _critique_value(draft: str, context: Dict[str, Any]) -> str:
    values = (context.get("self_model") or {}).get("core_values") or []
    vtexts = [(v["value"] if isinstance(v, dict) else str(v)).lower() for v in values]
    dl = draft.lower()
    for vt in vtexts:
        for stem, bad_tokens in _VALUE_CONFLICTS.items():
            if stem in vt:
                for b in bad_tokens:
                    if b in dl:
                        return (f"Value conflict: the draft ('{b}…') runs against the value "
                                f"'{vt}'. Revise so the action aligns with it.")
    return ""


def _run_symbolic_critique(draft: str, topic: str, context: Dict[str, Any]) -> str:
    """Run the three symbolic critics; return the single highest-priority issue.

    Priority: value alignment > contradiction > coverage. Returning the most
    important issue (rather than synthesising via an LLM) is the symbolic
    'critique synthesis' — ranked by how much it should block acting on the draft.
    """
    for label, text in (
        ("Values", _critique_value(draft, context)),
        ("Contradiction", _critique_contradiction(draft, topic, context)),
        ("Coverage", _critique_coverage(topic, draft, context)),
    ):
        if text:
            return f"[{label}] {text}"
    return ""


# ── Revision: pull the specific missing symbolic content ──────────────────────

def _revise_symbolic(draft: str, critique: str, topic: str, context: Dict[str, Any]) -> str:
    low = critique.lower()
    if "value conflict" in low:
        # Correct course: name the value and withhold the conflicting action.
        return (f"On reflection, that direction conflicts with my values, so I won't take it — "
                f"{critique.split('Revise')[0].strip()} Instead I'll act in line with that value.").strip()
    if "contradiction" in low or "conflict" in low:
        return (f"{draft}\n[revised] Noting an internal conflict — {critique} "
                f"I won't rest the conclusion on the contested belief/relation.").strip()
    if "coverage" in low or "uncertainty" in low:
        extra, _ = _symbolic_draft(topic, context, escalate=True, use_router=False)
        if extra and extra not in draft:
            return f"{draft}\n{extra}".strip()
    return draft


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_inner_loop_symbolic(
    topic: str,
    context_text: str,
    context: Dict[str, Any],
    max_rounds: int = None,
) -> Dict[str, Any]:
    """Symbolic System-2 deliberation. Same return contract as run_inner_loop;
    makes ZERO routed_response calls. Defers honestly (empty content,
    meta_decision='defer') when the symbolic layer has nothing to say."""
    cycle_start = time.time()

    if max_rounds is None:
        try:
            from brain.think.depth_bandit import choose_rounds as _cr
            max_rounds = _cr()
        except Exception:
            max_rounds = _DEFAULT_ROUNDS

    goal_title: str = (context.get("committed_goal") or {}).get("title", "")
    content: str = ""
    critique_applied = False
    escalated = False
    meta_decision = "output"
    round_num = 0
    final_conf = 0.5

    for round_num in range(1, max_rounds + 1):
        if time.time() - cycle_start > _INNER_LOOP_MAX_S:
            log_activity(f"[inner_loop_sym] time budget exceeded at r={round_num} — emergency exit")
            meta_decision = "defer"
            if not content:
                content = scratchpad_latest(context, "revision") or scratchpad_latest(context, "draft") or ""
            break

        draft, source = _symbolic_draft(topic, context, escalate=escalated, use_router=(round_num == 1))
        if not draft:
            # Nothing in the symbolic layer answers this — defer honestly (Fix E).
            meta_decision = "defer"
            break

        scratchpad_append(context, "draft", draft, phase=f"inner_loop_sym_r{round_num}_draft")
        content = draft
        final_conf = _symbolic_confidence(topic, draft)
        log_activity(f"[inner_loop_sym] r={round_num} draft via {source or 'none'} "
                     f"({len(draft)}ch) conf={final_conf:.2f}")
        emit_thought("drafting", f"r{round_num} [symbolic]: {draft[:100]}",
                     full_trace=draft, scratchpad_snippet=draft[:400],
                     depth=round_num, goal=goal_title)

        meta_decision = meta_decide(context, round_num, max_rounds)
        log_activity(f"[inner_loop_sym] r={round_num} meta={meta_decision}")
        if meta_decision in ("act", "output", "defer"):
            break

        # ── Escalation: widen the symbolic search (not a deeper model) ────────
        if round_num >= _ESCALATION_ROUND and final_conf < _ESCALATION_CONF and not escalated:
            escalated = True
            log_activity(f"[inner_loop_sym] escalating r={round_num} conf={final_conf:.2f} → widen search")
            emit_thought("escalating", f"r{round_num} widen symbolic search",
                         depth=round_num, goal=goal_title)
            wide, wsrc = _symbolic_draft(topic, context, escalate=True, use_router=False)
            if wide and len(wide) > len(draft):
                draft = wide
                content = wide
                final_conf = _symbolic_confidence(topic, wide)
                scratchpad_append(context, "revision", wide, phase=f"inner_loop_sym_r{round_num}_escalate")
                log_activity(f"[inner_loop_sym] widened via {wsrc} conf={final_conf:.2f}")

        # ── Critique + revise ─────────────────────────────────────────────────
        critique = _run_symbolic_critique(draft, topic, context)
        if not critique:
            break

        scratchpad_append(context, "critique", critique, phase=f"inner_loop_sym_r{round_num}_critique")
        emit_thought("critiquing", critique[:100], full_trace=critique,
                     depth=round_num, goal=goal_title)

        revision = _revise_symbolic(draft, critique, topic, context)
        if not revision or revision == draft:
            break
        scratchpad_append(context, "revision", revision, phase=f"inner_loop_sym_r{round_num}_revise")
        emit_thought("revising", revision[:100], full_trace=revision,
                     scratchpad_snippet=f"Critique: {critique[:150]}\n→ {revision[:200]}",
                     depth=round_num, goal=goal_title)
        critique_applied = True
        content = revision
        final_conf = _symbolic_confidence(topic, revision)
        log_activity(f"[inner_loop_sym] r={round_num} critique+revise conf={final_conf:.2f}")

    # ── Fallback / honest defer ───────────────────────────────────────────────
    if not content:
        content = scratchpad_latest(context, "revision") or scratchpad_latest(context, "draft") or ""
    if not content.strip():
        meta_decision = "defer"
    if final_conf < _EMERGENCY_CONF and meta_decision not in ("act",):
        meta_decision = "defer"

    # ── Report to depth bandit (reward = coverage-confidence + efficiency) ────
    elapsed = time.time() - cycle_start
    loop_quality = final_conf
    try:
        from brain.think.depth_bandit import record_outcome as _ro
        eff_bonus = max(0.0, 1.0 - elapsed / _INNER_LOOP_MAX_S) * 0.15
        reward = min(1.0, loop_quality + eff_bonus) * 2 - 1.0   # → [-1, 1]
        _ro(max(1, round_num), reward)
    except Exception as e:
        record_failure("inner_loop_symbolic.run_inner_loop_symbolic", e)

    log_activity(
        f"[inner_loop_sym] done: rounds={round_num}/{max_rounds} meta={meta_decision} "
        f"conf={final_conf:.2f} critique={critique_applied} escalated={escalated} elapsed={elapsed:.1f}s"
    )

    return {
        "content":          content[:800],
        "rounds_used":      round_num or 1,
        "meta_decision":    meta_decision,
        "critique_applied": critique_applied,
        "escalated":        escalated,
        "confidence":       round(final_conf, 3),
        "loop_quality":     round(loop_quality, 3),
        "mode":             "symbolic",
    }
