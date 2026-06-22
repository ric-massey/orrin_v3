# brain/think/think_utils/action_gate_helpers.py
# Support helpers for the action gate (Phase 4.5C, from action_gate.py): the
# pending-action queue (propose_action / resolve_pending_actions), novelty +
# outcome stamping, post-action reflection + clarification, the adaptive-context
# bookkeeping, and the spontaneous-expression / user-response injectors. Leaf of
# the action_gate package — it calls neither evaluate_and_act_if_needed nor
# take_action, so both import from here.
from brain.core.runtime_log import get_logger
from datetime import datetime, timezone

from brain.cognition.selfhood.boundary_check import check_violates_boundaries
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json
from brain.paths import FOCUS_GOAL

_log = get_logger(__name__)


def _current_focus_name():
    try:
        data = load_json(FOCUS_GOAL)
        if isinstance(data, dict):
            from brain.utils.goals import extract_current_focus_goal
            return extract_current_focus_goal(data)
    except Exception as _e:
        record_failure("action_gate._current_focus_name", _e)
    return None

_NOISE: frozenset = frozenset({"", ".", "...", "ok", "okay", "yes", "no", "hi", "hello"})
AGENTIC_TYPES = {
    "write_file",
    "execute_python_code",
    "run_tool",
    "scrape_text",
    "web_search",
    "update_file",
}
# Behavioral action types that are veto-grade: a self-protective boundary/values
# stop. These always resolve to the front of the queue, ahead of any urgency.
_VETO_ACTION_TYPES = frozenset({"refuse"})


def propose_action(context: dict, action: dict, *, urgency=None, veto: bool = False) -> None:
    """
    Single entry point for putting a behavioral action on the queue.

    Replaces the scattered `pending_actions.insert(0, …)` position-hacking (which
    encoded priority by list position and bypassed any arbiter — V3_AUDIT D4). All
    behavioral entry points now emit an explicit-urgency proposal here; the queue
    is resolved once per cycle by resolve_pending_actions (veto first, then urgency
    descending), so there is one place that decides "what runs now".
    """
    if not isinstance(action, dict):
        return
    if urgency is not None:
        action["urgency"] = float(urgency)
    if veto:
        action["veto"] = True
    context.setdefault("pending_actions", []).append(action)


def resolve_pending_actions(context: dict) -> None:
    """
    The ActionArbiter for the behavioral queue: stable-sort pending_actions so the
    highest-priority proposal is at the front (popped next). Veto-grade actions
    (boundary/values refusals) outrank everything; otherwise higher urgency wins.
    Stable, so equal-priority items keep their insertion order (FIFO within a tier).
    """
    q = context.get("pending_actions")
    if not isinstance(q, list) or len(q) < 2:
        return

    def _rank(a):
        if not isinstance(a, dict):
            return (0.0, 0.0)
        is_veto = 1.0 if (a.get("veto") or a.get("type") in _VETO_ACTION_TYPES) else 0.0
        try:
            urg = float(a.get("urgency") or 0.0)
        except (TypeError, ValueError):
            urg = 0.0
        return (is_veto, urg)

    q.sort(key=_rank, reverse=True)

def _novelty_for(action_type: str, context: dict, *, forced: bool = False) -> float:
    prev = (context.get("last_action_taken") or {}).get("type")
    base = 0.15
    agentic_bump = 0.2 if action_type in AGENTIC_TYPES else 0.05
    diff = 0.2 if prev and prev != action_type else 0.0
    forced_bonus = 0.25 if forced else 0.0
    return max(0.0, min(1.0, base + agentic_bump + diff + forced_bonus))

def _stamp_outcome(ctx: dict, outcome: dict) -> None:
    try:
        act = outcome.get("action") or {}
        action_type = act.get("type", "")
        success = bool(outcome.get("success", False))
        ctx["last_result"] = {
            "source": outcome.get("source"),
            "action_type": action_type,
            "success": success,
        }
        ctx["last_novelty"] = float(outcome.get("novelty") or 0.0)
        ctx.setdefault("last_acceptance_pass", False)
        # Ground rule outcomes against real action results
        if action_type:
            try:
                from brain.symbolic.ground_truth import record_action_result as _rar
                rule_id = ""
                for firing in (ctx.get("_recent_rule_firings") or [])[-1:]:
                    rule_id = firing.get("rule_id", "")
                _rar(action_type, success, rule_id=rule_id, context=ctx,
                     output_snippet=str(outcome.get("output", ""))[:200])
            except Exception as _e:
                record_failure("action_gate._stamp_outcome", _e)
    except Exception as _e:
        record_failure("action_gate._stamp_outcome.2", _e)

def reflect_on_last_action(context, action, result):
    """
    Classify action outcome without fragile freetext parsing.
    Returns one of: "success" | "retry" | "ask the user"

    Priority order:
    1. Bool result — direct signal from take_action
    2. Dict result — check success/error fields
    3. String result — heuristic keywords
    4. Ambiguous — structured LLM call (JSON, not freetext)
    """
    action_type = (action.get("type") if isinstance(action, dict) else str(action))

    # ── 1. Boolean result (most common: take_action returns True/False) ──────
    if result is True:
        return "success"
    if result is False:
        # Retryable action types get one retry before escalating
        if action_type in ("write_file", "execute_python_code", "execute_code", "tool_call"):
            return "retry"
        return "ask the user"

    # ── 2. Structured dict result ─────────────────────────────────────────────
    if isinstance(result, dict):
        if result.get("success") or result.get("ok"):
            return "success"
        error = str(result.get("error") or result.get("reason") or result.get("message") or "").lower()
        if any(k in error for k in ("permission", "access denied", "forbidden", "unauthorized")):
            return "ask the user"
        if any(k in error for k in ("timeout", "connection", "network", "temporarily")):
            return "retry"
        if error:
            return "retry"  # unknown structured error — try once more

    # ── 3. String result — heuristic ─────────────────────────────────────────
    if isinstance(result, str):
        low = result.lower()
        if any(k in low for k in ("success", "done", "completed", "ok", "✓")):
            return "success"
        if any(k in low for k in ("error", "failed", "exception", "❌", "traceback")):
            return "retry"

    # ── 4. Ambiguous — default to retry (safe, no LLM needed here) ──────────
    return "retry"

def generate_clarification_question(context, action):
    prompt = (
        f"I tried to execute the following action, but failed:\n{action}\n"
        "What is the single most important question I should ask the user to get unstuck? Reply only with the question."
    )
    try:
        from brain.symbolic.llm_gate import gated_generate
        return gated_generate(prompt, caller="action_gate/clarify", outcome=0.60)
    except Exception:
        return None

def moving_average(lst, n):
    if not lst or n <= 0:
        return 3
    return sum(lst[-n:]) / min(n, len(lst))

def _cycles(context):
    raw = context.get("cycle_count", 0)
    return raw.get("count", 0) if isinstance(raw, dict) else int(raw or 0)

def update_adaptive_context(context, action_type=None):
    context.setdefault("action_history", [])
    context.setdefault("cycles_since_agentic_action", 0)
    context.setdefault("prev_cycles_since_action", 0)
    context.setdefault("impasse_signal", 0.0)
    context.setdefault("committed_goal", None)
    context.setdefault("action_debt", 0)
    context.setdefault("act_now", False)

    now_cycle = _cycles(context)
    if action_type:
        context["action_history"].append(
            {"cycle": now_cycle, "action_type": action_type, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        context["action_history"] = context["action_history"][-200:]

    agentic_times = [a for a in context["action_history"] if isinstance(a, dict) and a.get("action_type") in AGENTIC_TYPES]
    if len(agentic_times) > 1:
        diffs = [agentic_times[i].get("cycle", 0) - agentic_times[i - 1].get("cycle", 0) for i in range(1, len(agentic_times))]
        avg_gap = moving_average(diffs, 10)
    else:
        avg_gap = 3

    dynamic_max_cycles = max(2, int(avg_gap * 1.2))

    debt = int(context.get("action_debt", 0) or 0)
    if context.get("act_now"):
        dynamic_max_cycles = max(1, int(dynamic_max_cycles * 0.6))
    if debt >= 2:
        dynamic_max_cycles = max(1, dynamic_max_cycles - min(debt, 3))

    prev = context.get("prev_cycles_since_action", 0)
    cur = context.get("cycles_since_agentic_action", 0)
    derivative = cur - prev
    context["prev_cycles_since_action"] = cur

    impasse_signal = context.get("impasse_signal", 0.0)
    if cur > dynamic_max_cycles:
        impasse_signal += 0.13 * (1.4 ** (cur - dynamic_max_cycles))
    else:
        impasse_signal = max(0, impasse_signal - 0.05)
    context["impasse_signal"] = min(impasse_signal, 1.0)

    return dynamic_max_cycles, derivative

def _maybe_inject_spontaneous_expression(context: dict, affect_state: dict) -> None:
    """
    Fire the salience → expression pipeline when Orrin's state is pressing for
    expression but no user input arrived this cycle. Covers social_deficit, strong
    emotion, blocked goals — any internal urgency that wants to become speech.
    Hard cooldown: won't fire if he spoke in the last 8 cycles.
    """
    _cycle = _cycles(context)
    if _cycle - int(context.get("last_speak_cycle") or 0) < 8:
        return
    # Audience awareness: spontaneous expression is a bid for contact, and with
    # nobody around for over an hour it just repeats the same internal pressure
    # ("unresolved: ...") to an empty room. The pressure still surfaces in the
    # private log via the state seeds; only the voice is gated.
    try:
        _sil = float((context.get("social_presence") or {}).get("silence_s") or 1e9)
    except Exception:
        _sil = 1e9
    if _sil > 3600:
        return
    try:
        from brain.think.state_processor import compute_cycle_state as _ccs
        from brain.behavior.expression import express as _express
        salience = _ccs(context)
        if not salience.output_triggered or salience.output_pressure < 0.50:
            return
        # Never voice the identical seed twice in a row — repetition without a
        # reply means it wasn't heard; saying it again adds nothing.
        if salience.output_seed and salience.output_seed == context.get("_last_spontaneous_seed"):
            return
        context["_last_spontaneous_seed"] = salience.output_seed
        _il_output = (context.get("_inner_loop_output") or "").strip()
        if _il_output and not salience.reasoning_conclusion:
            salience.reasoning_conclusion = _il_output[:400]
        text = _express(salience, context)
        if not text:
            return
        propose_action(context, {
            "type": "speak",
            "content": text,
            "urgency": salience.output_pressure,
            "description": f"Spontaneous: {salience.output_seed[:40]}",
        })
    except Exception as _e:
        record_failure("action_gate._maybe_inject_spontaneous_expression", _e)


def _maybe_inject_user_response(context: dict, affect_state: dict) -> None:
    """
    If the user has sent new input, inject a high-urgency user_response action into
    pending_actions so it gets handled before any behavior-generation proposals.

    Exceptions (no response injected):
    - social_penalty > 0.7: Orrin is offended — stays silent
    - Boundary violation: brief refusal injected instead
    - Input hasn't changed since last response (dedup)
    """
    user_input = (context.get("latest_user_input") or "").strip()
    if not user_input or user_input in _NOISE:
        _maybe_inject_spontaneous_expression(context, affect_state)
        return
    last_responded = (context.get("_last_responded_input") or "").strip()
    if user_input == last_responded:
        return  # already replied to this exact input

    # If a values-check already injected a refuse action this cycle, don't overwrite it
    if any(a.get("type") == "refuse" for a in context.get("pending_actions", [])):
        return

    emo = (affect_state or {})
    core_emo = (emo.get("core_signals") or emo) or {}
    social_penalty_val = float(core_emo.get("social_penalty", 0.0))

    # Orrin is deeply offended or ashamed — silence is intentional
    if social_penalty_val > 0.7:
        context["_last_responded_input"] = user_input
        return

    # Values-check refuse signal already determined — inject refuse action
    top_signals = context.get("top_signals") or []
    for _sig in top_signals:
        if "values_check" in (_sig.get("source") or "") and (_sig.get("content") or "").startswith("REFUSE:"):
            _reason = (_sig.get("content") or "").removeprefix("REFUSE:").strip()
            context["_last_responded_input"] = user_input
            propose_action(context, {
                "type": "refuse",
                "reason": _reason,
                "urgency": 0.93,
                "description": "Values-check refusal",
            }, veto=True)
            return

    # Boundary check — brief decline, not silence
    try:
        violations = check_violates_boundaries(user_input) or []
    except Exception:
        violations = []

    if violations:
        context["_last_responded_input"] = user_input
        propose_action(context, {
            "type": "user_response",
            "content": "That's not something I want to engage with.",
            "urgency": 0.95,
            "description": "Boundary violation — brief refusal",
        }, veto=True)
        return

    # Normal path: architecture → cycle state → speech pipeline → expression fallback
    try:
        from brain.think.state_processor import compute_cycle_state as _ccs
        from brain.behavior.expression import express as _express
        salience = _ccs(context, user_input=user_input)
        # Attach inner-loop reasoning conclusion from this cycle if available
        _il_output = (context.get("_inner_loop_output") or "").strip()
        if _il_output and not salience.reasoning_conclusion:
            salience.reasoning_conclusion = _il_output[:400]

        # Expression layer: vocabulary-based, no LLM. Language is Orrin's own,
        # grown from the vocabulary database rather than generated on demand.
        response_content = _express(salience, context, user_input)

        if not response_content:
            context["_last_responded_input"] = user_input
            return

        # Anticipatory self-consciousness: adapt to person's register before speaking
        try:
            from brain.behavior.pre_speak_check import pre_speak_check as _psc
            response_content, _disposition = _psc(
                response_content, context, urgency=salience.output_pressure
            )
        except Exception as _e:
            record_failure("action_gate._maybe_inject_user_response", _e)
        if not response_content:
            context["_last_responded_input"] = user_input
            return
    except Exception:
        response_content = "I'm here. Give me a moment."

    context["_last_responded_input"] = user_input
    propose_action(context, {
        "type": "user_response",
        "content": response_content,
        "urgency": 0.92,
        "description": f"Direct reply to: {user_input[:50]}",
    })


